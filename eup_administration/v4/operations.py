"""Validation and scheduling for independent administrative records."""
from datetime import timedelta
import frappe
from frappe.model.document import Document
from frappe.utils import get_datetime, getdate, now_datetime, today, add_days
from eup_administration.v4.rules import positive as _positive_rule
from eup_administration.v4.security import require_company, manager
from eup_administration.v4.workflow import _internal, _lock, save_internal, key


def _positive(value, label, allow_zero=False):
    """Expose business-rule failures as normal Frappe validation responses."""
    try:
        return _positive_rule(value, label, allow_zero=allow_zero)
    except ValueError as error:
        frappe.throw(str(error))


class Operation(Document):
    def validate(self):
        require_company(self.company)
        old = self.get_doc_before_save()
        if self.is_new():
            if self.doctype == "ADM Task Occurrence" and not _internal.get():
                frappe.throw("Occurrences are created by the recurring task processor")
            self.requested_by = self.requested_by if _internal.get() and self.requested_by else frappe.session.user
            self.workflow_state = None
            self.workflow_policy = None
            self.due_at = None
            if self.doctype == "ADM Equipment Booking":
                self.released = 0
        elif not _internal.get():
            if old.workflow_policy:
                frappe.throw("Started operations are immutable; use protected actions")
            for name in ("requested_by", "company", "department", "workflow_state", "workflow_policy", "due_at", "released"):
                if self.get(name) != old.get(name):
                    frappe.throw("Identity and workflow fields cannot be changed")
            self.check_permission("write")
        if not _internal.get() and self.assigned_to and not manager(self.company):
            frappe.throw("Only an administration manager can assign an operator")
        if self.is_new() and not manager(self.company):
            employee = frappe.db.get_value("Employee", {"user_id": frappe.session.user, "status": "Active"},
                                          ["company", "department"], as_dict=True)
            if not employee or employee.company != self.company:
                frappe.throw("Employee company mismatch")
            self.department = employee.department
        if self.department:
            department_company = frappe.db.get_value("Department", self.department, "company")
            if department_company and department_company != self.company:
                frappe.throw("Department company mismatch")
        if self.assigned_to:
            employee = frappe.db.get_value("Employee", {"user_id": self.assigned_to, "status": "Active"}, "company")
            if employee != self.company:
                frappe.throw("Assignee must be an active employee in this company")
        if self.get("vehicle"):
            if frappe.db.get_value("ADM Vehicle", self.vehicle, "company") != self.company:
                frappe.throw("Vehicle company mismatch")
        if self.doctype == "ADM Equipment Booking":
            self.validate_booking()
        elif self.doctype == "ADM Driver Checklist":
            _positive(self.odometer or 0, "Odometer", allow_zero=True)
            if getdate(self.check_date) > getdate(today()):
                frappe.throw("Checklist cannot be future dated")
            if not all(self.get(f) for f in ("brakes_ok", "tires_ok", "lights_ok", "documents_ok")) and not self.defect_notes:
                frappe.throw("Explain failed checklist checks")
        elif self.doctype == "ADM Contract Register":
            if getdate(self.expires_on) <= getdate(self.starts_on):
                frappe.throw("Contract end must follow start")
            _positive(self.notice_days or 0, "Notice days", allow_zero=True)
        elif self.doctype in {"ADM Recurring Task", "ADM Preventive Plan"}:
            if self.get("next_odometer") is not None:
                _positive(self.next_odometer, "Next odometer", allow_zero=True)
            _positive(self.interval_days, "Interval days")
            if int(self.interval_days) > 3660:
                frappe.throw("Interval exceeds ten years")
        elif self.doctype == "ADM Parcel":
            employee = frappe.db.get_value("Employee", {"user_id": self.recipient, "status": "Active"}, "company")
            if employee != self.company:
                frappe.throw("Recipient must be in this company")
            if not self.is_new() and self.delivered_at != old.delivered_at and not _internal.get():
                frappe.throw("Use the recipient acknowledgement action")
        if self.get("attachment"):
            file = frappe.db.get_value("File", {"file_url": self.attachment},
                                       ["name", "is_private", "owner", "attached_to_doctype", "attached_to_name"], as_dict=True)
            if not file or not file.is_private or (file.owner != frappe.session.user and
                    (file.attached_to_doctype != self.doctype or file.attached_to_name != self.name)):
                frappe.throw("Use a private attachment belonging to this record")

    def validate_booking(self):
        _lock("ADM Shared Equipment", self.equipment)
        equipment = frappe.get_doc("ADM Shared Equipment", self.equipment)
        if not equipment.enabled or equipment.company != self.company:
            frappe.throw("Equipment unavailable in this company")
        if get_datetime(self.ends_at) <= get_datetime(self.starts_at):
            frappe.throw("Booking end must follow start")
        # All saved bookings reserve time, including drafts. Explicit release required.
        conflicts = frappe.get_all("ADM Equipment Booking", filters={
            "equipment": self.equipment, "name": ["!=", self.name or ""],
            "starts_at": ["<", self.ends_at], "ends_at": [">", self.starts_at],
            "released": 0
        }, pluck="name", limit_page_length=1)
        if not self.get("released") and conflicts:
            frappe.throw("Equipment is already reserved in this interval")

    def on_trash(self):
        if self.workflow_policy or self.doctype == "ADM Task Occurrence":
            frappe.throw("Operational history cannot be deleted")
        if self.doctype == "ADM Equipment Booking":
            _lock("ADM Shared Equipment", self.equipment)


