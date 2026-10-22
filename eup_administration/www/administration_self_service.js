frappe.ready(function() {
    const api = "eup_administration.v4.";
    const list = document.getElementById("adm-portal-list");
    const status = document.getElementById("adm-portal-status");
    let home;
    function promptFields(fields, submit) {
        const dialog = document.createElement("dialog");
        dialog.setAttribute("aria-label", __("Administration request"));
        dialog.style.cssText = "max-width:95vw;width:540px;border:1px solid #ddd;border-radius:12px;padding:24px";
        const form = document.createElement("form");
        for (const f of fields) {
            const label = document.createElement("label");
            label.textContent = f.label; label.className = "d-block mt-3";
            const input = document.createElement(f.fieldtype === "Select" ? "select" : f.fieldtype === "Small Text" ? "textarea" : "input");
            input.className = "form-control"; input.name = f.fieldname; input.required = !!f.reqd;
            if (f.fieldtype === "Datetime") input.type = "datetime-local";
            if (f.fieldtype === "Select") for (const value of (f.options || "").split("\n")) {
                const option = document.createElement("option"); option.value = value; option.textContent = value; input.appendChild(option);
            }
            input.value = f.default || input.value || "";
            label.appendChild(input); form.appendChild(label);
        }
        const save = document.createElement("button"); save.type = "submit"; save.className = "btn btn-primary mt-3"; save.textContent = __("Continue");
        const cancel = document.createElement("button"); cancel.type = "button"; cancel.className = "btn btn-default mt-3"; cancel.textContent = __("Cancel");
        cancel.onclick = () => dialog.close(); form.append(save, cancel);
        form.onsubmit = event => {
            event.preventDefault();
            const values = Object.fromEntries(new FormData(form).entries());
            dialog.close(); submit(values);
        };
        dialog.appendChild(form); document.body.appendChild(dialog);
        dialog.addEventListener("close", () => dialog.remove(), {once:true});
        dialog.showModal();
    }
    const call = (method, args={}, type="GET") => frappe.call({method: api+method, args, type});
    function button(parent, label, action) {
        const b = document.createElement("button");
        b.type = "button"; b.className = "btn btn-default mr-2 mb-2"; b.textContent = label;
        b.addEventListener("click", action); parent.appendChild(b);
    }
    function refresh() {
        call("portal.home").then(r => {
            home = r.message;
            list.replaceChildren();
            status.textContent = __("Showing your visible administrative requests for the last seven days.");
            for (const row of home.records) {
                const panel = document.createElement("article");
                panel.className = "border rounded p-3 mb-3";
                const title = document.createElement("h3"); title.textContent = row.subject; panel.appendChild(title);
                const state = document.createElement("p"); state.textContent = row.workflow_state || __("Draft"); panel.appendChild(state);
                list.appendChild(panel);
                call("workflow.available", {doctype: row.doctype, name: row.name}).then(r => {
                    for (const action of r.message.actions || []) button(panel, action, () =>
                        call("workflow.transition", {doctype: row.doctype, name: row.name, action,
                            expected_revision: r.message.revision}, "POST").then(refresh));
                });
                button(panel, __("Rate completed service"), () => promptFields([
                    {fieldname:"rating",fieldtype:"Select",options:"1\n2\n3\n4\n5",label:__("Rating"),reqd:1},
                    {fieldname:"comment",fieldtype:"Small Text",label:__("Comment")}
                ], values => call("operations.feedback", {doctype:row.doctype,name:row.name,...values}, "POST").then(() => frappe.msgprint(__("Thank you.")))));
                if (row.doctype === "ADM Parcel") button(panel, __("Acknowledge receipt"), () =>
                    call("operations.acknowledge_parcel", {name:row.name}, "POST").then(refresh));
                if (row.doctype === "ADM Equipment Booking") button(panel, __("Release booking"), () =>
                    call("operations.release_booking", {name:row.name}, "POST").then(refresh));
            }
        });
    }
    document.getElementById("adm-refresh").addEventListener("click", refresh);
    document.getElementById("adm-new-request").addEventListener("click", () => {
        if (!home) return;
        promptFields([{fieldname:"doctype",fieldtype:"Select",
            options:"ADM Facility Ticket\nADM Parcel\nADM Equipment Booking",label:__("Request type"),reqd:1}], selected => {
            const type = selected.doctype;
            const policies = home.policies.filter(p => p.target_doctype === type);
            if (!policies.length) return frappe.msgprint(__("No enabled workflow is configured for this request type."));
            const fields = [
                {fieldname:"subject",fieldtype:"Data",label:__("Subject"),reqd:1},
                {fieldname:"description",fieldtype:"Small Text",label:__("Details")},
                {fieldname:"priority",fieldtype:"Select",options:"Low\nNormal\nHigh\nCritical",default:"Normal",label:__("Priority")},
                {fieldname:"policy_name",fieldtype:"Select",options:policies.map(p=>p.name).join("\n"),label:__("Workflow"),reqd:1}
            ];
            if (type === "ADM Facility Ticket") fields.push(
                {fieldname:"location",fieldtype:"Data",label:__("Location"),reqd:1},
                {fieldname:"category",fieldtype:"Select",options:"Electrical\nPlumbing\nCleaning\nSafety\nOther",label:__("Category")});
            if (type === "ADM Parcel") fields.push(
                {fieldname:"tracking_number",fieldtype:"Data",label:__("Tracking number"),reqd:1},
                {fieldname:"sender",fieldtype:"Data",label:__("Sender"),reqd:1},
                {fieldname:"recipient",fieldtype:"Link",options:"User",label:__("Recipient"),reqd:1});
            if (type === "ADM Equipment Booking") fields.push(
                {fieldname:"equipment",fieldtype:"Select",options:home.equipment.map(e=>e.name).join("\n"),label:__("Equipment"),reqd:1},
                {fieldname:"starts_at",fieldtype:"Datetime",label:__("Start"),reqd:1},
                {fieldname:"ends_at",fieldtype:"Datetime",label:__("End"),reqd:1});
            promptFields(fields, values => {
                const policy_name = values.policy_name;
                delete values.policy_name;
                call("portal.create_request", {doctype:type, values, policy_name}, "POST").then(refresh);
            });
        });
    });
    refresh();
});
