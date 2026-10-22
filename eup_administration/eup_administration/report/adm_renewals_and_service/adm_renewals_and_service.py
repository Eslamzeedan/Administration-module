from eup_administration.reporting import renewal_rows

def execute(filters=None):
    return [{"fieldname":"vehicle","label":"Vehicle","fieldtype":"Link","options":"ADM Vehicle","width":150},{"fieldname":"company","label":"Company","fieldtype":"Link","options":"Company","width":150},{"fieldname":"item","label":"Item","fieldtype":"Data","width":150},{"fieldname":"due_date","label":"Due Date","fieldtype":"Date","width":150},{"fieldname":"due_odometer","label":"Due Odometer","fieldtype":"Float","width":150}], renewal_rows(filters)
