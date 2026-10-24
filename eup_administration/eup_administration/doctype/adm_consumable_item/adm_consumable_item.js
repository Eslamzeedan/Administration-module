frappe.ui.form.on('ADM Consumable Item', {
    refresh(frm) {
        if (frm.is_new()) return;
        const roles = frappe.user_roles || [];
        const manager = roles.includes('Administration Manager') || roles.includes('System Manager');
        const store = manager || roles.includes('Administration Storekeeper');
        if (!store) return;
        function promptQty(title, action, fields) {
            frappe.prompt(fields, values => eup_administration.ui.call({
                method: `eup_administration.consumables.${action}`,
                args: {item:frm.doc.name, ...values}, freeze:true,
                callback: response => frappe.msgprint({title, message: JSON.stringify(response.message || {}), indicator:'green'})
            }), title, __('Post'));
        }
        const locationField = {fieldname:'location',fieldtype:'Link',options:'ADM Consumable Location',label:__('Admin Location'),reqd:1};
        frm.add_custom_button(__('Receive Stock'), () => promptQty(__('Receive Administrative Stock'), 'receive_consumables', [
            locationField,{fieldname:'qty',fieldtype:'Float',label:__('Quantity'),reqd:1},
            {fieldname:'reference',fieldtype:'Data',label:__('Receipt / Supplier Reference'),reqd:1},
            {fieldname:'remarks',fieldtype:'Small Text',label:__('Notes')}
        ]));
        frm.add_custom_button(__('Check Balance'), () => frappe.prompt([locationField], values => eup_administration.ui.call({
            method:'eup_administration.consumables.get_consumable_balance',
            args:{item:frm.doc.name,...values}, callback:r => frappe.msgprint(__('Current balance: {0}', [(r.message||{}).balance]))
        }), __('Administrative Stock Balance'), __('Check')));
        if (manager) frm.add_custom_button(__('Post Physical Count'), () => promptQty(__('Physical Stock Count'), 'reconcile_consumables', [
            locationField,{fieldname:'counted_qty',fieldtype:'Float',label:__('Counted Quantity'),reqd:1},
            {fieldname:'reason',fieldtype:'Small Text',label:__('Reason'),reqd:1}
        ]));
    }
});
