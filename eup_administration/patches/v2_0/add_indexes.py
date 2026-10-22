import frappe


def execute():
    # No record deletion or renaming. New company is derived from the existing room.
    frappe.db.sql('''UPDATE `tabADM Meeting Booking` booking
        INNER JOIN `tabADM Meeting Room` room ON room.name=booking.room
        SET booking.company=room.company WHERE booking.company IS NULL OR booking.company='' ''')
    for doctype, columns, name in (
        ('ADM Trip', ['vehicle', 'status', 'planned_start'], 'adm_v2_vehicle_trip'),
        ('ADM Trip', ['driver', 'status', 'planned_start'], 'adm_v2_driver_trip'),
        ('ADM Meeting Booking', ['room', 'status', 'starts_at'], 'adm_v2_room_booking'),
        ('ADM Meeting Booking', ['recurrence_root', 'status'], 'adm_v2_booking_series'),
        ('ADM Maintenance', ['vehicle', 'status', 'starts_at'], 'adm_v2_vehicle_service')):
        frappe.db.add_index(doctype, columns, name)
