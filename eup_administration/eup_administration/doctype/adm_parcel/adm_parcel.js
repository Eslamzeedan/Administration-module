// All mutations use POST; server permissions remain authoritative.
function adm_operation_setup(frm) {
    // An already-open Desk tab may still have the preceding shared asset revision.
    const intro = (message, color) => {
        if (typeof eup_administration.ui.intro === "function") eup_administration.ui.intro(frm, message, color);
        else if (message) frm.set_intro(message, color);
    };
    intro();
    if (frm.is_new()) {
        eup_administration.ui.request("eup_administration.v4.dashboard.context").then(info => {
            if (info.requires_employee) intro(__("An active employee linked to your company is required to create this request. Ask your administrator to complete your employee profile."), "yellow");
            else if (info.company) frm.set_value("company", info.company);
        }).catch(() => { /* The server still checks access when saving. */ });
        return;
    }
    if (frm.doc.workflow_policy) intro(__("This request is in a protected workflow. Use the Workflow and Approval actions to move it forward."), "blue");
    const api = "eup_administration.v4.";
    const perform = (method, args) => eup_administration.ui.call({method: api + method, type: "POST", args})
        .then(() => frm.reload_doc());
    eup_administration.ui.call({method: api + "workflow.available", args: {doctype: frm.doctype, name: frm.doc.name}})
        .then(({message: info}) => {
            if (!info) return;
            if (info.pending_action) intro(info.can_decide
                ? __("This request is waiting for your approval. Use the Approval actions to approve or reject it.")
                : __("This request is waiting for approval. An eligible approver must decide before it can continue."), "yellow");
            if (info.can_feedback) {
                frm.add_custom_button(__("Rate service"), () => frappe.prompt([
                    {fieldname: "rating", fieldtype: "Select", options: "1\n2\n3\n4\n5", label: __("Rating"), reqd: 1},
                    {fieldname: "comment", fieldtype: "Small Text", label: __("Comment")}
                ], values => perform("operations.feedback", {doctype: frm.doctype, name: frm.doc.name, ...values})), __("Feedback"));
            
            }
            for (const policy of info.policies || []) {
                frm.add_custom_button(__("Start: {0}", [policy.policy_title]),
                    () => perform("workflow.start", {doctype: frm.doctype, name: frm.doc.name, policy_name: policy.name}), __("Workflow"));
            }
            for (const action of info.actions || []) {
                frm.add_custom_button(__(action), () => perform("workflow.transition", {
                    doctype: frm.doctype, name: frm.doc.name, action, expected_revision: info.revision
                }), __("Workflow"));
            }
            if (info.can_decide) {
                for (const decision of ["Approved", "Rejected"]) {
                    frm.add_custom_button(__(decision), () => frappe.prompt(
                        [{fieldname: "comment", fieldtype: "Small Text", label: __("Reason"), reqd: decision === "Rejected"}],
                        values => perform("workflow.decide", {doctype: frm.doctype, name: frm.doc.name,
                            decision, expected_revision: info.revision, comment: values.comment})
                    ), __("Approval"));
                }
            }
        });
    if (frm.doctype === "ADM Parcel" && !frm.doc.delivered_at && frm.doc.recipient === frappe.session.user)
        frm.add_custom_button(__("Acknowledge receipt"), () => perform("operations.acknowledge_parcel", {name: frm.doc.name}));
    if (frm.doctype === "ADM Equipment Booking" && !frm.doc.released)
        frm.add_custom_button(__("Release reservation"), () => perform("operations.release_booking", {name: frm.doc.name}));
}

frappe.ui.form.on("ADM Parcel", {refresh: adm_operation_setup});

frappe.ui.form.on("ADM Parcel", {refresh(frm) { if (!frm.is_new()) frm.add_custom_button(__("Update operational details"), () => frappe.prompt([{"fieldname":"delivery_note","fieldtype":"Small Text","label":"Delivery note"}], values => eup_administration.ui.call({method:"eup_administration.v4.operations.update_details", type:"POST", args:{doctype:frm.doctype,name:frm.doc.name,values}}).then(() => frm.reload_doc()))); }});

frappe.ui.form.on("ADM Parcel", {refresh(frm) { if (!frm.is_new()) frm.add_custom_button(__("Assign operator"), () => frappe.prompt([{fieldname:"assigned_to",fieldtype:"Link",options:"User",label:__("Operator"),reqd:1}], values => eup_administration.ui.call({method:"eup_administration.v4.operations.assign_operator",type:"POST",args:{doctype:frm.doctype,name:frm.doc.name,...values}}).then(() => frm.reload_doc()))); }});
