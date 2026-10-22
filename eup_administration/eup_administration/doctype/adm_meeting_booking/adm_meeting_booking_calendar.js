frappe.views.calendar['ADM Meeting Booking'] = {
    field_map: {start: 'starts_at', end: 'ends_at', id: 'name', title: 'title'},
    filters: [{fieldtype: 'Link', fieldname: 'room', options: 'ADM Meeting Room', label: __('Room')}]
};
