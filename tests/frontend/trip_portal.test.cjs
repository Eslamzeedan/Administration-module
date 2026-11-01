/* Executes the shipped portal against an explicit DOM/network double; no browser or DB claim. */
const test = require("node:test");
const assert = require("node:assert/strict");
const fs = require("node:fs");
const path = require("node:path");
const vm = require("node:vm");
const root = path.resolve(__dirname, "../..");
const source = fs.readFileSync(path.join(root, "eup_administration/www/administration_trips.js"), "utf8");
const html = fs.readFileSync(path.join(root, "eup_administration/www/administration_trips.html"), "utf8");

class Element {
    constructor(tag) {
        this.tag = tag; this.children = []; this.dataset = {}; this.attrs = {};
        this.textContent = ""; this.events = {}; this.value = ""; this.disabled = false;
    }
    appendChild(child) { child.remove(); this.children.push(child); child.parent = this; return child; }
    insertBefore(child, before) {
        child.remove(); this.children.splice(this.children.indexOf(before), 0, child); child.parent = this;
    }
    remove() {
        if (this.parent) this.parent.children.splice(this.parent.children.indexOf(this), 1);
        this.parent = null;
    }
    replaceChildren() { for (const child of [...this.children]) child.remove(); }
    setAttribute(name, value) { this.attrs[name] = value; }
    addEventListener(name, handler) { this.events[name] = handler; }
    close() { this.events.close?.(); }
    showModal() { this.open = true; }
    focus() {}
    get previousElementSibling() { return this.parent?.children[this.parent.children.indexOf(this)-1]; }
    get nextElementSibling() { return this.parent?.children[this.parent.children.indexOf(this)+1]; }
    get elements() { return {namedItem: name => this.all().find(e => e.name === name)}; }
    all() { return this.children.flatMap(e => [e, ...e.all()]); }
    querySelector(selector) {
        return this.all().find(e => {
            if (selector === "[data-stops]") return e.dataset.stops;
            if (selector.startsWith('[name="')) return e.name === selector.slice(7,-2);
            if (selector === "dialog.adm-trips") return e.tag === "dialog" && e.className.includes("adm-trips");
            if (selector === ".adm-trips dialog") return false;
            return e.tag === selector;
        }) || null;
    }
}

const flush = () => new Promise(resolve => setImmediate(resolve));
async function setup(trips = []) {
    const body = new Element("body"), ids = {};
    for (const id of [...html.matchAll(/id="(adm-trip-[a-z-]+)"/g)].map(m => m[1])) {
        const el = new Element(id.endsWith("list") ? "div" : "button"); ids[id] = el; body.appendChild(el);
    }
    const calls = [], listeners = {}, events = {}, intervals = [];
    let result = {trips, has_more: false, is_driver: true, can_create: true};
    let reject, pending;
    const document = {
        body, hidden: false, createElement: tag => new Element(tag),
        getElementById: id => ids[id], querySelector: selector => body.querySelector(selector),
        addEventListener: (event, handler) => { events[event] = handler; }
    };
    const context = {
        __: text => text, document, Map,
        window: {setInterval: (fn, ms) => { intervals.push({fn, ms}); return 1; },
            clearInterval() {}, addEventListener: (event, handler) => { events[event] = handler; }},
        FormData: class {
            constructor(form) { this.values = form.all().filter(e => e.tag === "input" && e.name).map(e => [e.name, e.value]); }
            [Symbol.iterator]() { return this.values[Symbol.iterator](); }
        },
        frappe: {session: {user: "employee"}, ready: fn => fn(),
            realtime: {on: (event, handler) => { listeners[event] = handler; }, off() {}}},
        eup_administration: {ui: {
            number: v => String(v), message: e => e.message,
            request: async (method, args, type) => {
                calls.push({method, args, type});
                if (reject) throw new Error(reject);
                if (pending && type === "POST") await pending;
                return method.endsWith(".home") ? structuredClone(result) : {name: "NEW"};
            }
        }}
    };
    vm.runInNewContext(source, context);
    await flush();
    const button = (parent, label) => parent.all().find(e => e.tag === "button" && e.textContent === label);
    return {body, document, ids, calls, listeners, events, intervals, button,
        result: value => { result = value; }, reject: value => { reject = value; },
        pending: value => { pending = value; }, form: () => body.querySelector("form"),
        posts: () => calls.filter(c => c.type === "POST")};
}
const trip = extra => ({name: "TRIP", purpose: "Synthetic QA", origin: "HQ", destination: "Office",
    status: "In Progress", requested_by: "employee", planned_start: "2099-01-01 08:00",
    planned_end: "2099-01-01 10:00", modified: "1", stops: [], ...extra});

test("employee cannot see driving controls; untrusted strings are text", async () => {
    const h = await setup([trip({purpose: '<img src=x onerror=alert(1)>', operate: false})]);
    assert.equal(h.body.querySelector("h2").textContent, '<img src=x onerror=alert(1)>');
    assert.equal(h.body.querySelector("img"), null);
    assert.equal(h.button(h.body, "Arrived at destination"), undefined);
    assert.equal(h.button(h.body, "End Trip"), undefined);
});

