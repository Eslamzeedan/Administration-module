frappe.query_reports["ADM Low Stock"] = {
    filters: [
    {
        "fieldname": "company",
        "fieldtype": "Link",
        "options": "Company",
        "label": "Company",
        "reqd": 1
    }
]
};
