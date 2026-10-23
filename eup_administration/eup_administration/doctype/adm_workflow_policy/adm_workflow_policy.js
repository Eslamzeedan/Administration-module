frappe.ui.form.on("ADM Workflow Policy", {
    refresh(frm) {
        eup_administration.ui.intro(frm, __("Design the stages and decisions for one administrative service. Used policies are protected; duplicate a policy to create a new version."), "blue");
        frm.add_custom_button(__("Preview flow"), () => {
            const esc = frappe.utils.escape_html;
            const states = (frm.doc.states || []).filter(s => s.state);
            const transitions = (frm.doc.transitions || []).filter(t => t.action || t.from_state || t.to_state || t.allowed_role);
            if (!states.length) return frappe.msgprint(__("Add at least one named state, or load the review template."));
            if (transitions.some(t => !t.action || !t.from_state || !t.to_state || !t.allowed_role))
                return frappe.msgprint(__("Complete the action, source state, destination state and role for every transition."));
            const steps = states.map(s => "<span>" + esc(s.state) + (s.is_terminal ? " ✓" : "") + "</span>").join("");
            const lines = transitions.map(t => "<li>" + esc(t.from_state) + " → " + esc(t.to_state) + ": " + esc(t.action) +
                " [" + esc(t.allowed_role) + "]" + (t.approval_required ? " — " + __("approval required") : "") + "</li>").join("");
            frappe.msgprint({title:__("Workflow preview"),message:'<div class="adm-step-list">'+steps+"</div><ul>"+lines+"</ul>"});
        });
        if (frm.is_new()) frm.add_custom_button(__("Load review template"), async () => {
            const states = (frm.doc.states || []).some(s => s.state || s.sla_hours || s.escalation_role || s.is_terminal);
            const transitions = (frm.doc.transitions || []).some(t => t.action || t.from_state || t.to_state || t.allowed_role ||
                t.approval_required || (t.conditions && t.conditions.trim() !== "[]"));
            const bands = (frm.doc.approval_bands || []).some(b => b.transition_action || b.approver_role);
            if (states || transitions || bands) return frappe.msgprint(__("The template needs an empty draft. Keep your changes, or create a new policy to use the template."));
            for (const table of ["states","transitions","approval_bands"]) frm.clear_table(table);
            await frm.set_value("initial_state","Draft");
            ["Draft","Review","Completed"].forEach((state,i)=>frm.add_child("states",{
                state,is_terminal:i===2?1:0,sla_hours:i===2?0:24,escalation_role:"Administration Manager"
            }));
            frm.add_child("transitions",{action:"Submit",from_state:"Draft",to_state:"Review",
                allowed_role:"Administration User",conditions:"[]",approval_required:0});
            frm.add_child("transitions",{action:"Complete",from_state:"Review",to_state:"Completed",
                allowed_role:"Administration Manager",conditions:"[]",approval_required:1});
            frm.add_child("approval_bands",{transition_action:"Complete",step_number:1,approver_role:"Administration Manager",
                same_company:1,same_department:0,allow_delegation:1});
            frm.refresh_fields(); frm.dirty();
            frappe.show_alert({message:__("Review template added. Set the company and title, then review before saving."),indicator:"green"});
        });
        frm.add_custom_button(__("Add condition"), () => {
            const actions = [...new Set((frm.doc.transitions || []).map(t=>t.action).filter(Boolean))];
            if (!actions.length) return frappe.msgprint(__("Add a named transition first."));
            frappe.prompt([
                {fieldname:"action",fieldtype:"Select",options:actions.join("\n"),reqd:1,label:__("Transition")},
                {fieldname:"field",fieldtype:"Select",options:"priority\ndepartment\ncompany\ncategory\nseverity",reqd:1,label:__("Field")},
                {fieldname:"op",fieldtype:"Select",options:"eq\nne",reqd:1,label:__("Comparison")},
                {fieldname:"value",fieldtype:"Data",reqd:1,label:__("Value")}
            ], async values => {
                const row = (frm.doc.transitions || []).find(t=>t.action===values.action);
                if (!row) return;
                let conditions;
                try { conditions = JSON.parse(row.conditions || "[]"); } catch (_) { return frappe.msgprint(__("Correct the existing condition JSON first.")); }
                if (!Array.isArray(conditions)) return frappe.msgprint(__("Conditions must be a JSON list."));
                conditions.push({field:values.field,op:values.op,value:values.value});
                await frappe.model.set_value(row.doctype,row.name,"conditions",JSON.stringify(conditions,null,2));
            });
        });
    }
});
