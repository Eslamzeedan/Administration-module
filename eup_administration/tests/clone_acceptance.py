"""Operator-only acceptance on the restored disposable clone, never an HTTP API.

This module deliberately is not named test_*: the ordinary 30-test staging suite
must not create HR fixtures. Run ``run_matrix`` explicitly on the restored clone.
All matrix fixtures are real User/Employee rows inside one rolled-back transaction;
no Company, financial master, credential or role definition is generated.
"""
import hashlib
import json
import re
from pathlib import Path
import subprocess
import sys
import tempfile
import time
import unittest
from uuid import uuid4

import frappe
from frappe.exceptions import UniqueValidationError
from frappe.utils import add_days, add_to_date, now_datetime, today

from eup_administration.acceptance_rules import (matrix_file_cleanup_plan, require_one_success,
                                                  validate_clone_environment)
from eup_administration.tests.test_v4_independent_integration import protected_snapshot
from eup_administration.v4 import dashboard, operations, portal, security, workflow

BENCH = Path('/home/frappe/frappe-bench-v4')
CLONE = 'test-administration-v4-restore.local'


def guard():
    validate_clone_environment(str(Path.cwd().resolve()), frappe.local.site,
                               str(Path(frappe.get_site_path()).resolve()), frappe.conf)


def fingerprint():
    """Compare hashes only; never print User, HR or application record contents."""
    names = frappe.get_all('DocType', filters={'name': ['like', 'ADM %']}, pluck='name')
    names += ['User', 'Employee', 'Has Role', 'Role', 'User Permission', 'DocPerm',
              'Custom DocPerm', 'Workspace', 'File']
    result = {'protected': protected_snapshot(), 'records': {}}
    for name in sorted(set(names)):
        if not frappe.db.table_exists(name):
            continue
        # Identifiers come only from real DocType names, quoted as identifiers.
        table = '`tab' + name.replace('`', '``') + '`'
        rows = frappe.db.sql('SELECT * FROM ' + table + ' ORDER BY name', as_dict=True)
        digest = hashlib.sha256(json.dumps(rows, sort_keys=True, default=str).encode()).hexdigest()
        result['records'][name] = [len(rows), digest]
    singles = frappe.db.sql("SELECT * FROM `tabSingles` WHERE doctype LIKE 'ADM %%' ORDER BY doctype, field", as_dict=True)
    result['records']['ADM Singles'] = [len(singles), hashlib.sha256(
        json.dumps(singles, sort_keys=True, default=str).encode()).hexdigest()]
    return result


def restore_snapshot():
    """Read-only source/clone comparison, including actual public/private file bytes."""
    if (Path.cwd().resolve() not in (BENCH, BENCH / 'sites') or frappe.local.site not in
            ('test-administration-v4.local', CLONE) or
            Path(frappe.get_site_path()).resolve() != BENCH / 'sites' / frappe.local.site):
        raise AssertionError('Read-only restore snapshot requires the exact test bench/site')
    frappe.set_user('Administrator')
    files = {}
    site_root = Path(frappe.get_site_path()).resolve()
    for folder in ('public/files', 'private/files'):
        root = site_root / folder
        if not root.exists():
            continue
        for file in sorted(root.rglob('*')):
            if file.is_symlink():
                raise AssertionError('File snapshot refuses symlinks')
            if file.is_file():
                if not file.resolve().is_relative_to(site_root):
                    raise AssertionError('File escaped the test site')
                files[str(file.relative_to(site_root))] = hashlib.sha256(file.read_bytes()).hexdigest()
    # CLI snapshots are JSON. Keep the in-process shape identical when recovery
    # compares a freshly read snapshot with one loaded from the original log.
    return {'data': json.loads(json.dumps(fingerprint())), 'files': files}


