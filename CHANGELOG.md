# 4.0.0rc1 — independent administration staging candidate

18 additive DocTypes, workflow designer, authenticated self-service, command center, operational dispatch/maintenance/parcel/equipment/contract/incident/task features and isolated acceptance tests. No financial bridge. See V4_IMPLEMENTATION_AND_ACCEPTANCE.md for exact scope and untested gates.

## 2.1.0rc1 — Runner/Careem staging candidate

- Add non-fleet ADM Service Request with Careem Ride and Errand Stop child DocTypes.
- Add requester, runner and department approver roles, row/document permission hooks,
  POST-only approvals/dispatch/execution, private receipts and costs calculated from rides.
- Department/company derived from the requester's active Employee record; prevent
  non-admin self-approval, forged state and foreign/public receipts.
- Company vehicle ADM Trip remains unchanged and is not created for runners.
- No Careem booking or finance/GL integration; test staging first.

# 2.0.0

- Added operational fuel/expense ledgers and protected manager submission, maintenance scheduling/completion and service due data.
- Added trip rejection, resource/document/capacity checks, enabled driver-role authorization and action capabilities.
- Fixed permission hook handling of the v16 ptype argument. Drivers can operate assigned trips through checked actions while ordinary writes remain denied.
- Added structured meeting services and finite daily/weekly recurrence with atomic rollback and series cancellation.
- Added permission-aware dashboard and four reports with separate currency totals.
- Added source-backed v2 workspace and preservation of the original runtime-created workspace.
- Added pre/post schema patches, indexes and booking company backfill; retained all original DocTypes/fields and data identities.
- Added current reads/row locks, odometer overflow rejection, private receipt checks and protected master history.
- Added local and guarded staging tests, read-only preservation snapshots and upgrade/rollback guides.

Input archive SHA256: 4bb17e52fb862c324d4c555e8c2ff960e143f3d57585c782bb6124dd402ea4d4

## 2.2.0rc1 — Admin consumables staging candidate (2026-10-22)

- Added company-scoped `ADM Consumable Item`, `ADM Consumable Location`, `ADM Supply Request` + child lines, append-only `ADM Consumable Transaction`, and administrative returnable custody.
- Added explicit request/approval/issue/cancel workflow, stock receipts, physical count adjustments, stock queries and departmental consumption reports.
- Added strict role, row and company isolation; approvals cannot exceed request and movements never allow negative stock.
- Added Desk action buttons and offline unit/schema tests. Original fleet controller/DocType files left unchanged.
- **Not yet verified against a live Frappe v16/MariaDB bench; no production deployment.**
