import copy
import hashlib
import unittest

from eup_administration.acceptance_rules import (BENCH, CLONE, SOURCE,
                                                matrix_file_cleanup_plan, require_one_success,
                                                validate_clone_environment)


class CloneSafetyTests(unittest.TestCase):
    def setUp(self):
        self.config = {'adm_acceptance_clone': 1, 'adm_allow_integration_tests': 1,
                       'pause_scheduler': 1, 'mute_emails': 1, 'adm_v4_jobs_enabled': 0,
                       'adm_acceptance_source_site': SOURCE,
                       'adm_acceptance_source_db': 'source_fixture_db', 'db_name': 'fresh_clone_db'}

    def check(self, **changes):
        config = self.config | changes
        return validate_clone_environment(BENCH, CLONE, BENCH + '/sites/' + CLONE, config)

    def test_only_exact_separate_clone_is_accepted(self):
        self.check()
        for bench, site, site_path in (
            ('/home/frappe/frappe-bench', CLONE, BENCH + '/sites/' + CLONE),
            (BENCH, SOURCE, BENCH + '/sites/' + SOURCE),
            (BENCH, 'erpnext-v16.eup-cairo.local', BENCH + '/sites/' + CLONE),
            (BENCH, CLONE, '/home/frappe/frappe-bench/sites/' + CLONE),
        ):
            with self.subTest(site=site, path=site_path), self.assertRaises(AssertionError):
                validate_clone_environment(bench, site, site_path, self.config)

    def test_missing_or_string_flags_fail_closed(self):
        for flag in ('adm_acceptance_clone', 'adm_allow_integration_tests', 'pause_scheduler', 'mute_emails'):
            for value in (None, 0, '0', '1', 'true'):
                with self.subTest(flag=flag, value=value), self.assertRaises(AssertionError):
                    self.check(**{flag: value})

    def test_bench_execute_sites_cwd_is_supported_without_other_paths(self):
        validate_clone_environment(BENCH + '/sites', CLONE, BENCH + '/sites/' + CLONE, self.config)
        for cwd in ('/home/frappe/frappe-bench/sites', BENCH + '/sites/other', '/tmp'):
            with self.subTest(cwd=cwd), self.assertRaises(AssertionError):
                validate_clone_environment(cwd, CLONE, BENCH + '/sites/' + CLONE, self.config)

    def test_enabled_jobs_and_shared_database_are_rejected(self):
        for changes in ({'adm_v4_jobs_enabled': 1}, {'adm_v4_jobs_enabled': '0'},
                        {'db_name': 'source_fixture_db'}, {'db_name': None},
                        {'adm_acceptance_source_db': None}, {'adm_acceptance_source_site': 'production'}):
            with self.subTest(changes=changes), self.assertRaises(AssertionError):
                self.check(**changes)


class MatrixFileCleanupTests(unittest.TestCase):
    def setUp(self):
        self.before = {'data': {'records': {'User': [3, 'unchanged']},
                                'protected': {'GL Entry': [0, 'unchanged']}},
                       'files': {'private/files/original.pdf': 'original-hash'}}
        self.contents = {
            'private/files/ADM-CLONE-' + 'a' * 32 + '.txt': b'Synthetic clone QA ' + b'b' * 32,
            'public/files/ADM-CLONE-' + 'c' * 32 + '.txt': b'Synthetic public QA ' + b'd' * 32}
        self.after = copy.deepcopy(self.before)
        self.after['files'].update({name: hashlib.sha256(value).hexdigest()
                                    for name, value in self.contents.items()})

    def check(self):
        return matrix_file_cleanup_plan(self.before, self.after, self.contents)

    def test_only_new_exact_synthetic_orphans_are_selected(self):
        self.assertEqual(self.check(), sorted(self.contents))
        self.assertEqual(matrix_file_cleanup_plan(self.before, self.before, {}), [])

    def test_database_and_protected_changes_block_all_cleanup(self):
        for section in ('records', 'protected'):
            with self.subTest(section=section):
                after = copy.deepcopy(self.after)
                after['data'][section]['changed'] = [1, 'different']
                with self.assertRaises(AssertionError):
                    matrix_file_cleanup_plan(self.before, after, self.contents)

    def test_changed_or_removed_original_file_blocks_cleanup(self):
        for value in (None, 'changed'):
            after = copy.deepcopy(self.after)
            if value is None:
                del after['files']['private/files/original.pdf']
            else:
                after['files']['private/files/original.pdf'] = value
            with self.subTest(value=value), self.assertRaises(AssertionError):
                matrix_file_cleanup_plan(self.before, after, self.contents)

    def test_unrelated_traversal_nested_or_renamed_file_is_refused(self):
        for name in ('private/files/report.pdf', '../ADM-CLONE-' + 'a' * 32 + '.txt',
                     'public/files/nested/ADM-CLONE-' + 'a' * 32 + '.txt',
                     'private/files/ADM-CLONE-' + 'a' * 31 + '.txt'):
            after = copy.deepcopy(self.before)
            content = b'Synthetic clone QA ' + b'b' * 32
            after['files'][name] = hashlib.sha256(content).hexdigest()
            with self.subTest(name=name), self.assertRaises(AssertionError):
                matrix_file_cleanup_plan(self.before, after, {name: content})

    def test_non_fixture_bytes_and_wrong_public_private_identity_are_refused(self):
        name = next(iter(self.contents))
        for value in (b'business data', b'Synthetic public QA ' + b'b' * 32,
                      b'Synthetic clone QA ' + b'b' * 32 + b'extra'):
            after = copy.deepcopy(self.before)
            after['files'][name] = hashlib.sha256(value).hexdigest()
            with self.subTest(value=value), self.assertRaises(AssertionError):
                matrix_file_cleanup_plan(self.before, after, {name: value})

    def test_changed_hash_is_refused(self):
        self.after['files'][next(iter(self.contents))] = 'changed-after-snapshot'
        with self.assertRaises(AssertionError):
            self.check()

    def test_missing_or_extra_content_inventory_is_refused(self):
        for contents in ({}, dict(self.contents, extra=b'unknown')):
            with self.subTest(keys=list(contents)), self.assertRaises(AssertionError):
                matrix_file_cleanup_plan(self.before, self.after, contents)


class RaceEvidenceTests(unittest.TestCase):
    def test_success_and_expected_rejection_in_either_order(self):
        yes = {'ok': True, 'value': {'name': 'winner'}}
        no = {'ok': False, 'type': 'ValidationError', 'error': 'Workflow changed. Reload before continuing.'}
        for results in ([yes, no], [no, yes]):
            self.assertIs(require_one_success(results, [('ValidationError', 'Reload')]), yes)

    def test_both_success_both_failure_or_missing_worker_are_not_passes(self):
        yes = {'ok': True}
        no = {'ok': False, 'type': 'ValidationError', 'error': 'Reload'}
        for results in ([yes, yes], [no, no], [yes], [], [yes, no, no]):
            with self.subTest(results=results), self.assertRaises(AssertionError):
                require_one_success(results, [('ValidationError', 'Reload')])

    def test_unrelated_failure_is_not_a_guard_pass(self):
        for kind, message in (('PermissionError', 'Reload'), ('ValidationError', 'Missing field'),
                              ('OperationalError', 'Deadlock'), ('ImportError', 'No module')):
            with self.subTest(kind=kind), self.assertRaises(AssertionError):
                require_one_success([{'ok': True}, {'ok': False, 'type': kind, 'error': message}],
                                    [('ValidationError', 'Reload')])
