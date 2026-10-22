frappe.ui.form.on('ADM Admin Custody', {
    refresh(frm) {
        if (frm.is_new() || frm.doc.status !== 'Issued') return;
        const roles = frappe.user_roles || [];
        if (!roles.some(role => ['Administration Storekeeper','Administration Manager','System Manager'].includes(role))) return;
        frm.add_custom_button(__('Register Return'), () => {
            frappe.prompt([{fieldname:'condition_in',fieldtype:'Small Text',label:__('Return Condition'),reqd:1}],
                values => frappe.call({method:'eup_administration.consumables.return_custody',
                    args:{name:frm.doc.name,...values},freeze:true,callback:()=>frm.reload_doc()}),
                __('Return Administrative Custody'), __('Return'));
        });
    }
});
