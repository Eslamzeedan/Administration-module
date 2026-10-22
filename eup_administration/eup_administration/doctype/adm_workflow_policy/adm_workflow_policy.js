frappe.ui.form.on("ADM Workflow Policy", {
    refresh(frm) {
        frm.add_custom_button(__("Preview flow"), () => {
            const escape = frappe.utils.escape_html;
            const states = (frm.doc.states || []).map(s => escape(s.state) + (s.is_terminal ? " ✓" : "")).join(" · ");
            const transitions = (frm.doc.transitions || []).map(t =>
                "<li>" + escape(t.from_state) + " → " + escape(t.to_state) + ": " + escape(t.action) +
                " [" + escape(t.allowed_role) + "]" + (t.approval_required ? " — approval required" : "") + "</li>").join("");
            frappe.msgprint({title: __("Workflow preview"), message: "<p>" + states + "</p><ul>" + transitions + "</ul>"});
        });
        if (frm.is_new()) frm.add_custom_button(__("Load review template"), () => {
            if ((frm.doc.states || []).length) return frappe.msgprint(__("Clear the state table before loading a template."));
            frm.set_value("initial_state", "Draft");
            ["Draft", "Review", "Completed"].forEach((state, i) => {
                const row = frm.add_child("states", {state, is_terminal: i === 2 ? 1 : 0,
                    sla_hours: i === 2 ? 0 : 24, escalation_role: "Administration Manager"});
            });
            frm.add_child("transitions", {action: "Submit", from_state: "Draft", to_state: "Review",
                allowed_role: "Administration User", conditions: "[]", approval_required: 0});
            frm.add_child("transitions", {action: "Complete", from_state: "Review", to_state: "Completed",
                allowed_role: "Administration Manager", conditions: "[]", approval_required: 1});
            frm.add_child("approval_bands", {transition_action: "Complete", step_number: 1,
                approver_role: "Administration Manager", same_company: 1, same_department: 0, allow_delegation: 1});
            frm.refresh_fields();
            frm.dirty();
        });
        frm.add_custom_button(__("Add condition"), () => frappe.prompt([
            {fieldname: "action", fieldtype: "Select", options: (frm.doc.transitions || []).map(t => t.action).join("\n"), reqd: 1, label: __("Transition")},
            {fieldname: "field", fieldtype: "Select", options: "priority\ndepartment\ncompany\ncategory\nseverity", reqd: 1, label: __("Field")},
            {fieldname: "op", fieldtype: "Select", options: "eq\nne", reqd: 1, label: __("Comparison")},
            {fieldname: "value", fieldtype: "Data", reqd: 1, label: __("Value")}
        ], values => {
            const row = (frm.doc.transitions || []).find(t => t.action === values.action);
            if (!row) return;
            try {
                const conditions = JSON.parse(row.conditions || "[]");
                conditions.push({field: values.field, op: values.op, value: values.value});
                frappe.model.set_value(row.doctype, row.name, "conditions", JSON.stringify(conditions, null, 2));
            } catch (e) { frappe.msgprint(__("Correct the existing condition JSON first.")); }
        }));
    }
});
