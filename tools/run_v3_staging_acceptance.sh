#!/usr/bin/env bash
# ONE full integrated v3 acceptance run. Never execute on a production bench/site.
set -Eeuo pipefail

SITE="${1:?Usage: ./tools/run_v3_staging_acceptance.sh test-site.example.local}"
BENCH="$(pwd -P)"
APP="$BENCH/apps/eup_administration"
SRC="$(readlink -f "$APP")"
LOGDIR="$HOME/adm_v3_acceptance_${SITE//[^a-zA-Z0-9._-]/_}_$(date +%Y%m%d_%H%M%S)"

if [[ "$SITE" != test-* && "$SITE" != staging-* ]]; then
  echo "REFUSED: use a dedicated site beginning test- or staging-." >&2
  exit 2
fi
if [[ "$SITE" == "erpnext-v16.eup-cairo.local" || "$BENCH" == "/home/frappe/frappe-bench" ]]; then
  echo "REFUSED: never run this script on the known primary bench/site." >&2
  exit 2
fi
if [[ ! -f "$BENCH/sites/$SITE/site_config.json" || ! -f "$SRC/eup_administration/hooks.py" ]]; then
  echo "REFUSED: independent staging site/app missing." >&2
  exit 2
fi
if ! git -C "$SRC" rev-parse --abbrev-ref HEAD | grep -qx 'feature/administration-v3-all-in-one-staging'; then
  echo "REFUSED: staging app checkout must be on the reviewed v3 feature branch." >&2
  exit 2
fi
mkdir -p "$LOGDIR"
echo "=== STAGING BENCH: $BENCH ==="
echo "=== STAGING SITE: $SITE ==="
echo "=== LOGS: $LOGDIR ==="

# Protect backups from automated task execution.
bench --site "$SITE" set-maintenance-mode on
bench --site "$SITE" disable-scheduler

# Note: disable all external SMTP/webhook integrations via staging network isolation.
bench --site "$SITE" backup --with-files | tee "$LOGDIR/00_backup.log"
bench --site "$SITE" execute eup_administration.deployment.snapshot > "$LOGDIR/before.json"
python3 -m json.tool "$LOGDIR/before.json" >/dev/null

bench --site "$SITE" migrate 2>&1 | tee "$LOGDIR/01_migrate.log"
bench build --app eup_administration 2>&1 | tee "$LOGDIR/02_build.log"
bench --site "$SITE" execute eup_administration.v3.bootstrap.configure | tee "$LOGDIR/03_setup.log"
bench --site "$SITE" execute eup_administration.v3.registry.rebuild_registry | tee "$LOGDIR/04_backfill.log"
bench --site "$SITE" clear-cache
bench --site "$SITE" execute eup_administration.deployment.snapshot > "$LOGDIR/after.json"
python3 apps/eup_administration/tools/compare_snapshots.py "$LOGDIR/before.json" "$LOGDIR/after.json" | tee "$LOGDIR/05_compare.log"

# Re-run migration to catch non-idempotent schema setup.
bench --site "$SITE" migrate 2>&1 | tee "$LOGDIR/06_repeat_migrate.log"
bench --site "$SITE" execute eup_administration.deployment.snapshot > "$LOGDIR/after_repeat.json"
python3 apps/eup_administration/tools/compare_snapshots.py "$LOGDIR/before.json" "$LOGDIR/after_repeat.json" | tee "$LOGDIR/07_repeat_compare.log"

bench --site "$SITE" set-config allow_tests 1
bench --site "$SITE" set-config adm_allow_integration_tests 1
bench --site "$SITE" run-tests --app eup_administration 2>&1 | tee "$LOGDIR/08_all_integrations.log"

# Explicitly keep scheduler disabled and maintenance mode enabled for browser/manual acceptance.
echo "AUTOMATED STAGING PASS: inspect logs and continue manual roles/concurrency/browser/restore."
echo "No deployment to production has been performed."
