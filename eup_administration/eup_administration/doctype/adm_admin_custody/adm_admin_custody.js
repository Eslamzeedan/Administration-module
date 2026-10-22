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

frappe.ui.form.on("ADM Admin Custody", {
    refresh(frm) {
        if (frm.is_new()) return;
        frm.add_custom_button(__("Custody QR label"), () => frappe.call({
            method: "eup_administration.v4.dashboard.custody_label", args: {name: frm.doc.name}
        }).then(r => {
            const info = r.message;
            const escape = frappe.utils.escape_html;
            frappe.msgprint({title: __("Authenticated custody label"), message:
                '<img alt="QR" width="240" src="' + info.qr + '"><p>' + escape(info.label) +
                '</p><p>' + __("Scanning requires login and record permission.") + '</p>'});
        }));
    }
});
