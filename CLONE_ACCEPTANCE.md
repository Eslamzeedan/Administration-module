# Remaining release acceptance — restored test clone only

The installed application is RC4. The user supplied 8/8 v4 and 30/30 full-site
integration passes at 4f2b7a2. A later agent-operated Chrome pass proved distinct
approval/rejection and their immutable audits, required rejection reason, recipient
receipt and a rejected stale-tab repeat, employee-linked portal creation, Arabic/RTL,
and one denied cross-company read. A two-tab workflow attempt was also rejected
with “Workflow changed. Reload before continuing.” Its valid request/rejection added
two audit events (six total on the synthetic rejection case, last revision 6).
These are actual scoped checks, not complete release acceptance.

## Added executable acceptance

`tools/restore_v4_acceptance_clone.sh BASE TARGET` is user-run from exactly
`/home/frappe/frappe-bench-v4`. It requires a clean feature checkout, pinned ancestry,
the expected remote, stopped test ports, physical app/site paths and no existing
`test-administration-v4-restore.local`. No primary site/bench is accepted.

It creates a full source backup and rollback branch, installs only the reviewed
test/operator code, takes source hashes, creates a fresh uniquely named clone DB,
restores DB/public/private files into that clone, and compares administrative,
HR/security, protected-table and file hashes. Source DB credentials are never
copied to the clone. Only test-fixture settings and encryption keys are copied
without printing them. Root/new-site password prompts are entered by the user
privately. No --force validation bypass, reinstall, production restore, automatic
site deletion or automatic restore on failure.

The clone remains muted, in maintenance and with scheduler/jobs off. It runs the
ordinary full app suite (at least 30 real tests, no skips), compares restored data
again, then explicitly runs ten additional real-permission tests:

- Ordinary Administration User/Employee portal creation → terminal workflow →
  feedback/uniqueness, including scoped visible records.
- Owner/operator visibility and forbidden assignment/detail writes.
- Cross-company read/write/report and forged self-service identity fields.
- A requester who really has the approver role still cannot self-approve; direct
  forged-state saves remain forbidden.
- Distinct actors for sequential approval steps and stale revisions.
- Expired delegation rejection and valid delegation actor/delegator audit.
- Disabled-delegator rejection.
- Actual private-file bytes and owner/stranger/foreign download permissions;
  public attachments are rejected by the operation controller.
- Recipient-only/one-time receipt and booking owner release permissions.
- Required rejection reason, retained source state and rejected decision replay.

Five temporary User/Employee identities use existing Company/Gender/Role masters;
they receive no password/welcome email. They exist only inside the clone matrix
transaction and are rolled back. After DB rollback, any remaining new synthetic
fixture bytes are moved into a private evidence directory under bench/logs. Every
DB hash and every original file must already match; only the exact generated
filename/content/hash pattern is eligible, and any persisted File reference blocks
cleanup. No existing file is removed. The complete original snapshot must then
match exactly.
No dummy ERPNext/financial DocTypes or master data are generated.

Four further races use separate Python processes and database connections. Both
workers establish a consistent-read snapshot before a barrier releases them. The
harness requires the precise expected rejection and final persisted invariants;
two successes, missing workers, unrelated permission/import errors, deadlocks or
zero coverage cannot be reported as a pass. Cases: overlapping equipment bookings,
same workflow revision, feedback uniqueness, and one-time parcel acknowledgement.
New synthetic race rows are intentionally retained on the disposable clone only.
The source snapshot must remain unchanged. These races may expose defects that
the existing sequential tests could not; no passing VM result is claimed yet.

On any failure, keep logs and stop. A partly created clone is retained for
diagnosis; the script refuses to overwrite it on rerun. Any source test maintenance
mode is restored only after review. No primary service is restarted or killed.

## Real-time browser acceptance

`./env/bin/python apps/eup_administration/tools/serve_v4_acceptance.py` runs in the
foreground on the same guarded test bench after the source site is reopened. It
starts only a loopback web process, Frappe Socket.io on a private Unix socket and
a fixed same-origin proxy at the existing port 8004. It starts no scheduler,
worker, Redis or production service, changes no framework/app code or existing
configuration, and stops only its own child PIDs on Ctrl+C. Private runtime config
contains only the existing bench Redis endpoints and is not printed. The proxy
fixes the site header, preserves normal authentication/origin checks, and accepts
no arbitrary proxy destination or unrelated WebSocket upgrade.

