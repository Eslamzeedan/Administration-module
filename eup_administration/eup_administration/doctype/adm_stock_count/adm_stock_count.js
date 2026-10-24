frappe.ui.form.on("ADM Stock Count", {
  refresh(frm) {
    if (frm.is_new()) return;
    const operations = {"Draft":["Submit Count","submit_count"],"Submitted":["Approve Count","approve_count"],"Approved":["Post Adjustment","post_count"]};
    const next = operations[frm.doc.status];
    if (next) frm.add_custom_button(next[0], () => {
      frappe.confirm("Confirm this stock-count action?", () => eup_administration.ui.call({
        method:"eup_administration.v3.inventory."+next[1], type:"POST",
        args:{name:frm.doc.name}, callback:()=>frm.reload_doc()
      }));
    });
  }
});
