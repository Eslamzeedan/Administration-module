from eup_administration.consumables import consumable_low_stock


def execute(filters=None):
    filters = filters or {}
    columns = [{'fieldname': 'item', 'label': 'Item', 'fieldtype': 'Link', 'width': 180, 'options': 'ADM Consumable Item'}, {'fieldname': 'item_name', 'label': 'Item Name', 'fieldtype': 'Data', 'width': 180}, {'fieldname': 'location', 'label': 'Location', 'fieldtype': 'Link', 'width': 180, 'options': 'ADM Consumable Location'}, {'fieldname': 'uom', 'label': 'UOM', 'fieldtype': 'Data', 'width': 180}, {'fieldname': 'minimum_balance', 'label': 'Minimum Balance', 'fieldtype': 'Float', 'width': 180}, {'fieldname': 'balance', 'label': 'Balance', 'fieldtype': 'Float', 'width': 180}]
    return columns, consumable_low_stock(filters.get('company'))
