#!/usr/bin/env bash
# Update only the already-provisioned disposable VM. Never stop/modify another bench.
set -Eeuo pipefail
if [[ "$#" != 1 ]]; then
  echo "Usage: bash tools/update_ui_staging.sh REVIEWED_FULL_COMMIT_SHA" >&2; exit 2
fi
TARGET="$1"
SITE=test-administration-v4.local
BENCH=/home/frappe/frappe-bench-v4
BRANCH=feature/administration-v4-independent-staging
cd "$BENCH"
[[ "$(pwd -P)" == "$BENCH" ]]
[[ "$(realpath "sites/$SITE")" == "$BENCH/sites/$SITE" ]]
for app_name in frappe erpnext eup_administration; do
  [[ "$(realpath "apps/$app_name")" == "$BENCH/apps/$app_name" ]] || {
    echo "Refused: app source must belong to the isolated bench." >&2; exit 2;
  }
done
APP="$BENCH/apps/eup_administration"
[[ "$(git -C "$APP" branch --show-current)" == "$BRANCH" ]]
[[ -z "$(git -C "$APP" status --porcelain)" ]]
[[ "$TARGET" =~ ^[0-9a-f]{40}$ ]]
[[ "$(git -C "$APP" remote get-url adm-v4-fixes)" == "https://github.com/Eslamzeedan/Administration-module.git" ]]
command -v ss >/dev/null
if [[ -n "$(ss -ltnH 'sport = :8004')" ]]; then
  echo "Stop only the foreground test server on port 8004 using Ctrl+C, then rerun." >&2
  exit 2
fi
LOGDIR="$BENCH/logs/adm-ui-$(date +%Y%m%d-%H%M%S)"
mkdir -p "$LOGDIR"
ROLLBACK="adm-ui-before-$(date +%Y%m%d-%H%M%S)"
git -C "$APP" branch "$ROLLBACK"
printf 'Rollback branch: %s\nLogs: %s\n' "$ROLLBACK" "$LOGDIR"
bench --site "$SITE" backup --with-files | tee "$LOGDIR/00-backup.log"
git -C "$APP" fetch adm-v4-fixes "$BRANCH"
git -C "$APP" merge-base --is-ancestor HEAD "$TARGET"
git -C "$APP" merge-base --is-ancestor "$TARGET" "adm-v4-fixes/$BRANCH"
git -C "$APP" merge --ff-only "$TARGET"
[[ "$(git -C "$APP" rev-parse HEAD)" == "$TARGET" ]]
bench --site "$SITE" set-maintenance-mode on
bench --site "$SITE" disable-scheduler
bench --site "$SITE" execute eup_administration.deployment.ui_snapshot > "$LOGDIR/before.json"
env/bin/python -m json.tool "$LOGDIR/before.json" >/dev/null
bench --site "$SITE" migrate 2>&1 | tee "$LOGDIR/01-migrate.log"
bench build --app eup_administration 2>&1 | tee "$LOGDIR/02-build.log"
bench --site "$SITE" clear-cache
bench --site "$SITE" execute eup_administration.deployment.ui_snapshot > "$LOGDIR/after.json"
env/bin/python - "$LOGDIR/before.json" "$LOGDIR/after.json" <<'PY'
import json, sys
with open(sys.argv[1]) as stream:
    before = json.load(stream)
with open(sys.argv[2]) as stream:
    after = json.load(stream)
if before != after:
    changed = [key for key in before if before.get(key) != after.get(key)]
    raise SystemExit("STOP: source/permission/protected snapshot changed: " + ", ".join(changed))
print("PASS: legacy sources, permissions, workspaces and protected tables unchanged.")
PY
bench --site "$SITE" run-tests --app eup_administration \
  --module eup_administration.tests.test_registry_integrity 2>&1 | tee "$LOGDIR/03-registry-tests.log"
bench --site "$SITE" run-tests --app eup_administration 2>&1 | tee "$LOGDIR/04-all-tests.log"
if grep -Eiq 'skipped[=: ]+[1-9][0-9]*|[1-9][0-9]* skipped|Ran 0 tests' "$LOGDIR/04-all-tests.log"; then
  echo "STOP: integration coverage incomplete; review the test fixtures." >&2
  exit 3
fi
bench --site "$SITE" execute eup_administration.deployment.ui_snapshot > "$LOGDIR/after-tests.json"
env/bin/python - "$LOGDIR/before.json" "$LOGDIR/after-tests.json" <<'PY'
import json, sys
with open(sys.argv[1]) as stream:
    before = json.load(stream)
with open(sys.argv[2]) as stream:
    after = json.load(stream)
if before != after:
    raise SystemExit("STOP: integrity snapshot changed after tests.")
print("PASS: integration tests left protected and legacy data unchanged.")
PY
bench --site "$SITE" set-maintenance-mode off
bench --site "$SITE" clear-cache
printf 'STAGING UPDATE PASSED. Keep the backup and rollback branch %s.\n' "$ROLLBACK"
echo "Start the test UI with: bench --site test-administration-v4.local serve --port 8004 --noreload"
# On failure, stop and retain logs; do not reinstall or touch production.
