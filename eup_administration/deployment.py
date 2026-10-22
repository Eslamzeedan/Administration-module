"""Read-only operator diagnostics, invoked via bench execute. No HTTP exposure."""
import hashlib
import json
import frappe
from eup_administration.services import admin_only

LEGACY_FIELDS = {
    "ADM Driver": [
        "name",
        "docstatus",
        "owner",
        "creation",
        "modified",
        "driver_name",
        "user",
        "enabled",
        "employee",
        "license_expiry"
    ],
    "ADM Meeting Booking": [
        "name",
        "docstatus",
        "owner",
        "creation",
        "modified",
        "title",
        "room",
        "organizer",
        "starts_at",
        "ends_at",
        "attendee_count",
        "requirements",
        "meeting_link",
        "status"
    ],
    "ADM Meeting Room": [
        "name",
        "docstatus",
        "owner",
        "creation",
        "modified",
        "room_name",
        "company",
        "branch",
        "floor",
        "capacity",
        "enabled",
        "buffer_minutes",
        "equipment"
    ],
    "ADM Trip": [
        "name",
        "docstatus",
        "owner",
        "creation",
        "modified",
        "purpose",
        "company",
        "requested_by",
        "department",
        "cost_center",
        "origin",
        "destination",
        "planned_start",
        "planned_end",
        "passenger_count",
        "vehicle",
        "driver",
        "status",
        "gap_reason",
        "start_odometer",
        "end_odometer",
        "distance_km",
        "actual_start",
        "actual_end",
        "duration_minutes",
        "approved_by"
    ],
    "ADM Vehicle": [
        "name",
        "docstatus",
        "owner",
        "creation",
        "modified",
        "plate_number",
        "company",
        "branch",
        "make_model",
        "ownership",
        "status",
        "last_odometer",
        "initial_odometer",
        "license_expiry",
        "insurance_expiry",
        "documents"
    ]
}


def snapshot():
    admin_only()
    result = {'site': frappe.local.site, 'app_versions': {}, 'legacy': {}, 'workspace': {}, 'permissions': {}}
    for app in ('frappe', 'erpnext', 'eup_administration'):
        module = __import__(app)
        result['app_versions'][app] = getattr(module, '__version__', 'unknown')
    for doctype, fields in LEGACY_FIELDS.items():
        records = frappe.get_all(doctype, fields=fields, order_by='name asc', limit_page_length=0)
        encoded = json.dumps(records, sort_keys=True, default=str, ensure_ascii=False).encode('utf-8')
        result['legacy'][doctype] = {'count': len(records), 'sha256': hashlib.sha256(encoded).hexdigest()}
        result['permissions'][doctype] = frappe.get_all('DocPerm', filters={'parent':doctype},
            fields=['role','permlevel','read','write','create','delete','submit','cancel','report','export'],
            order_by='idx asc',limit_page_length=0)
        result['permissions'][doctype + ' custom'] = frappe.get_all('Custom DocPerm', filters={'parent':doctype},
            fields=['role','permlevel','read','write','create','delete','submit','cancel','report','export'],
            order_by='idx asc',limit_page_length=0)
    for name in ('EuP Administration','EuP Administration v2'):
        if frappe.db.exists('Workspace',name):
            doc = frappe.get_doc('Workspace',name)
            result['workspace'][name] = {'standard':doc.get('standard'), 'public':doc.public,
                'content_sha256':hashlib.sha256((doc.content or '').encode('utf-8')).hexdigest(),
                'shortcuts':[{'label':r.label,'type':r.type,'link_to':r.link_to} for r in doc.shortcuts]}
    return result
