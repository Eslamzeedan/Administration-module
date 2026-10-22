# EuP Administration v2.2.0rc1: consumables staging acceptance

**STATUS: STAGING CANDIDATE ONLY. DO NOT INSTALL DIRECTLY ON PRODUCTION.**

## Boundaries

- The `ADM Consumable *`, `ADM Supply Request *`, and `ADM Admin Custody` objects are dedicated operational records. They DO NOT alter `Item`, `Warehouse`, `Stock Ledger Entry`, `Asset`, `GL Entry`, or `Payment Entry` in ERPNext.
- Runner/Careem requests remain a separate workflow and create no `ADM Trip` or vehicle odometer entries.
- Do not store financial or official accounting asset valuations only in this module. Finance must retain approved financial controls in ERPNext; this module is a physical quantity/audit trail.
- A returnable office item such as a stapler can go into `ADM Admin Custody`; financially capitalized assets must remain in ERPNext Asset.

## Before migrating any site

1. Export and compare the currently installed `eup_administration` code with this candidate. The historical v2 archive might **not** be identical to code on the live site; stop if they differ.
2. Create a **disposable** Frappe v16 + ERPNext v16 staging environment (MariaDB, Redis, bench) with a separately restored *scrubbed* site backup; use separate filesystem paths, ports and site URL, and no live integrations.
3. Take a database backup and save hashes of existing `ADM Vehicle`, `ADM Trip`, `ADM Driver`, `ADM Fuel Log`, `ADM Trip Expense`, maintenance/meeting DocTypes and records. Never use the production bench for staging.
4. Verify `bench --version`, `bench --site <STAGING_SITE> list-apps`, `bench --site <STAGING_SITE> backup` and confirm a known-good restore point.

## Migrate only the disposable site

```bash
# Example: run as the frappe service account on a disposable bench.
cd /home/frappe/frappe-bench-staging
# Put verified candidate into apps/eup_administration with a separate code checkout.
bench --site <STAGING_SITE> set-config adm_allow_integration_tests 1
bench --site <STAGING_SITE> migrate
bench build --app eup_administration
bench --site <STAGING_SITE> run-tests --app eup_administration
```

`<STAGING_SITE>` is a placeholder, NOT the live `erpnext-v16.eup-cairo.local`. The integration suite explicitly skips production and unflagged staging sites. Treat any skipped tests as **not executed**, not passing.

## Manual test, with an Admin and at least 3 separate test users

1. Create a consumable item (`PAPER-A4`, `Nos` or `Ream`, Company) and enabled Admin Consumable Location.
2. Grant a test requester `Administration Requester`, a different departmental approver `Administration Department Approver`, and test storekeeper `Administration Storekeeper`; map each to an active Employee and Company. Verify each user can see only authorized records.
3. Post a stock **receipt** of 10 reams, with reference `TEST-RECEIPT-001`.
4. As requester, create Supply Request for 8; submit. Verify self-approval blocked.
5. As a different same-department approver, approve 6, not 8. Wrong-department approval must fail.
6. As storekeeper, issue 4; request becomes **Partially Issued**. Issue 2 more; request becomes **Fulfilled** and closes. Attempt another issue; must fail.
7. Try to issue 5 more than on-hand; must be denied without creating a movement or changing the request quantity.
8. Verify append-only movement history and a remaining stock balance of 4 from the original 10 (unless another test posted stock).
9. Perform a physical count adjustment to 3 as Manager with a written reason; verify one Adjustment Out entry and balance 3.
10. Check low-stock and department-consumption read-only APIs with appropriate company/role checks. Verify a non-admin cannot query another company's records.
11. Test returnable custody with an active Employee; use Return action, including mandatory return condition; edit after return must fail.
12. Confirm old vehicle trip start/end odometer and maintenance conflict checks, meeting booking and Runner/Careem flows still work, with no changed old schema or loss of data.
13. Attempt direct API creation/update/delete of a posted `ADM Consumable Transaction`; must be forbidden, including when the caller is an administrator.
14. Repeat overlapping stock issuance and stock count under concurrent sessions to confirm MariaDB row locks and no negative balances.

## Important functional caveats

- The order/approval workflow is implemented via secured POST methods, not Frappe's built-in Workflow state machine; do not enable an overlapping Workflow without a design review.
- Cost/valuation and integration with Purchase Invoice, Payments, ERPNext Stock and financial assets are **not implemented**.
- No native Careem booking/payment integration is included; the Runner flow logs Careem rides and private receipts only.
- Low-stock thresholds apply per location, with the item's global threshold; for per-location thresholds add a configuration DocType.
- The unit tests use mocks and structural tests; they do not prove that real Frappe v16 install/migrate, DocPerms, concurrency or browser rendering works.
- Original source v2 baseline must be compared to the **actual site code** before deployment.

## Rollback

On staging, restore its pre-migration database + matching pre-upgrade app checkout together; do not just reverse the Git commit. Rehearse restore. For production, proceed only with an approved deployment/rollback plan after signoff on data preservation and the acceptance checklist.
