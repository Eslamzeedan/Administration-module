# EuP Administration v2 — EuP Egypt

Version **2.1.0rc1** (staging candidate based on v2.0.0). Target: Frappe/ERPNext **v16**, MariaDB/InnoDB, site timezone **Africa/Cairo**. Built from the supplied v0.1.0 ZIP. Locally validated; staging installation, database concurrency and browser checks remain required.

## Runner / Careem MVP (v2.1 staging candidate)

- Separate **ADM Service Request**, **ADM Errand Stop** and **ADM Careem Ride**. Runner travel uses Careem, not ADM Vehicle / ADM Trip.
- Employee department approvals, administration dispatch, runner execution, private ride receipts and verification; POST-only actions. No automatic Careem or accounting integration.
- See **STAGING_RUNNER_ACCEPTANCE.md**. Do not assume this archived v2 baseline matches the currently installed app.

## Included

- Existing trip requests and manager approval/assignment; rejection with reason. Assigned drivers start/end trips through protected POST actions with mandatory readings. Role, enabled login/driver, document expiry, passenger capacity and conflicts are checked.
- ADM Fuel Log: liters, price, calculated cost, reading and private receipt. ADM Trip Expense: tolls, parking, travel and other costs. Requesters/drivers create drafts on their started/completed trips; managers Submit/Cancel.
- ADM Maintenance: schedule, start/complete, completion cost/reading, next service date/reading; conflicting trips are blocked.
- Meeting calendar, capacity and preparation buffer; structured services with manager fulfillment, Daily/Weekly recurrence (2–52 total), atomic creation and cancellation of confirmed series occurrences.
- Dashboard and four reports: Trip Register, Fleet Costs, Meeting Utilization, Renewals and Service. Reports respect account and company restrictions; currency totals remain separate.
- Original workspace retained/recreated only when missing; new **EuP Administration v2** workspace has its source JSON in the app.
- Additive migrations, before/after legacy-data checksums, local tests and guarded staging integration tests.

## Upgrade

Read [UPGRADE_AND_ROLLBACK.md](UPGRADE_AND_ROLLBACK.md) and [STAGING_ACCEPTANCE.md](STAGING_ACCEPTANCE.md). Upgrade the existing app; do not uninstall/reinstall it. Use a separate staging bench: application code is shared by every site in the same bench. No remote or production changes were performed.

The archive has one eup_administration-v2 folder. Its contents are the application root: pyproject.toml and the eup_administration Python package sit side by side. Keep the existing app identity and module names.

## Use

1. Assign Administration Manager / Administration User / Administration Driver as appropriate. Link each driver to an enabled login with Administration Driver. Verify existing Company User Permissions and customized permissions.
2. Request trip → manager Approve & Assign or Reject → assigned driver Start/End. Explain any gap since the latest reading. Zero distance is allowed; backwards/nonfinite readings are rejected.
3. Record Fuel / Record Expense from the trip form. Upload private receipts. Managers review and Submit; cancel/amend submitted costs through Frappe controls.
4. Schedule/start/complete maintenance. Completion updates the latest vehicle reading. Master availability is managed separately: a vehicle marked Maintenance stays unavailable until a manager sets it to Available.
5. Create meetings with services. Repeat Booking includes the seed in the count. A conflict cancels creation of all new occurrences. Cancel Remaining Series cancels all still-confirmed occurrences, including past meetings left confirmed. Complete past meetings first when you need to retain them in utilization reports.
6. Open EuP Administration v2 for the dashboard/reports. Calendar details follow record permissions. Check Room Availability shows occupied intervals without other organizers’ private titles.

## Limits

- Costs are operational records; no automatic ERPNext GL, payment or Expense Claim posting.
- Approval is by Administration Manager. No department-specific approval hierarchy or automatic email reminders.
- Finite Daily/Weekly recurrence only; local wall-clock times follow the site timezone. Test Africa/Cairo DST boundary dates on your installed revision.
- Meeting utilization is booked hours clipped to the selected range, not a percentage of room opening hours. Trip distance is the whole completed trip distance for trips overlapping the planning window.
- Driver interface uses responsive Desk, without a separate mobile app.
- Already-deleted workspace custom content cannot be recovered from the source ZIP; restore it from an older database backup on staging.
- No hard-delete permission is granted by this package.

## Local checks

```bash
python -m unittest discover -s tests -v
python -m compileall -q eup_administration
find eup_administration -name "*.js" -exec node --check {} \;
```

See [VALIDATION.md](VALIDATION.md) for executed checks and remaining staging checks.

## Official v16 references consulted

- [Permission hooks](https://github.com/frappe/frappe/blob/version-16/frappe/permissions.py)
- [Synchronization and orphan cleanup](https://github.com/frappe/frappe/blob/version-16/frappe/model/sync.py)
- [Workspace controller](https://github.com/frappe/frappe/blob/version-16/frappe/desk/doctype/workspace/workspace.py)
- [Document operations and row locking](https://github.com/frappe/frappe/blob/version-16/frappe/model/document.py)

Your exact installed v16 revision must still pass the staging process.

## Consumables (v2.2.0rc1 — staging only)

Administration consumables are independent of ERPNext Stock and Assets. The new
DocTypes are `ADM Consumable Item`, `ADM Consumable Location`, `ADM Supply Request`,
`ADM Supply Request Line`, `ADM Consumable Transaction`, and `ADM Admin Custody`.
A Storekeeper can receive and issue supplies only through protected POST actions;
Administration Managers also reconcile physical counts. Requests have department
approval and one or more supply lines. Ledgers are append-only, and `ADM Trip`
vehicle/odometer records are never created by Runner/Careem errands.

For deploy prerequisites and test cases see `STAGING_CONSUMABLES_ACCEPTANCE.md`.
This version is not certified for production until real bench/migration/concurrency
and permissions tests are completed on a disposable Frappe/ERPNext v16 site.
