frappe.pages['administration-dashboard'].on_page_load = function(wrapper) {
    const page = frappe.ui.make_app_page({parent: wrapper, title: __('Administration Dashboard'), single_column: true});
    const from = page.add_field({fieldname: 'from_date', label: __('From'), fieldtype: 'Date', default: frappe.datetime.add_days(frappe.datetime.get_today(), -30)});
    const to = page.add_field({fieldname: 'to_date', label: __('To'), fieldtype: 'Date', default: frappe.datetime.get_today()});
    const company = page.add_field({fieldname: 'company', label: __('Company'), fieldtype: 'Link', options: 'Company'});
    const body = $('<div class="p-4"></div>').appendTo(page.main);
    const load = () => frappe.call({method: 'eup_administration.reporting.dashboard', args: {from_date: from.get_value(), to_date: to.get_value(), company: company.get_value()}, freeze: true}).then(r => {
        const d = r.message; body.empty(); $('<p class="text-muted"></p>').text(__(d.scope)).appendTo(body);
        const cards = $('<div class="row"></div>').appendTo(body);
        const card = (label, value) => { const el = $('<div class="col-sm-6 col-lg-3 mb-3"><div class="border rounded p-3"><div class="text-muted"></div><strong class="h3"></strong></div></div>'); el.find('.text-muted').text(__(label)); el.find('strong').text(value); cards.append(el); };
        card('Completed Distance (km)', flt(d.distance_km, 2)); card('Meetings', d.meeting_count); card('Booked Hours', d.booked_hours); card('Renewals / Services Due', d.renewals_due);
        $('<h4></h4>').text(__('Trip Status')).appendTo(body);
        for (const [status, count] of Object.entries(d.trip_status)) $('<p></p>').text(__(status) + ': ' + count).appendTo(body);
        $('<h4></h4>').text(__('Operational Costs')).appendTo(body);
        for (const [currency, amount] of Object.entries(d.costs_by_currency)) $('<p></p>').text(currency + ': ' + flt(amount, 2)).appendTo(body);
        $('<p class="text-muted"></p>').text(__(d.cost_scope)).appendTo(body);
        const links = $('<div class="d-flex flex-wrap" style="gap:12px"></div>').appendTo(body);
        for (const report of ['ADM Trip Register', 'ADM Fleet Costs', 'ADM Meeting Utilization', 'ADM Renewals and Service']) $('<button class="btn btn-default"></button>').text(__(report)).on('click', () => frappe.set_route('query-report', report, {from_date: from.get_value(), to_date: to.get_value(), company: company.get_value()})).appendTo(links);
    });
    page.set_primary_action(__('Refresh'), load); load();
};
