"""Approval inbox and transactional in-app notices for runner requests."""
import frappe
from frappe.utils import cint
from eup_administration import runner

DOCTYPE = "ADM Service Request"


def actionable(doc, user):
    return (user not in {doc.requested_by, doc.assigned_runner}
            and runner.approver_for(doc, user)
            and frappe.has_permission(DOCTYPE, "read", doc=doc, user=user))


def members(role):
    candidates = frappe.get_all("Has Role", filters={"role": role, "parenttype": "User"}, pluck="parent")
    if not candidates:
        return []
    return frappe.get_all("User", filters={"name": ["in", candidates], "enabled": 1}, pluck="name")


def notify_transition(doc):
    before = doc.get_doc_before_save()
    if not before or doc.status == before.status:
        return
    if doc.status == "Pending Approval":
        recipients = {u for u in members(runner.APPROVER_ROLE) if actionable(doc, u)}
        if not recipients:
            recipients = {u for u in members("Administration Manager") if actionable(doc, u)}
        if not recipients:
            recipients = {u for u in members("System Manager") if actionable(doc, u)}
        title = "مشوار مندوب بانتظار موافقتك"
    elif doc.status in {"Approved", "Rejected"}:
        recipients = {doc.requested_by}
        title = "تمت الموافقة على مشوار المندوب" if doc.status == "Approved" else "تم رفض مشوار المندوب"
    else:
        return
    for user in sorted(recipients):
        # Store a mobile/in-app notice in the same transaction as the decision.
        # Notification Log.after_insert may send mail; this channel is in-app only.
        notice = frappe.get_doc(dict(doctype="Notification Log", for_user=user,
            from_user=frappe.session.user, type="Alert", app="eup_administration",
            document_type=DOCTYPE, document_name=doc.name, title=title, subject=title))
        notice.db_insert()
        frappe.publish_realtime("notification", user=user, after_commit=True)


@frappe.whitelist(methods=["GET"])
def pending(offset=0):
    user = frappe.session.user
    if not (runner.is_admin(user) or runner.APPROVER_ROLE in runner.roles(user)):
        return {"rows": [], "more": False}
    filters = {"status": "Pending Approval", "requested_by": ["!=", user]}
    if not runner.is_admin(user):
        emp = runner.employee_record(user)
        if not emp or not emp.department:
            return {"rows": [], "more": False}
        filters.update(company=emp.company, department=emp.department)
    offset = max(0, cint(offset))
    rows = frappe.get_list(DOCTYPE, filters=filters, fields=["name"], order_by="creation asc, name asc",
                           start=offset, page_length=21)
    data = []
    for row in rows[:20]:
        doc = frappe.get_doc(DOCTYPE, row.name)
        if actionable(doc, user):
            doc.apply_fieldlevel_read_permissions()
            data.append({key: doc.get(key) for key in
                         ("name","purpose","service_location","needed_by","department","priority","requested_by")})
    return {"rows": data, "more": len(rows)>20}


@frappe.whitelist(methods=["POST"])
def decide(name, decision, reason=""):
    doc = runner._load(name)
    if not actionable(doc, frappe.session.user):
        frappe.throw("لا تملك صلاحية اتخاذ القرار على هذا المشوار", frappe.PermissionError)
    if decision == "approve":
        return runner.approve_request(name)
    if decision == "reject":
        return runner.reject_request(name, reason)
    frappe.throw("قرار غير صالح")
