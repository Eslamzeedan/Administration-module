"""Source registration plus preservation during Frappe 16.31.0 Workspace imports.

The fixed old timestamp makes ordinary sync leave existing documents alone. The
before_import hook also copies the complete existing payload for a forced/future
import. No global framework override, source rewrite or nonexistent standard flag.
"""
from copy import deepcopy
import json
from pathlib import Path
import frappe

WORKSPACES = ('EuP Administration', 'EuP Administration v2', 'EuP Administration v3')
VOLATILE = {'name', 'owner', 'creation', 'modified', 'modified_by', 'idx', 'docstatus',
    'parent', 'parenttype', 'parentfield', '__islocal', '__unsaved'}


def definition(name):
    if name not in WORKSPACES:
        raise ValueError('Unknown administration workspace')
    slug = name.lower().replace(' ', '_')
    source = Path(__file__).parent/'eup_administration'/'workspace'/slug/(slug+'.json')
    return json.loads(source.read_text(encoding='utf-8'))


def preserve_on_import(doc, method=None):
    # Only official import/install/migration paths run this hook. A user API cannot
    # use it to adopt another workspace's privileges or read its configuration.
    if doc.name not in WORKSPACES or not frappe.flags.in_import:
        return
    if not frappe.db.exists('Workspace', doc.name):
        return
    existing = frappe.get_doc('Workspace', doc.name).as_dict()
    # Include custom fields and every child table; preserve row identities and
    # configuration, not just visible content. Frappe resets __islocal for import.
    for key, value in existing.items():
        if (not key.startswith('_') or key in {'_user_tags','_comments','_assign','_liked_by'}) and key not in {'doctype', 'name'}:
            doc.set(key, deepcopy(value))


def ensure_workspaces():
    for name in WORKSPACES:
        if not frappe.db.exists('Workspace', name):
            data = definition(name)
            # Deployment metadata timestamps are an import policy, not user data.
            data.pop('modified', None)
            frappe.get_doc(data).insert(ignore_permissions=True)


def semantic_payload(value):
    """Normalize bookkeeping only; retain workspace/child-table custom fields."""
    if isinstance(value, list):
        return [semantic_payload(row) for row in value]
    if isinstance(value, dict):
        return {key: semantic_payload(item) for key, item in value.items()
            if key not in VOLATILE and (not key.startswith('_') or key in {'_user_tags','_comments','_assign','_liked_by'}) and key != 'doctype'}
    return value
