"""Opt-in internal SLA escalation, no outbound mail or webhooks."""
import frappe
from frappe.utils import now_datetime
from eup_administration.v4.workflow import _load, _audit, save_internal


def escalate():
    if not frappe.conf.get("adm_v4_jobs_enabled"):
        return
    for row in frappe.get_all("ADM Workflow Run", filters={
        "due_at": ["<", now_datetime()], "escalated": 0
    }, fields=["reference_doctype", "reference_name"]):
        doc, run, policy = _load(row.reference_doctype, row.reference_name)
        if run.escalated or not run.due_at or run.due_at >= now_datetime():
            continue
        state = next(s for s in policy.states if s.state == run.current_state)
        if state.is_terminal:
            continue
        run.escalated = 1
        run.revision += 1
        save_internal(run)
        _audit(doc, run, "SLA Escalation", run.current_state, run.current_state,
               comment="Escalation role: " + (state.escalation_role or "Administration Manager"))
        save_internal(frappe.get_doc({
            "doctype": "ADM SLA Escalation", "reference_doctype": doc.doctype,
            "reference_name": doc.name, "company": doc.company,
            "escalation_role": state.escalation_role or "Administration Manager",
            "state": run.current_state, "due_at": run.due_at,
            "escalation_key": run.name + ":" + str(run.revision)
        }), insert=True)
