frappe.ui.form.on('ADM Meeting Booking', {
    refresh(frm) {
        if (frm.is_new() || frm.doc.status !== 'Confirmed') return;
        if (!frm.doc.recurrence_root) frm.add_custom_button(__('Repeat Booking'), () => frappe.prompt([
            {fieldname: 'frequency', label: __('Frequency'), fieldtype: 'Select', options: 'Daily\nWeekly', reqd: 1},
            {fieldname: 'count', label: __('Total Occurrences (including this booking)'), fieldtype: 'Int', default: 2, reqd: 1}
        ], values => eup_administration.ui.call({method: 'eup_administration.meetings.repeat_booking', args: {name: frm.doc.name, ...values}, freeze: true}).then(() => frm.reload_doc())));
        if (frm.doc.recurrence_root) frm.add_custom_button(__('Cancel Remaining Series'), () => frappe.confirm(__('Cancel all confirmed bookings in this series?'), () => eup_administration.ui.call({method: 'eup_administration.meetings.cancel_series', args: {name: frm.doc.name}, freeze: true}).then(() => frm.reload_doc())));
        frm.add_custom_button(__('Check Room Availability'), () => eup_administration.ui.call({method: 'eup_administration.services.room_availability', args: {room: frm.doc.room, starts_at: frm.doc.starts_at, ends_at: frm.doc.ends_at}}).then(r => {
            const periods = (r.message || []).map(v => frappe.utils.escape_html(v.starts_at) + ' — ' + frappe.utils.escape_html(v.ends_at));
            frappe.msgprint({title: __('Occupied periods including preparation buffer'), message: periods.length ? periods.join('<br>') : __('No conflicting bookings')});
        }));
        for (const status of ['Completed', 'Cancelled']) {
            frm.add_custom_button(__(status === 'Completed' ? 'Complete Meeting' : 'Cancel Booking'), () => frappe.confirm(__('Confirm this action?'), () => eup_administration.ui.call({
                method: 'eup_administration.services.close_booking', args: {name: frm.doc.name, status}, freeze: true, callback: () => frm.reload_doc()
            })));
        }
    }
});
