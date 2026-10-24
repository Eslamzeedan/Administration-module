frappe.ui.form.on('ADM Trip', {
    async refresh(frm) {
        if (frm.is_new()) return;
        const capabilities = (await eup_administration.ui.call({method: 'eup_administration.services.trip_capabilities', args: {name: frm.doc.name}})).message;
        const manager = capabilities.manager;
        const call = (method, args = {}) => eup_administration.ui.call({method: 'eup_administration.services.' + method, args: {name: frm.doc.name, ...args}, freeze: true, callback: () => frm.reload_doc()});
        const promptReading = method => frappe.prompt([
            {fieldname: 'odometer', label: __('Odometer (km)'), fieldtype: 'Float', reqd: 1},
            ...(method === 'start_trip' ? [{fieldname: 'gap_reason', label: __('Explain any kilometers since the last trip'), fieldtype: 'Small Text'}] : [])
        ], values => call(method, values), method === 'start_trip' ? __('Start Trip') : __('End Trip'), __('Confirm'));
        if ((manager || capabilities.requester) && frm.doc.status === 'Draft') frm.add_custom_button(__('Request Trip'), () => call('request_trip'));
        if (manager && frm.doc.status === 'Requested') frm.add_custom_button(__('Approve & Assign'), () => frappe.prompt([
            {fieldname: 'vehicle', label: __('Vehicle'), fieldtype: 'Link', options: 'ADM Vehicle', reqd: 1},
            {fieldname: 'driver', label: __('Driver'), fieldtype: 'Link', options: 'ADM Driver', reqd: 1}
        ], values => call('assign_trip', values), __('Assign Trip'), __('Approve')));
        if (manager && frm.doc.status === 'Requested') frm.add_custom_button(__('Reject Trip'), () => frappe.prompt({fieldname: 'reason', label: __('Reason'), fieldtype: 'Small Text', reqd: 1}, values => call('reject_trip', values)));
        if (['In Progress', 'Completed'].includes(frm.doc.status)) {
            frm.add_custom_button(__('Record Fuel'), () => frappe.new_doc('ADM Fuel Log', {trip: frm.doc.name, vehicle: frm.doc.vehicle}));
            frm.add_custom_button(__('Record Expense'), () => frappe.new_doc('ADM Trip Expense', {trip: frm.doc.name, vehicle: frm.doc.vehicle}));
        }
        if (capabilities.operate && frm.doc.status === 'Assigned') frm.add_custom_button(__('Start'), () => promptReading('start_trip'));
        if (capabilities.operate && frm.doc.status === 'In Progress') frm.add_custom_button(__('End'), () => promptReading('end_trip'));
        if ((manager || capabilities.requester) && ['Draft', 'Requested', 'Assigned'].includes(frm.doc.status)) frm.add_custom_button(__('Cancel Trip'), () => frappe.confirm(__('Cancel this trip?'), () => call('cancel_trip')));
    }
});
