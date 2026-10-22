# EuP Administration Management

Private GitHub home for the **EuP Egypt Administration** Frappe application, targeting **Frappe / ERPNext v16**.

> **Important:** The working `eup_administration` app already exists outside this repository. This repository has not yet been populated with that existing source. Do **not** install the repository over the running app or replace production files. First import and review the current application code, DocTypes, hooks, migrations and dependencies in an isolated staging environment.

## Scope

1. **Administration Service Desk** — one employee-facing request portal with approvals and assignments.
2. **Runner & Errands** — cross-department bank, shipping, government, document and purchasing errands. **Runners normally travel using Careem, NOT company fleet vehicles.** Capture booked journey identifiers, pickup/drop-off, estimated and actual fare, receipt, payer, approval and reconciliation. Never assume Careem API integration exists.
3. **Fleet** — separate company cars, drivers, maintenance, odometer readings and authorized vehicle trips. Runner tasks must not automatically create fleet trips.
4. **Administrative Consumables** — stationery, paper, cleaning materials and other supplies in a dedicated administrative ledger separated operationally from ERPNext Stock and fixed Assets.
5. **Meeting Rooms** — preserve and extend existing booking features.
6. **Dashboard** — turnaround time, SLA, pending approvals, runner workload and consumption by department.

## Deployment safeguards

- Preserve the existing `eup_administration` app identity and installed DocTypes until a migration audit proves what can be changed.
- Stage first: separate bench, database, site, code checkout and backups.
- No direct edits or deployments to `erpnext-v16.eup-cairo.local` from this repository.
- Keep `main` deployable after source import and tests; implement changes in `feature/*` branches and review pull requests.
- Do not store bank account numbers, cheque images or confidential documents in GitHub. Documents uploaded in Frappe must be permission-protected and retention-controlled.

## Implementation sequence

- [ ] Import original app source; inventory existing DocTypes and migrations; record baseline and pass smoke tests.
- [ ] Runner & Careem transport request workflow, approvals, dispatch, proof, fare reconciliation.
- [ ] Administrative consumables separate operational ledger, requisitions, receipt, issue, adjustment, counts.
- [ ] Service Desk and notifications.
- [ ] Fleet and meeting rooms integration, reporting and UI polish.

Detailed specifications live in `docs/` on the development branch. Do not treat unreviewed design documents as deployed features.
