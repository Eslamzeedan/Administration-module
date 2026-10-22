# Staging acceptance — required before production

Use a separate disposable v16/MariaDB bench. Restore a representative copy of existing records. Keep outbound integrations/email disabled. Set the timezone to Africa/Cairo. Do not run these tests against erpnext-v16.eup-cairo.local.

## Automated integration tests

These are included but were **not run during local delivery**. They use the real ORM/permissions/database and create test users and records on staging.

```bash
bench --site YOUR_STAGING_SITE set-config adm_allow_integration_tests 1
bench --site YOUR_STAGING_SITE set-config allow_tests 1
bench --site YOUR_STAGING_SITE run-tests --app eup_administration
```

A company must already exist. Review output: skipped tests do not count as a pass. Test fixtures use unique driver logins, avoiding collisions with an existing Administrator driver. Remove the test flags afterward or restore the staging clone. If existing Custom DocPerm blocks a test requester, investigate that configuration rather than resetting production permissions.

## Upgrade and preservation

- Save legacy counts/checksums and permissions while writes are paused; migrate twice and compare after each pass.
- Confirm original workspace content/shortcuts remain and v2 workspace exists after both migrations.
- Verify new booking company values match existing room companies. Inspect migration log for errors or unexpected orphan deletion.
- Restore the pre-upgrade backup in a rehearsal and confirm the rollback procedure works.

## Browser and permission matrix

| Account | Expected behavior |
|---|---|
| Requester | Own trips/bookings; edit draft trips; request/cancel before start; own-trip cost drafts |
| Assigned enabled driver | Read assigned trips, Start/End buttons, readings required; no ordinary trip editing; own-trip fuel/expense drafts |
| Another driver | Cannot list/read/operate the other driver’s trip or see their costs |
| Disabled driver or removed driver role | Cannot operate trips |
| Administration Manager | Assign/reject trips, approve/cancel costs, manage maintenance, fulfill meeting services |
| Company-restricted manager | Cannot read or act on records linked to another company; dashboard and reports obey the same restriction |
| Guest | No API, reports or administration records |

Test direct REST saves as well as visible buttons. Try forging requested_by/organizer, state, odometer, protected recurrence root, submitted amount and fulfilled services. All must reject or normalize protected values safely. Mutating action APIs must reject GET. Public receipts must be rejected; private attachments remain inaccessible to another user.

## Fleet scenarios

- Draft → Requested → Assigned → In Progress → Completed; separate rejected request with reason; cancellation before start only.
- Missing/negative/NaN/Infinity/backwards reading fails. Start gap requires reason. Equal start/end remains valid. Latest vehicle reading follows committed actions only.
- Expired license/insurance, disabled login, unavailable vehicle, capacity exceeded and conflicting driver/vehicle/maintenance fail assignment/start.
- Fuel liters × unit price is computed; manager submission makes a cost reportable; cancel removes it from approved totals. Historical fuel does not alter vehicle reading.
- Maintenance overlap fails; start blocks trips; completion records cost/reading and reports future due service correctly.

## Meetings

- Back-to-back booking at exactly the buffer boundary succeeds; one minute inside the buffer fails. Capacity and disabled room fail.
- Repeat Daily/Weekly across month/year and Cairo DST boundary. Original organizer and requested services are retained.
- Conflict on the final recurrence leaves no earlier new occurrences and no seed series annotation.
- Only the organizer/manager can modify/cancel visible series bookings; another requester sees occupancy times without private titles.
- Calendar renders and report booked hours are clipped to date filter bounds.

## Concurrent database/API checks

Use two authenticated browser/API sessions on staging and inspect committed data after both calls. Application locks and current reads prioritize safety; a database deadlock may reject one request, which may be retried after reloading. No failed request may leave partial data.

1. Two overlapping assignments to the same vehicle or driver: at most one succeeds.
2. Two simultaneous starts of the same trip: one state transition/reading update only.
3. Simultaneous room bookings: at most one overlapping booking commits.
4. Maintenance scheduling versus trip assignment: no committed overlap.
5. Two recurring series on the same room: no overlapping occurrence and no partial series.
6. End Trip versus maintenance completion: latest reading cannot go backwards.

## Sign-off

Record exact Frappe/ERPNext/app versions, migration log, test results (including skips), browser screenshots, preservation snapshots and backup restore result. Only approve production when critical checks pass on that exact revision.
