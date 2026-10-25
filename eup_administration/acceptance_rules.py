"""Pure fail-closed checks for the operator-only disposable-clone harness."""
import hashlib
import re

BENCH = '/home/frappe/frappe-bench-v4'
SOURCE = 'test-administration-v4.local'
CLONE = 'test-administration-v4-restore.local'


def validate_clone_environment(bench, site, site_path, config):
    # bench execute invokes Frappe from the bench's sites directory; standalone
    # worker interpreters run from the bench root. Both are exact named paths.
    if bench == BENCH + '/sites':
        bench = BENCH
    if bench != BENCH or site != CLONE or site_path != BENCH + '/sites/' + CLONE:
        raise AssertionError('Only the exact disposable clone path is allowed')
    for flag in ('adm_acceptance_clone', 'adm_allow_integration_tests', 'pause_scheduler', 'mute_emails'):
        if config.get(flag) not in (1, True):
            raise AssertionError('Clone safety flag must be enabled: ' + flag)
    if config.get('adm_v4_jobs_enabled') not in (None, 0, False):
        raise AssertionError('Scheduled v4 jobs must stay disabled')
    if (config.get('adm_acceptance_source_site') != SOURCE or
            not config.get('adm_acceptance_source_db') or
            not config.get('db_name') or
            config['db_name'] == config['adm_acceptance_source_db']):
        raise AssertionError('Clone database must differ from the recorded test source')


def require_one_success(results, expected_errors):
    """An unrelated setup/permission/SQL error is not evidence of a working guard."""
    if len(results) != 2 or sum(r.get('ok') is True for r in results) != 1:
        raise AssertionError('Race requires exactly one success: ' + repr(results))
    loser = next(r for r in results if r.get('ok') is not True)
    if not any(loser.get('type') == kind and text in loser.get('error', '')
               for kind, text in expected_errors):
        raise AssertionError('Unexpected race failure: ' + repr(loser))
    return next(r for r in results if r.get('ok') is True)


def matrix_file_cleanup_plan(before, after, contents):
    """Accept only newly generated fixture bytes after every DB row rolled back."""
    if before['data'] != after['data']:
        raise AssertionError('Matrix changed persisted app/HR/security/protected data')
    original, current = before['files'], after['files']
    if any(current.get(name) != digest for name, digest in original.items()):
        raise AssertionError('Matrix removed or changed a pre-existing file')
    added = sorted(set(current) - set(original))
    if set(contents) != set(added):
        raise AssertionError('Cleanup content inventory differs from added files')
    for name in added:
        if not re.fullmatch(r'(public|private)/files/ADM-CLONE-[0-9a-f]{32}\.txt', name):
            raise AssertionError('Cleanup refuses an unrelated file path')
        prefix = b'Synthetic clone QA ' if name.startswith('private/') else b'Synthetic public QA '
        content = contents[name]
        if not re.fullmatch(re.escape(prefix) + rb'[0-9a-f]{32}', content):
            raise AssertionError('Cleanup refuses non-fixture file contents')
        if hashlib.sha256(content).hexdigest() != current[name]:
            raise AssertionError('Fixture file hash changed during cleanup')
    return added
