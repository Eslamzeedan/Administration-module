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
transaction and are rolled back. Frappe file rollback removes generated test bytes;
full hashes verify that app/HR/security/protected rows and files are unchanged.
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
