#!/usr/bin/env bash
# Resume only the known matrix cleanup failure; never create or restore a DB.
set -Eeuo pipefail
umask 077
base=${1:?Expected installed SHA required}
target=${2:?Reviewed target SHA required}
log_name=${3:?Original completed restore log name required}
bench_dir=/home/frappe/frappe-bench-v4
source_site=test-administration-v4.local
clone_site=test-administration-v4-restore.local
app=apps/eup_administration
test "$(pwd -P)" = "$bench_dir"
for item in frappe erpnext eup_administration; do
  test "$(realpath "apps/$item")" = "$bench_dir/apps/$item"
done
for site in "$source_site" "$clone_site"; do
  test "$(realpath "sites/$site")" = "$bench_dir/sites/$site"
done
[[ "$base" =~ ^[0-9a-f]{40}$ && "$target" =~ ^[0-9a-f]{40}$ ]]
[[ "$log_name" =~ ^adm-complete-acceptance-[A-Za-z0-9]{6}$ ]]
logs="$bench_dir/logs/$log_name"
test "$(realpath "$logs")" = "$logs"
for name in source-before.json clone-restored.json clone-after-suite.json; do
  test -f "$logs/$name"
  test "$(realpath "$logs/$name")" = "$logs/$name"
done
test "$(git -C "$app" branch --show-current)" = feature/administration-v4-independent-staging
test "$(git -C "$app" rev-parse HEAD)" = "$base"
test -z "$(git -C "$app" status --porcelain)"
test "$(git -C "$app" remote get-url adm-v4-fixes)" = https://github.com/Eslamzeedan/Administration-module.git
test -z "$(ss -ltnH '( sport = :8004 or sport = :8005 or sport = :18004 )')"
./env/bin/python - "$source_site" "$clone_site" <<'PY'
import json, sys
from pathlib import Path
root = Path('/home/frappe/frappe-bench-v4/sites')
source, clone = [json.loads((root / site / 'site_config.json').read_text()) for site in sys.argv[1:]]
assert source.get('maintenance_mode') and source.get('pause_scheduler') == 1
assert clone.get('maintenance_mode') and clone.get('pause_scheduler') == 1
assert source.get('adm_v4_jobs_enabled') in (None, 0, False)
assert clone.get('adm_acceptance_source_db') == source['db_name']
assert clone['db_name'] != source['db_name']
print('Existing source/clone remain isolated, paused and in maintenance.')
PY
git -C "$app" fetch adm-v4-fixes feature/administration-v4-independent-staging
git -C "$app" merge-base --is-ancestor "$base" "$target"
git -C "$app" merge-base --is-ancestor "$target" adm-v4-fixes/feature/administration-v4-independent-staging
retry=$(mktemp -d "$bench_dir/logs/adm-resume-acceptance-XXXXXX")
printf 'Resume logs: %s\n' "$retry"
git -C "$app" branch "adm-before-matrix-file-fix-$(date +%Y%m%d-%H%M%S)"
git -C "$app" merge --ff-only "$target"
test "$(git -C "$app" rev-parse HEAD)" = "$target"
bench --site "$source_site" execute eup_administration.tests.clone_acceptance.restore_snapshot > "$retry/source-before.json"
./env/bin/python - "$logs/source-before.json" "$retry/source-before.json" <<'PY'
import json, sys
assert json.load(open(sys.argv[1])) == json.load(open(sys.argv[2])), 'Source changed; stop before recovery'
print('SOURCE PASS: original source snapshot still matches.')
PY
bench --site "$clone_site" execute eup_administration.tests.clone_acceptance.recover_matrix_files \
  --kwargs "{\"log_name\": \"$log_name\"}" 2>&1 | tee "$retry/00-file-recovery.log"
bench --site "$clone_site" execute eup_administration.tests.clone_acceptance.run_matrix \
  2>&1 | tee "$retry/01-real-role-matrix.log"
bench --site "$clone_site" execute eup_administration.tests.clone_acceptance.restore_snapshot > "$retry/clone-after-matrix.json"
./env/bin/python - "$logs/clone-after-suite.json" "$retry/clone-after-matrix.json" <<'PY'
import json, sys
assert json.load(open(sys.argv[1])) == json.load(open(sys.argv[2])), 'Matrix changed original data/files'
print('MATRIX INTEGRITY PASS: exact restored data and file hashes unchanged.')
PY
bench --site "$clone_site" execute eup_administration.tests.clone_acceptance.run_races \
  2>&1 | tee "$retry/02-simultaneous-races.log"
bench --site "$source_site" execute eup_administration.tests.clone_acceptance.restore_snapshot > "$retry/source-after.json"
./env/bin/python - "$logs/source-before.json" "$retry/source-after.json" <<'PY'
import json, sys
assert json.load(open(sys.argv[1])) == json.load(open(sys.argv[2])), 'Source changed during clone acceptance'
print('SOURCE PASS: original source data and file hashes unchanged.')
PY
bench --site "$source_site" set-maintenance-mode off
bench --site "$source_site" clear-cache
printf 'RESUMED CLONE ACCEPTANCE PASSED. Clone retained, muted, paused and unserved. Logs: %s\n' "$retry"
