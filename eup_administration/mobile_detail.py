"""Localized display labels for permission-checked mobile record details."""
import frappe
from eup_administration.mobile_catalog import allowed_type


def display(doc, meta, language):
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
            value = [display(row, child_meta, language) for row in value]
        else:
            value = str(value)
        fields.append(dict(label=frappe._(df.label or df.fieldname, lang=language), value=value))
    return fields


@frappe.whitelist(methods=["GET"])
def get(doctype, name, language="ar"):
    if language not in {"ar", "en"}:
        frappe.throw("Unsupported language")
    meta = allowed_type(doctype)
    doc = frappe.get_doc(doctype, name)
    doc.check_permission("read")
    doc.apply_fieldlevel_read_permissions()
    return display(doc, meta, language)
