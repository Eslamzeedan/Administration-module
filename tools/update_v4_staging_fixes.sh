#!/usr/bin/env bash
# Pinned fixes only on the independently provisioned test VM. No migrate/restore.
set -Eeuo pipefail
[[ "$#" == 2 ]] || { echo "Usage: bash update_v4_staging_fixes.sh BASE_SHA TARGET_SHA" >&2; exit 2; }
BASE="$1"
TARGET="$2"
BENCH=/home/frappe/frappe-bench-v4
SITE=test-administration-v4.local
BRANCH=feature/administration-v4-independent-staging
cd "$BENCH"
[[ "$(pwd -P)" == "$BENCH" ]]
[[ "$(realpath "sites/$SITE")" == "$BENCH/sites/$SITE" ]]
for app_name in frappe erpnext eup_administration; do
  [[ "$(realpath "apps/$app_name")" == "$BENCH/apps/$app_name" ]]
done
APP="$BENCH/apps/eup_administration"
[[ "$BASE" =~ ^[0-9a-f]{40}$ && "$TARGET" =~ ^[0-9a-f]{40}$ ]]
[[ "$(git -C "$APP" branch --show-current)" == "$BRANCH" ]]
[[ -z "$(git -C "$APP" status --porcelain)" ]]
[[ "$(git -C "$APP" rev-parse HEAD)" == "$BASE" ]]
[[ "$(git -C "$APP" remote get-url adm-v4-fixes)" == https://github.com/Eslamzeedan/Administration-module.git ]]
command -v ss >/dev/null
listeners="$(ss -ltnH 'sport = :8004')"
[[ -z "$listeners" ]] || {
  echo "Stop only the foreground port-8004 test server with Ctrl+C, then rerun." >&2; exit 2;
}
git -C "$APP" fetch adm-v4-fixes "$BRANCH"
git -C "$APP" merge-base --is-ancestor "$BASE" "$TARGET"
git -C "$APP" merge-base --is-ancestor "$TARGET" "adm-v4-fixes/$BRANCH"
LOGDIR="$(mktemp -d "$BENCH/logs/adm-v4-fixes-XXXXXX")"
ROLLBACK="adm-v4-before-fixes-$(date +%Y%m%d-%H%M%S)"
git -C "$APP" branch "$ROLLBACK"
printf 'Code rollback: %s\nLogs: %s\n' "$ROLLBACK" "$LOGDIR"
bench --site "$SITE" backup --with-files | tee "$LOGDIR/00-backup.log"
bench --site "$SITE" set-maintenance-mode on
bench --site "$SITE" disable-scheduler
bench --site "$SITE" execute eup_administration.deployment.ui_snapshot > "$LOGDIR/before.json"
env/bin/python -m json.tool "$LOGDIR/before.json" >/dev/null
git -C "$APP" merge --ff-only "$TARGET"
[[ "$(git -C "$APP" rev-parse HEAD)" == "$TARGET" ]]
bench build --app eup_administration 2>&1 | tee "$LOGDIR/01-build.log"
bench --site "$SITE" clear-cache
bench --site "$SITE" run-tests --app eup_administration \
  --module eup_administration.tests.test_v4_independent_integration \
  2>&1 | tee "$LOGDIR/02-v4-tests.log"
bench --site "$SITE" run-tests --app eup_administration \
  2>&1 | tee "$LOGDIR/03-all-tests.log"
env/bin/python - "$LOGDIR/02-v4-tests.log" "$LOGDIR/03-all-tests.log" <<'PY'
import re
import sys
from pathlib import Path
for filename, minimum in zip(sys.argv[1:], (8, 30), strict=True):
    text = re.sub(r"\x1b\[[0-?]*[ -/]*[@-~]", "", Path(filename).read_text())
    counts = re.findall(r"(?m)^Ran\s+(\d+)\s+tests?\s+in\b", text)
    if not counts or int(counts[-1]) < minimum or not re.search(r"(?m)^OK\s*$", text):
        raise SystemExit("STOP: missing/incomplete successful test summary: " + filename)
    if re.search(r"skipped[=: ]+[1-9][0-9]*|[1-9][0-9]* skipped|(?m:^FAILED\b)", text, re.I):
        raise SystemExit("STOP: skipped/failed test coverage: " + filename)
    print(f"PASS: {counts[-1]} tests, no skips: {filename}")
PY
bench --site "$SITE" execute eup_administration.deployment.ui_snapshot > "$LOGDIR/after-tests.json"
env/bin/python - "$LOGDIR/before.json" "$LOGDIR/after-tests.json" <<'PY'
import json
import sys
from pathlib import Path
before, after = (json.loads(Path(p).read_text()) for p in sys.argv[1:])
if before != after:
    raise SystemExit("STOP: legacy/permissions/workspace/protected snapshot changed; retain logs.")
print("PASS: legacy, permissions, workspace and protected tables unchanged after tests.")
PY
bench --site "$SITE" set-maintenance-mode off
bench --site "$SITE" clear-cache
printf 'STAGING FIXES PASSED. Keep rollback branch %s and all backup paths.\n' "$ROLLBACK"
echo "Start only the test UI: bench --site test-administration-v4.local serve --port 8004 --noreload"
# Failure leaves this disposable site in maintenance mode; retain evidence, do not reinstall.
