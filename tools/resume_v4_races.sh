#!/usr/bin/env bash
# Resume races after a verified matrix; never create/restore/drop a DB or recover files.
set -Eeuo pipefail
umask 077
base=${1:?Expected installed SHA required}
target=${2:?Reviewed target SHA required}
log_name=${3:?Original completed restore log name required}
matrix_log=${4:?Completed matrix log name required}
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
[[ "$matrix_log" =~ ^adm-resume-acceptance-[A-Za-z0-9]{6}$ ]]
logs="$bench_dir/logs/$log_name"
matrix_logs="$bench_dir/logs/$matrix_log"
test "$(realpath "$matrix_logs")" = "$matrix_logs"
test -f "$matrix_logs/clone-after-matrix.json"
test "$(realpath "$matrix_logs/clone-after-matrix.json")" = "$matrix_logs/clone-after-matrix.json"
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
retry=$(mktemp -d "$bench_dir/logs/adm-resume-races-XXXXXX")
printf 'Resume logs: %s\n' "$retry"
git -C "$app" branch "adm-before-race-cwd-$(date +%Y%m%d-%H%M%S)"
git -C "$app" merge --ff-only "$target"
test "$(git -C "$app" rev-parse HEAD)" = "$target"
bench --site "$source_site" execute eup_administration.tests.clone_acceptance.restore_snapshot > "$retry/source-before.json"
./env/bin/python - "$logs/source-before.json" "$retry/source-before.json" <<'PY'
import json, sys
assert json.load(open(sys.argv[1])) == json.load(open(sys.argv[2])), 'Source changed; stop before recovery'
print('SOURCE PASS: original source snapshot still matches.')
PY
bench --site "$clone_site" execute eup_administration.tests.clone_acceptance.restore_snapshot > "$retry/clone-before-races.json"
./env/bin/python - "$logs/source-before.json" "$logs/clone-restored.json" "$logs/clone-after-suite.json" "$matrix_logs/clone-after-matrix.json" "$retry/clone-before-races.json" <<'PY'
import json, sys
baseline, restored, suite, matrix, current = [json.load(open(p)) for p in sys.argv[1:]]
assert baseline == restored == suite == matrix, 'Completed restore/suite/matrix snapshots must match'
assert baseline['files'] == current['files'], 'Clone files changed after the completed matrix'
assert baseline['data']['protected'] == current['data']['protected'], 'Protected data changed'
for name in ('User', 'Employee', 'Has Role', 'Role', 'User Permission', 'DocPerm', 'Custom DocPerm', 'Workspace', 'File'):
    assert baseline['data']['records'].get(name) == current['data']['records'].get(name), 'Clone security/HR data changed: ' + name
print('MATRIX EVIDENCE PASS: prior complete matrix verified; clone files/security/HR/protected data unchanged.')
print('Earlier synthetic race records are retained on this clone only; no cleanup or restore performed.')
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
printf 'RACES AND SOURCE INTEGRITY PASSED. Clone retained, muted, paused and unserved. Logs: %s\n' "$retry"
