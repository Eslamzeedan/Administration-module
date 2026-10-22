from eup_administration.consumables import department_consumption


def execute(filters=None):
    filters = filters or {}
    columns = [{'fieldname': 'department', 'label': 'Department', 'fieldtype': 'Link', 'width': 180, 'options': 'Department'}, {'fieldname': 'item', 'label': 'Item', 'fieldtype': 'Link', 'width': 180, 'options': 'ADM Consumable Item'}, {'fieldname': 'item_name', 'label': 'Item Name', 'fieldtype': 'Data', 'width': 180}, {'fieldname': 'uom', 'label': 'UOM', 'fieldtype': 'Data', 'width': 180}, {'fieldname': 'quantity_issued', 'label': 'Quantity Issued', 'fieldtype': 'Float', 'width': 180}]
    return columns, department_consumption(filters.get('start_date'), filters.get('end_date'), filters.get('company'))
