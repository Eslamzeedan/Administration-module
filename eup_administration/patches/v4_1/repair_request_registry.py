"""Rebuild only the derived administration index; preserve source/audit history."""
import frappe


def execute():
    if not frappe.db.table_exists("ADM Request Registry"):
        return
    from eup_administration.v3.registry import rebuild_registry
    # Patch runner can operate under another context. Restore it even on error.
    previous = frappe.session.user
    try:
        frappe.set_user("Administrator")
        rebuild_registry()
    finally:
        frappe.set_user(previous)
