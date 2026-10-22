# Runner + Careem v2.1.0rc1 staging acceptance

**Not a production release.** The archived v2 source may differ from the current live app. Compare the live package and its DocTypes before deciding on an upgrade. Never overwrite an active app without a checked rollback plan.

## Preconditions

- Isolated Frappe / ERPNext v16 Staging Bench and cloned sample database (sanitize bank-related attachments); no shared editable source path with production.
- Full site + code backup and verified restore test. Follow UPGRADE_AND_ROLLBACK.md for v2 compatibility considerations.
- Existing v2 fleet and meeting tests pass on the staging site. Test the actual versions of Frappe, ERPNext, HRMS and app.
- Setup active Employees with matching Department, Company and User ID. Grant only necessary role(s): Administration Requester, Administration Department Approver, Administration Runner, Administration Manager.

## Workflow tests

1. From Accounts employee: create Bank service request with destination and multiple errand stops; verify owner, Company, Department are derived server-side.
2. Nonmatching department approver cannot see/approve it; matching approver can; same user cannot approve their own request.
3. Manager assigns runner; runner can view, not direct-edit protected fields. Runner cannot act on a task assigned to another runner.
4. Runner starts mission; uploads 2 private Careem receipts and records 2 legs (outbound/return); total equals receipts and there is **no ADM Trip created**.
5. Attempt public/foreign file URLs, repeat booking references, negative/NaN fare, GET actions, direct status changes: all reject.
6. Runner submits private proof and completion notes; department approver verifies and closes.
7. Finance reviews reconciliation manually; check that no Expense Claim, Payment Entry, Bank Transaction, Journal Entry or General Ledger records were automatically created.
8. Verify rejected, cancelled and urgent requests. Test Cairo timezone handling in user interface.
9. Confirm User Permissions for Company and custom DocPerm overlays do not widen access. Test private File attachments with another normal user, not just the API.
10. Run repeat migration, check DocType source existence and legacy data counts before/after.

## Operational gaps to solve before broader deployment

- Controlled financial custody for cash/cheques, dual handover and finance-only confidential details.
- Route batching, runner SLA, notifications, Careem expense settlement workflow, production reports.
- Attach picker behavior and mobile buttons must be manually checked on the exact Frappe v16 release.

## Local checks (not a substitute for staging)

	docroot=eup_administration/eup_administration/doctype
	python -m unittest discover -s tests -v
	python -m compileall -q eup_administration
	find "$docroot" -name '*.js' -exec node --check {} \;

## Rollout decision

Do not merge/deploy unless original app code is compared, staged migration succeeds, there is no data loss, all role scenarios pass, and rollback has been rehearsed.
