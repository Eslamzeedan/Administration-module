# EuP Administration: independent administrative operations

**Explicit business requirement — October 22, 2026:** The module is exclusively for managing company administrative operations. It must not create, modify, approve, submit, cancel or delete any ERPNext accounting, procurement or stock record.

## Allowed operational data
- Internal vehicles, drivers, trips, odometer, fuel expense and maintenance history.
- Meetings/rooms, office supplies and independent internal quantity ledger, custody and stock counts.
- General employee service requests, runner errands and Careem receipts.
- Administration policy approvals, notifications and operational KPIs.
- Optional **read-only** reference to `Company`, `Department`, `Employee` and `User` on the same Frappe site.

## Forbidden write targets
`GL Entry`, `Journal Entry`, `Payment Entry`, `Payment Request`, `Expense Claim`, `Purchase Invoice`, `Purchase Order`, `Material Request`, `Stock Entry`, `Stock Ledger Entry`, `Asset` and any other ERPNext financial/procurement/valuation DocType.

No pricing or fuel cost should reach General Ledger, Accounts Payable, ERPNext Stock or ERPNext Assets. Ledger movements recorded by `ADM Consumable Transaction` have purely administrative significance.

## Release gate
1. Source scan: no ERPNext accounting/procurement/stock **mutating** API or enabled bridge.
2. Disable external webhooks, emails and scheduled jobs in test environment.
3. Snapshot representative accounting, procurement and inventory tables **before** all administration flows.
4. Exercise fleet, meetings, runner, supply issue/return, general approvals, stock counts, custody and reports.
5. Compare data count and integrity hashes **afterwards**, including negative testing.
6. Insist on physical staging separation: independent bench/app checkout, MariaDB database and isolated network.
7. Do not claim financial non-interference was proven until integration tests actually complete on an isolated Frappe v16 site.

NOTE: Application-level independence is not the same as physical isolation. If installed inside ERPNext's Frappe Site, it shares a database server and core DocTypes. For hard separation use another Site/DB (and optionally a separate VM), and avoid direct ERPNext DB credentials.
