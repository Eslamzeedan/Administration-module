frappe.ui.form.on('ADM Maintenance', {
    refresh(frm) {
        if (frm.is_new()) return;
        const act = (status, args = {}) => frappe.call({method: 'eup_administration.fleet.maintenance_action', args: {name: frm.doc.name, status, ...args}, freeze: true}).then(() => frm.reload_doc());
        if (frm.doc.status === 'Scheduled') {
            frm.add_custom_button(__('Start Maintenance'), () => act('In Progress'));
            frm.add_custom_button(__('Cancel Maintenance'), () => frappe.confirm(__('Cancel this maintenance?'), () => act('Cancelled')));
        }
        if (frm.doc.status === 'In Progress') frm.add_custom_button(__('Complete Maintenance'), () => frappe.prompt([
            {fieldname: 'odometer', label: __('Odometer'), fieldtype: 'Float', reqd: 1},
            {fieldname: 'cost', label: __('Total Cost'), fieldtype: 'Currency', reqd: 1},
            {fieldname: 'next_due_date', label: __('Next Service Date'), fieldtype: 'Date'},
            {fieldname: 'next_due_odometer', label: __('Next Service Odometer'), fieldtype: 'Float'}
        ], values => act('Completed', values)));
    }
});
