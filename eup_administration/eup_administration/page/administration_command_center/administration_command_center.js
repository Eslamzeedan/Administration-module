frappe.pages["administration-command-center"].on_page_load = function(wrapper) {
    const page = frappe.ui.make_app_page({parent: wrapper, title: __("Administration Command Center"), single_column: true});
    const company = page.add_field({fieldname: "company", label: __("Company"), fieldtype: "Link", options: "Company", reqd: 1});
    const body = $('<div class="p-4"></div>').appendTo(page.main);
    const esc = frappe.utils.escape_html;
    const api = "eup_administration.v4.";
    function render(data) {
        body.empty();
        $("<p>").text(__("Administrative operations only · visible records · {0} to {1}", [data.from_date, data.to_date])).appendTo(body);
        const cards = $('<div class="row"></div>').appendTo(body);
        for (const [dt, count] of Object.entries(data.visible_counts)) {
            const card = $('<div class="col-md-4 mb-3"><button class="btn btn-default w-100"></button></div>').appendTo(cards);
            card.find("button").text(__(dt.replace("ADM ", "")) + " · " + count).on("click", () => frappe.set_route("List", dt, {company: company.get_value()}));
        }
        $("<h4>").text(__("Attention required")).appendTo(body);
        $("<p>").text(__("Overdue visible workflows: {0}", [data.overdue])).appendTo(body);
        for (const row of [...data.contract_notices.map(x => ({...x, dt: "ADM Contract Register"})),
                          ...data.preventive_due.map(x => ({...x, dt: "ADM Preventive Plan"}))]) {
            $('<button class="btn btn-link d-block"></button>').text(row.subject).appendTo(body).on("click", () => frappe.set_route("Form", row.dt, row.name));
        }
        $("<h4>").text(__("Service and incident analysis")).appendTo(body);
        $("<pre>").text(JSON.stringify({priorities: data.priorities, facilities: data.facility_categories,
            incidents: data.incident_categories, missing_root_causes: data.unresolved_root_causes, satisfaction: data.satisfaction}, null, 2)).appendTo(body);
        $("<h4>").text(__("My visible operations")).appendTo(body);
        for (const row of data.records) $('<button class="btn btn-link d-block"></button>').text(
            row.subject + " · " + (row.workflow_state || __("Draft"))
        ).appendTo(body).on("click", () => frappe.set_route("Form", row.doctype, row.name));
    }
    function load(method="command_center") {
        if (!company.get_value()) return frappe.msgprint(__("Select a company."));
        return frappe.call({method: api + "dashboard." + method, args: {company: company.get_value()}}).then(r => render(r.message));
    }
    page.set_primary_action(__("Refresh"), () => load());
    page.add_menu_item(__("Weekly report"), () => load("weekly_report"));
    page.add_menu_item(__("Workflow Designer"), () => frappe.set_route("List", "ADM Workflow Policy"));
    page.add_menu_item(__("SLA escalations"), () => frappe.set_route("List", "ADM SLA Escalation"));
    page.add_menu_item(__("Approval inbox"), () => frappe.call({method: api + "dashboard.inbox"}).then(r => {
        body.empty();
        $("<h4>").text(__("My approvals")).appendTo(body);
        for (const row of r.message || []) {
            const panel = $('<div class="border rounded p-3 mb-2"></div>').appendTo(body);
            $("<p>").text(row.subject + " · " + row.action).appendTo(panel);
            for (const decision of ["Approved", "Rejected"])
                $('<button class="btn btn-default mr-2"></button>').text(__(decision)).appendTo(panel).on("click", () => {
                    frappe.prompt([{fieldname: "comment", fieldtype: "Small Text", label: __("Reason"), reqd: decision === "Rejected"}],
                        values => frappe.call({method: api + "workflow.decide", type: "POST", args: {
                            doctype: row.doctype, name: row.name, decision, expected_revision: row.revision, comment: values.comment
                        }}).then(() => panel.remove()));
                });
        }
    }));
    page.add_menu_item(__("Dispatch suggestions"), () => frappe.prompt([
        {fieldname: "start", label: __("Start"), fieldtype: "Datetime", reqd: 1},
        {fieldname: "end", label: __("End"), fieldtype: "Datetime", reqd: 1},
        {fieldname: "passengers", label: __("Passengers"), fieldtype: "Int", default: 1, reqd: 1}
    ], values => frappe.call({method: api + "dashboard.dispatch_suggestions",
        args: {company: company.get_value(), ...values}}).then(r => frappe.msgprint({
            title: __("Advisory dispatch"), message: "<pre>" + esc(JSON.stringify(r.message, null, 2)) + "</pre>"
        }))));
    page.add_menu_item(__("Consumption estimate"), () => frappe.prompt([
        {fieldname: "item", label: __("Administrative item"), fieldtype: "Link", options: "ADM Consumable Item", reqd: 1}
    ], values => frappe.call({method: api + "dashboard.consumption_forecast",
        args: {company: company.get_value(), ...values}}).then(r => frappe.msgprint({
            title: __("Historical mean estimate"), message: "<pre>" + esc(JSON.stringify(r.message, null, 2)) + "</pre>"
        }))));
};
