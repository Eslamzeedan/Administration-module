app_name = "eup_administration"
app_title = "EuP Administration"
app_publisher = "EuP Egypt"
app_description = "Vehicle trips and meeting room bookings"
app_email = "it@eupegypt.com"
app_license = "MIT"
required_apps = ["erpnext"]
after_install = "eup_administration.install.setup"
after_migrate = "eup_administration.install.setup"
permission_query_conditions = {
    "ADM Trip": "eup_administration.permissions.trip_query",
    "ADM Meeting Booking": "eup_administration.permissions.booking_query",
}
has_permission = {
    "ADM Trip": "eup_administration.permissions.trip_permission",
    "ADM Meeting Booking": "eup_administration.permissions.booking_permission",
}

before_install = "eup_administration.install.ensure_roles"
permission_query_conditions.update({
    "ADM Driver": "eup_administration.permissions.driver_query",
    "ADM Fuel Log": "eup_administration.permissions.fuel_query",
    "ADM Trip Expense": "eup_administration.permissions.expense_query",
})
has_permission.update({
    "ADM Driver": "eup_administration.permissions.driver_permission",
    "ADM Fuel Log": "eup_administration.permissions.ledger_permission",
    "ADM Trip Expense": "eup_administration.permissions.ledger_permission",
})


# Administration Service Desk / Runner (Careem) MVP
permission_query_conditions["ADM Service Request"] = "eup_administration.runner.request_query"
has_permission["ADM Service Request"] = "eup_administration.runner.request_permission"

# Administration consumables: operational store separated from ERPNext stock / assets.
permission_query_conditions["ADM Supply Request"] = "eup_administration.consumables.supply_request_query"
has_permission["ADM Supply Request"] = "eup_administration.consumables.supply_request_permission"
permission_query_conditions["ADM Consumable Transaction"] = "eup_administration.consumables.transaction_query"
has_permission["ADM Consumable Transaction"] = "eup_administration.consumables.transaction_permission"
permission_query_conditions["ADM Admin Custody"] = "eup_administration.consumables.custody_query"
has_permission["ADM Admin Custody"] = "eup_administration.consumables.custody_permission"


# V3 additive integration: old approval/start/end POST methods remain authoritative.
doc_events = {
    dt: {
        "after_insert": "eup_administration.v3.registry.sync_document",
        "on_update": "eup_administration.v3.registry.sync_document",
    }
    for dt in (
        "ADM Trip", "ADM Service Request", "ADM Supply Request",
        "ADM Meeting Booking", "ADM Admin Custody", "ADM General Service Request"
    )
}
permission_query_conditions["ADM General Service Request"] = "eup_administration.v3.security.general_query"
has_permission["ADM General Service Request"] = "eup_administration.v3.security.general_permission"
permission_query_conditions["ADM Request Registry"] = "eup_administration.v3.security.registry_query"
has_permission["ADM Request Registry"] = "eup_administration.v3.security.registry_permission"
scheduler_events = {
    "hourly": ["eup_administration.v3.notifications.process_outbox"],
    "daily": ["eup_administration.v3.notifications.daily_sla_digest"],
}

# V4: additive administrative-only operations. Legacy API hooks remain unchanged.
permission_query_conditions["ADM Facility Ticket"] = "eup_administration.v4.security.adm_facility_ticket_query"
has_permission["ADM Facility Ticket"] = "eup_administration.v4.security.operation_permission"
permission_query_conditions["ADM Driver Checklist"] = "eup_administration.v4.security.adm_driver_checklist_query"
has_permission["ADM Driver Checklist"] = "eup_administration.v4.security.operation_permission"
permission_query_conditions["ADM Preventive Plan"] = "eup_administration.v4.security.adm_preventive_plan_query"
has_permission["ADM Preventive Plan"] = "eup_administration.v4.security.operation_permission"
permission_query_conditions["ADM Parcel"] = "eup_administration.v4.security.adm_parcel_query"
has_permission["ADM Parcel"] = "eup_administration.v4.security.operation_permission"
permission_query_conditions["ADM Equipment Booking"] = "eup_administration.v4.security.adm_equipment_booking_query"
has_permission["ADM Equipment Booking"] = "eup_administration.v4.security.operation_permission"
permission_query_conditions["ADM Contract Register"] = "eup_administration.v4.security.adm_contract_register_query"
has_permission["ADM Contract Register"] = "eup_administration.v4.security.operation_permission"
permission_query_conditions["ADM Operational Incident"] = "eup_administration.v4.security.adm_operational_incident_query"
has_permission["ADM Operational Incident"] = "eup_administration.v4.security.operation_permission"
permission_query_conditions["ADM Recurring Task"] = "eup_administration.v4.security.adm_recurring_task_query"
has_permission["ADM Recurring Task"] = "eup_administration.v4.security.operation_permission"
permission_query_conditions["ADM Task Occurrence"] = "eup_administration.v4.security.adm_task_occurrence_query"
has_permission["ADM Task Occurrence"] = "eup_administration.v4.security.operation_permission"
permission_query_conditions["ADM Workflow Policy"] = "eup_administration.v4.security.master_query"
has_permission["ADM Workflow Policy"] = "eup_administration.v4.security.master_permission"
permission_query_conditions["ADM Shared Equipment"] = "eup_administration.v4.security.master_query"
has_permission["ADM Shared Equipment"] = "eup_administration.v4.security.master_permission"
permission_query_conditions["ADM SLA Escalation"] = "eup_administration.v4.security.escalation_query"
has_permission["ADM SLA Escalation"] = "eup_administration.v4.security.escalation_permission"
scheduler_events["hourly"].append("eup_administration.v4.jobs.escalate")
scheduler_events["daily"].append("eup_administration.v4.operations.recurring")
permission_query_conditions["ADM Workflow Run"] = "eup_administration.v4.security.master_query"
has_permission["ADM Workflow Run"] = "eup_administration.v4.security.master_permission"
permission_query_conditions["ADM Workflow Audit"] = "eup_administration.v4.security.master_query"
has_permission["ADM Workflow Audit"] = "eup_administration.v4.security.master_permission"
permission_query_conditions["ADM Operation Feedback"] = "eup_administration.v4.security.master_query"
has_permission["ADM Operation Feedback"] = "eup_administration.v4.security.master_permission"

# Content revisions keep long-lived browser caches consistent with form scripts.
from hashlib import sha256 as _sha256
from pathlib import Path as _Path

_ui_public = _Path(__file__).resolve().parent / "public"
_ui_js_revision = _sha256((_ui_public / "js/administration_ui.js").read_bytes()).hexdigest()[:16]
_ui_css_revision = _sha256((_ui_public / "css/administration.css").read_bytes()).hexdigest()[:16]

# Shared assets are visually scoped to administration routes.
app_include_js = [f"/assets/eup_administration/js/administration_ui.js?v={_ui_js_revision}"]
app_include_css = [f"/assets/eup_administration/css/administration.css?v={_ui_css_revision}"]
web_include_js = list(app_include_js)
web_include_css = list(app_include_css)
