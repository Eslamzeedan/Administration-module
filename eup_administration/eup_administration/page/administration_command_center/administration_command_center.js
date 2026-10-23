frappe.pages["administration-command-center"].on_page_load = function(wrapper) {
    const page = frappe.ui.make_app_page({parent: wrapper, title: __("Administration Command Center"), single_column: true});
    const ui = eup_administration.ui;
    const company = page.add_field({fieldname:"company",label:__("Company"),fieldtype:"Link",options:"Company"});
    const from = page.add_field({fieldname:"from_date",label:__("From"),fieldtype:"Date",default:frappe.datetime.add_days(frappe.datetime.get_today(),-6)});
    const to = page.add_field({fieldname:"to_date",label:__("To"),fieldtype:"Date",default:frappe.datetime.get_today()});
    const root = $('<main class="adm-shell"></main>').appendTo(page.main);
    ui.hero(root, __("A clear view of your operations"), __("Requests, approvals and attention points, together in one workspace."));
    const tools = $('<div class="adm-toolbar"></div>').appendTo(root);
    ui.action(tools, __("Operations overview"), () => load());
    ui.action(tools, __("Approval inbox"), () => loadInbox());
    ui.action(tools, __("Workflow Designer"), () => ui.open("ADM Workflow Policy"));
    ui.action(tools, __("Employee self-service"), () => { window.location.href = "/administration_self_service"; });
    const content = $("<div></div>").appendTo(root);
    let context, generation = 0;
    const contextReady = ui.request("eup_administration.v4.dashboard.context").then(async info => {
        context = info;
        if (info.company) {
            await company.set_value(info.company);
            if (!info.can_choose_company) {
                company.get_query = () => ({filters:{name:info.company}});
            }
        }
        return info;
    });
    async function ready() {
        await contextReady;
        if (context.requires_employee) {
            ui.state(content, __("Connect your employee profile"),
                __("Your account needs an active employee linked to this company. Ask your administrator to complete the employee link, then refresh."), "empty");
            return false;
        }
        if (!company.get_value()) {
            ui.state(content, __("Choose a company to get started"),
                __("Select a company above, then choose Refresh. Only records you are allowed to access will appear."));
            return false;
        }
        return true;
    }
    function render(data) {
        content.empty();
        const metrics = $('<div class="adm-metrics"></div>').appendTo(content);
        const total = Object.values(data.visible_counts || {}).reduce((sum,n) => sum+Number(n),0);
        ui.metric(metrics, __("Visible operations"), total, data.from_date + " — " + data.to_date);
        ui.metric(metrics, __("Overdue workflows"), data.overdue, __("Needs a closer look"));
        ui.metric(metrics, __("Attention points"), data.contract_notices.length+data.preventive_due.length, __("Contracts and preventive plans"));
        const rating = data.satisfaction.average;
        ui.metric(metrics, __("Service rating"), rating,
            rating === null ? __("No ratings yet") : __("{0} responses · out of 5",[data.satisfaction.responses]));
        const grid = $('<div class="adm-columns"></div>').appendTo(content);
        const left = $("<div></div>").appendTo(grid), right = $("<div></div>").appendTo(grid);
        const operations = ui.section(left, __("Your operations"), __("Open a category to browse permitted records."));
        const counts = $('<div class="adm-metrics" style="margin-top:16px"></div>').appendTo(operations);
        for (const [dt,count] of Object.entries(data.visible_counts || {})) ui.metric(counts, __(dt.replace("ADM ","")), count,
            __("Open list"), () => frappe.set_route("List",dt,{company:company.get_value()}));
        const records = ui.section(left, __("Recent activity"), __("Requests in the selected period"));
        if (!(data.records || []).length) ui.state(records, __("A fresh start"), __("There are no visible operations for this period. Try a different date range or create a request."));
        for (const row of data.records || []) ui.row(records,row.subject,row.workflow_state||__("Draft"),
            __(row.doctype.replace("ADM ",""))+" · "+row.name,() => ui.open(row.doctype,row.name));
        const attention = ui.section(right, __("Attention required"), __("Review upcoming notices and overdue work."));
        const notices = [...data.contract_notices.map(r=>({...r,dt:"ADM Contract Register"})),
            ...data.preventive_due.map(r=>({...r,dt:"ADM Preventive Plan"}))];
        if (!notices.length) ui.state(attention, __("You're all caught up"), __("No contract or preventive notices need attention."));
        for (const row of notices) ui.row(attention,row.subject,__("Review"),__(row.dt.replace("ADM ","")),()=>ui.open(row.dt,row.name));
        const priorities = ui.section(right, __("Priority mix")); ui.bars(priorities,data.priorities);
        const facilities = ui.section(right, __("Facilities")); ui.bars(facilities,data.facility_categories);
        const incidents = ui.section(right, __("Incident categories")); ui.bars(incidents,data.incident_categories);
        $('<p class="adm-note"></p>').text(__("Incidents without a root cause: {0}",[data.unresolved_root_causes])).appendTo(incidents);
        $('<p class="adm-note"></p>').text(__("Based on records visible to your account. Administrative operations only.")).appendTo(content);
    }
    async function load(method="command_center") {
        const ticket = ++generation;
        ui.state(content,__("Loading your workspace"),__("Bringing your latest visible records together."),"loading");
        try {
            if (!await ready() || ticket !== generation) return;
            const args = method === "weekly_report" ? {company:company.get_value(),week_ending:to.get_value()} :
                {company:company.get_value(),from_date:from.get_value(),to_date:to.get_value()};
            const data = await ui.request("eup_administration.v4.dashboard."+method,args);
            if (ticket !== generation) return;
            render(data);
        } catch (error) {
            if (ticket === generation) ui.state(content,__("This view couldn't be loaded"),ui.message(error),"error",()=>load(method));
        }
    }
    async function loadInbox() {
        const ticket = ++generation;
        ui.state(content,__("Loading approvals"),__("Checking the requests assigned to you."),"loading");
        try {
            const rows = await ui.request("eup_administration.v4.dashboard.inbox");
            if (ticket !== generation) return;
            content.empty();
            const panel = ui.section(content,__("Your approval inbox"),__("Each decision is checked against your role, company and the latest workflow revision."));
            if (!rows.length) ui.state(panel,__("No approvals waiting"),__("Requests needing your decision will appear here."));
            for (const row of rows) {
                const card = $('<article class="adm-portal-card" style="margin-top:12px"></article>').appendTo(panel);
                $("<h3></h3>").text(row.subject).appendTo(card);
                $("<p class='adm-note'></p>").text(row.action+" · "+row.name).appendTo(card);
                const actions = $('<div class="adm-toolbar"></div>').appendTo(card);
                ui.action(actions,__("Open request"),()=>ui.open(row.doctype,row.name));
                for (const decision of ["Approved","Rejected"]) ui.action(actions,__(decision),()=>frappe.prompt(
                    [{fieldname:"comment",fieldtype:"Small Text",label:__("Reason"),reqd:decision==="Rejected"}],
                    async values => {
                        try {
                            await ui.request("eup_administration.v4.workflow.decide",{
                                doctype:row.doctype,name:row.name,decision,expected_revision:row.revision,comment:values.comment},"POST");
                            await loadInbox();
                        } catch (error) { frappe.msgprint(ui.message(error)); }
                    }),decision==="Approved");
            }
        } catch (error) {
            if (ticket === generation) ui.state(content,__("Approvals couldn't be loaded"),ui.message(error),"error",loadInbox);
        }
    }
    page.set_primary_action(__("Refresh"),async () => { await load(); });
    page.add_menu_item(__("Weekly report"),async () => { await load("weekly_report"); });
    page.add_menu_item(__("Workflow Designer"),()=>ui.open("ADM Workflow Policy"));
    page.add_menu_item(__("SLA escalations"),()=>ui.open("ADM SLA Escalation"));
    page.add_menu_item(__("Approval inbox"),loadInbox);
    page.add_menu_item(__("Dispatch suggestions"),()=>frappe.prompt([
        {fieldname:"start",label:__("Start"),fieldtype:"Datetime",reqd:1},
        {fieldname:"end",label:__("End"),fieldtype:"Datetime",reqd:1},
        {fieldname:"passengers",label:__("Passengers"),fieldtype:"Int",default:1,reqd:1}
    ],async values => {
        try {
            const data = await ui.request("eup_administration.v4.dashboard.dispatch_suggestions",{company:company.get_value(),...values});
            const box = $("<div></div>");
            if (!data.suggestions.length) ui.state(box,__("No suitable vehicle"),__("Review capacity, documents, checklists and existing assignments."));
            for (const row of data.suggestions) ui.row(box,row.plate,__("Available"),
                __("Spare seats: {0} · Odometer: {1}",[row.spare_seats,ui.number(row.odometer)]),()=>ui.open("ADM Vehicle",row.vehicle));
            ui.dialog(__("Dispatch suggestions"),box);
        } catch (error) { frappe.msgprint(ui.message(error)); }
    }));
    page.add_menu_item(__("Consumption estimate"),()=>frappe.prompt([
        {fieldname:"item",label:__("Administrative item"),fieldtype:"Link",options:"ADM Consumable Item",reqd:1}
    ],async values => {
        try {
            const data = await ui.request("eup_administration.v4.dashboard.consumption_forecast",{company:company.get_value(),...values});
            // The full explainable estimate remains available without changing its calculation.
            ui.dialog(__("Historical mean estimate"),$("<pre></pre>").text(JSON.stringify(data,null,2)));
        } catch (error) { frappe.msgprint(ui.message(error)); }
    }));
    load();
};
