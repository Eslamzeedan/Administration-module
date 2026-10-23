# Administration 4.0.0rc2 — staging UI and integrity review

Release candidate on PR #9, based on d06175f. No production deployment or blanket claim
of complete acceptance. Preserve the user's in-progress maintenance form.

## Changes
- Scoped navy/teal design for Administration pages/forms/lists and employee self-service:
  responsive cards, clear headings, readable spacing, status badges, keyboard focus,
  logical RTL spacing, reduced motion and loading/empty/error states.
- New request hub, command center, fleet/meetings overview and portal presentation.
- Native Promise wrapper makes existing form action calls compatible with v16 buttons.
- Workflow template removes automatic blank rows without overwriting configured drafts;
  preview/condition builder validates incomplete transitions and non-list JSON.
- Session-bound employee context explains missing profiles without granting access.
  Role/company/self-approval/revision guards remain server-authoritative.
- Deterministic insert naming fixed in registry, approval cases and requester feedback.
  Legacy hash-named approval cancellation and duplicate feedback are recognized.
- Registry sync locks its source, maintains a canonical ADMREG row and removes only
  duplicate derived index rows for that same source. Original requests, events,
  approvals, feedback and notification history are retained.
- A post-model-sync patch rebuilds the index under the migration flag without events/
  notifications. The existing DocType JSON schemas remain unchanged.

## Evidence
The PR records actual final-commit CI results. Local checks include all JavaScript syntax
and ten executable frontend regressions. Python offline checks run in CI because this
workstation has no installed Python. New Python regressions exercise v16 naming, repeated
hooks, status changes, repair/idempotency, migration, notification suppression, approval
cancellation, duplicate feedback and employee-context scope. Three live registry tests added.

Prior d06175f evidence: 159 offline tests and 26/26 live integration tests (user's logs),
plus agent-operated browser QA that found the defects. Those passes do not verify rc2.

| Area | Review coverage | Remaining live acceptance |
|---|---|---|
| Fleet/trips/maintenance | Existing authorization/state tests, source review, Promise-compatible actions | Browser actor/action matrix |
| Meetings/check-in | Earlier UI capacity/conflict/buffer/cancel checks; existing tests | Repeat on new assets; check-in time window |
| General approvals | Existing self-approval tests; naming/cancellation regression | Two distinct actors in browser |
| Administrative supplies/custody | Existing boundary/controller tests; scoped form styling | Storekeeper/requester/private-file/QR UI |
| Nine v4 operations | Existing validation/scope/idempotency tests; state-aware actions | Matching active Employee/User company matrix |
| Workflow designer | Template/preview/condition regressions; live save/start/transition/details/feedback/freeze/disable lifecycle | Concurrent revisions and distinct approvers |
| Dashboards/portal | Live company/count/rating/weekly report; invalid-range error and successful retry; 390px layout | Portal employee login, cross-company role matrix and RTL |
| Registry migration | Idempotent repair tests and three real-site tests | Backup/migrate/hash comparison/repeat |
| Notifications/scheduler | Existing opt-in guards; rebuild emits no events | Remain disabled unless separately tested |
| Production | No access/change | Separate decision after acceptance |

## Disposable VM update
1. Save the current maintenance draft if needed. Stop only the foreground port-8004
   test server with Ctrl+C in its own terminal.
2. From /home/frappe/frappe-bench-v4, fetch the reviewed feature branch without changing
   the checkout. Extract tools/update_ui_staging.sh from the exact reviewed commit using
   git show, then run that script with the same full commit SHA. Exact commands follow
   CI in the chat; no moving-branch checkout, reset, force-push or reinstall.
3. The script verifies real paths for this bench/site/all three apps, clean feature
   checkout, expected repository and stopped test server. It creates a rollback branch,
   backs up DB/files before fast-forward, migrates, builds only this app, checks legacy/
   permission/protected hashes, runs targeted/full tests and leaves the scheduler off.
   Failure stops the script; retain logs, do not reinstall or continue to production.
4. Start bench --site test-administration-v4.local serve --port 8004 --noreload.
   Refresh browser assets. Use an existing linked active Employee/User in the right
   company, or staging Administrator for manager views. Do not weaken the guards,
   add broad roles or fabricate HR/financial DocTypes to make acceptance pass.
5. Repeat the browser/role matrix and capture actual evidence.

## Rollback
Keep printed backup paths and rollback branch. Stop only the test server; with checkout
clean, switch --detach to that rollback branch, rebuild this app and clear only the test
site's cache. Code rollback does not undo the derived-index repair. Database rollback
requires restoring the exact previous database/public/private-files backup to
test-administration-v4.local only, after reviewing the paths. No production commands.

## Subsequent live browser acceptance at 38972b2
The user supplied the guarded updater success tail (OK, unchanged protected/legacy data,
STAGING UPDATE PASSED). The tail omits Ran N tests, so the exact live count is unrecorded.
The agent then tested the real staging UI in Chrome with the user-provided Administrator
session: command-center company selection/counts, a distinct test policy and facility
ticket, Start -> Draft -> Submit -> Review -> Complete -> Completed, operational details,
feedback, a second feedback attempt from a stale tab, and policy immutability. The duplicate
was rejected by the unique reference-key guard; dashboard still showed one response at 5/5.
The request has three workflow audit records. Changing the used policy title was rejected;
the original title was restored and the test policy successfully disabled. The test ticket
remains Completed as acceptance evidence; no existing policy, role or Employee was modified.
This was a direct-transition test policy; it does not prove two-person approval acceptance.
A frontend follow-up replaces only this app's intro banner when v16 appends repeated
messages, preserving unrelated warnings. Its live installation/retest remains pending.
After the viewport override settled, Chrome measured clientWidth=390 and scrollWidth=390.
The command-center cards and controls fit without horizontal overflow. A reversed date
range was rejected by the server, Refresh stayed enabled, and correcting the range then
using Try again restored the original counts and single 5/5 response. The weekly-report
action also loaded successfully. The temporary viewport override was reset; desktop
measured 1440px again. RTL is still unverified. Browser tests still require an appropriate
employee login for the portal and independent approvers for the approval matrix.
No production or financial write.
