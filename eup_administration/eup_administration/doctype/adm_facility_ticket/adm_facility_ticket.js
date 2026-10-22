// All mutations use POST; server permissions remain authoritative.
function adm_operation_setup(frm) {
    if (frm.is_new()) return;
    const api = "eup_administration.v4.";
    const perform = (method, args) => frappe.call({method: api + method, type: "POST", args})
        .then(() => frm.reload_doc());
    frappe.call({method: api + "workflow.available", args: {doctype: frm.doctype, name: frm.doc.name}})
        .then(({message: info}) => {
            if (!info) return;
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
    frm.add_custom_button(__("Rate service"), () => frappe.prompt([
        {fieldname: "rating", fieldtype: "Select", options: "1\n2\n3\n4\n5", label: __("Rating"), reqd: 1},
        {fieldname: "comment", fieldtype: "Small Text", label: __("Comment")}
    ], values => perform("operations.feedback", {doctype: frm.doctype, name: frm.doc.name, ...values})), __("Feedback"));
    if (frm.doctype === "ADM Parcel" && !frm.doc.delivered_at)
        frm.add_custom_button(__("Acknowledge receipt"), () => perform("operations.acknowledge_parcel", {name: frm.doc.name}));
    if (frm.doctype === "ADM Equipment Booking" && !frm.doc.released)
        frm.add_custom_button(__("Release reservation"), () => perform("operations.release_booking", {name: frm.doc.name}));
}

frappe.ui.form.on("ADM Facility Ticket", {refresh: adm_operation_setup});

frappe.ui.form.on("ADM Facility Ticket", {refresh(frm) { if (!frm.is_new()) frm.add_custom_button(__("Update operational details"), () => frappe.prompt([{"fieldname":"resolution","fieldtype":"Small Text","label":"Resolution"}], values => frappe.call({method:"eup_administration.v4.operations.update_details", type:"POST", args:{doctype:frm.doctype,name:frm.doc.name,values}}).then(() => frm.reload_doc()))); }});

frappe.ui.form.on("ADM Facility Ticket", {refresh(frm) { if (!frm.is_new()) frm.add_custom_button(__("Assign operator"), () => frappe.prompt([{fieldname:"assigned_to",fieldtype:"Link",options:"User",label:__("Operator"),reqd:1}], values => frappe.call({method:"eup_administration.v4.operations.assign_operator",type:"POST",args:{doctype:frm.doctype,name:frm.doc.name,...values}}).then(() => frm.reload_doc()))); }});
