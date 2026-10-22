"""Step-based, role-scoped approvals for the new general service workflow."""
from hashlib import sha256
import frappe
from frappe.utils import now_datetime, get_datetime
from eup_administration.v3.security import active_employee, is_manager, roles


def case_name(doctype, name):
    return "ADMAPP-" + sha256((doctype + ":" + name).encode("utf-8")).hexdigest()[:32]


def _policy(doc):
    policies = frappe.get_all(
        "ADM Approval Policy",
        filters={"request_type": "General", "company": doc.company, "enabled": 1},
        fields=["name"], order_by="modified desc", limit_page_length=2
    )
    if len(policies) != 1:
        frappe.throw("Exactly one enabled General approval policy is required for this company")
    policy = frappe.get_doc("ADM Approval Policy", policies[0].name)
    steps = sorted(policy.get("steps") or [], key=lambda d: d.step_number or 0)
    if not steps or [int(s.step_number) for s in steps] != list(range(1, len(steps) + 1)):
        frappe.throw("Approval policy steps must be sequential from 1")
    return policy, steps


def validate_policy(doc):
    numbers = [int(s.step_number) for s in doc.get("steps") or []]
    if not numbers or sorted(numbers) != list(range(1, len(numbers) + 1)):
        frappe.throw("Approval policy requires steps numbered 1,2,3...")
    if any(not s.approver_role for s in doc.steps):
        frappe.throw("Every approval step needs an approver role")
    if doc.name and frappe.db.exists("ADM Approval Case", {"policy": doc.name, "status": "Pending"}):
        if doc.get_doc_before_save():
            old = doc.get_doc_before_save()
            if any((doc.get(k) != old.get(k) for k in ("enabled", "company", "request_type"))) or [
                (s.step_number, s.approver_role, s.same_department, s.same_company)
                for s in doc.steps
            ] != [(s.step_number, s.approver_role, s.same_department, s.same_company) for s in old.steps]:
                frappe.throw("Policy cannot change while approval cases are pending")


def create_case(doc):
    if not frappe.db.get_single_value("ADM Settings", "enable_v3_requests"):
        frappe.throw("The v3 service request feature is disabled")
    policy, steps = _policy(doc)
    key = case_name(doc.doctype, doc.name)
    if frappe.db.exists("ADM Approval Case", key):
        frappe.throw("Approval case already exists for this request")
    return frappe.get_doc({
        "doctype": "ADM Approval Case", "name": key,
        "reference_doctype": doc.doctype, "reference_name": doc.name,
        "policy": policy.name, "company": doc.company, "department": doc.department,
        "requested_by": doc.requested_by, "status": "Pending",
        "current_step": 1, "created_on": now_datetime()
    }).insert(ignore_permissions=True)


def _authorized(step, case, actor):
    if actor == case.requested_by:
        return False, None
    if step.approver_role in roles(actor):
        from_user = None
    else:
        from_user = None
        if not step.allow_delegation:
            return False, None
        for d in frappe.get_all("ADM Approval Delegation",
            filters={"delegate": actor, "enabled": 1, "company": case.company},
            fields=["delegator", "department", "valid_from", "valid_until"]):
            now = get_datetime(now_datetime())
            if (d.valid_from and now < get_datetime(d.valid_from)) or (d.valid_until and now > get_datetime(d.valid_until)):
                continue
            if step.approver_role in roles(d.delegator):
                from_user = d.delegator
                if not d.department or d.department == case.department:
                    break
                from_user = None
        if not from_user or from_user == case.requested_by:
            return False, None
    acting_employee = active_employee(actor)
    if step.same_company and (not acting_employee or acting_employee.company != case.company):
        return False, None
    if step.same_department and (not acting_employee or acting_employee.department != case.department):
        return False, None
    if from_user:
        original_employee = active_employee(from_user)
        if not original_employee or original_employee.company != case.company:
            return False, None
        if step.same_department and original_employee.department != case.department:
            return False, None
    return True, from_user


@frappe.whitelist(methods=["POST"])
def decide(case_id, decision, comment=None):
    if decision not in {"Approved", "Rejected"}:
        frappe.throw("Unknown decision")
    if not frappe.db.sql("SELECT name FROM `tabADM Approval Case` WHERE name=%s FOR UPDATE", (case_id,)):
        frappe.throw("Approval case missing")
    case = frappe.get_doc("ADM Approval Case", case_id)
    if case.status != "Pending" or case.reference_doctype != "ADM General Service Request":
        frappe.throw("Case is no longer pending or has an unsupported request type")
    request = frappe.get_doc(case.reference_doctype, case.reference_name)
    if request.status != "Pending Approval":
        frappe.throw("Request status changed; reload before approving")
    policy, steps = _policy(request)
    if policy.name != case.policy:
        frappe.throw("Approval policy has changed; administrator review needed")
    step = steps[int(case.current_step) - 1]
    ok, delegation = _authorized(step, case, frappe.session.user)
    if not ok:
        frappe.throw("Not authorized to decide this step", frappe.PermissionError)
    if decision == "Rejected" and not (comment or "").strip():
        frappe.throw("Rejection reason is required")
    frappe.get_doc({
        "doctype": "ADM Approval Decision", "approval_case": case.name,
        "step_number": case.current_step, "actor": frappe.session.user,
        "delegated_from": delegation, "decision": decision,
        "decided_on": now_datetime(), "comment": comment
    }).insert(ignore_permissions=True)
    if decision == "Rejected":
        case.status = "Rejected"
        request.status = "Rejected"
    elif case.current_step >= len(steps):
        case.status = "Approved"
        request.status = "Approved"
    else:
        case.current_step += 1
    if case.status != "Pending":
        case.decided_on = now_datetime()
    case.save(ignore_permissions=True)
    from eup_administration.v3.general import write_action
    write_action(request)
    return {"case": case.name, "approval_status": case.status,
            "request_status": request.status, "next_step": case.current_step}


def cancel_case(doc):
    key = case_name(doc.doctype, doc.name)
    if not frappe.db.exists("ADM Approval Case", key):
        return
    frappe.db.sql("SELECT name FROM `tabADM Approval Case` WHERE name=%s FOR UPDATE", (key,))
    case = frappe.get_doc("ADM Approval Case", key)
    if case.status == "Pending":
        case.status = "Cancelled"
        case.save(ignore_permissions=True)


@frappe.whitelist()
def pending_for_me():
    """Never expose another department's case or requester private data."""
    user = frappe.session.user
    result = []
    for case in frappe.get_all("ADM Approval Case",
        filters={"status": "Pending", "reference_doctype": "ADM General Service Request"},
        fields=["name","policy","current_step","company","department","requested_by","reference_name"],
        limit_page_length=500):
        policy = frappe.get_doc("ADM Approval Policy", case.policy)
        matching = [x for x in policy.steps if int(x.step_number) == int(case.current_step)]
        if matching and _authorized(matching[0], case, user)[0]:
            result.append({"case": case.name, "request": case.reference_name,
                           "company": case.company, "department": case.department})
    return result
