frappe.query_reports["ADM Department Consumption"] = {
    filters: [
    {
        "fieldname": "company",
        "fieldtype": "Link",
        "options": "Company",
        "label": "Company",
        "reqd": 1
    },
    {
        "fieldname": "start_date",
        "fieldtype": "Date",
        "label": "From Date",
        "reqd": 1
    },
    {
        "fieldname": "end_date",
        "fieldtype": "Date",
        "label": "To Date",
        "reqd": 1
    }
]
};