test("driver current-stop button posts exact stop and event once while busy", async () => {
    const h = await setup([trip({operate: true, next_stop: "STOP", next_event: "arrive", stops: [
        {name: "STOP", location: "Office", expected_wait_minutes: 5} ]})]);
    let release; h.pending(new Promise(resolve => { release = resolve; }));
    const button = h.button(h.body, "Arrived at stop");
    const first = button.onclick(); await flush();
    await button.onclick();
    assert.equal(h.posts().length, 1);
    assert.deepEqual(JSON.parse(JSON.stringify(h.posts()[0].args)), {name: "TRIP", stop_name: "STOP", event: "arrive"});
    assert.match(h.posts()[0].method, /trip_stops.mark_stop$/);
    release(); await first;
});

test("departure action uses depart and hides end until server allows it", async () => {
    const h = await setup([trip({operate: true, next_stop: "STOP", next_event: "depart", stops: [
        {name: "STOP", location: "Office", arrived_at: "2026-11-01 10:00"} ]})]);
    assert.equal(h.button(h.body, "End Trip"), undefined);
    await h.button(h.body, "Departed from stop").onclick();
    assert.equal(h.posts()[0].args.event, "depart");
});

test("single destination arrival does not end the trip", async () => {
    const h = await setup([trip({operate: true, can_end: true})]);
    await h.button(h.body, "Arrived at destination").onclick();
    assert.match(h.posts()[0].method, /trip_stops.arrive_destination$/);
    assert.equal(h.posts().length, 1);
});

test("start reading is required and goes through the existing POST endpoint", async () => {
    const h = await setup([trip({status: "Assigned", operate: true})]);
    await h.button(h.body, "Start Trip").onclick();
    const form = h.form();
    assert.equal(form.elements.namedItem("odometer").required, true);
    form.elements.namedItem("odometer").value = "1000";
    form.elements.namedItem("gap_reason").value = "Transfer";
    await form.onsubmit({preventDefault() {}});
    assert.match(h.posts()[0].method, /services.start_trip$/);
    assert.equal(h.posts()[0].args.odometer, "1000");
    assert.equal(h.body.querySelector("dialog.adm-trips"), null);
});

test("employee creates ordered visits, reorders/removes them and submits no identity", async () => {
    const h = await setup();
    h.ids["adm-trip-new"].onclick();
    const form = h.form();
    for (const [key, value] of Object.entries({purpose: "Visit", origin: "HQ", destination: "Office",
        planned_start: "2099-01-01T08:00", planned_end: "2099-01-01T10:00", passenger_count: "2"}))
        form.elements.namedItem(key).value = value;
    const add = h.button(form, "Add stop");
    add.onclick(); add.onclick(); add.onclick();
    const stops = form.querySelector("[data-stops]");
    stops.children[0].querySelector('[name="location"]').value = "Office";
    stops.children[1].querySelector('[name="location"]').value = "Bank";
    h.button(stops.children[1], "Move up").onclick();
    h.button(stops.children[2], "Remove stop").onclick();
    await form.onsubmit({preventDefault() {}});
    const values = h.posts()[0].args.values;
    assert.deepEqual(Array.from(values.stops, row => row.location), ["Bank", "Office"]);
    assert.equal(values.planned_start, "2099-01-01 08:00:00");
    assert.equal(values.planned_end, "2099-01-01 10:00:00");
    assert.equal(values.company, undefined);
    assert.equal(values.requested_by, undefined);
    assert.match(h.posts()[0].method, /trip_portal.create$/);
});

test("failed create retains dialog values and reenables submit", async () => {
    const h = await setup();
    h.ids["adm-trip-new"].onclick();
    const form = h.form(); form.elements.namedItem("purpose").value = "Retain me";
    h.reject("Permission denied");
    await form.onsubmit({preventDefault() {}});
    assert.equal(h.form(), form);
    assert.equal(form.elements.namedItem("purpose").value, "Retain me");
    assert.equal(h.button(form, "Confirm").disabled, false);
    assert.ok(form.all().some(el => el.textContent === "Permission denied"));
});

test("permission failure clears stale records", async () => {
    const h = await setup([trip()]);
    assert.equal(h.intervals[0].ms, 30000);
    h.reject("Access revoked");
    await h.ids["adm-trip-refresh"].onclick();
    assert.equal(h.ids["adm-trip-list"].children.length, 0);
    assert.equal(h.ids["adm-trip-status"].textContent, "Access revoked");
});

test("paging uses bounded offsets and driver view resets the page", async () => {
    const h = await setup();
    h.result({trips: [], has_more: true, is_driver: true, can_create: true});
    await h.ids["adm-trip-next"].onclick(); await flush();
    assert.equal(h.calls.at(-1).args.start, 20);
    await h.ids["adm-trip-driver"].onclick(); await flush();
    assert.equal(h.calls.at(-1).args.view, "driver");
    assert.equal(h.calls.at(-1).args.start, 0);
});

test("polling performs no request in a hidden tab or while editing", async () => {
    const h = await setup();
    const before = h.calls.length;
    h.document.hidden = true;
    h.intervals[0].fn(); await flush();
    assert.equal(h.calls.length, before);
    h.document.hidden = false;
    h.ids["adm-trip-new"].onclick();
    h.intervals[0].fn(); await flush();
    assert.equal(h.calls.length, before);
});

test("realtime refreshes through scoped API and announces changed progress", async () => {
    const h = await setup([trip()]);
    h.result({trips: [trip({modified: "2", status: "Completed"})], has_more: false});
    h.listeners.adm_trip_progress(); await flush();
    assert.equal(h.calls.at(-1).method, "eup_administration.trip_portal.home");
    assert.equal(h.ids["adm-trip-alert"].textContent, "Your trip progress has changed.");
    assert.ok(h.ids["adm-trip-list"].all().some(e => e.textContent.includes("Completed")));
});
