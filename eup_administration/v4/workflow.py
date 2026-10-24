"""Protected, version-frozen administrative workflow engine."""
from contextvars import ContextVar
from hashlib import sha256
import frappe
from frappe.model.document import Document
from frappe.utils import now_datetime, add_to_date
from eup_administration.v4.rules import OPERATIONS, validate_graph, matches
from eup_administration.v4.security import require_company, manager
from eup_administration.v3.security import roles
from eup_administration.v3.approval import _authorized as _legacy_authorized

_internal = ContextVar("adm_v4_workflow", default=False)


def _authorized(step, case, actor):
    ok, delegator = _legacy_authorized(step, case, actor)
    if delegator and not frappe.db.get_value("User", delegator, "enabled"):
        return False, None
    return ok, delegator


def key(doctype, name):
    if doctype not in OPERATIONS:
        frappe.throw("Unsupported administrative workflow target")
    return sha256((doctype + ":" + name).encode()).hexdigest()


class Audit(Document):
    def before_insert(self):
        if not _internal.get():
            frappe.throw("Use protected workflow actions", frappe.PermissionError)

    def validate(self):
        if not _internal.get():
            frappe.throw("Workflow records are immutable", frappe.PermissionError)

    def on_trash(self):
        frappe.throw("Workflow records cannot be deleted", frappe.PermissionError)


class WorkflowPolicy(Document):
    def validate(self):
        require_company(self.company)
        if self.target_doctype not in OPERATIONS:
            frappe.throw("Only new independent administrative DocTypes are supported")
        if not manager(self.company):
            frappe.throw("Administration manager required", frappe.PermissionError)
        try:
            validate_graph([x.as_dict() for x in self.states],
                           [x.as_dict() for x in self.transitions], self.initial_state,
                           [x.as_dict() for x in self.approval_bands])
        except (ValueError, TypeError, KeyError) as e:
            frappe.throw(str(e))
        if not self.is_new() and frappe.db.exists("ADM Workflow Run", {"policy": self.name}):
            old = self.get_doc_before_save()
            scalar = ("target_doctype", "company", "initial_state", "policy_title")
            tables = ("states", "transitions", "approval_bands")
            def rows(doc, name):
                return [{k: v for k, v in r.as_dict().items() if k not in {
                    "modified", "modified_by", "creation", "owner", "docstatus"
                }} for r in doc.get(name)]
            if old and (any(old.get(k) != self.get(k) for k in scalar) or
                        any(rows(old, k) != rows(self, k) for k in tables)):
                frappe.throw("Used policy structure is immutable. Duplicate to create a new version.")
        for row in list(self.transitions) + list(self.approval_bands):
            role = row.get("allowed_role") or row.get("approver_role")
            if role in {"Guest", "All"}:
                frappe.throw("Guest and All cannot operate administrative workflows")
        self.enabled_key = sha256((self.company + ":" + self.target_doctype).encode()).hexdigest() if self.enabled else None
        if self.enabled:
            others = frappe.get_all("ADM Workflow Policy", filters={
                "company": self.company, "target_doctype": self.target_doctype, "enabled": 1
            }, pluck="name")
            if any(n != self.name for n in others):
                frappe.throw("Disable the previous unused policy before enabling another")

    def on_trash(self):
        if frappe.db.exists("ADM Workflow Run", {"policy": self.name}):
            frappe.throw("Used policies cannot be deleted")


def save_internal(doc, insert=False):
    if doc.doctype in {"ADM Workflow Run", "ADM Workflow Audit", "ADM Operation Feedback"}:
        doc.company = frappe.db.get_value(doc.reference_doctype, doc.reference_name, "company")
    token = _internal.set(True)
    try:
        return doc.insert(ignore_permissions=True) if insert else doc.save(ignore_permissions=True)
    finally:
        _internal.reset(token)


def _lock(doctype, name):
    # Table identifiers come exclusively from a closed server-side allowlist.
    allowed = set(OPERATIONS) | {"ADM Workflow Run", "ADM Shared Equipment", "ADM Workflow Policy"}
    if doctype not in allowed:
        frappe.throw("Unsupported lock target")
    if not frappe.db.sql("SELECT name FROM `tab" + doctype + "` WHERE name=%s FOR UPDATE", (name,)):
        frappe.throw("Record missing")


