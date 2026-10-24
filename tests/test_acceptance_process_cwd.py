"""Real child-process and file-path regressions; no Frappe/DB pass is implied."""
import ast
import json
import os
import re
from pathlib import Path
import subprocess
import sys
import tempfile
import time
from types import ModuleType, SimpleNamespace
import unittest
from unittest.mock import patch


ROOT = Path(__file__).resolve().parents[1]
CLONE = 'test-administration-v4-restore.local'


def load_function(relative, name, namespace):
    file = ROOT / relative
    tree = ast.parse(file.read_text())
    function = next(node for node in tree.body if isinstance(node, ast.FunctionDef) and node.name == name)
    exec(compile(ast.Module(body=[function], type_ignores=[]), str(file), 'exec'), namespace)
    return namespace[name]


class AcceptanceProcessCwdTests(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.bench = Path(temporary.name).resolve()
        (self.bench / 'logs').mkdir()
        (self.bench / 'sites' / CLONE / 'logs').mkdir(parents=True)
        self.rollbacks = []

    def test_resume_embedded_python_compiles(self):
        file = ROOT / 'tools/resume_v4_races.sh'
        blocks = re.findall(r"<<'PY'\n(.*?)^PY$", file.read_text(), re.M | re.S)
        self.assertGreaterEqual(len(blocks), 5)
        for index, source in enumerate(blocks):
            with self.subTest(block=index):
                compile(source, str(file) + f':python-block-{index}', 'exec')

    def race(self, child_code):
        def launch(command, **kwargs):
            # Keep the real launcher kwargs/payload; replace only DB/application
            # work with a tiny child that exercises Frappe's relative log paths.
            return subprocess.Popen([command[0], '-c', child_code, command[-1]], **kwargs)
        namespace = {'Path': Path, 'BENCH': self.bench, 'guard': lambda: None,
                     'tempfile': tempfile, 'time': time, 'json': json, 'sys': sys,
                     'subprocess': SimpleNamespace(Popen=launch, PIPE=subprocess.PIPE),
                     'frappe': SimpleNamespace(db=SimpleNamespace(
                         rollback=lambda: self.rollbacks.append(True)))}
        return load_function('eup_administration/tests/clone_acceptance.py', 'race', namespace)

    def test_two_independent_children_use_real_site_and_bench_log_paths(self):
        child = '''
import json, os, sys, time
from pathlib import Path
data = json.loads(sys.argv[1])
for file in ('../logs/database.log', data['site'] + '/logs/database.log'):
    with open(file, 'a') as log:
        log.write(str(os.getpid()) + '\\n')
control = Path(data['control'])
(control / ('ready-' + str(data['index']))).write_text('ready')
deadline = time.monotonic() + 10
while not (control / 'go').exists():
    assert time.monotonic() < deadline
    time.sleep(0.01)
print('ADM_RACE_RESULT=' + json.dumps({'ok': True, 'cwd': os.getcwd(), 'pid': os.getpid()}))
'''
        results = self.race(child)('booking', {'site': CLONE})
        self.assertEqual(len({row['pid'] for row in results}), 2)
        self.assertEqual({row['cwd'] for row in results}, {str(self.bench / 'sites')})
        self.assertEqual(len((self.bench / 'logs/database.log').read_text().splitlines()), 2)
        self.assertEqual(len((self.bench / 'sites' / CLONE / 'logs/database.log').read_text().splitlines()), 2)
        self.assertFalse((self.bench / CLONE).exists())
        self.assertEqual(self.rollbacks, [True])

    def test_startup_failure_is_not_a_race_pass_and_retains_both_worker_logs(self):
        child = "import sys; print('startup failure evidence', file=sys.stderr); sys.exit(3)"
        with self.assertRaisesRegex(AssertionError, 'Both real DB workers'):
            self.race(child)('booking', {})
        control, = (self.bench / 'logs').glob('adm-clone-race-*')
        logs = []
        for index in (0, 1):
            logs.append((control / f'worker-{index}.log').read_text())
            self.assertFalse((control / f'ready-{index}').exists())
        self.assertTrue(any('startup failure evidence' in log for log in logs))
        self.assertEqual(self.rollbacks, [True])

    def test_worker_rejects_unsafe_environment_before_any_db_connection(self):
        calls = []
        def reject():
            raise AssertionError('unsafe clone')
        namespace = {'json': json, 'CLONE': CLONE, 'BENCH': self.bench,
                     'frappe': SimpleNamespace(init=lambda **kw: calls.append('init'),
                                               connect=lambda: calls.append('connect')),
                     'guard': reject}
        worker = load_function('eup_administration/tests/clone_acceptance.py', 'worker_main', namespace)
        with self.assertRaisesRegex(AssertionError, 'unsafe clone'):
            worker('{}')
        self.assertEqual(calls, ['init'])

    def test_web_checks_root_then_uses_sites_cwd_for_runtime_logging(self):
        app = ModuleType('frappe.app')
        def application():
            self.assertEqual(Path.cwd(), self.bench / 'sites')
            for file in ('../logs/web.log', CLONE + '/logs/web.log'):
                Path(file).write_text('test runtime log')
            return 'test-wsgi-application'
        app.application_with_statics = application
        frappe = ModuleType('frappe')
        frappe.app = app
        serving = ModuleType('werkzeug.serving')
        werkzeug = ModuleType('werkzeug')
        werkzeug.serving = serving
        serving.run_simple = lambda host, port, application, **kw: self.assertEqual(
            (host, port, application, kw), ('127.0.0.1', 18004, 'test-wsgi-application',
                {'use_reloader': False, 'use_debugger': False, 'threaded': True}))
        namespace = {'os': os, 'BENCH': self.bench, 'SITE': CLONE,
                     'check_paths': lambda: self.assertEqual(Path.cwd(), self.bench)}
        web = load_function('tools/serve_v4_acceptance.py', 'web', namespace)
        original = Path.cwd()
        try:
            os.chdir(self.bench)
            with patch.dict(sys.modules, {'frappe': frappe, 'frappe.app': app, 'werkzeug': werkzeug,
                                          'werkzeug.serving': serving}):
                web()
        finally:
            os.chdir(original)
        self.assertEqual((self.bench / 'logs/web.log').read_text(), 'test runtime log')
        self.assertEqual((self.bench / 'sites' / CLONE / 'logs/web.log').read_text(), 'test runtime log')
