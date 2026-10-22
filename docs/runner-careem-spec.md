# Runner & Errands — Careem-first MVP

**Baseline:** The currently operational `eup_administration` Frappe/ERPNext v16 application has not yet been imported into this GitHub repository. The existing local archives `eup_administration.zip` and `eup_administration-v2.zip` must be compared with the actual installed app before source import or deployment.

## Business model

- Employee in Accounts, Logistics, HR, Purchasing, Sales, etc. creates an Administration Service Request.
- Department approver accepts/rejects it. Approvers may not approve their own requests or own errand completion.
- Administration Manager dispatches the request to a designated **Administration Runner**.
- Runner uses **Careem** for travel, not an `ADM Vehicle`. One errand can have multiple Careem rides.
- Capture pickup/drop-off, date/time, Careem booking reference, actual EGP fare and **private receipt** per ride. Employee/runner records execution proof; department approver verifies completion.
- Administration does **not** integrate with the Careem booking API; rides are booked outside the application and entered manually.
- Operational fares are not Expense Claims, GL entries, cash disbursements or bank transactions. Finance settles externally after verifying receipts.
- **Never** put bank account, card, cheque numbers or cash handling details in the request description. Sensitive financial custody is a follow-on restricted DocType, not a free-text field.
- Runner rides **must not** create any `ADM Trip`, require a company vehicle, touch odometers, fuel logs or company fleet cost reporting.

## MVP DocTypes

| DocType | Kind | Critical fields |
|---|---|---|
| `ADM Service Request` | master | request_type, purpose, destination, requested_by, department, company, priority, needed_by, assigned_runner, status, amount totals, proof |
| `ADM Errand Stop` | child | entity/location, required action, non-sensitive envelope reference |
| `ADM Careem Ride` | child | pickup, drop-off, date/time, Careem booking reference, fare, private receipt |

All rows are scoped by Frappe permission hooks. Request ownership and department/company are derived **on the server** from Employee. New roles: Administration Requester, Administration Runner, Administration Department Approver. Existing Administration Manager and System Manager retain administrative access.

## Lifecycle

`Draft → Pending Approval → Approved → Assigned → In Progress → Completed → Closed`.

Terminal/alternative outcomes: Rejected (from Pending Approval), Cancelled (before work starts). Changes to lifecycle are permitted only by POST workflow actions, never via direct form edits. Assigned runner is checked on every action. Finance must review operational expense evidence separately before reimbursement.

## MVP acceptance cases

1. Requester cannot read another department's request without assigned/approver permission.
2. Department approver can only approve for matching Employee company and department, and not their own.
3. Runner cannot reassign tasks, approve them, or close them, and can only add Careem rides to tasks assigned to them.
4. Public receipts, foreign private files, invalid fares (negative, NaN) and duplicate ride references are rejected.
5. Completion requires private execution proof; closure requires an independent approver.
6. No new company fleet trip or odometer record is created when recording a Careem ride.
7. Earlier `ADM Trip` and meeting room flows continue passing regression tests.
8. No production deployment until the isolated Staging Bench has passed a schema migration and end-to-end scenario review.

## Beyond MVP

- Runner route batching across multiple requests
- Per-stop execution statuses, SLA alerts, in-app notifications, runner mobile view
- Explicit cash / cheque custody handover with Finance-only fields and dual acknowledgements
- Careem cost reimbursement approval and account reconciliation
- Administration Service Desk employee landing page
