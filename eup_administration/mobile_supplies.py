"""Native supply request and fulfilment, using the operational stock ledger."""
import frappe
from frappe.utils import cint
from eup_administration import consumables as stock
from eup_administration import mobile_work

REQUEST = "ADM Supply Request"
ITEM = "ADM Consumable Item"
LOCATION = "ADM Consumable Location"
OPEN = ("Approved", "Partially Issued")


@frappe.whitelist(methods=["GET"])
def items():
    frappe.has_permission(REQUEST, "create", throw=True)
    employee = stock.employee_for()
    if not employee or not employee.company or not employee.department:
        frappe.throw("Active employee with company and department required")
    return {"department": employee.department,
            "items": frappe.get_list(ITEM, filters={"company": employee.company,"enabled":1},
                fields=["name","item_name","uom"], order_by="item_name asc, name asc",limit_page_length=0)}


@frappe.whitelist(methods=["POST"])
def submit(purpose, needed_by, lines):
    frappe.has_permission(REQUEST, "create", throw=True)
    lines=frappe.parse_json(lines) if isinstance(lines,str) else lines
    if not isinstance(lines,list) or not 1<=len(lines)<=stock.MAX_LINES or not str(purpose or "").strip():
        frappe.throw("Purpose and 1 to 60 supply lines required")
    allowed={row.name for row in items()["items"]}
    values=[]
    for line in lines:
        if not isinstance(line,dict) or line.get("item") not in allowed:
            frappe.throw("Item unavailable")
        values.append({"item":line["item"], "requested_qty":float(stock.quantity(line.get("qty")))})
    doc=frappe.get_doc(dict(doctype=REQUEST, purpose=purpose.strip(), needed_by=needed_by,items=values)).insert()
    return stock.submit_supply_request(doc.name)


@frappe.whitelist(methods=["GET"])
def pending(offset=0):
    result=mobile_work.queue("pending",offset)
    result["can_store"]=stock.can_store()
    return result


@frappe.whitelist(methods=["GET"])
def waiting(offset=0):
    stock.require_store()
    rows=frappe.get_list(REQUEST,filters={"status":["in",OPEN]},fields=["name","department","purpose","needed_by","status"],
                        start=max(0,cint(offset)),page_length=21,order_by="needed_by asc, creation asc, name asc")
    return {"rows":rows[:20],"more":len(rows)>20}


@frappe.whitelist(methods=["GET"])
def detail(name):
    doc=frappe.get_doc(REQUEST,name)
    doc.check_permission("read")
    doc.apply_fieldlevel_read_permissions()
    store=stock.can_store() and doc.status in OPEN
    lines=[]
    for r in doc.get("items") or []:
        lines.append(dict(name=r.name,item=r.item,requested=r.requested_qty,approved=r.approved_qty or 0,
                          issued=r.issued_qty or 0,remaining=float(stock.quantity(r.approved_qty or 0,allow_zero=True)
                                                              -stock.quantity(r.issued_qty or 0,allow_zero=True))))
    locations=frappe.get_list(LOCATION,filters={"enabled":1,"company":doc.company},fields=["name","location_name"],
                              order_by="location_name asc",limit_page_length=0) if store else []
    return dict(name=doc.name,purpose=doc.purpose,department=doc.department,date=doc.needed_by,status=doc.status,
                reason=doc.rejection_reason,lines=lines,can_store=bool(store),locations=locations)


@frappe.whitelist(methods=["POST"])
def issue(name,line,location,qty,expected_issued):
    # Compare with the amount displayed to the operator while holding the request lock.
    # Every successful issue strictly increases this value, even on partial issues.
    stock.require_store()
    stock._lock(REQUEST,name)
    doc=frappe.get_doc(REQUEST,name,for_update=True)
    doc.check_permission("read")
    row=next((r for r in doc.items if r.name==line),None)
    if row is None:
        frappe.throw("Unknown supply line")
    expected=stock.quantity(expected_issued,allow_zero=True)
    current=stock.quantity(row.issued_qty or 0,allow_zero=True)
    if current!=expected:
        return {"changed":False,"status":doc.status,"issued":float(current)}
    frappe.get_doc(LOCATION,location).check_permission("read")
    result=stock.issue_consumables(name,line,location,qty)
    return {"changed":True,"status":result["status"]}
