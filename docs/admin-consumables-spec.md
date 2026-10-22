# Administrative Consumables — isolated operating ledger (next implementation milestone)

**Goal:** paper, stationery, cleaning supplies and operational consumables controlled by Administration, **without** mixing them with ERPNext Stock Ledger, Warehouses or fixed-asset records.

## Boundary

- Distinct `ADM*` DocTypes, independent quantities and custody, administrative reporting by site / cost center / department.
- **No direct writes** to ERPNext `Item`, `Stock Entry`, `Stock Ledger Entry`, `Warehouse`, `Asset`, `GL Entry`.
- Purchases and tax invoices continue to be handled by Purchasing / Accounts in ERPNext under normal controls. Store document references without generating accounting entries.
- Capital items (printers, laptops etc.) remain in ERPNext Assets / approved asset register, not the consumables ledger.

## Planned data model

| DocType | Fields / behavior |
|---|---|
| `ADM Consumable Item` | category, SKU, UOM, reorder threshold, operational valuation, enabled |
| `ADM Admin Store` | company, site, custodian, active status |
| `ADM Consumable Balance` | per store/item current quantity, updated under locking transaction |
| `ADM Supply Request` | requester, company, department, justification, lines, status, approval |
| `ADM Supply Request Line` | item, requested quantity, approved quantity, issued quantity |
| `ADM Consumable Movement` | receive, issue, return, count adjustment; posting date, quantity, batch reference, approver, immutable audit |
| `ADM Custody` | reusable low-value tools issued to a person, expected return, acknowledgement, condition and return date |

## Workflow

Employee creates supply request → Department Manager approval when required → Admin Storekeeper reserves/issues available quantity → recipient confirms receipt → balance updated atomically.

For receipts: Administration accepts items (recording source Purchase Receipt reference if available); do not duplicate ERPNext valuation. Stock corrections require reason and manager approval; no negative balance.

## Controls

1. Every posted movement is append-only; reversal uses a new counter-movement and approval, never changing historical quantity.
2. Atomic company/store/item quantity update under DB row lock; reject negative stock and duplicate fulfillment.
3. Private attachment for delivery acknowledgements and count adjustment evidence.
4. Transaction totals are operational quantities; avoid implying they are the legal accounting inventory.
5. Reorder minimum alerts, monthly count, audit history and consumption by department/site.
6. No uncontrolled connection between admin consumables and raw materials/production warehouses.

## Acceptance

- Two concurrent issue attempts for last available pack of paper: at most one succeeds.
- Requester cannot approve own request, storekeeper cannot increase stock via issue, runner/driver cannot access stock ledger unless assigned permissions.
- Historical report reconciles receipts - issues + returns + adjustments to live balance.
- No changes to ERPNext Stock/Asset/GL during administrative movements.

**Status:** designed / backlog. Not yet coded, deployed or validated on Frappe.