class CloneMatrix(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        guard()
        frappe.set_user('Administrator')
        cls.company = frappe.conf.get('adm_test_company')
        cls.other_company = frappe.conf.get('adm_test_other_company', '_Test Company')
        if cls.company == cls.other_company or not all(
                frappe.db.exists('Company', c) for c in (cls.company, cls.other_company)):
            raise AssertionError('Two existing isolated fixture Companies are required; none are generated')
        cls.users = []
        cls.suffix = uuid4().hex[:12]
        cls.requester = cls.make_actor('requester', 'Administration User')
        cls.approver = cls.make_actor('approver', 'Administration Manager')
        cls.second = cls.make_actor('second', 'Administration Manager')
        cls.stranger = cls.make_actor('stranger', 'Administration User')
        cls.foreign = cls.make_actor('foreign', 'Administration Manager', cls.other_company)

    @classmethod
    def make_actor(cls, label, role, company=None):
        company = company or cls.company
        identifier = 'adm-clone-' + label + '-' + cls.suffix
        user = frappe.get_doc({'doctype': 'User', 'email': identifier + '@example.test',
            'first_name': 'ADM clone QA ' + label, 'enabled': 1, 'user_type': 'System User',
            'send_welcome_email': 0, 'roles': [{'role': role}, {'role': 'Employee'}]}).insert()
        cls.users.append(user.name)
        template = frappe.db.get_value('Employee', {'user_id': frappe.conf.adm_test_approver,
            'status': 'Active'}, ['gender', 'naming_series'], as_dict=True)
        if not template or not template.gender:
            raise AssertionError('Existing active fixture Employee must supply an existing Gender')
        fields = {'doctype': 'Employee', 'first_name': 'ADM clone QA ' + label,
            'gender': template.gender, 'date_of_birth': '1990-01-01',
            'date_of_joining': '2020-01-01', 'status': 'Active', 'company': company,
            'user_id': user.name, 'create_user_permission': 0, 'employee_number': identifier}
        if template.naming_series:
            fields['naming_series'] = template.naming_series
        frappe.get_doc(fields).insert()
        return user.name

    def setUp(self):
        frappe.set_user('Administrator')
        frappe.db.savepoint('adm_clone_case')
        self.addCleanup(self.restore_case)

    def restore_case(self):
        frappe.set_user('Administrator')
        frappe.db.rollback(save_point='adm_clone_case')
        for user in self.users:
            frappe.clear_cache(user=user)

    def actor(self, user):
        frappe.set_user(user)

    def ticket(self, user=None, company=None):
        self.actor(user or self.requester)
        return frappe.get_doc({'doctype': 'ADM Facility Ticket', 'subject': 'ADM CLONE QA',
            'company': company or self.company, 'location': 'Synthetic clone office'}).insert()

    def policy(self, approval=False, steps=1, allow_delegation=1):
        self.actor('Administrator')
        for name in frappe.get_all('ADM Workflow Policy', filters={'company': self.company,
                'target_doctype': 'ADM Facility Ticket', 'enabled': 1}, pluck='name'):
            old = frappe.get_doc('ADM Workflow Policy', name)
            old.enabled = 0
            old.save()
        return frappe.get_doc({'doctype': 'ADM Workflow Policy', 'company': self.company,
            'policy_title': 'ADM CLONE QA', 'target_doctype': 'ADM Facility Ticket',
            'enabled': 1, 'initial_state': 'Draft', 'states': [
                {'state': 'Draft'}, {'state': 'Done', 'is_terminal': 1}],
            'transitions': [{'action': 'Complete', 'from_state': 'Draft', 'to_state': 'Done',
                'allowed_role': 'Administration User', 'approval_required': int(approval),
                'conditions': '[]'}], 'approval_bands': [
                {'transition_action': 'Complete', 'step_number': n,
                 'approver_role': 'Administration Manager', 'same_company': 1,
                 'same_department': 0, 'allow_delegation': allow_delegation}
                for n in range(1, steps + 1)] if approval else []}).insert()

    def pending(self, steps=1, allow_delegation=1):
        policy = self.policy(True, steps, allow_delegation)
        doc = self.ticket()
        workflow.start(doc.doctype, doc.name, policy.name)
        result = workflow.transition(doc.doctype, doc.name, 'Complete', 1)
        return doc, result

    def audit_count(self, doc):
        return frappe.db.count('ADM Workflow Audit', {'reference_doctype': doc.doctype,
                                                     'reference_name': doc.name})

    def test_limited_employee_portal_to_feedback(self):
        policy = self.policy()
        hidden = self.ticket(self.approver)
        self.actor(self.requester)
        self.assertFalse(security.manager(self.company))
        self.assertNotIn('Administration Manager', frappe.get_roles())
        created = portal.create_request('ADM Facility Ticket', {'subject': 'CLONE PORTAL QA',
            'location': 'Synthetic office'}, policy.name)
        doc = frappe.get_doc(created['doctype'], created['name'])
        self.assertEqual((doc.company, doc.requested_by, doc.workflow_state),
                         (self.company, self.requester, 'Draft'))
        visible = {(r['doctype'], r['name']) for r in portal.home()['records']}
        self.assertIn((doc.doctype, doc.name), visible)
        self.assertNotIn((hidden.doctype, hidden.name), visible)
        self.assertEqual(workflow.transition(doc.doctype, doc.name, 'Complete', 1)['state'], 'Done')
        result = operations.feedback(doc.doctype, doc.name, 4, 'CLONE QA')
        with self.assertRaises((frappe.DuplicateEntryError, UniqueValidationError)):
            operations.feedback(doc.doctype, doc.name, 1, 'Duplicate')
        self.assertEqual(frappe.db.count('ADM Operation Feedback', {'reference_name': doc.name}), 1)
        self.assertEqual(frappe.db.get_value('ADM Operation Feedback', result['feedback'],
                                            ['rating', 'comment']), (4, 'CLONE QA'))

    def test_limited_role_owner_assignee_and_forbidden_assignment(self):
        own = self.ticket()
        hidden = self.ticket(self.approver)
        assigned = self.ticket(self.approver)
        operations.assign_operator(assigned.doctype, assigned.name, self.requester)
        self.actor(self.requester)
        visible = frappe.get_list('ADM Facility Ticket', pluck='name', limit_page_length=0)
        self.assertIn(own.name, visible)
        self.assertIn(assigned.name, visible)
        self.assertNotIn(hidden.name, visible)
        with self.assertRaises(frappe.PermissionError):
            hidden.check_permission('read')
        with self.assertRaises(frappe.PermissionError):
            operations.assign_operator(own.doctype, own.name, self.stranger)
        with self.assertRaises(frappe.PermissionError):
            operations.update_details(hidden.doctype, hidden.name, {'resolution': 'Forbidden'})
        operations.update_details(assigned.doctype, assigned.name, {'resolution': 'CLONE QA operator'})
        self.assertEqual(frappe.db.get_value(assigned.doctype, assigned.name, 'resolution'), 'CLONE QA operator')
        self.assertFalse(frappe.db.get_value(own.doctype, own.name, 'assigned_to'))
        self.assertFalse(frappe.db.get_value(hidden.doctype, hidden.name, 'resolution'))

    def test_cross_company_read_write_dashboard_and_portal_forgery(self):
        foreign = self.ticket(self.foreign, self.other_company)
        self.actor(self.approver)
        self.assertNotIn(foreign.name, frappe.get_list(foreign.doctype, pluck='name'))
        for action in (lambda: foreign.check_permission('read'),
                       lambda: workflow.available(foreign.doctype, foreign.name),
                       lambda: operations.update_details(foreign.doctype, foreign.name, {'resolution': 'No'}),
                       lambda: operations.assign_operator(foreign.doctype, foreign.name, self.approver),
                       lambda: dashboard.command_center(self.other_company)):
            with self.assertRaises(frappe.PermissionError):
                action()
        self.actor(self.requester)
        before = frappe.db.count('ADM Facility Ticket')
        with self.assertRaises(frappe.ValidationError):
            portal.create_request('ADM Facility Ticket', {'subject': 'No', 'location': 'No',
                'company': self.other_company}, 'FORGED')
        with self.assertRaises(frappe.PermissionError):
            frappe.get_doc({'doctype': foreign.doctype, 'subject': 'No', 'location': 'No',
                'company': self.other_company}).insert(ignore_permissions=True)
        self.assertEqual(frappe.db.count('ADM Facility Ticket'), before)

    def test_actual_self_approval_and_forged_state_are_rejected(self):
        doc, info = self.pending()
        # A requester who genuinely has the approver role still cannot approve self.
        self.actor('Administrator')
        user = frappe.get_doc('User', self.requester)
        user.append('roles', {'role': 'Administration Manager'})
        user.save()
        frappe.clear_cache(user=self.requester)
        self.actor(self.requester)
        self.assertIn('Administration Manager', frappe.get_roles())
        before = self.audit_count(doc)
        with self.assertRaises(frappe.PermissionError):
            workflow.decide(doc.doctype, doc.name, 'Approved', info['revision'])
        doc.reload()
        doc.workflow_state = 'Done'
        with self.assertRaises(frappe.ValidationError):
            doc.save(ignore_permissions=True)
        self.assertEqual(self.audit_count(doc), before)
        self.assertEqual(frappe.db.get_value(doc.doctype, doc.name, 'workflow_state'), 'Draft')

    def test_multistep_requires_distinct_approvers_and_rejects_stale_revision(self):
        doc, info = self.pending(steps=2)
        self.actor(self.approver)
        result = workflow.decide(doc.doctype, doc.name, 'Approved', info['revision'])
        self.assertEqual(result['state'], 'Draft')
        before = self.audit_count(doc)
        with self.assertRaisesRegex(frappe.ValidationError, 'different approver'):
            workflow.decide(doc.doctype, doc.name, 'Approved', result['revision'])
        self.actor(self.second)
        with self.assertRaisesRegex(frappe.ValidationError, 'Reload'):
            workflow.decide(doc.doctype, doc.name, 'Approved', info['revision'])
        self.assertEqual(self.audit_count(doc), before)
        done = workflow.decide(doc.doctype, doc.name, 'Approved', result['revision'])
        self.assertEqual(done['state'], 'Done')
        self.assertEqual(self.audit_count(doc), before + 1)

    def test_delegation_expiry_and_identity_are_enforced(self):
        doc, info = self.pending()
        self.actor('Administrator')
        delegation = frappe.get_doc({'doctype': 'ADM Approval Delegation', 'company': self.company,
            'delegator': self.approver, 'delegate': self.stranger, 'enabled': 1,
            'valid_from': add_to_date(now_datetime(), hours=-2),
            'valid_until': add_to_date(now_datetime(), hours=-1), 'reason': 'CLONE QA'}).insert()
        self.actor(self.stranger)
        before = self.audit_count(doc)
        with self.assertRaises(frappe.PermissionError):
            workflow.decide(doc.doctype, doc.name, 'Approved', info['revision'])
        self.assertEqual(self.audit_count(doc), before)
        self.actor('Administrator')
        delegation.valid_until = add_to_date(now_datetime(), hours=1)
        delegation.save()
        self.actor(self.stranger)
        self.assertEqual(workflow.decide(doc.doctype, doc.name, 'Approved', info['revision'])['state'], 'Done')
        audit = frappe.get_all('ADM Workflow Audit', filters={'reference_name': doc.name,
            'decision': 'Approved'}, fields=['actor', 'delegated_from'])
        self.assertEqual([(a.actor, a.delegated_from) for a in audit], [(self.stranger, self.approver)])

    def test_disabled_delegator_cannot_authorize_a_decision(self):
        doc, info = self.pending()
        self.actor('Administrator')
        frappe.get_doc({'doctype': 'ADM Approval Delegation', 'company': self.company,
            'delegator': self.approver, 'delegate': self.stranger, 'enabled': 1,
            'valid_from': add_to_date(now_datetime(), hours=-1),
            'valid_until': add_to_date(now_datetime(), hours=1), 'reason': 'CLONE QA'}).insert()
        frappe.db.set_value('User', self.approver, 'enabled', 0)
        frappe.clear_cache(user=self.approver)
        self.actor(self.stranger)
        before = self.audit_count(doc)
        with self.assertRaises(frappe.PermissionError):
            workflow.decide(doc.doctype, doc.name, 'Approved', info['revision'])
        self.assertEqual(self.audit_count(doc), before)

    def test_private_file_download_and_public_attachment_guards(self):
        from frappe.utils.file_manager import save_file
        self.actor(self.requester)
        parcel = frappe.get_doc({'doctype': 'ADM Parcel', 'subject': 'CLONE QA attachment',
            'company': self.company, 'tracking_number': uuid4().hex, 'sender': 'CLONE QA',
            'recipient': self.approver, 'tracking_type': 'Parcel'}).insert()
        # Real synthetic bytes, no HR/business document and no stub File record.
        private = save_file('ADM-CLONE-' + uuid4().hex + '.txt', 'Synthetic clone QA ' + uuid4().hex,
                            parcel.doctype, parcel.name, is_private=1)
        parcel.attachment = private.file_url
        parcel.save()
        self.assertTrue(private.is_downloadable())
        self.actor(self.stranger)
        self.assertFalse(private.is_downloadable())
        self.actor(self.foreign)
        self.assertFalse(private.is_downloadable())
        self.actor(self.requester)
        public = save_file('ADM-CLONE-' + uuid4().hex + '.txt', 'Synthetic public QA ' + uuid4().hex,
                           None, None, is_private=0)
        parcel.attachment = public.file_url
        with self.assertRaisesRegex(frappe.ValidationError, 'private attachment'):
            parcel.save()
        self.assertEqual(frappe.db.get_value(parcel.doctype, parcel.name, 'attachment'), private.file_url)
        # Savepoint rollback undoes File rows, but cannot guarantee byte cleanup.
        # The outer runner quarantines only verified new synthetic orphan bytes
        # after full DB rollback, then checks the original complete snapshot.

    def test_recipient_and_booking_owner_guards(self):
        self.actor(self.requester)
        parcel = frappe.get_doc({'doctype': 'ADM Parcel', 'subject': 'CLONE QA parcel',
            'company': self.company, 'tracking_number': uuid4().hex, 'sender': 'CLONE QA',
            'recipient': self.approver, 'tracking_type': 'Parcel'}).insert()
        with self.assertRaises(frappe.PermissionError):
            operations.acknowledge_parcel(parcel.name)
        self.actor(self.approver)
        operations.acknowledge_parcel(parcel.name)
        delivered = frappe.db.get_value(parcel.doctype, parcel.name, 'delivered_at')
        with self.assertRaises(frappe.PermissionError):
            operations.acknowledge_parcel(parcel.name)
        self.assertEqual(frappe.db.get_value(parcel.doctype, parcel.name, 'delivered_at'), delivered)
        equipment = frappe.get_doc({'doctype': 'ADM Shared Equipment', 'company': self.company,
            'equipment_name': 'CLONE QA', 'enabled': 1}).insert()
        self.actor(self.requester)
        start = add_to_date(now_datetime(), days=30)
        booking = frappe.get_doc({'doctype': 'ADM Equipment Booking', 'company': self.company,
            'subject': 'CLONE QA', 'equipment': equipment.name, 'starts_at': start,
            'ends_at': add_to_date(start, hours=1)}).insert()
        self.actor(self.stranger)
        with self.assertRaises(frappe.PermissionError):
            operations.release_booking(booking.name)
        self.assertFalse(frappe.db.get_value(booking.doctype, booking.name, 'released'))
        self.actor(self.requester)
        operations.release_booking(booking.name)
        self.assertEqual(frappe.db.get_value(booking.doctype, booking.name, 'released'), 1)

    def test_rejection_reason_and_decision_retry_do_not_complete(self):
        doc, info = self.pending()
        self.actor(self.approver)
        before = self.audit_count(doc)
        with self.assertRaisesRegex(frappe.ValidationError, 'reason'):
            workflow.decide(doc.doctype, doc.name, 'Rejected', info['revision'], '  ')
        self.assertEqual(self.audit_count(doc), before)
        result = workflow.decide(doc.doctype, doc.name, 'Rejected', info['revision'], 'CLONE QA reason')
        self.assertEqual(result['state'], 'Draft')
        self.assertFalse(result['pending_action'])
        with self.assertRaises(frappe.ValidationError):
            workflow.decide(doc.doctype, doc.name, 'Approved', result['revision'])
        self.assertEqual(self.audit_count(doc), before + 1)



def quarantine_matrix_files(before):
    """Keep exact synthetic orphan bytes as evidence outside the site's files."""
    guard()
    after = restore_snapshot()
    root = Path(frappe.get_site_path()).resolve()
    added = set(after['files']) - set(before['files'])
    contents = {}
    paths = {}
    for name in added:
        candidate = root / name
        if (candidate.is_symlink() or not candidate.is_file() or
                candidate.resolve() != candidate or not candidate.is_relative_to(root)):
            raise AssertionError('Fixture cleanup refuses a symlink or escaped path')
        contents[name] = candidate.read_bytes()
        paths[name] = candidate
    plan = matrix_file_cleanup_plan(before, after, contents)
    # Validate every candidate before moving anything. Never touch a persisted File.
    for name in plan:
        url = '/' + name.removeprefix('public/')
        if frappe.db.exists('File', {'file_url': url}):
            raise AssertionError('Fixture cleanup refuses a referenced File')
    if plan:
        evidence = Path(tempfile.mkdtemp(prefix='adm-clone-file-evidence-', dir=BENCH / 'logs'))
        manifest = {'site': CLONE, 'files': {name: after['files'][name] for name in plan}}
        (evidence / 'manifest.json').write_text(json.dumps(manifest, indent=2))
        for name in plan:
            candidate = paths[name]
            if (candidate.is_symlink() or candidate.resolve() != candidate or
                    hashlib.sha256(candidate.read_bytes()).hexdigest() != after['files'][name]):
                raise AssertionError('Fixture file changed before quarantine')
            destination = evidence / ('private-' if name.startswith('private/') else 'public-')
            destination = destination.with_name(destination.name + candidate.name)
            if destination.exists():
                raise AssertionError('Fixture evidence target already exists')
            candidate.rename(destination)
        print('Synthetic fixture bytes retained outside site files: ' + str(evidence))
    if restore_snapshot() != before:
        raise AssertionError('Matrix cleanup did not restore the exact original snapshot')


def recover_matrix_files(log_name):
    """One-time guarded recovery of the two known orphan files, without restore."""
    guard()
    if not re.fullmatch(r'adm-complete-acceptance-[A-Za-z0-9]{6}', log_name):
        raise AssertionError('Require the exact acceptance log directory name')
    logs = BENCH / 'logs' / log_name
    if logs.resolve() != logs or not logs.is_dir():
        raise AssertionError('Acceptance logs escaped their exact directory')
    snapshots = []
    for name in ('source-before.json', 'clone-restored.json', 'clone-after-suite.json'):
        file = logs / name
        if file.resolve() != file:
            raise AssertionError('Snapshot path must not be a symlink')
        snapshots.append(json.loads(file.read_text()))
    before = snapshots[0]
    if any(item != before for item in snapshots):
        raise AssertionError('Original restore/full-suite evidence does not match')
    after = restore_snapshot()
    added = set(after['files']) - set(before['files'])
    if (len(added) != 2 or
            sum(name.startswith('private/files/') for name in added) != 1 or
            sum(name.startswith('public/files/') for name in added) != 1):
        raise AssertionError('Recovery requires exactly the known private/public fixture pair')
    quarantine_matrix_files(before)
    return {'recovered_fixture_files': 2, 'original_data_and_files_unchanged': True}


def run_matrix():
    guard()
    frappe.set_user('Administrator')
    before = restore_snapshot()
    original_in_test = frappe.flags.in_test
    frappe.flags.in_test = True
    try:
        result = unittest.TextTestRunner(verbosity=2).run(
            unittest.defaultTestLoader.loadTestsFromTestCase(CloneMatrix))
    finally:
        frappe.set_user('Administrator')
        frappe.db.rollback()  # Undo all fixture identities/roles and app rows.
        frappe.flags.in_test = original_in_test
        for user in CloneMatrix.users if hasattr(CloneMatrix, 'users') else []:
            frappe.clear_cache(user=user)
    quarantine_matrix_files(before)
    if not result.wasSuccessful() or result.skipped or result.testsRun != 10:
        raise AssertionError('Clone matrix did not pass all ten real tests without skips')
    return {'matrix_tests': result.testsRun, 'passed': True, 'persisted_data_unchanged': True}


def worker_main(payload):
    """Separate interpreter/DB transaction. Invoked only by the clone coordinator."""
    payload = json.loads(payload)
    frappe.init(site=CLONE, sites_path=str(BENCH / 'sites'))
    guard()  # Validate exact paths/config/distinct DB before opening a connection.
    frappe.connect()
    try:
        frappe.set_user(payload.get('user', 'Administrator'))
        # Deliberately establish a consistent-read snapshot before the row lock.
        # This reproduces real requests that read user/metadata before an action.
        frappe.db.sql('SELECT COUNT(*) FROM `tabUser`')
        control = Path(payload['control']).resolve()
        if control.parent != BENCH / 'logs' or not control.name.startswith('adm-clone-race-'):
            raise AssertionError('Unexpected race control directory')
        (control / ('ready-' + str(payload['index']))).write_text('ready')
        deadline = time.monotonic() + 25
        while not (control / 'go').exists():
            if time.monotonic() > deadline:
                raise TimeoutError('Race barrier timeout')
            time.sleep(0.02)
        kind = payload['kind']
        if kind == 'booking':
            value = {'name': frappe.get_doc(payload['document']).insert().name}
        elif kind == 'workflow':
            value = workflow.transition(payload['doctype'], payload['name'], 'Complete', 1)
        elif kind == 'parcel':
            value = operations.acknowledge_parcel(payload['name'])
        elif kind == 'feedback':
            value = operations.feedback(payload['doctype'], payload['name'],
                                        payload['rating'], 'CLONE RACE QA')
        else:
            raise AssertionError('Unknown race case')
        frappe.db.commit()
        result = {'ok': True, 'value': value, 'index': payload['index']}
    except Exception as error:
        frappe.db.rollback()
        result = {'ok': False, 'type': type(error).__name__, 'error': str(error)}
    finally:
        frappe.destroy()
    print('ADM_RACE_RESULT=' + json.dumps(result, default=str))


def race(kind, payload):
    guard()
    control = Path(tempfile.mkdtemp(prefix='adm-clone-race-', dir=BENCH / 'logs'))
    processes = []
    try:
        for index in (0, 1):
            data = dict(payload, kind=kind, control=str(control), index=index)
            if kind == 'feedback':
                data['rating'] = 5 if index == 0 else 1
            processes.append(subprocess.Popen([sys.executable, '-c',
                'from eup_administration.tests.clone_acceptance import worker_main; '
                'import sys; worker_main(sys.argv[1])', json.dumps(data, default=str)],
                # Frappe's logger resolves site/logs and ../logs from sites cwd.
                cwd=BENCH / 'sites', stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True))
        deadline = time.monotonic() + 20
        while not all((control / ('ready-' + str(n))).exists() for n in (0, 1)):
            if time.monotonic() > deadline or any(p.poll() is not None for p in processes):
                raise AssertionError('Both real DB workers must reach the barrier')
            time.sleep(0.05)
        (control / 'go').write_text('go')
        results = []
        for index, process in enumerate(processes):
            out, err = process.communicate(timeout=40)
            (control / ('worker-' + str(index) + '.log')).write_text(out + '\n' + err)
            lines = [line for line in out.splitlines() if line.startswith('ADM_RACE_RESULT=')]
            if process.returncode or len(lines) != 1:
                raise AssertionError('Worker crashed; inspect ' + str(control))
            results.append(json.loads(lines[0].split('=', 1)[1]))
        return results
    finally:
        for index, process in enumerate(processes):
            if process.poll() is None:
                process.terminate()
                process.wait(timeout=10)
            log = control / ('worker-' + str(index) + '.log')
            if not log.exists():
                out, err = process.communicate(timeout=5)
                log.write_text(out + '\n' + err)
        # Any locks/snapshots in the coordinating connection must be refreshed.
        frappe.db.rollback()


def run_races():
    """Four simultaneous races; intentional QA records remain only on the clone."""
    guard()
    frappe.set_user('Administrator')
    before = protected_snapshot()
    company = frappe.conf.adm_test_company
    case = CloneMatrix()
    case.company = company
    case.requester = 'Administrator'
    equipment = frappe.get_doc({'doctype': 'ADM Shared Equipment', 'company': company,
        'equipment_name': 'ADM CLONE RACE ' + uuid4().hex[:12], 'enabled': 1}).insert()
    start = add_to_date(now_datetime(), days=45)
    document = {'doctype': 'ADM Equipment Booking', 'company': company, 'subject': 'ADM CLONE RACE',
        'equipment': equipment.name, 'starts_at': str(start), 'ends_at': str(add_to_date(start, hours=1))}
    frappe.db.commit()
    results = race('booking', {'document': document})
    require_one_success(results, [('ValidationError', 'already reserved')])
    if frappe.db.count('ADM Equipment Booking', {'equipment': equipment.name, 'released': 0}) != 1:
        raise AssertionError('Overlapping bookings were committed')
    print('RACE PASS: equipment overlap, two independent transactions')

    policy = case.policy()
    # Administrator explicitly exercises the same protected transition endpoint.
    policy.transitions[0].allowed_role = 'System Manager'
    policy.save()
    doc = case.ticket()
    workflow.start(doc.doctype, doc.name, policy.name)
    frappe.db.commit()
    results = race('workflow', {'doctype': doc.doctype, 'name': doc.name})
    require_one_success(results, [('ValidationError', 'Reload')])
    run_name = frappe.db.get_value('ADM Workflow Run', {'reference_key': workflow.key(doc.doctype, doc.name)}, 'name')
    run = frappe.get_doc('ADM Workflow Run', run_name)
    if (int(run.revision) != 2 or run.current_state != 'Done' or case.audit_count(doc) != 2):
        raise AssertionError('Workflow race duplicated/lost a transition or audit')
    print('RACE PASS: workflow revision and exactly one transition audit')

    frappe.db.commit()
    results = race('feedback', {'doctype': doc.doctype, 'name': doc.name})
    winner = require_one_success(results, [('UniqueValidationError', ''),
                                           ('DuplicateEntryError', '')])
    if frappe.db.count('ADM Operation Feedback', {'reference_name': doc.name}) != 1:
        raise AssertionError('Feedback race produced multiple rows')
    if not frappe.db.exists('ADM Operation Feedback', winner['value']['feedback']):
        raise AssertionError('Winning feedback was not persisted')
    expected_rating = 5 if winner['index'] == 0 else 1
    if frappe.db.get_value('ADM Operation Feedback', winner['value']['feedback'],
                           ['rating', 'comment']) != (expected_rating, 'CLONE RACE QA'):
        raise AssertionError('Duplicate attempt changed the original feedback')
    print('RACE PASS: feedback unique constraint under simultaneous requests')

    recipient = frappe.conf.adm_test_approver
    parcel = frappe.get_doc({'doctype': 'ADM Parcel', 'subject': 'ADM CLONE RACE', 'company': company,
        'tracking_number': uuid4().hex, 'sender': 'ADM CLONE QA', 'recipient': recipient,
        'tracking_type': 'Parcel'}).insert()
    frappe.db.commit()
    results = race('parcel', {'name': parcel.name, 'user': recipient})
    require_one_success(results, [('PermissionError', 'acknowledge once')])
    if not frappe.db.get_value(parcel.doctype, parcel.name, 'delivered_at'):
        raise AssertionError('Parcel acknowledgement was not persisted')
    versions = frappe.get_all('Version', filters={'ref_doctype': parcel.doctype, 'docname': parcel.name},
                              fields=['data'])
    changes = [r for r in versions if 'delivered_at' in r.data]
    if len(changes) != 1:
        raise AssertionError('Parcel race updated delivery more than once')
    if protected_snapshot() != before:
        raise AssertionError('Race cases changed protected data')
    print('RACE PASS: recipient acknowledges exactly once')
    return {'race_cases': 4, 'passed': True, 'protected_unchanged': True,
            'scope': 'QA rows retained on restored clone only'}
