frappe.ui.form.on("ADM General Service Request", {
  refresh(frm) {
    if (frm.is_new()) return;
    const method = "eup_administration.v3.general.";
    function run(action, args) {
      frappe.call({method: method + action, type: "POST",
        args: Object.assign({name: frm.doc.name}, args || {}),
        callback: function() { frm.reload_doc(); }});
    }
    if (frm.doc.status === "Draft") frm.add_custom_button("Submit for Approval", () => run("submit"));
    if (frm.doc.status === "Approved") frm.add_custom_button("Assign", () => {
      frappe.prompt([{fieldname:"assignee",fieldtype:"Link",options:"User",label:"Assign to",reqd:1}],
        values => run("assign",values),"Assign Service");
    });
    if (frm.doc.status === "Assigned") frm.add_custom_button("Start", () => run("start"));
    if (frm.doc.status === "In Progress") frm.add_custom_button("Complete", () => {
      frappe.prompt([{fieldname:"notes",fieldtype:"Small Text",label:"Completion notes",reqd:1}],
        values => run("complete",values),"Complete Service");
    });
    if (frm.doc.status === "Completed") frm.add_custom_button("Close", () => run("close"));
  }
});
