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
