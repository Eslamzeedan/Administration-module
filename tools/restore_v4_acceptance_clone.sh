#!/usr/bin/env bash
# User-run restore rehearsal. Only a never-before-created clone DB is overwritten.
set -Eeuo pipefail
umask 077
base=${1:?Expected base SHA required}
target=${2:?Reviewed target SHA required}
bench_dir=/home/frappe/frappe-bench-v4
source_site=test-administration-v4.local
clone_site=test-administration-v4-restore.local
app=apps/eup_administration
test "$(pwd -P)" = "$bench_dir"
for item in frappe erpnext eup_administration; do
  test "$(realpath "apps/$item")" = "$bench_dir/apps/$item"
done
test "$(realpath "sites/$source_site")" = "$bench_dir/sites/$source_site"
test ! -e "sites/$clone_site"
test ! -L "sites/$clone_site"
test "${#base}" = 40
test "${#target}" = 40
[[ "$base" =~ ^[0-9a-f]+$ && "$target" =~ ^[0-9a-f]+$ ]]
test "$(git -C "$app" branch --show-current)" = feature/administration-v4-independent-staging
test "$(git -C "$app" rev-parse HEAD)" = "$base"
test -z "$(git -C "$app" status --porcelain)"
test "$(git -C "$app" remote get-url adm-v4-fixes)" = https://github.com/Eslamzeedan/Administration-module.git
command -v ss >/dev/null
listeners=$(ss -ltnH '( sport = :8004 or sport = :8005 or sport = :18004 )')
test -z "$listeners" || { echo 'Stop only the foreground staging servers, then retry.' >&2; exit 2; }
git -C "$app" fetch adm-v4-fixes feature/administration-v4-independent-staging
git -C "$app" merge-base --is-ancestor "$base" "$target"
git -C "$app" merge-base --is-ancestor "$target" adm-v4-fixes/feature/administration-v4-independent-staging
log_dir=$(mktemp -d "$bench_dir/logs/adm-complete-acceptance-XXXXXX")
printf 'Logs: %s\n' "$log_dir"
rollback="adm-before-clone-acceptance-$(date +%Y%m%d-%H%M%S)"
git -C "$app" branch "$rollback"
printf 'Code rollback: %s\n' "$rollback"
bench --site "$source_site" set-maintenance-mode on
bench --site "$source_site" disable-scheduler
bench --site "$source_site" set-config pause_scheduler 1
./env/bin/python - "$source_site" "$log_dir" <<'PY'
import json, sys
from pathlib import Path
site, logs = sys.argv[1:]
root = Path('sites') / site / 'private' / 'backups'
Path(logs, 'existing-backups.json').write_text(json.dumps([p.name for p in root.iterdir()]))
PY
bench --site "$source_site" backup --with-files 2>&1 | tee "$log_dir/00-source-backup.log"
./env/bin/python - "$source_site" "$log_dir" <<'PY'
import json, sys, tarfile
from pathlib import Path, PurePosixPath
site, logs = sys.argv[1:]
root = (Path('sites') / site / 'private' / 'backups').resolve()
old = set(json.loads(Path(logs, 'existing-backups.json').read_text()))
new = [p for p in root.iterdir() if p.name not in old and p.name.endswith('-database.sql.gz')]
assert len(new) == 1, 'Require one newly created, unencrypted full database backup'
prefix = new[0].name.removesuffix('-database.sql.gz')
paths = {'database': new[0], 'public': root / (prefix + '-files.tar'),
         'private': root / (prefix + '-private-files.tar')}
for kind, p in paths.items():
    assert p.is_file() and p.stat().st_size and p.resolve().parent == root
    if kind != 'database':
        with tarfile.open(p) as archive:
            for member in archive.getmembers():
                name = PurePosixPath(member.name)
                assert not name.is_absolute() and '..' not in name.parts, 'Unsafe archive member'
                assert not member.issym() and not member.islnk(), 'Restore test refuses archive links'
Path(logs, 'backup-paths.json').write_text(json.dumps({k: str(v) for k, v in paths.items()}))
for kind in ('database', 'public', 'private'):
    Path(logs, kind + '-path').write_text(str(paths[kind]))