@frappe.whitelist(methods=["POST"])
def acknowledge_parcel(name):
    _lock("ADM Parcel", name)
    doc = frappe.get_doc("ADM Parcel", name)
    require_company(doc.company)
    if frappe.session.user != doc.recipient or doc.delivered_at:
        frappe.throw("Only recipient may acknowledge once", frappe.PermissionError)
    doc.delivered_at = now_datetime()
    save_internal(doc)
    return {"delivered_at": doc.delivered_at}


@frappe.whitelist(methods=["POST"])
def release_booking(name):
    _lock("ADM Equipment Booking", name)
    doc = frappe.get_doc("ADM Equipment Booking", name)
    require_company(doc.company)
    doc.check_permission("read")
    if not manager(doc.company) and frappe.session.user != doc.requested_by:
        frappe.throw("Owner or manager required", frappe.PermissionError)
    doc.released = 1
    save_internal(doc)
    return {"released": True}


@frappe.whitelist(methods=["POST"])
def feedback(doctype, name, rating, comment=None):
    key(doctype, name)
    _lock(doctype, name)
    doc = frappe.get_doc(doctype, name)
    require_company(doc.company)
    if doc.requested_by != frappe.session.user or int(rating) not in range(1, 6):
        frappe.throw("Requester and rating 1 through 5 required", frappe.PermissionError)
    if not doc.workflow_policy:
        frappe.throw("Complete the workflow first")
    policy = frappe.get_doc("ADM Workflow Policy", doc.workflow_policy)
    if not any(s.state == doc.workflow_state and s.is_terminal for s in policy.states):
        frappe.throw("Feedback requires a terminal workflow state")
    row = save_internal(frappe.get_doc({"doctype": "ADM Operation Feedback",
        "reference_doctype": doctype, "reference_name": name, "reference_key": key(doctype, name),
        "requested_by": frappe.session.user, "rating": int(rating), "comment": comment}), insert=True)
    return {"feedback": row.name}


def recurring():
    """Explicit opt-in job; row locks and unique occurrence keys prevent duplicates."""
    if not frappe.conf.get("adm_v4_jobs_enabled"):
        return
    for item in frappe.get_all("ADM Recurring Task", filters={"enabled": 1, "next_due": ["<=", today()]}, pluck="name"):
        _lock("ADM Recurring Task", item)
        task = frappe.get_doc("ADM Recurring Task", item)
        if not task.enabled or getdate(task.next_due) > getdate(today()):
            continue
        occurrence_key = key(task.doctype, task.name) + ":" + str(task.next_due)
        if not frappe.db.exists("ADM Task Occurrence", {"occurrence_key": occurrence_key}):
            save_internal(frappe.get_doc({"doctype": "ADM Task Occurrence",
                "subject": task.subject, "company": task.company, "department": task.department,
                "requested_by": task.requested_by, "assigned_to": task.assigned_to, "description": task.description, "priority": task.priority,
                "task": task.name, "occurrence_date": task.next_due,
                "occurrence_key": occurrence_key}), insert=True)
        task.next_due = add_days(task.next_due, int(task.interval_days))
        save_internal(task)


EDITABLE = {
    "ADM Facility Ticket": {"resolution"},
    "ADM Operational Incident": {"root_cause", "corrective_action"},
    "ADM Parcel": {"delivery_note"},
    "ADM Preventive Plan": {"last_service_date", "next_service_date", "next_odometer"},
    "ADM Recurring Task": {"enabled", "next_due", "interval_days"},
}


@frappe.whitelist(methods=["POST"])
def update_details(doctype, name, values):
    key(doctype, name)
    _lock(doctype, name)
    doc = frappe.get_doc(doctype, name)
    require_company(doc.company)
    if not manager(doc.company) and frappe.session.user != doc.assigned_to:
        frappe.throw("Assigned operator or administration manager required", frappe.PermissionError)
    if doctype == "ADM Recurring Task" and not manager(doc.company):
        frappe.throw("Only a manager can change recurring schedules", frappe.PermissionError)
    values = frappe.parse_json(values) if isinstance(values, str) else values
    if not isinstance(values, dict) or not values or not set(values) <= EDITABLE.get(doctype, set()):
        frappe.throw("Unsupported detail fields")
    for field, value in values.items():
        if isinstance(value, (dict, list)):
            frappe.throw("Detail values must be scalar")
        if field in {"last_service_date", "next_service_date", "next_due"}:
            value = getdate(value)
        elif field == "enabled":
            if value not in (0, 1, "0", "1"):
                frappe.throw("Enabled must be zero or one")
            value = int(value)
        elif field == "interval_days":
            value = int(_positive(value, "Interval days"))
        elif field == "next_odometer":
            value = _positive(value, "Next odometer", allow_zero=True)
        elif not isinstance(value, str) or len(value) > 10000:
            frappe.throw("Detail text must be at most 10000 characters")
        doc.set(field, value)
    save_internal(doc)
    return {"name": doc.name}


@frappe.whitelist(methods=["POST"])
def assign_operator(doctype, name, assigned_to):
    key(doctype, name)
    _lock(doctype, name)
    doc = frappe.get_doc(doctype, name)
    if not manager(doc.company):
        frappe.throw("Company administration manager required", frappe.PermissionError)
    doc.assigned_to = assigned_to
    save_internal(doc)  # Validates employee company and records the tracked field change.
    if doc.workflow_policy:
        from eup_administration.v4.workflow import _load, _audit
        _, run, _ = _load(doctype, name)
        run.revision += 1
        save_internal(run)
        _audit(doc, run, "Assign operator", run.current_state, run.current_state,
               comment="Assigned to " + assigned_to)
    return {"assigned_to": doc.assigned_to}
