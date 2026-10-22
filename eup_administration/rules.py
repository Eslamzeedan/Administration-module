"""Framework-independent input validation shared by controllers and tests."""
from datetime import timedelta
from decimal import Decimal, InvalidOperation

def reading(value):
    if value is None or value == "" or isinstance(value, bool):
        raise ValueError("Odometer reading is required")
    try:
        result = Decimal(str(value))
    except InvalidOperation as exc:
        raise ValueError("Invalid odometer reading") from exc
    if not result.is_finite() or result < 0:
        raise ValueError("Odometer reading must be finite and nonnegative")
    converted = float(result)
    from math import isfinite
    if not isfinite(converted):
        raise ValueError('Reading is outside the supported numeric range')
    return converted

def start_reading(value, previous, reason=""):
    current, previous = reading(value), reading(previous)
    if current < previous:
        raise ValueError("Start reading cannot be below the vehicle's last reading")
    if current > previous and not str(reason or "").strip():
        raise ValueError("Explain the kilometers since the previous recorded reading")
    return current

def trip_distance(start, end):
    start, end = reading(start), reading(end)
    if end < start:
        raise ValueError("End reading cannot be below start reading")
    return round(end - start, 3)

def overlaps(a_start, a_end, b_start, b_end, buffer_minutes=0):
    if a_end <= a_start or b_end <= b_start:
        raise ValueError("End must follow start")
    pad = timedelta(minutes=buffer_minutes)
    return a_start < b_end + pad and a_end + pad > b_start


def money(value, positive=True):
    result = reading(value)
    if positive and result <= 0:
        raise ValueError('Amount or quantity must be positive')
    return result


def recurrence_dates(start, end, frequency, count):
    if frequency not in ('Daily', 'Weekly'):
        raise ValueError('Recurrence must be Daily or Weekly')
    try:
        number = int(count)
    except (TypeError, ValueError, OverflowError) as exc:
        raise ValueError('Occurrence count must be an integer') from exc
    if isinstance(count, bool) or str(number) != str(count) or not 2 <= number <= 52:
        raise ValueError('Total occurrences must be an integer from 2 to 52')
    if end <= start:
        raise ValueError('End must follow start')
    step = timedelta(days=1 if frequency == 'Daily' else 7)
    if end - start > step:
        raise ValueError('Occurrences would overlap')
    return [(start + step * i, end + step * i) for i in range(1, number)]
