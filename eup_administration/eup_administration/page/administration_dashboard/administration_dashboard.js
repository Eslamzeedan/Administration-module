frappe.pages["administration-dashboard"].on_page_load = function(wrapper) {
    const page = frappe.ui.make_app_page({parent:wrapper,title:__("Fleet & meetings"),single_column:true});
    const ui = eup_administration.ui;
    const from = page.add_field({fieldname:"from_date",label:__("From"),fieldtype:"Date",default:frappe.datetime.add_days(frappe.datetime.get_today(),-30)});
    const to = page.add_field({fieldname:"to_date",label:__("To"),fieldtype:"Date",default:frappe.datetime.get_today()});
    const company = page.add_field({fieldname:"company",label:__("Company"),fieldtype:"Link",options:"Company"});
    const root = $('<main class="adm-shell"></main>').appendTo(page.main);
    ui.hero(root,__("Keep everyday operations moving"),__("Follow vehicle activity, meeting use and upcoming renewals in one clear view."));
    const tools = $('<div class="adm-toolbar"></div>').appendTo(root);
    ui.action(tools,__("Trips"),()=>ui.open("ADM Trip"));
    ui.action(tools,__("Meeting bookings"),()=>ui.open("ADM Meeting Booking"));
    ui.action(tools,__("Administration home"),()=>frappe.set_route("administration-v3"));
    const body = $("<div></div>").appendTo(root);
    let generation = 0;
    async function load() {
        const ticket = ++generation;
        ui.state(body,__("Loading your overview"),__("Preparing the selected period."),"loading");
        try {
            const data = await ui.request("eup_administration.reporting.dashboard",{
                from_date:from.get_value(),to_date:to.get_value(),company:company.get_value()
            });
            if (ticket !== generation) return;
            body.empty();
            const metrics = $('<div class="adm-metrics"></div>').appendTo(body);
            ui.metric(metrics,__("Completed distance"),data.distance_km,__("Kilometres"));
            ui.metric(metrics,__("Meetings"),data.meeting_count,__("Excluding cancelled bookings"));
            ui.metric(metrics,__("Booked hours"),data.booked_hours,__("Within the selected period"));
            ui.metric(metrics,__("Renewals & services due"),data.renewals_due,__("Review upcoming requirements"));
            const columns = $('<div class="adm-columns"></div>').appendTo(body);
            const trip = ui.section(columns,__("Trip activity")); ui.bars(trip,data.trip_status);
            const costs = ui.section(columns,__("Recorded operating costs"),__("Fuel, trip expenses and completed maintenance."));
            if (!Object.keys(data.costs_by_currency).length) ui.state(costs,__("No operating costs recorded"),__("Costs will appear when permitted records are completed."));
            for (const [currency,amount] of Object.entries(data.costs_by_currency)) {
                const row = $('<div class="adm-bar-row"><div><span></span><strong></strong></div></div>');
                row.find("span").text(currency); row.find("strong").text(ui.number(amount)); row.appendTo(costs);
            }
            const reports = ui.section(body,__("Reports"),__("Explore the details for this period."));
            const links = $('<div class="adm-toolbar" style="margin-top:16px"></div>').appendTo(reports);
            for (const name of ["ADM Trip Register","ADM Fleet Costs","ADM Meeting Utilization","ADM Renewals and Service"])
                ui.action(links,__(name.replace("ADM ","")),()=>frappe.set_route("query-report",name,{
                    from_date:from.get_value(),to_date:to.get_value(),company:company.get_value()
                }));
            $('<p class="adm-note"></p>').text(__("Only permitted administrative records are included. Operating costs do not create accounting entries.")).appendTo(body);
        } catch (error) {
            if (ticket === generation) ui.state(body,__("Overview couldn't be loaded"),ui.message(error),"error",load);
        }
    }
    page.set_primary_action(__("Refresh"),load);
    load();
};
