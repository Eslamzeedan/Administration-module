frappe.pages["administration-v3"].on_page_load = function(wrapper) {
    const page = frappe.ui.make_app_page({parent:wrapper,title:__("EuP Administration"),single_column:true});
    const ui = eup_administration.ui;
    const root = $('<main class="adm-shell"></main>').appendTo(page.main);
    ui.hero(root,__("Your administration workspace"),__("A simpler way to follow requests, review approvals and keep everyday operations moving."));
    const shortcuts = $('<div class="adm-toolbar"></div>').appendTo(root);
    ui.action(shortcuts,__("New service request"),()=>frappe.new_doc("ADM General Service Request"),true);
    ui.action(shortcuts,__("Command center"),()=>frappe.set_route("administration-command-center"));
    ui.action(shortcuts,__("Meeting bookings"),()=>ui.open("ADM Meeting Booking"));
    ui.action(shortcuts,__("Fleet overview"),()=>frappe.set_route("administration-dashboard"));
    const metrics = $('<div class="adm-metrics"></div>').appendTo(root);
    const columns = $('<div class="adm-columns"></div>').appendTo(root);
    const left = $("<div></div>").appendTo(columns), right = $("<div></div>").appendTo(columns);
    const requests = ui.section(left,__("My requests"),__("Current status from the administration request registry."));
    const approvals = ui.section(right,__("My approvals"),__("Decisions currently assigned to you."));
    const mix = ui.section(right,__("Service mix"),__("Visible requests by service."));
    let generation = 0;
    async function load() {
        const ticket = ++generation;
        ui.state(requests,__("Loading requests"),"","loading");
        ui.state(approvals,__("Loading approvals"),"","loading");
        ui.state(mix,__("Loading overview"),"","loading");
        const jobs = [
            ui.request("eup_administration.v3.registry.my_requests"),
            ui.request("eup_administration.v3.approval.pending_for_me"),
            ui.request("eup_administration.v3.reporting.dashboard")
        ];
        const [req,appr,overview] = await Promise.allSettled(jobs);
        if (ticket !== generation) return;
        requests.empty(); approvals.empty(); mix.empty(); metrics.empty();
        if (req.status === "fulfilled") {
            if (!req.value.length) ui.state(requests,__("No requests yet"),__("Start with a new service request, or book a meeting room."));
            for (const row of req.value) ui.row(requests,row.summary||row.reference_name,row.source_status,
                __(row.service_family)+" · "+row.reference_name,()=>ui.open(row.reference_doctype,row.reference_name));
        } else ui.state(requests,__("Requests couldn't be loaded"),ui.message(req.reason),"error",load);
        if (appr.status === "fulfilled") {
            if (!appr.value.length) ui.state(approvals,__("You're all caught up"),__("There are no approvals waiting for you."));
            for (const row of appr.value) {
                const item = $('<div style="padding:12px 0;border-bottom:1px solid var(--adm-line)"></div>').appendTo(approvals);
                $("<strong></strong>").text(row.request).appendTo(item);
                $("<p class='adm-note'></p>").text(row.department||__("General service")).appendTo(item);
                const actions = $('<div class="adm-toolbar"></div>').appendTo(item);
                ui.action(actions,__("Open"),()=>ui.open("ADM General Service Request",row.request));
                for (const decision of ["Approved","Rejected"]) ui.action(actions,__(decision),()=>frappe.prompt(
                    [{fieldname:"comment",fieldtype:"Small Text",label:__("Decision note"),reqd:decision==="Rejected"}],
                    async values => {
                        try {
                            await ui.request("eup_administration.v3.approval.decide",{case_id:row.case,decision,comment:values.comment},"POST");
                            await load();
                        } catch (error) { frappe.msgprint(ui.message(error)); }
                    }),decision==="Approved");
            }
        } else ui.state(approvals,__("Approvals couldn't be loaded"),ui.message(appr.reason),"error",load);
        if (overview.status === "fulfilled") {
            const data = overview.value;
            ui.metric(metrics,__("Visible requests"),data.total,__("Across your permitted services"));
            ui.metric(metrics,__("Overdue"),data.overdue,__("Active requests past their due time"));
            ui.metric(metrics,__("Waiting for you"),appr.status==="fulfilled"?appr.value.length:0,__("Approval decisions"));
            ui.bars(mix,data.by_service);
        } else ui.state(mix,__("Overview couldn't be loaded"),ui.message(overview.reason),"error",load);
    }
    page.set_primary_action(__("Refresh"),load);
    page.add_inner_button(__("New service request"),()=>frappe.new_doc("ADM General Service Request"));
    load();
};
