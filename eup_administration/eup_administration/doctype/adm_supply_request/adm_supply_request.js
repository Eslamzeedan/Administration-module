/* All buttons are convenience only: access is enforced server-side. */
frappe.ui.form.on('ADM Supply Request', {
    refresh(frm) {
        if (frm.is_new()) return;
        const roles = frappe.user_roles || [];
        const isManager = roles.includes('Administration Manager') || roles.includes('System Manager');
        const isRequester = frm.doc.requested_by === frappe.session.user;
        const isApprover = roles.includes('Administration Department Approver') || isManager;
        const isStore = roles.includes('Administration Storekeeper') || isManager;
        function invoke(action, args, label) {
            frappe.call({
                method: `eup_administration.consumables.${action}`,
                args: { name: frm.doc.name, ...args },
                freeze: true,
                callback: () => { frappe.show_alert({message: label || __('Updated'), indicator: 'green'}); frm.reload_doc(); }
            });
        }
        if (frm.doc.status === 'Draft' && (isRequester || isManager)) {
            frm.add_custom_button(__('Send for Approval'), () => invoke('submit_supply_request', {}, __('Sent for approval')));
        }
        if (frm.doc.status === 'Pending Approval' && isApprover) {
            frm.add_custom_button(__('Approve Quantities'), () => {
                const rows = frm.doc.items || [];
                const fields = rows.map((row, index) => ({
                    fieldtype: 'Float', fieldname: `approved_${index}`,
                    label: `${row.item} (${__('requested')} ${row.requested_qty})`,
                    default: row.requested_qty, reqd: 1
                }));
                frappe.prompt(fields, values => {
                    const amounts = {};
                    rows.forEach((row,index) => { amounts[row.name] = values[`approved_${index}`]; });
                    invoke('approve_supply_request', {approved_quantities: JSON.stringify(amounts)}, __('Approved'));
                }, __('Approve Supply Request'), __('Approve'));
            });
            frm.add_custom_button(__('Reject'), () => {
                frappe.prompt([{fieldtype:'Small Text',fieldname:'reason',label:__('Reason'),reqd:1}],
                    values => invoke('reject_supply_request', {reason: values.reason}, __('Rejected')),
                    __('Reject Supply Request'), __('Reject'));
            });
        }
        if (['Draft','Pending Approval','Approved'].includes(frm.doc.status) && (isManager || isRequester)) {
            frm.add_custom_button(__('Cancel Request'), () => {
                frappe.confirm(__('Cancel this request?'), () => invoke('cancel_supply_request', {}, __('Cancelled')));
            });
        }
        if (['Approved','Partially Issued'].includes(frm.doc.status) && isStore) {
            frm.add_custom_button(__('Issue Supplies'), () => {
                const open = (frm.doc.items || []).filter(row => (row.approved_qty || 0) > (row.issued_qty || 0));
                if (!open.length) { frappe.msgprint(__('No quantities remain to issue')); return; }
                frappe.prompt([
                    {fieldtype:'Select',fieldname:'line_name',label:__('Supply Line'),reqd:1,
                        options: open.map(row => row.name).join('\n')},
                    {fieldtype:'Link',fieldname:'location',label:__('Admin Location'),options:'ADM Consumable Location',reqd:1},
                    {fieldtype:'Float',fieldname:'qty',label:__('Quantity'),reqd:1}
                ], values => frappe.call({
                    method:'eup_administration.consumables.issue_consumables',
                    args:{request_name:frm.doc.name, ...values}, freeze:true,
                    callback: () => frm.reload_doc()
                }), __('Issue Administrative Supplies'), __('Issue'));
            });
        }
    }
});
