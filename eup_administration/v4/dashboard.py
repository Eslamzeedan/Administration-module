"""Scoped command center, inbox, weekly reports and explainable dispatch."""
from collections import Counter
from datetime import timedelta
from urllib.parse import quote
import frappe
from frappe.utils import getdate, get_datetime, today, now_datetime, add_days, get_url
from eup_administration.v4.rules import OPERATIONS, forecast, positive
from eup_administration.v4.security import require_company, manager
from eup_administration.v4.workflow import _authorized, _case


def _rows(doctype, filters, fields):
    # No silent truncation: fail and ask the user to narrow their reporting range.
    rows = frappe.get_list(doctype, filters=filters, fields=fields, limit_page_length=5001)
    if len(rows) > 5000:
        frappe.throw("More than 5000 visible records; narrow the reporting date range")
    return rows


@frappe.whitelist()
def context():
    """UI guidance only; all data/action endpoints still enforce company access."""
    employee = frappe.db.get_value("Employee",
        {"user_id": frappe.session.user, "status": "Active"}, ["company"], as_dict=True)
    administrator = frappe.session.user == "Administrator"
    company = employee.company if employee else None
    return {"company": company, "requires_employee": not administrator and not employee,
            "can_choose_company": administrator, "can_manage": bool(company and manager(company))}


@frappe.whitelist()
def inbox():
    employee = frappe.db.get_value("Employee", {"user_id": frappe.session.user, "status": "Active"},
                                    ["company", "department"], as_dict=True)
    if not employee:
        return []
    result = []
    runs = frappe.get_all("ADM Workflow Run", filters={"pending_action": ["is", "set"]},
                         fields=["name", "reference_doctype", "reference_name", "policy", "pending_action", "approval_step", "revision"],
                         limit_page_length=1001, order_by="modified asc")
    # This scan exposes only cases individually authorized below. Cursor paging is a future scaling task.
    if len(runs) > 1000:
        frappe.throw("Approval inbox exceeds 1000 pending runs; administrator review required")
    for run in runs:
        doc = frappe.get_doc(run.reference_doctype, run.reference_name)
        if doc.company != employee.company:
            continue
        policy = frappe.get_doc("ADM Workflow Policy", run.policy)
        step = next((s for s in policy.approval_bands if s.transition_action == run.pending_action and s.step_number == run.approval_step), None)
        if step and _authorized(step, _case(doc), frappe.session.user)[0]:
            result.append({"doctype": doc.doctype, "name": doc.name, "subject": doc.subject,
                           "action": run.pending_action, "revision": run.revision})
    return result


@frappe.whitelist()
def command_center(company, from_date=None, to_date=None):
    require_company(company)
    end = getdate(to_date or today())
    start = getdate(from_date or add_days(end, -6))
    if end < start or (end-start).days > 90:
        frappe.throw("Report range must be between one and 91 days")
    summaries, problems, records = {}, Counter(), []
    for doctype in OPERATIONS:
        rows = _rows(doctype, {"company": company, "creation": ["between", [str(start), str(end + timedelta(days=1))]]},
                     ["name", "subject", "workflow_state", "priority", "due_at"])
        summaries[doctype] = len(rows)
        for row in rows:
            problems[row.priority or "Normal"] += 1
            records.append({"doctype": doctype, **row})
    facilities = _rows("ADM Facility Ticket", {"company": company, "creation": ["between", [str(start), str(end + timedelta(days=1))]]},
                      ["category"])
    incidents = _rows("ADM Operational Incident", {"company": company, "creation": ["between", [str(start), str(end + timedelta(days=1))]]},
                     ["category", "severity", "root_cause"])
    contracts = _rows("ADM Contract Register", {"company": company, "expires_on": ["<=", add_days(today(), 90)]},
                     ["name", "subject", "expires_on", "notice_days"])
    contract_notices = [r for r in contracts if getdate(r.expires_on) - timedelta(days=int(r.notice_days or 0)) <= getdate(today())]
    preventive = _rows("ADM Preventive Plan", {"company": company}, ["name", "subject", "vehicle", "next_service_date", "next_odometer"])
    due_plans = []
    for plan in preventive:
        odometer = frappe.db.get_value("ADM Vehicle", plan.vehicle, "last_odometer") or 0
        if getdate(plan.next_service_date) <= getdate(today()) or (plan.next_odometer and odometer >= plan.next_odometer):
            due_plans.append(plan)
    ratings = _rows("ADM Operation Feedback", {"company": company,
        "creation": ["between", [str(start), str(end + timedelta(days=1))]]}, ["rating"]) if manager(company) else []
    return {"satisfaction": {"responses": len(ratings),
            "average": sum(r.rating for r in ratings)/len(ratings) if ratings else None},
            "from_date": str(start), "to_date": str(end), "visible_counts": summaries,
            "records": records, "priorities": dict(problems),
            "facility_categories": dict(Counter(r.category or "Other" for r in facilities)),
            "incident_categories": dict(Counter(r.category for r in incidents)),
            "unresolved_root_causes": sum(not r.root_cause for r in incidents),
            "contract_notices": contract_notices, "preventive_due": due_plans,
            "overdue": sum(bool(r["due_at"] and get_datetime(r["due_at"]) < now_datetime()) for r in records),
            "scope": "Visible administrative records only; no accounting impact"}