def _load(doctype, name, expected_revision=None):
    key(doctype, name)
    _lock(doctype, name)
    # Locking only name does not refresh later ordinary snapshot reads.
    doc = frappe.get_doc(doctype, name, for_update=True)
    require_company(doc.company)
    run_name = frappe.db.get_value("ADM Workflow Run", {"reference_key": key(doctype, name)}, "name", for_update=True)
    if not run_name:
        frappe.throw("Start the workflow first")
    _lock("ADM Workflow Run", run_name)
    run = frappe.get_doc("ADM Workflow Run", run_name, for_update=True)
    if expected_revision is not None and int(expected_revision) != int(run.revision):
        frappe.throw("Workflow changed. Reload before continuing.")
    policy = frappe.get_doc("ADM Workflow Policy", run.policy)
    return doc, run, policy


def _audit(doc, run, action, before, after, decision="", step=0, comment=None, delegated_from=None):
    save_internal(frappe.get_doc({
        "doctype": "ADM Workflow Audit", "reference_doctype": doc.doctype,
        "reference_name": doc.name, "policy": run.policy, "from_state": before,
        "to_state": after, "action": action, "actor": frappe.session.user,
        "decision": decision, "step_number": step, "comment": comment,
        "delegated_from": delegated_from, "revision": str(run.revision)
    }), insert=True)


def _set_state(doc, run, policy, state):
    settings = next(s for s in policy.states if s.state == state)
    run.current_state = state
    run.pending_action = None
    run.approval_step = 0
    run.revision = int(run.revision or 0) + 1
    run.escalated = 0
    run.due_at = add_to_date(now_datetime(), hours=settings.sla_hours) if settings.sla_hours and not settings.is_terminal else None
    doc.workflow_state = state
    doc.workflow_policy = policy.name
    doc.due_at = run.due_at
    save_internal(run)
    save_internal(doc)


@frappe.whitelist(methods=["POST"])
def start(doctype, name, policy_name):
    key(doctype, name)
    _lock(doctype, name)
    doc = frappe.get_doc(doctype, name, for_update=True)
    require_company(doc.company)
    doc.check_permission("write")
    if doc.workflow_policy or frappe.db.exists("ADM Workflow Run", {"reference_key": key(doctype, name)}):
        frappe.throw("Workflow already started")
    _lock("ADM Workflow Policy", policy_name)
    policy = frappe.get_doc("ADM Workflow Policy", policy_name, for_update=True)
    if not policy.enabled or policy.target_doctype != doctype or policy.company != doc.company:
        frappe.throw("Policy is not enabled for this document")
    run = save_internal(frappe.get_doc({
        "doctype": "ADM Workflow Run", "reference_doctype": doctype,
        "reference_name": name, "reference_key": key(doctype, name),
        "policy": policy.name, "revision": 0
    }), insert=True)
    _set_state(doc, run, policy, policy.initial_state)
    _audit(doc, run, "Start", "", run.current_state)
    return {"state": run.current_state, "revision": run.revision}


def _transition(policy, run, action, doc):
    t = next((t for t in policy.transitions if t.action == action and t.from_state == run.current_state), None)
    if not t or not matches(t.conditions, doc.as_dict()):
        frappe.throw("Transition unavailable or conditions not met")
    return t


@frappe.whitelist(methods=["POST"])
def transition(doctype, name, action, expected_revision, comment=None):
    doc, run, policy = _load(doctype, name, expected_revision)
    doc.check_permission("read")
    if run.pending_action:
        frappe.throw("An approval is already pending")
    t = _transition(policy, run, action, doc)
    if t.allowed_role not in roles():
        frappe.throw("Transition role required", frappe.PermissionError)
    before = run.current_state
    if t.approval_required:
        run.pending_action = action
        run.approval_step = 1
        run.revision += 1
        save_internal(run)
        _audit(doc, run, action, before, before, "Requested", comment=comment)
    else:
        _set_state(doc, run, policy, t.to_state)
        _audit(doc, run, action, before, t.to_state, comment=comment)
    return {"state": run.current_state, "revision": run.revision, "pending_action": run.pending_action}