PY
git -C "$app" merge --ff-only "$target"
test "$(git -C "$app" rev-parse HEAD)" = "$target"
bench --site "$source_site" execute eup_administration.tests.clone_acceptance.restore_snapshot > "$log_dir/source-before.json"
./env/bin/python -m json.tool "$log_dir/source-before.json" >/dev/null
clone_db="adm_v4_restore_$(date +%Y%m%d_%H%M%S)"
printf 'Creating only disposable clone %s (database %s). Enter prompts privately.\n' "$clone_site" "$clone_db"
bench new-site "$clone_site" --db-name "$clone_db"
test "$(realpath "sites/$clone_site")" = "$bench_dir/sites/$clone_site"
# Copy only fixture settings/encryption keys; never copy source DB credentials.
configure_clone() {
./env/bin/python - "$source_site" "$clone_site" "$clone_db" <<'PY'
import json, os, sys
from pathlib import Path
source, clone, expected_db = sys.argv[1:]
assert source == 'test-administration-v4.local' and clone == 'test-administration-v4-restore.local'
root = Path('/home/frappe/frappe-bench-v4/sites')
src = root / source / 'site_config.json'
dst = root / clone / 'site_config.json'
assert src.resolve() == src and dst.resolve() == dst
a, b = json.loads(src.read_text()), json.loads(dst.read_text())
assert b['db_name'] == expected_db and b['db_name'] != a['db_name']
for key in ('encryption_key', 'backup_encryption_key', 'adm_test_company', 'adm_test_approver'):
    if key in a:
        b[key] = a[key]
b.update(adm_acceptance_clone=1, adm_acceptance_source_site=source,
         adm_acceptance_source_db=a['db_name'], adm_allow_integration_tests=1,
         adm_test_other_company=a.get('adm_test_other_company', '_Test Company'),
         pause_scheduler=1, mute_emails=1, adm_v4_jobs_enabled=0, allow_tests=1, maintenance_mode=1)
temporary = dst.with_name('site_config.acceptance-tmp.json')
with temporary.open('x') as handle:
    json.dump(b, handle, indent=2)
os.chmod(temporary, 0o600)
temporary.replace(dst)
print('Clone path/database safety verified; no credentials displayed.')
PY
}
configure_clone
database=$(cat "$log_dir/database-path")
public=$(cat "$log_dir/public-path")
private=$(cat "$log_dir/private-path")
# No --force: retain SQL validation and downgrade checks. Only fresh clone DB is targeted.
bench --site "$clone_site" restore "$database" --with-public-files "$public" --with-private-files "$private"
configure_clone
bench --site "$clone_site" disable-scheduler
bench --site "$clone_site" execute eup_administration.tests.clone_acceptance.restore_snapshot > "$log_dir/clone-restored.json"
./env/bin/python - "$log_dir/source-before.json" "$log_dir/clone-restored.json" <<'PY'
import json, sys
a, b = [json.load(open(p)) for p in sys.argv[1:]]
assert a == b, 'Restored data/file hashes differ; keep logs and stop'
print('RESTORE PASS: administrative, HR/security, protected data and file hashes match source.')
PY
bench --site "$clone_site" run-tests --app eup_administration 2>&1 | tee "$log_dir/01-full-suite.log"
./env/bin/python - "$log_dir/01-full-suite.log" <<'PY'
import re, sys
text = re.sub(r'\x1b\[[0-9;]*m', '', open(sys.argv[1]).read())
counts = re.findall(r'Ran (\d+) tests?', text)
assert counts and int(counts[-1]) >= 30 and re.search(r'^OK\s*$', text, re.M)
assert not re.search(r'FAILED|skipped[=: ]+[1-9]|[1-9]\d* skipped', text, re.I)
print('FULL SUITE PASS: nonzero full app coverage, no skipped tests.')
PY
bench --site "$clone_site" execute eup_administration.tests.clone_acceptance.restore_snapshot > "$log_dir/clone-after-suite.json"
./env/bin/python - "$log_dir/source-before.json" "$log_dir/clone-after-suite.json" <<'PY'
import json, sys
assert json.load(open(sys.argv[1])) == json.load(open(sys.argv[2])), 'Full suite changed restored data/files'
print('INTEGRITY PASS: full suite left restored app/HR/security/protected data/files unchanged.')
PY
bench --site "$clone_site" execute eup_administration.tests.clone_acceptance.run_matrix 2>&1 | tee "$log_dir/02-real-role-matrix.log"
bench --site "$clone_site" execute eup_administration.tests.clone_acceptance.run_races 2>&1 | tee "$log_dir/03-simultaneous-races.log"
bench --site "$source_site" execute eup_administration.tests.clone_acceptance.restore_snapshot > "$log_dir/source-after.json"
./env/bin/python - "$log_dir/source-before.json" "$log_dir/source-after.json" <<'PY'
import json, sys
a, b = [json.load(open(p)) for p in sys.argv[1:]]
assert a == b, 'Source test site changed during clone acceptance'
print('SOURCE PASS: original test data/files unchanged by clone acceptance.')
PY
bench --site "$source_site" set-maintenance-mode off
bench --site "$source_site" clear-cache
printf 'CLONE ACCEPTANCE PASSED. Clone retained, muted, scheduler off, not served. Logs: %s\n' "$log_dir"
printf 'No production or source database restore performed. Real-time/browser checks remain separate.\n'