@frappe.whitelist()
def weekly_report(company, week_ending=None):
    end = getdate(week_ending or today())
    return command_center(company, str(end-timedelta(days=6)), str(end))


@frappe.whitelist()
def consumption_forecast(company, item, from_date=None, to_date=None):
    require_company(company)
    if not manager(company):
        frappe.throw("Administration manager required", frappe.PermissionError)
    end = getdate(to_date or today())
    start = getdate(from_date or end-timedelta(days=27))
    if end < start or (end-start).days > 90:
        frappe.throw("Choose at most 91 days")
    rows = _rows("ADM Consumable Transaction", {
        "company": company, "item": item, "movement_type": "Issue",
        "posting_time": ["between", [str(start), str(end+timedelta(days=1))]]
    }, ["posting_time", "quantity"])
    daily = {start + timedelta(days=n): 0.0 for n in range((end-start).days+1)}
    for r in rows:
        day = getdate(r.posting_time)
        if day in daily:
            daily[day] += float(r.quantity or 0)
    if not rows:
        return {"available": False, "reason": "No issue history in the selected interval"}
    result = forecast(list(daily.values()))
    result["warning"] = "Baseline estimate; assumes complete issue history and stable demand"
    return result


@frappe.whitelist()
def dispatch_suggestions(company, start, end, passengers=1):
    require_company(company)
    if not manager(company):
        frappe.throw("Administration manager required", frappe.PermissionError)
    start, end = get_datetime(start), get_datetime(end)
    if end <= start or (end-start).total_seconds() > 31*86400:
        frappe.throw("Choose a valid interval of at most 31 days")
    passengers = positive(passengers, "Passengers")
    vehicles = _rows("ADM Vehicle", {"company": company, "status": "Available"},
                    ["name", "plate_number", "seat_capacity", "license_expiry", "insurance_expiry", "last_odometer"])
    # The coordinator must see all conflicts. Query internal occupancy only; no passenger data returned.
    blocked = set(frappe.get_all("ADM Trip", filters={"company": company,
        "status": ["in", ["Assigned", "In Progress"]], "planned_start": ["<", end],
        "planned_end": [">", start]}, pluck="vehicle"))
    blocked.update(frappe.get_all("ADM Maintenance", filters={"company": company,
        "status": ["in", ["Scheduled", "In Progress"]], "starts_at": ["<", end],
        "ends_at": [">", start]}, pluck="vehicle"))
    plans = _rows("ADM Preventive Plan", {"company": company},
                   ["vehicle", "next_service_date", "next_odometer"])
    readings = {v.name: v.last_odometer or 0 for v in vehicles}
    blocked.update(p.vehicle for p in plans if getdate(p.next_service_date) <= end.date() or
                   (p.next_odometer and readings.get(p.vehicle, 0) >= p.next_odometer))
    candidates = []
    for v in vehicles:
        if v.name in blocked or (v.seat_capacity or 0) < passengers:
            continue
        if not v.license_expiry or not v.insurance_expiry or min(getdate(v.license_expiry), getdate(v.insurance_expiry)) < end.date():
            continue
        checks = frappe.get_all("ADM Driver Checklist", filters={"company": company, "vehicle": v.name, "check_date": str(start.date())},
                                fields=["brakes_ok", "tires_ok", "lights_ok", "documents_ok"],
                                order_by="creation desc", limit_page_length=1)
        if not checks or not all(checks[0].get(f) for f in ("brakes_ok", "tires_ok", "lights_ok", "documents_ok")):
            continue
        candidates.append({"vehicle": v.name, "plate": v.plate_number,
                           "spare_seats": v.seat_capacity-passengers, "odometer": v.last_odometer,
                           "reason": "No occupancy conflict, valid documents and daily safety checks"})
    return {"suggestions": sorted(candidates, key=lambda v: (v["spare_seats"], v["odometer"] or 0)),
            "advisory": "Suggestions only. Existing trip assignment API rechecks conflicts; no automatic allocation."}


@frappe.whitelist()
def custody_label(name):
    doc = frappe.get_doc("ADM Admin Custody", name)
    doc.check_permission("read")
    require_company(doc.company)
    # No bearer token or personal details: scanning always requires login and record permission.
    from pyqrcode import create
    from io import BytesIO
    from base64 import b64encode
    url = get_url("/app/adm-admin-custody/" + quote(name, safe=""))
    stream = BytesIO()
    create(url).svg(stream, scale=5, quiet_zone=4)
    return {"url": url, "qr": "data:image/svg+xml;base64," + b64encode(stream.getvalue()).decode(),
            "label": name, "requires_login": True}
