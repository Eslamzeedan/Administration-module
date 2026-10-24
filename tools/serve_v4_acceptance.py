"""Foreground, staging-only web + Socket.io supervisor. Ctrl+C stops its own PIDs.

No scheduler/worker/Redis/service is started. Existing bench/site config is never
changed. Frappe web binds loopback; Socket.io uses a private Unix socket; only the
same already-authorized staging UI port 8004 is exposed.
"""
import json
import os
from pathlib import Path
import signal
import socket
import subprocess
import sys
import tempfile
import time

BENCH = Path('/home/frappe/frappe-bench-v4')
SITE = 'test-administration-v4.local'


def check_paths():
    if Path.cwd().resolve() != BENCH:
        raise SystemExit('Run only from the isolated frappe-bench-v4')
    for item in ('frappe', 'erpnext', 'eup_administration'):
        if (BENCH / 'apps' / item).resolve() != BENCH / 'apps' / item:
            raise SystemExit('Shared/symlinked app checkout refused')
    if (BENCH / 'sites' / SITE).resolve() != BENCH / 'sites' / SITE:
        raise SystemExit('Unexpected test site path')


def web():
    check_paths()
    import frappe.app
    from werkzeug.serving import run_simple
    frappe.app._site = SITE
    frappe.app._sites_path = str(BENCH / 'sites')
    app = frappe.app.application_with_statics()
    run_simple('127.0.0.1', 18004, app, use_reloader=False,
               use_debugger=False, threaded=True)


def main():
    check_paths()
    if subprocess.check_output(['git', '-C', 'apps/eup_administration', 'status', '--porcelain'], text=True).strip():
        raise SystemExit('Commit/clean the staging checkout first')
    for port in (8004, 18004):
        with socket.socket() as probe:
            try:
                probe.bind(('0.0.0.0', port))
            except OSError:
                raise SystemExit(f'Port {port} is already in use; stop only its staging foreground server')
    config = {}
    for filename in ('common_site_config.json', SITE + '/site_config.json'):
        config.update(json.loads((BENCH / 'sites' / filename).read_text()))
    if config.get('maintenance_mode'):
        raise SystemExit('Test site is in maintenance mode; inspect the acceptance failure before reopening')
    if not config.get('pause_scheduler') or config.get('adm_v4_jobs_enabled'):
        raise SystemExit('Keep the staging scheduler and v4 jobs disabled')
    if not config.get('redis_queue') or not config.get('redis_cache'):
        raise SystemExit('Require explicit existing bench Redis endpoints; no service will be started')
    previous_mask = os.umask(0o077)
    runtime = Path(tempfile.mkdtemp(prefix='adm-realtime-', dir=BENCH / 'logs'))
    os.umask(previous_mask)
    uds = runtime / 'socket.io.sock'
    # node_utils supports FRAPPE_BENCH_ROOT and UDS. Copy only Redis endpoints.
    (runtime / 'config.json').write_text(json.dumps({
        'redis_queue': config['redis_queue'], 'redis_cache': config['redis_cache'],
        'socketio_uds': str(uds), 'default_site': SITE}))
    os.chmod(runtime / 'config.json', 0o600)
    env = dict(os.environ, FRAPPE_BENCH_ROOT=str(runtime), FRAPPE_SITE=SITE,
               FRAPPE_SOCKETIO_UDS=str(uds), ADM_ACCEPTANCE_SOCKET=str(uds),
               FRAPPE_REDIS_QUEUE=config['redis_queue'], FRAPPE_REDIS_CACHE=config['redis_cache'])
    processes = []
    handles = []
    stopping = False

    def stop(_signum=None, _frame=None):
        nonlocal stopping
        stopping = True
        for process in reversed(processes):
            if process.poll() is None:
                process.terminate()

    signal.signal(signal.SIGINT, stop)
    signal.signal(signal.SIGTERM, stop)
    try:
        for name, command in (
            ('web', [sys.executable, str(Path(__file__).resolve()), '--web']),
            ('socketio', ['node', str(BENCH / 'apps/frappe/socketio.js')]),
        ):
            handle = (runtime / (name + '.log')).open('w')
            handles.append(handle)
            child_env = dict(os.environ) if name == 'web' else env
            processes.append(subprocess.Popen(command, cwd=BENCH, env=child_env, stdout=handle, stderr=handle))
        deadline = time.monotonic() + 20
        while not uds.exists():
            if time.monotonic() > deadline or any(p.poll() is not None for p in processes):
                raise RuntimeError('Staging upstream did not start; inspect ' + str(runtime))
            time.sleep(0.1)
        processes.append(subprocess.Popen(['node', str(Path(__file__).with_name('v4_acceptance_proxy.cjs').resolve())],
                                           cwd=BENCH, env=env))
        print('Staging web + real-time only. No worker/scheduler or production service started.', flush=True)
        print('Private runtime logs: ' + str(runtime), flush=True)
        while all(p.poll() is None for p in processes):
            time.sleep(0.5)
        if not stopping:
            raise RuntimeError('A staging child stopped unexpectedly; inspect runtime logs')
    finally:
        stop()
        for process in processes:
            try:
                process.wait(timeout=10)
            except subprocess.TimeoutExpired:
                process.kill()
                process.wait()
        for handle in handles:
            handle.close()


if __name__ == '__main__':
    if sys.argv[1:] == ['--web']:
        web()
    elif not sys.argv[1:]:
        main()
    else:
        raise SystemExit('No arbitrary site/port arguments are accepted')
