# rc6 acceptance — 2026-11-25

Base: b1094009095832669caf9f62fdca6c089399d84a. Status: release candidate; not production acceptance.

## Changes

- Register the missing original Workspace source; preserve original/v2/v3 content, roles, child rows and custom fields on forced imports. Do not use Workspace.standard, absent in Frappe 16.31.0.
- Add opt-in adm_single_navigation: one EuP Administration desktop icon/sidebar. Hide legacy navigation without deleting saved configuration. Existing sites retain their navigation unless opted in.
- Add real two-process MariaDB races for assigned-driver Start, stop arrival/departure and End; require exactly one success, the intended duplicate rejection, unchanged winning timestamps, 85 km distance and vehicle reading.

## Actual execution on isolated Ubuntu / Python 3.14.7 / Frappe 16.31.0 / ERPNext 16.32.3

- 249 offline Python tests PASS, no skips.
- 36 Node frontend/proxy tests PASS, no skips (frontend implementation unchanged).
- Full final integration suite: 40/40 PASS, no skips (including both new Workspace/navigation cases).
- 2 added real import/navigation tests PASS: repeated forced import of all three Workspace names preserves customization; opt-in navigation shows exactly one icon.
- 10 real-role acceptance tests PASS with persisted-data integrity.
- 4 existing independent-transaction races PASS: equipment, workflow/audit, feedback uniqueness, parcel receipt.
- 4 new assigned-driver races PASS: Start, stop arrival, stop departure, End; 12,500 → 12,585 = 85 km.
- Clone upgrade and repeated migration passed legacy-record, permission and Workspace comparisons. A further migration after the rc6 Workspace/navigation fix also passed these comparisons.
- Full database/config/public/private backups were taken for source and clone before changes. No production changes or database restoration in this pass.

The first navigation experiment exposed the old missing Workspace source: Frappe deleted the legacy Workspace on the disposable clone and integration correctly failed. The fixed candidate registers the source and protects forced imports. The missing clone Workspace was recreated from defaults; this does NOT demonstrate restoring old customization from backup. The source site was not migrated/deleted.

## Pending gates

Fresh staging reinstall requested by the user is NOT EXECUTED: MariaDB root authentication failed before destructive actions; the operator is checking credentials. Fresh fixture setup, clean install, final browser/mobile/RTL/accessibility checks with limited employees/drivers, separate-account realtime, and restoration of the new backup remain UNVERIFIED. Previous rc5 restore evidence is recorded separately in CLONE_ACCEPTANCE.md and is not a new run. Final-head CI must be checked after publication.

Do not promote to a stable production release until these gates are passed. No GPS, external-calendar provider, native mobile application or financial bridge is added.

## Opt-in navigation on a backed-up independent staging site

~~~bash
bench --site YOUR_STAGING_SITE set-config adm_single_navigation 1
bench --site YOUR_STAGING_SITE migrate
bench --site YOUR_STAGING_SITE clear-cache
~~~

## Additional races (guarded disposable clone only)

~~~bash
bench --site test-administration-v4-restore.local execute eup_administration.tests.clone_acceptance.run_trip_races
~~~

Expected four RACE PASS lines and race_cases=4, passed=true, protected_unchanged=true. Synthetic identities/trips/vehicles remain only on the exact guarded clone. Never run on production. Private backups, credentials, raw company data and snapshots must not be published.

## Source-site comparison

After clone acceptance, original-site file hashes, protected accounting/stock tables and all captured application/HR/permission/Workspace hashes matched. The User table retained 16 rows but its full-content hash changed; the cause was not established in this pass (the source UI remained available). Therefore a complete unchanged-source snapshot is NOT marked PASS. No source database restore or reinstall occurred.
