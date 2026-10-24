import unittest

from eup_administration.acceptance_rules import (BENCH, CLONE, SOURCE,
                                                require_one_success, validate_clone_environment)


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

    def test_enabled_jobs_and_shared_database_are_rejected(self):
        for changes in ({'adm_v4_jobs_enabled': 1}, {'adm_v4_jobs_enabled': '0'},
                        {'db_name': 'source_fixture_db'}, {'db_name': None},
                        {'adm_acceptance_source_db': None}, {'adm_acceptance_source_site': 'production'}):
            with self.subTest(changes=changes), self.assertRaises(AssertionError):
                self.check(**changes)


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
