"""Role-filtered service discovery for the EuP mobile client."""
import frappe
from frappe.utils import cint

MODULE = "EuP Administration"

# Labels used by the Egyptian employee app. New module records are discovered automatically.
GROUPS = {
    "الطلبات والموافقات": {
        "General Service Request": "طلبات الخدمات العامة", "Service Request": "مشاوير المناديب",
        "Request Registry": "سجل الطلبات", "Request Event": "أحداث الطلبات",
        "Approval Case": "حالات الموافقة", "Approval Decision": "قرارات الموافقة",
        "Request Feedback": "تقييم الطلبات", "Operation Feedback": "تقييم العمليات"},
    "الأسطول والنقل": {
        "Trip": "الرحلات", "Trip Expense": "مصاريف الرحلات", "Vehicle": "السيارات",
        "Driver": "السائقون", "Fuel Log": "سجل الوقود", "Maintenance": "الصيانة",
        "Vehicle Document": "مستندات السيارات", "Vehicle Incident": "حوادث السيارات",
        "Driver Checklist": "فحص السائق", "Preventive Plan": "خطط الصيانة الوقائية"},
    "الاجتماعات والحجوزات": {
        "Meeting Room": "قاعات الاجتماعات", "Meeting Booking": "حجوزات القاعات والتقويم",
        "Meeting Checkin": "تسجيل حضور الاجتماعات", "Equipment Booking": "حجوزات المعدات",
        "Shared Equipment": "المعدات المشتركة"},
    "المخازن والعهد": {
        "Supply Request": "طلبات المستلزمات", "Consumable Item": "أصناف المستهلكات",
        "Consumable Location": "المخازن", "Consumable Transaction": "حركات المخزون",
        "Stock Count": "الجرد", "Admin Custody": "العهد", "Custody Handover": "تسليم العهد"},
    "المرافق والتشغيل": {
        "Facility Ticket": "بلاغات المرافق", "Parcel": "الطرود والشحنات",
        "Contract Register": "سجل العقود", "Operational Incident": "الحوادث التشغيلية",
        "Recurring Task": "المهام المتكررة", "Task Occurrence": "تنفيذ المهام"},
    "الإعدادات وسير العمل": {
        "Settings": "إعدادات الإدارة", "Approval Policy": "سياسات الموافقة",
        "Approval Delegation": "تفويض الموافقات", "SLA Policy": "سياسات مستوى الخدمة",
        "SLA Escalation": "تصعيد مستوى الخدمة", "Workflow Policy": "تصميم سير العمل",
        "Workflow Audit": "تدقيق سير العمل", "Workflow Run": "عمليات سير العمل",
        "Notification Outbox": "صندوق إرسال الإشعارات"},
    "التقارير": {
        "Department Consumption": "استهلاك الأقسام", "Fleet Costs": "تكاليف الأسطول",
        "Low Stock": "الأصناف منخفضة المخزون", "Meeting Utilization": "استخدام قاعات الاجتماعات",
        "Renewals and Service": "التجديدات والصيانة", "Trip Register": "سجل الرحلات"},
    "لوحات الإدارة": {
        "administration-command-center": "مركز التحكم والخدمة الذاتية",
        "administration-dashboard": "لوحة مؤشرات الإدارة", "administration-v3": "مركز العمليات"}
}

def entry(kind, name, **extra):
    key = name.removeprefix("ADM ")
    for group, labels in GROUPS.items():
        if key in labels:
            break
    else:
        group = {"Report": "التقارير", "Page": "لوحات الإدارة"}.get(kind, "خدمات إضافية")
    return dict(kind=kind, name=name, group=group, label=GROUPS.get(group, {}).get(key, key), **extra)

@frappe.whitelist(methods=["GET"])
def catalog():
    result = []
    for row in frappe.get_all("DocType", filters=dict(module=MODULE, istable=0),
                              fields=["name", "issingle"], order_by="name"):
        if frappe.has_permission(row.name, "read"):
            result.append(entry("DocType", row.name, single=bool(row.issingle),
                                create=bool(not row.issingle and frappe.has_permission(row.name, "create"))))
    for row in frappe.get_all("Report", filters=dict(module=MODULE, disabled=0),
                              fields=["name", "ref_doctype"], order_by="name"):
        if frappe.has_permission(row.ref_doctype, "report") and frappe.get_doc("Report", row.name).is_permitted():
            result.append(entry("Report", row.name))
    for name in frappe.get_all("Page", filters=dict(module=MODULE), pluck="name", order_by="name"):
        if frappe.get_doc("Page", name).is_permitted():
            result.append(entry("Page", name))
    return result

def allowed_type(doctype):
    meta = frappe.get_meta(doctype)
    if meta.module != MODULE or meta.istable or not frappe.has_permission(doctype, "read"):
        frappe.throw("Access denied", frappe.PermissionError)
    return meta

@frappe.whitelist(methods=["GET"])
def records(doctype, offset=0):
    meta = allowed_type(doctype)
    if meta.issingle:
        return [{"name": doctype}]
    return frappe.get_list(doctype, fields=["name"], order_by="modified desc, name desc",
                           start=max(0,cint(offset)), page_length=21)

def display(doc, meta):
    fields = []
    for df in meta.fields:
        if (df.hidden or not df.fieldname or df.fieldtype in {"Password","Code","HTML","Button","Signature","Attach Image","Image","Attach"}
                or df.fieldname == "cost_center"):
            continue
        value = doc.get(df.fieldname)
        if value is None or value == "" or value == []:
            continue
        if df.fieldtype in ("Table", "Table MultiSelect"):
            child_meta = frappe.get_meta(df.options)
            value = [display(row, child_meta) for row in value]
        else:
            value = str(value)
        fields.append(dict(label=frappe._(df.label or df.fieldname, lang="ar"), value=value))
    return fields

@frappe.whitelist(methods=["GET"])
def detail(doctype, name):
    meta = allowed_type(doctype)
    doc = frappe.get_doc(doctype, name)
    doc.check_permission("read")
    doc.apply_fieldlevel_read_permissions()
    return display(doc, meta)
