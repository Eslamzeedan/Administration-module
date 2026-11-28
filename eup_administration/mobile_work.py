"""Permission-scoped employee queues. Business transitions stay in the module controllers."""
import frappe
from frappe.utils import cint, getdate, add_days
from eup_administration import consumables, runner, services, trip_portal
from eup_administration.permissions import active_driver, is_admin
from eup_administration.mobile_errands import actionable, members

TRIP = "ADM Trip"
ERRAND = "ADM Service Request"
SUPPLY = "ADM Supply Request"
BOOKING = "ADM Meeting Booking"
SPECS = {
    TRIP: ("requested_by", "purpose", "planned_start", "destination"),
    ERRAND: ("requested_by", "purpose", "needed_by", "service_location"),
    SUPPLY: ("requested_by", "purpose", "needed_by", None),
    BOOKING: ("organizer", "room", "starts_at", None),
}

def authorized(doc):
    if doc.requested_by == frappe.session.user:
        return False
    if doc.doctype == TRIP:
        return is_admin()
    if doc.doctype == SUPPLY:
        return consumables.department_approver(doc)
    return actionable(doc, frappe.session.user)

def row_for(doc):
    _, title, date, destination = SPECS[doc.doctype]
    return dict(kind=doc.doctype, name=doc.name, title=doc.get(title), date=str(doc.get(date) or ""),
                location=doc.get(destination) if destination else "", status=doc.status,
                driver=doc.get("driver"), vehicle=doc.get("vehicle"), reason=doc.get("rejection_reason"))

@frappe.whitelist(methods=["GET"])
def queue(view, offset=0):
    if view not in ("mine","pending","today"):
        frappe.throw("Invalid view")
    offset=max(0,cint(offset))
    rows=[]
    user=frappe.session.user
    for kind,(owner,_,date,_) in SPECS.items():
        if not frappe.has_permission(kind,"read"):
            continue
        if view=="mine":
            filters={owner:user}
        elif view=="pending":
            if kind==BOOKING or (kind==TRIP and not is_admin()):
                continue
            filters={"status":"Requested" if kind==TRIP else "Pending Approval",owner:["!=",user]}
        else:
            if kind not in (ERRAND,TRIP):
                continue
            assignee=active_driver() if kind==TRIP else user
            if not assignee:
                continue
            filters={"driver" if kind==TRIP else "assigned_runner":assignee,"status":["in",["Assigned","In Progress"]]}
        # Walk in batches to respect user permissions and post-filter departmental approvals.
        start=0
        order=date+" asc, name asc" if view=="today" else "modified desc, name desc"
        accepted=0
        while accepted<offset+21:
            batch=frappe.get_list(kind,filters=filters,fields=["name"],start=start,page_length=50,order_by=order)
            for item in batch:
                doc=frappe.get_doc(kind,item.name)
                if not doc.has_permission("read") or (view=="pending" and not authorized(doc)):
                    continue
                if view=="today" and doc.status!="In Progress" and getdate(doc.get(date))!=getdate():
                    continue
                doc.apply_fieldlevel_read_permissions()
                row=row_for(doc)
                rows.append((row["date"] if view=="today" else str(doc.modified),kind,doc.name,row))
                accepted+=1
                if accepted>=offset+21:
                    break
            if len(batch)<50:
                break
            start+=50
    rows.sort(key=lambda r:r[:3],reverse=view!="today")
    return {"rows":[r[3] for r in rows[offset:offset+20]],"more":len(rows)>offset+20}

def notice(doc, user, title):
    if not user or not frappe.db.get_value("User",user,"enabled") or not doc.has_permission("read",user=user):
        return
    log=frappe.get_doc(dict(doctype="Notification Log", for_user=user, from_user=frappe.session.user,
        type="Alert",app="eup_administration", document_type=doc.doctype,document_name=doc.name,
        title=title,subject=title))
    log.db_insert()
    frappe.publish_realtime("notification",user=user,after_commit=True)

@frappe.whitelist(methods=["POST"])
def request_car(values):
    result=trip_portal.create(values)
    doc=frappe.get_doc(TRIP,result["name"])
    for user in set(members("Administration Manager"))-{doc.requested_by}:
        notice(doc,user,"Car request awaiting approval")
    return result

@frappe.whitelist(methods=["GET"])
def resources(name):
    services.admin_only()
    doc=frappe.get_doc(TRIP,name)
    doc.check_permission("read")
    if not authorized(doc) or doc.status!="Requested":
        frappe.throw("Trip is not available for dispatch",frappe.PermissionError)
    return dict(vehicles=frappe.get_list("ADM Vehicle",filters={"company":doc.company,"status":"Available"},pluck="name",limit_page_length=0),
                drivers=frappe.get_list("ADM Driver",filters={"enabled":1},fields=["name","driver_name"],limit_page_length=0))

@frappe.whitelist(methods=["POST"])
def decide(kind,name,action,vehicle=None,driver=None,reason=""):
    if kind not in (TRIP,SUPPLY) or action not in ("approve","reject"):
        frappe.throw("Invalid decision")
    doc=frappe.get_doc(kind,name)
    doc.check_permission("read")
    if not authorized(doc):
        frappe.throw("Not authorized",frappe.PermissionError)
    if kind==TRIP:
        if action=="approve":
            services.assign_trip(name,vehicle,driver)
        else:
            services.reject_trip(name,reason)
    elif action=="approve":
        consumables.approve_supply_request(name)
    else:
        consumables.reject_supply_request(name,reason)
    doc.reload()
    if kind==TRIP and action=="approve":
        notice(doc,frappe.db.get_value("ADM Driver",doc.driver,"user"),"A trip was assigned to you")
    notice(doc,doc.requested_by,("Car request " if kind==TRIP else "Supply request ")+("approved" if action=="approve" else "rejected"))
    return {"name":name,"status":doc.status}
