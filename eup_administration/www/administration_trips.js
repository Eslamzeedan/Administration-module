frappe.ready(function() {
    "use strict";
    const ui = eup_administration.ui, api = "eup_administration.";
    const byId = id => document.getElementById("adm-trip-" + id);
    const list = byId("list"), status = byId("status"), alert = byId("alert");
    let view = "mine", offset = 0, busy = false, loaded = false, previous = new Map();
    const text = (parent, tag, value, className) => {
        const el = document.createElement(tag);
        el.textContent = value == null ? "" : value;
        if (className) el.className = className;
        parent.appendChild(el); return el;
    };
    function action(parent, label, handler) {
        const button = text(parent, "button", label, "btn btn-primary");
        button.type = "button";
        button.onclick = async () => {
            if (busy) return;
            busy = true; button.disabled = true;
            try { await handler(); }
            catch (error) { alert.textContent = ui.message(error); }
            finally { busy = false; await refresh(); }
        };
        return button;
    }
    async function post(method, args) { return ui.request(api + method, args, "POST"); }
    function dialog(title, build, submit) {
        const box = document.createElement("dialog");
        box.className = "adm-dialog adm-self-service adm-trips";
        box.setAttribute("aria-label", title); text(box, "h2", title);
        const form = document.createElement("form"); box.appendChild(form);
        build(form);
        const errors = text(form, "p", ""); errors.setAttribute("role", "alert");
        const toolbar = document.createElement("div"); toolbar.className = "adm-toolbar";
        form.appendChild(toolbar);
        const save = text(toolbar, "button", __("Confirm"), "btn btn-primary"); save.type = "submit";
        const cancel = text(toolbar, "button", __("Cancel"), "btn btn-default"); cancel.type = "button";
        let sending = false;
        cancel.onclick = () => box.close();
        form.onsubmit = async event => {
            event.preventDefault();
            if (sending) return;
            sending = true; save.disabled = cancel.disabled = true;
            try { await submit(form); box.close(); box.remove(); await refresh(); }
            catch (error) { errors.textContent = ui.message(error); }
            finally { sending = false; save.disabled = cancel.disabled = false; }
        };
        box.addEventListener("cancel", event => { if (sending) event.preventDefault(); });
        box.addEventListener("close", () => box.remove(), {once: true});
        document.body.appendChild(box); box.showModal();
        form.querySelector("input")?.focus();
    }
    function input(parent, label, name, type = "text", required = false, value = "") {
        const wrap = document.createElement("label"); wrap.textContent = label;
        const el = document.createElement("input");
        el.name = name; el.type = type; el.required = required; el.value = value;
        el.className = "form-control"; wrap.appendChild(el); parent.appendChild(wrap);
        return el;
    }
    function reading(trip, method) {
        dialog(method === "start_trip" ? __("Start Trip") : __("End Trip"), form => {
            const meter = input(form, __("Odometer (km)"), "odometer", "number", true);
            meter.min = "0"; meter.step = "any";
            if (method === "start_trip") input(form, __("Explain any kilometers since the last trip"), "gap_reason");
        }, form => post("services." + method, {name: trip.name, ...Object.fromEntries(new FormData(form))}));
    }
    function render(trip) {
        const card = document.createElement("article"); card.className = "adm-portal-card";
        list.appendChild(card); text(card, "h2", trip.purpose);
        text(card, "p", trip.name + " · " + __(trip.status), "adm-note");
        text(card, "p", trip.origin + " → " + trip.destination);
        text(card, "p", __("Planned Start") + ": " + trip.planned_start + " · " + __("Planned End") + ": " + trip.planned_end);
        text(card, "p", __("Vehicle") + ": " + (trip.vehicle || "—") + " · " + __("Driver") + ": " + (trip.driver_name || trip.driver || "—"));
        text(card, "p", __("Requested By") + ": " + (trip.requester_name || trip.requested_by || "—"));
        if (trip.rejection_reason) text(card, "p", __("Rejection Reason") + ": " + trip.rejection_reason);
        if (trip.actual_start) text(card, "p", __("Actual Start") + ": " + trip.actual_start);
        if (trip.destination_arrived_at) text(card, "p", __("Destination Arrived At") + ": " + trip.destination_arrived_at);
        if (trip.actual_end) text(card, "p", __("Actual End") + ": " + trip.actual_end + " · " + __("Distance (km)") + ": " + ui.number(trip.distance_km));
        const visits = document.createElement("ol"); card.appendChild(visits);
        for (const stop of trip.stops) {
            const item = document.createElement("li"); visits.appendChild(item);
            text(item, "strong", stop.location);
            text(item, "p", (stop.purpose || "") + " · " + __("Expected Wait (minutes)") + ": " + stop.expected_wait_minutes);
            text(item, "p", __("Arrived At") + ": " + (stop.arrived_at || "—") + " · " + __("Departed At") + ": " + (stop.departed_at || "—"));
            if (trip.operate && trip.status === "In Progress" && trip.next_stop === stop.name)
                action(item, trip.next_event === "arrive" ? __("Arrived at stop") : __("Departed from stop"),
                    () => post("trip_stops.mark_stop", {name: trip.name, stop_name: stop.name, event: trip.next_event}));
        }
        const actions = document.createElement("div"); actions.className = "adm-toolbar"; card.appendChild(actions);
        if (trip.operate && trip.status === "Assigned") action(actions, __("Start Trip"), () => reading(trip, "start_trip"));
        if (trip.operate && trip.status === "In Progress" && !trip.stops.length && !trip.destination_arrived_at)
            action(actions, __("Arrived at destination"), () => post("trip_stops.arrive_destination", {name: trip.name}));
        if (trip.can_end) action(actions, __("End Trip"), () => reading(trip, "end_trip"));
        if (trip.can_cancel) action(actions, __("Cancel Trip"), () => dialog(__("Cancel this trip?"), () => {},
            () => post("services.cancel_trip", {name: trip.name})));
        if (trip.status === "Draft" && trip.requested_by === frappe.session.user)
            action(actions, __("Request Trip"), () => post("services.request_trip", {name: trip.name}));
    }
    async function refresh() {
        if (busy || document.querySelector(".adm-trips dialog") || document.querySelector("dialog.adm-trips")) return;
        busy = true; byId("refresh").disabled = true;
        status.textContent = __("Loading your trips");
        try {
            const result = await ui.request(api + "trip_portal.home", {view, start: offset});
            const changed = loaded && result.trips.some(t => previous.has(t.name) && previous.get(t.name) !== t.modified);
            if (changed) alert.textContent = __("Your trip progress has changed.");
            previous = new Map(result.trips.map(t => [t.name, t.modified])); loaded = true;
            list.replaceChildren();
            result.trips.forEach(render);
            status.textContent = result.trips.length ? __("Latest trip progress") : __("No trips in this view");
            byId("driver").hidden = !result.is_driver; byId("new").hidden = !result.can_create;
            byId("mine").setAttribute("aria-pressed", String(view === "mine"));
            byId("driver").setAttribute("aria-pressed", String(view === "driver"));
            byId("previous").disabled = offset === 0; byId("next").disabled = !result.has_more;
        } catch (error) {
            list.replaceChildren(); status.textContent = ui.message(error);
            byId("previous").disabled = byId("next").disabled = true;
        } finally { busy = false; byId("refresh").disabled = false; }
    }
    byId("new").onclick = () => dialog(__("Request a vehicle"), form => {
        input(form, __("Purpose"), "purpose", "text", true);
        input(form, __("Origin"), "origin", "text", true);
        input(form, __("Destination"), "destination", "text", true);
        input(form, __("Planned Start"), "planned_start", "datetime-local", true);
        input(form, __("Planned End"), "planned_end", "datetime-local", true);
        const passengers = input(form, __("Passengers"), "passenger_count", "number", true, "1");
        passengers.min = "1"; passengers.step = "1";
        text(form, "p", __("Add visits in travel order, including the final destination. Add your return point last if returning. Leave empty for a single destination."));
        const stops = document.createElement("div"); stops.dataset.stops = "1"; form.appendChild(stops);
        const add = text(form, "button", __("Add stop"), "btn btn-default"); add.type = "button";
        add.onclick = () => {
            if (stops.children.length >= 30) return;
            const row = document.createElement("fieldset"); stops.appendChild(row);
            text(row, "legend", __("Trip Stop"));
            input(row, __("Stop Address"), "location", "text", true).maxLength = 140;
            input(row, __("Stop Purpose"), "stop_purpose").maxLength = 2000;
            const wait = input(row, __("Expected Wait (minutes)"), "expected_wait_minutes", "number", false, "0");
            wait.min = "0"; wait.max = "1440"; wait.step = "1";
            for (const [label, direction] of [[__("Move up"), -1], [__("Move down"), 1]]) {
                const move = text(row, "button", label, "btn btn-default"); move.type = "button";
                move.onclick = () => {
                    if (direction < 0 && row.previousElementSibling) stops.insertBefore(row, row.previousElementSibling);
                    if (direction > 0 && row.nextElementSibling) stops.insertBefore(row.nextElementSibling, row);
                };
            }
            const remove = text(row, "button", __("Remove stop"), "btn btn-default"); remove.type = "button";
            remove.onclick = () => row.remove();
        };
    }, async form => {
        const values = {};
        for (const key of ["purpose", "origin", "destination", "planned_start", "planned_end", "passenger_count"])
            values[key] = form.elements.namedItem(key).value;
        for (const key of ["planned_start", "planned_end"]) values[key] = values[key].replace("T", " ") + (values[key].length === 16 ? ":00" : "");
        values.stops = [...form.querySelector("[data-stops]").children].map(row => ({
            location: row.querySelector('[name="location"]').value,
            purpose: row.querySelector('[name="stop_purpose"]').value,
            expected_wait_minutes: row.querySelector('[name="expected_wait_minutes"]').value || "0"
        }));
        await post("trip_portal.create", {values});
    });
    byId("mine").onclick = () => { if (!busy) { view = "mine"; offset = 0; loaded = false; refresh(); } };
    byId("driver").onclick = () => { if (!busy) { view = "driver"; offset = 0; loaded = false; refresh(); } };
    byId("previous").onclick = () => { if (!busy) { offset = Math.max(0, offset - 20); refresh(); } };
    byId("next").onclick = () => { if (!busy) { offset += 20; refresh(); } };
    byId("refresh").onclick = refresh;
    document.addEventListener("visibilitychange", () => { if (!document.hidden) refresh(); });
    const onProgress = () => { alert.textContent = __("Your trip progress has changed."); refresh(); };
    if (frappe.realtime && frappe.realtime.on) frappe.realtime.on("adm_trip_progress", onProgress);
    const timer = window.setInterval(() => { if (!document.hidden) refresh(); }, 30000);
    window.addEventListener("pagehide", () => { window.clearInterval(timer); if (frappe.realtime && frappe.realtime.off) frappe.realtime.off("adm_trip_progress", onProgress); }, {once: true});
    refresh();
});
