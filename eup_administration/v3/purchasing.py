"""Approval-only ERPNext bridge. No stock or financial postings."""
import frappe
from frappe.utils import nowdate, now_datetime, getdate
from eup_administration.v3.security import is_manager


def _require_manager():
    if not is_manager():
        frappe.throw("Administration Manager required", frappe.PermissionError)


def build_preview(request):
    if request.status not in {"Approved", "Partially Issued"}:
        frappe.throw("Only an approved supply request can be linked to purchasing")
    lines = []
    for row in request.items:
        qty = float(row.approved_qty or 0) - float(row.issued_qty or 0)
        if qty <= 0:
            continue
        maps = frappe.get_all("ADM Consumable ERP Mapping", filters={
            "administration_item": row.item, "company": request.company, "enabled": 1
        }, fields=["erpnext_item", "warehouse"], limit_page_length=2)
        if len(maps) != 1 or not maps[0].erpnext_item:
            frappe.throw("Missing or ambiguous ERP mapping for item " + row.item)
        item = maps[0].erpnext_item
        if not frappe.db.get_value("Item", item, "is_stock_item"):
            frappe.throw("Only enabled stock items may use the purchasing bridge: " + item)
        if frappe.db.get_value("Item", item, "disabled"):
            frappe.throw("ERP item is disabled: " + item)
        if maps[0].warehouse and frappe.db.get_value("Warehouse", maps[0].warehouse, "company") != request.company:
            frappe.throw("Warehouse is in a different company")
        lines.append({
            "item_code": item, "qty": qty,
            "schedule_date": str(max(getdate(nowdate()), getdate(request.needed_by or nowdate()))),
            "warehouse": maps[0].warehouse
        })
    if not lines:
        frappe.throw("There are no unissued approved quantities to purchase")
    return {"company": request.company, "material_request_type": "Purchase", "items": lines}


@frappe.whitelist()
def preview_material_request(request_name):
    _require_manager()
    req = frappe.get_doc("ADM Supply Request", request_name)
    req.check_permission("read")
    return build_preview(req)


@frappe.whitelist(methods=["POST"])
def create_material_request(request_name):
    _require_manager()
    if not frappe.db.get_single_value("ADM Settings", "enable_purchasing_bridge"):
        frappe.throw("ERPNext Purchasing bridge is disabled")
    if not frappe.has_permission("Material Request", "create"):
        frappe.throw("Material Request create permission is required", frappe.PermissionError)
    # Lock the source before looking up prior bridge links.
    if not frappe.db.sql("SELECT name FROM `tabADM Supply Request` WHERE name=%s FOR UPDATE", (request_name,)):
        frappe.throw("Supply request not found")
    req = frappe.get_doc("ADM Supply Request", request_name)
    req.check_permission("read")
    existing = frappe.db.get_value("ADM Purchasing Link",
        {"supply_request": req.name, "status": "Created"}, "material_request")
    if existing:
        return {"material_request": existing, "created": False}
    mr = frappe.get_doc({"doctype": "Material Request", **build_preview(req)})
    mr.insert()  # Deliberately remains draft; procurement approves/submits it.
    frappe.get_doc({
        "doctype": "ADM Purchasing Link", "supply_request": req.name,
        "company": req.company, "material_request": mr.name,
        "status": "Created", "created_by": frappe.session.user,
        "created_on": now_datetime()
    }).insert(ignore_permissions=True)
    return {"material_request": mr.name, "created": True, "status": "Draft"}