def _case(doc):
    return frappe._dict(requested_by=doc.requested_by, company=doc.company, department=doc.department)


@frappe.whitelist(methods=["POST"])
def decide(doctype, name, decision, expected_revision, comment=None):
    doc, run, policy = _load(doctype, name, expected_revision)
    if not run.pending_action or decision not in {"Approved", "Rejected"}:
        frappe.throw("No pending approval or invalid decision")
    t = _transition(policy, run, run.pending_action, doc)
    steps = sorted([s for s in policy.approval_bands if s.transition_action == t.action], key=lambda s: s.step_number)
    step = steps[int(run.approval_step)-1]
    ok, delegation = _authorized(step, _case(doc), frappe.session.user)
    if not ok:
        frappe.throw("Not authorized for this approval step", frappe.PermissionError)
    if decision == "Rejected" and not (comment or "").strip():
        frappe.throw("Rejection reason required")
    previous = frappe.get_all("ADM Workflow Audit", filters={
        "reference_doctype": doctype, "reference_name": name,
        "action": t.action, "decision": "Approved"
    }, fields=["actor", "delegated_from", "revision"], for_update=True)
    # A person or their delegator may approve only one step in the current attempt.
    last_request = frappe.db.get_value("ADM Workflow Audit", {
        "reference_doctype": doctype, "reference_name": name,
        "action": t.action, "decision": "Requested"
    }, "revision", order_by="creation desc", for_update=True)
    identities = {frappe.session.user, delegation} - {None}
    if any(int(x.revision or 0) >= int(last_request or 0) and identities & {x.actor, x.delegated_from} for x in previous):
        frappe.throw("A different approver is required for each step")
    before, action, number = run.current_state, run.pending_action, run.approval_step
    if decision == "Rejected":
        run.pending_action = None
        run.approval_step = 0
        run.revision += 1
        save_internal(run)
    elif number == len(steps):
        _set_state(doc, run, policy, t.to_state)
    else:
        run.approval_step += 1
        run.revision += 1
        save_internal(run)
    _audit(doc, run, action, before, run.current_state, decision, number, comment, delegation)
    return {"state": run.current_state, "revision": run.revision, "pending_action": run.pending_action}


@frappe.whitelist()
def available(doctype, name):
    key(doctype, name)
    doc = frappe.get_doc(doctype, name)
    require_company(doc.company)
    doc.check_permission("read")
    run_name = frappe.db.get_value("ADM Workflow Run", {"reference_key": key(doctype, name)}, "name")
    if not run_name:
        policies = frappe.get_list("ADM Workflow Policy", filters={"company": doc.company, "target_doctype": doctype, "enabled": 1}, fields=["name", "policy_title"])
        return {"policies": policies, "actions": [], "can_feedback": False}
    run = frappe.get_doc("ADM Workflow Run", run_name)
    policy = frappe.get_doc("ADM Workflow Policy", run.policy)
    step = next((s for s in policy.approval_bands if s.transition_action == run.pending_action and s.step_number == run.approval_step), None)
    return {"revision": run.revision, "state": run.current_state,
            "pending_action": run.pending_action,
            "can_decide": bool(step and _authorized(step, _case(doc), frappe.session.user)[0]),
            "can_acknowledge": bool(doc.doctype == "ADM Parcel" and doc.recipient == frappe.session.user and not doc.delivered_at),
            "can_release": bool(doc.doctype == "ADM Equipment Booking" and not doc.released and
                                (doc.requested_by == frappe.session.user or manager(doc.company))),
            "can_feedback": bool(doc.requested_by == frappe.session.user and
                any(s.state == run.current_state and s.is_terminal for s in policy.states) and
                not frappe.db.exists("ADM Operation Feedback", {"reference_key": key(doctype, name)})),
            "actions": [t.action for t in policy.transitions if not run.pending_action and t.from_state == run.current_state and t.allowed_role in roles() and matches(t.conditions, doc.as_dict())]}
