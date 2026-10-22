"""Pure, bounded policy expressions. No eval, SQL, imports or document access."""
import json
import math
import operator

OPERATIONS = (
    "ADM Facility Ticket", "ADM Driver Checklist", "ADM Preventive Plan",
    "ADM Parcel", "ADM Equipment Booking", "ADM Contract Register",
    "ADM Operational Incident", "ADM Recurring Task", "ADM Task Occurrence",
)
CONDITION_FIELDS = {"priority", "department", "company", "category", "severity"}
OPS = {"eq": operator.eq, "ne": operator.ne, "in": lambda a, b: a in b}


def conditions(raw):
    value = json.loads(raw or "[]") if isinstance(raw, str) else ([] if raw is None else raw)
    if not isinstance(value, list) or len(value) > 20:
        raise ValueError("Conditions must be a list of at most 20 comparisons")
    for row in value:
        if not isinstance(row, dict) or set(row) != {"field", "op", "value"}:
            raise ValueError("Each condition needs field, op and value")
        if row["field"] not in CONDITION_FIELDS or row["op"] not in OPS:
            raise ValueError("Unsupported condition field or operator")
        expected = row["value"]
        if row["op"] == "in":
            if not isinstance(expected, list) or len(expected) > 50 or not all(isinstance(x, str) for x in expected):
                raise ValueError("in requires a list of at most 50 strings")
        elif not isinstance(expected, str):
            raise ValueError("Comparison value must be text")
    return value


def matches(raw, values):
    return all(OPS[c["op"]](values.get(c["field"]), c["value"]) for c in conditions(raw))


def positive(value, label, allow_zero=False):
    try:
        result = float(value)
    except (ValueError, TypeError):
        raise ValueError(label + " must be numeric") from None
    if not math.isfinite(result) or result < 0 or (not allow_zero and result == 0):
        raise ValueError(label + " must be finite and positive")
    return result


def validate_graph(states, transitions, initial, bands):
    names = [s["state"] for s in states]
    if not names or len(names) > 50 or len(set(names)) != len(names) or initial not in names:
        raise ValueError("States must be unique and contain the initial state")
    if len(transitions) > 100 or len(bands) > 100:
        raise ValueError("Policy exceeds size limit")
    terminal = {s["state"] for s in states if s.get("is_terminal")}
    if initial in terminal or not terminal:
        raise ValueError("Policy needs a nonterminal start and a terminal state")
    actions = []
    for s in states:
        positive(s.get("sla_hours") or 0, "SLA hours", allow_zero=True)
    for t in transitions:
        if not t.get("action") or t["action"] in actions:
            raise ValueError("Action labels must be unique")
        actions.append(t["action"])
        if t["from_state"] not in names or t["to_state"] not in names or t["from_state"] in terminal:
            raise ValueError("Invalid transition states")
        if not t.get("allowed_role"):
            raise ValueError("Transition requires a role")
        conditions(t.get("conditions"))
        selected = [b for b in bands if b["transition_action"] == t["action"]]
        numbers = [int(b["step_number"]) for b in selected]
        if bool(t.get("approval_required")) != bool(selected) or sorted(numbers) != list(range(1, len(numbers)+1)):
            raise ValueError("Approval bands must be sequential from 1")
        for b in selected:
            if not b.get("approver_role") or not b.get("same_company"):
                raise ValueError("Approval needs role and mandatory company isolation")
    if any(b["transition_action"] not in actions for b in bands):
        raise ValueError("Approval band references unknown action")
    reachable = {initial}
    for _ in names:
        reachable |= {t["to_state"] for t in transitions if t["from_state"] in reachable}
    if reachable != set(names):
        raise ValueError("All states must be reachable")
    # Every reachable state must have a route to a terminal state.
    finishing = set(terminal)
    for _ in names:
        finishing |= {t["from_state"] for t in transitions if t["to_state"] in finishing}
    if finishing != set(names):
        raise ValueError("Every state needs a path to a terminal state")


def forecast(quantities, horizon_days=7):
    """Transparent trailing mean, not a trained predictive model."""
    if len(quantities) < 7:
        return {"available": False, "reason": "At least seven daily samples required"}
    clean = [positive(q, "Daily consumption", allow_zero=True) for q in quantities[-28:]]
    mean = sum(clean) / len(clean)
    return {"available": True, "method": "trailing_daily_mean",
            "sample_days": len(clean), "daily_mean": mean,
            "expected_quantity": mean * positive(horizon_days, "Horizon")}
