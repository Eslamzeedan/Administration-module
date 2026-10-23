/* Shared administrative UI only. Native promises support Frappe v16 action buttons. */
frappe.provide("eup_administration.ui");
(function(ui) {
    "use strict";
    ui.call = async options => await frappe.call(options);
    ui.request = async (method, args = {}, type = "GET") => {
        const response = await ui.call({method, args, type});
        if (!response) throw new Error(__("The server did not return a response. Please try again."));
        if (response.exc) throw response;
        return response.message;
    };
    ui.message = error => {
        try {
            const response = error.responseJSON || error;
            const messages = JSON.parse(response._server_messages || "[]");
            if (messages.length) {
                const item = JSON.parse(messages[0]);
                return String(item.message || "").replace(/<[^>]*>/g, "");
            }
        } catch (_) { /* Fall through to a short, non-technical message. */ }
        return error && error.message && !/TypeError|Traceback/.test(error.message)
            ? error.message : __("We couldn't load this view. Check your access and try again.");
    };
    ui.intro = (frm, message, color = "blue") => {
        // v16 appends introductions. Replace only this app's own banner, keeping other warnings.
        const container = frm.layout && frm.layout.message;
        if (container) container.children(".adm-intro").remove();
        if (!message) return;
        frm.set_intro(message, color);
        if (container) container.children(".form-message").last().addClass("adm-intro");
    };
    ui.state = (root, title, description, kind = "empty", retry) => {
        root.empty();
        const box = $('<div class="adm-state"><span class="adm-state-mark" aria-hidden="true"></span><h3></h3><p></p></div>');
        box.addClass("adm-state-" + (["empty","loading","error","success"].includes(kind) ? kind : "empty"));
        box.attr({role: kind === "error" ? "alert" : "status", "aria-live": "polite"});
        box.find("h3").text(title);
        box.find("p").text(description || "");
        if (retry) $('<button type="button" class="btn btn-default adm-retry"></button>')
            .text(__("Try again")).on("click", retry).appendTo(box);
        return box.appendTo(root);
    };
    ui.hero = (root, title, description, tag = __("ADMINISTRATION")) => {
        const hero = $('<section class="adm-hero"><div><span class="adm-eyebrow"></span><h2></h2><p></p></div><span class="adm-hero-orbit" aria-hidden="true"></span></section>');
        hero.find(".adm-eyebrow").text(tag); hero.find("h2").text(title);
        hero.find("p").text(description); return hero.appendTo(root);
    };
    ui.section = (root, title, description) => {
        const panel = $('<section class="adm-panel"><div class="adm-section-heading"><h3></h3><p></p></div><div class="adm-panel-body"></div></section>');
        panel.find("h3").text(title); panel.find(".adm-section-heading p").text(description || "");
        panel.appendTo(root); return panel.find(".adm-panel-body");
    };
    ui.number = value => new Intl.NumberFormat(document.documentElement.lang || "en",
        {maximumFractionDigits: 1}).format(Number(value) || 0);
    ui.metric = (root, label, value, hint, action) => {
        const card = $(action ? '<button type="button" class="adm-metric"></button>' : '<article class="adm-metric"></article>');
        $('<span class="adm-metric-label"></span>').text(label).appendTo(card);
        $('<strong class="adm-metric-value"></strong>').text(value === null ? "—" : ui.number(value)).appendTo(card);
        $('<span class="adm-metric-hint"></span>').text(hint || __("Visible to your account")).appendTo(card);
        if (action) { card.attr("aria-label", label + ": " + value); card.on("click", action); }
        return card.appendTo(root);
    };
    ui.badge = (state = __("Draft")) => {
        const positive = /^(Completed|Closed|Done|Approved|Fulfilled|Returned|Present)$/i.test(state);
        const negative = /^(Rejected|Critical)$/i.test(state);
        const quiet = /^(Cancelled|Released|Draft)$/i.test(state);
        return $('<span class="adm-badge"></span>').addClass(positive ? "adm-badge-success" :
            negative ? "adm-badge-danger" : quiet ? "adm-badge-muted" : "adm-badge-pending").text(__(state));
    };
    ui.row = (root, title, state, detail, open) => {
        const row = $('<button type="button" class="adm-request-row"><span class="adm-row-copy"><strong></strong><small></small></span><span class="adm-row-state"></span><span class="adm-row-arrow" aria-hidden="true">↗</span></button>');
        row.find("strong").text(title); row.find("small").text(detail || "");
        row.find(".adm-row-state").append(ui.badge(state)); row.on("click", open);
        return row.appendTo(root);
    };
    ui.bars = (root, values, empty = __("No activity in this period")) => {
        const items = Object.entries(values || {}), max = Math.max(1, ...items.map(([, v]) => Number(v) || 0));
        if (!items.length) return ui.state(root, empty, __("New activity will appear here."));
        for (const [label, value] of items) {
            const line = $('<div class="adm-bar-row"><div><span></span><strong></strong></div><span class="adm-bar-track"><i></i></span></div>');
            line.find("div span").text(__(label)); line.find("strong").text(ui.number(value));
            line.find("i").css("width", Math.max(0, Math.min(100, 100 * Number(value) / max)) + "%");
            line.appendTo(root);
        }
    };
    ui.action = (root, label, action, primary = false) =>
        $('<button type="button"></button>').addClass(primary ? "btn btn-primary" : "btn btn-default")
            .text(label).on("click", action).appendTo(root);
    ui.dialog = (title, content) => {
        const dialog = new frappe.ui.Dialog({title, fields:[{fieldname:"body",fieldtype:"HTML"}]});
        dialog.fields_dict.body.$wrapper.append(content); dialog.show(); return dialog;
    };
    ui.open = (doctype, name) => {
        if (frappe.router && typeof frappe.set_route === "function")
            return frappe.set_route(name ? "Form" : "List", doctype, ...(name ? [name] : []));
        const route = encodeURIComponent(String(doctype).toLowerCase().replace(/ /g, "-"));
        return window.location.assign("/desk/" + route + (name ? "/" + encodeURIComponent(name) : ""));
    };
    const scoped = () => {
        const route = frappe.get_route ? frappe.get_route() : [];
        document.body.classList.toggle("adm-workspace", route.some(part =>
            /^ADM |^adm-|^administration/.test(String(part))));
    };
    if (typeof $ !== "undefined") $(function() {
        scoped();
        if (frappe.router && frappe.router.on) frappe.router.on("change", scoped);
        $(document).on("page-change", scoped);
    });
})(eup_administration.ui);