Why a bridge: Frappe v16's browser client uses the page origin outside dev_server,
whereas a standalone bench serve has no Socket.io route. This does not require
weakening authentication or editing Frappe/ERPNext. References:
[client](https://github.com/frappe/frappe/blob/v16.31.0/frappe/public/js/frappe/socketio_client.js),
[node configuration](https://github.com/frappe/frappe/blob/v16.31.0/node_utils.js),
[namespace authentication](https://github.com/frappe/frappe/blob/v16.31.0/realtime/middlewares/authenticate.js),
[restore command](https://github.com/frappe/frappe/blob/v16.31.0/frappe/commands/site.py).

CI runs the pure clone safety/race-evidence regressions, proxy HTTP/auth/header/
WebSocket tests, Python compilation including tools, and shell syntax. CI is not
Frappe integration, actual restore or authenticated browser-delivery evidence.
Live restore/matrix/race and real-time acceptance remain pending user-run VM logs
and the subsequent browser check. Accessibility, the remaining operation-specific
UI cases and an ordinary-user browser login are still tracked separately.

First real operator run reached 4c58d41, created the source backup and stopped at
the read-only source snapshot guard before any clone was created. The guard had
accepted only the bench root, whereas bench execute runs from its sites directory.
The follow-up accepts only these two exact named staging directories, retaining
the strict resolved-site/database/config checks. An offline regression checks the
sites working directory and rejects the primary bench and unrelated paths. This
failed first attempt is not restore/matrix/race acceptance; retain its logs/backup.

## Real clone run and explicit resume

The user-run retry at 685eabd successfully restored DB/public/private files and
matched all original hashes. All 30 application tests passed without skips and
left restored app/HR/security/protected data and file hashes unchanged. All ten
real-role cases passed, but their final integrity assertion failed. A subsequent
read-only diagnostic on log adm-complete-acceptance-FnpkNi proved: no changed
tables, protected data unchanged, exactly two added files, no removed files and
no changed original bytes. The fixture file rollback had left the synthetic
private/public pair on disk. This is a failed cleanup gate, not a matrix integrity
pass. No races ran and no real-time success is claimed.

The correction retains every integrity condition and quarantines only provable
new synthetic orphan bytes after full DB rollback. Seven offline regressions
reject changed rows/protected data, removed/modified originals, unrelated paths,
non-fixture bytes, changed hashes and incomplete inventories.

For the already existing clone, use tools/resume_v4_acceptance_clone.sh BASE TARGET
adm-complete-acceptance-FnpkNi. It refuses a dirty/wrong checkout, active test
ports, unpaused sites, mismatched original restore/full-suite evidence or a
changed source snapshot. It never creates/restores/drops a site or database. The
one-time recovery requires exactly one private and one public fixture file,
retains the bytes and manifest outside site files, then verifies the exact old
snapshot. It reruns all ten cases and four races and compares source hashes again.
Only a fully successful run reopens the source test site. If it stops after race
fixtures were committed, keep the logs/clone and diagnose; do not rerun recovery
or a site-creation/restore command.

## Verified matrix and race-startup correction

The user installed 84e8ddd and ran the guarded resume (log
adm-resume-acceptance-1P3IXl). Source hashes matched. The original two synthetic
files were retained as evidence, all ten real-role cases passed again in 5.885s,
and MATRIX INTEGRITY PASS confirmed the exact original data/file hashes after
cleanup. This supersedes the earlier matrix-integrity-pending state above.

The first race then stopped before either worker reached its barrier. Both logs
in adm-clone-race-1ad_anfv show FileNotFoundError during frappe.connect: the logger
tried bench/clone/logs/database.log rather than bench/sites/clone/logs/database.log.
Frappe v16 logger paths are relative to the sites working directory, even when
frappe.init receives an absolute sites_path. This was a harness startup error,
not a concurrency pass or evidence of a controller defect. The committed synthetic
equipment fixture is retained on the clone; no booking outcome was produced.

The correction launches both race children with cwd=BENCH/sites and validates
clone paths/config/distinct DB before connect. The test web child also changes
from its validated bench root to sites before importing/serving Frappe, preventing
the same relative logging failure. No directories, symlinks, framework settings,
logging bypasses or production services are added. Offline regressions exercise
two real child processes writing relative site/bench logs and synchronizing,
startup-failure log retention, rejection before DB connect and web runtime cwd.
These tests do not emulate a successful live DB race.

Use tools/resume_v4_races.sh BASE TARGET RESTORE_LOG MATRIX_LOG for the existing
clone after this known startup failure. It checks original restore/full-suite/
completed-matrix snapshots, current source hashes and clone HR/security/protected/
file hashes. It retains earlier synthetic race rows, creates no site/database,
performs no restore or fixture-file recovery, and reruns the four strict races.
Only successful races and the final unchanged-source comparison reopen the source
test site. Failures retain logs/clone and stop; no race success is claimed yet.

Logger reference: https://github.com/frappe/frappe/blob/v16.31.0/frappe/utils/logger.py

## rc5 — actual simultaneous booking defect

The user installed ff2214f and reran from adm-resume-races-BrOK6w. Source hashes
and prior complete-matrix evidence matched; clone files/security/HR/protected
data were unchanged. Both independent workers then committed overlapping
bookings (slld2r0aid and sllaotiikp). The strict exactly-one-success gate failed.
This is an actual application concurrency defect, not a harness startup error.
Both synthetic rows are retained on the restored clone for evidence. The later
workflow/feedback/parcel races did not run.

rc5 fixes the equipment controller conflict read with a bound SELECT FOR UPDATE
while holding the existing equipment mutex. An ordinary SELECT after a name-only
lock can still read the transaction's older consistent-read snapshot. Equipment
availability is read with Frappe get_doc(for_update=True). The same locked-read
review changes protected operation/recurring-task loads and workflow document/run
loads to current reads, including run lookup and approval-attempt history. Used
policy structure remains frozen; all existing company/role/requester/revision
checks and unique feedback constraints remain intact. No global transaction
isolation change, commit, permission relaxation, financial write or ERPNext edit.

Offline regressions model a stale snapshot that hides a committed booking,
revision, current recipient or delivered timestamp. They execute the real
controller functions and require the intended denial with no save; query identity
and strict half-open overlap parameters stay bound. They are not live DB race
evidence. The original four strict simultaneous races are unchanged.

Because controllers changed, resume_v4_races.sh now reruns the full app suite
(at least 30, no skips) and all ten real-role cases before the races. It compares
the complete retained clone snapshot before/after this revalidation, including
the earlier synthetic conflicting booking evidence. No existing booking is
automatically deleted, released or repaired. Source hashes are compared again
only after all strict races pass; the source test server stays closed on failure.
The revised resume and rc5 live results remain pending operator execution.

Frappe locking-load reference: https://github.com/frappe/frappe/blob/v16.31.0/frappe/model/document.py
