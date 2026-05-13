"""
tools/utility_tools.py – Utility agent tools:
  - Mathematical calculator
  - Unit converter (length, weight, temperature, currency stubs)
  - Reminder management
"""

from __future__ import annotations

import math
from datetime import datetime, timezone
from typing import Optional

import dateparser
from simpleeval import simple_eval, EvalWithCompoundTypes
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from models import Reminder, ReminderStatus


# ─────────────────────────────────────────────────────────────────────────────
#  Calculator
# ─────────────────────────────────────────────────────────────────────────────

# Safe constants available inside expressions (non-callable)
_SAFE_NAMES = {
    "pi": math.pi,
    "e": math.e,
}

# Safe functions available inside expressions (callable)
_SAFE_FUNCTIONS = {
    "abs": abs, "round": round, "min": min, "max": max,
    "sum": sum, "pow": pow, "sqrt": math.sqrt,
    "sin": math.sin, "cos": math.cos, "tan": math.tan,
    "log": math.log, "log10": math.log10, "log2": math.log2,
    "ceil": math.ceil, "floor": math.floor,
}


def calculate(expression: str) -> dict:
    """
    Safely evaluate a mathematical expression.

    Args:
        expression: A mathematical expression string, e.g. '(45 * 12) / 7' or 'sqrt(144)'.

    Returns:
        A dict with 'result' key or 'error' key if evaluation fails.

    Examples:
        calculate("2 + 2")           → {"result": 4}
        calculate("sqrt(144)")        → {"result": 12.0}
        calculate("15% of 2400")      → not valid; use "2400 * 0.15"
    """
    # Handle percentage shorthands like "15% of 2400"
    expr = expression.strip()
    if "% of" in expr.lower():
        try:
            parts = expr.lower().split("% of")
            pct = float(parts[0].strip())
            base = float(parts[1].strip())
            result = (pct / 100) * base
            return {"result": round(result, 6), "expression": expression}
        except Exception:
            pass

    try:
        evaluator = EvalWithCompoundTypes(names=_SAFE_NAMES, functions=_SAFE_FUNCTIONS)
        result = evaluator.eval(expr)
        if isinstance(result, float):
            result = round(result, 10)
        return {"result": result, "expression": expression}
    except Exception as exc:
        return {"error": f"Could not evaluate expression: {exc}", "expression": expression}


# ─────────────────────────────────────────────────────────────────────────────
#  Unit Converter
# ─────────────────────────────────────────────────────────────────────────────

_CONVERSIONS: dict[str, dict[str, float]] = {
    # Length (base: metres)
    "m": 1.0, "km": 1000.0, "cm": 0.01, "mm": 0.001,
    "mile": 1609.344, "miles": 1609.344,
    "yard": 0.9144, "yards": 0.9144,
    "foot": 0.3048, "feet": 0.3048, "ft": 0.3048,
    "inch": 0.0254, "inches": 0.0254, "in": 0.0254,
    # Weight (base: kilograms)
    "kg": 1.0, "g": 0.001, "mg": 0.000001,
    "lb": 0.453592, "lbs": 0.453592, "pound": 0.453592, "pounds": 0.453592,
    "oz": 0.0283495, "ounce": 0.0283495, "ounces": 0.0283495,
    "tonne": 1000.0, "ton": 907.185,
    # Volume (base: litres)
    "l": 1.0, "litre": 1.0, "liters": 1.0, "ml": 0.001,
    "gallon": 3.78541, "gallons": 3.78541,
    "pint": 0.473176, "pints": 0.473176,
    "cup": 0.236588, "cups": 0.236588,
    # Speed (base: m/s)
    "mps": 1.0, "kmph": 1/3.6, "kph": 1/3.6, "mph": 0.44704,
    # Data (base: bytes)
    "byte": 1.0, "bytes": 1.0, "kb": 1024.0, "mb": 1048576.0,
    "gb": 1073741824.0, "tb": 1099511627776.0,
}

_LENGTH_UNITS = {"m", "km", "cm", "mm", "mile", "miles", "yard", "yards", "foot", "feet", "ft", "inch", "inches", "in"}
_WEIGHT_UNITS = {"kg", "g", "mg", "lb", "lbs", "pound", "pounds", "oz", "ounce", "ounces", "tonne", "ton"}
_VOLUME_UNITS = {"l", "litre", "liters", "ml", "gallon", "gallons", "pint", "pints", "cup", "cups"}
_SPEED_UNITS  = {"mps", "kmph", "kph", "mph"}
_DATA_UNITS   = {"byte", "bytes", "kb", "mb", "gb", "tb"}

_UNIT_FAMILIES = [_LENGTH_UNITS, _WEIGHT_UNITS, _VOLUME_UNITS, _SPEED_UNITS, _DATA_UNITS]


def _same_family(u1: str, u2: str) -> bool:
    u1, u2 = u1.lower(), u2.lower()
    for family in _UNIT_FAMILIES:
        if u1 in family and u2 in family:
            return True
    # Temperature handled separately
    temp_units = {"c", "celsius", "f", "fahrenheit", "k", "kelvin"}
    return u1 in temp_units and u2 in temp_units


def _convert_temperature(value: float, from_unit: str, to_unit: str) -> float:
    fu, tu = from_unit.lower()[0], to_unit.lower()[0]  # first char
    # Convert from → Celsius
    if fu == "f":
        celsius = (value - 32) * 5 / 9
    elif fu == "k":
        celsius = value - 273.15
    else:
        celsius = value
    # Convert Celsius → to
    if tu == "f":
        return celsius * 9 / 5 + 32
    elif tu == "k":
        return celsius + 273.15
    return celsius


def convert_units(value: float, from_unit: str, to_unit: str) -> dict:
    """
    Convert a numeric value between units.

    Supported categories: length, weight, volume, speed, data size, temperature.

    Args:
        value: The numeric value to convert.
        from_unit: Source unit (e.g. 'km', 'kg', 'celsius', 'gb').
        to_unit: Target unit (e.g. 'miles', 'lbs', 'fahrenheit', 'mb').

    Returns:
        Dict with 'result', 'from', 'to' keys.
    """
    fu, tu = from_unit.lower().strip(), to_unit.lower().strip()

    # Temperature
    temp_units = {"c", "celsius", "f", "fahrenheit", "k", "kelvin"}
    if fu[0] in "cfk" and tu[0] in "cfk" and (fu in temp_units or tu in temp_units):
        try:
            result = _convert_temperature(value, fu, tu)
            return {"result": round(result, 4), "from": f"{value} {from_unit}", "to": f"{result:.4f} {to_unit}"}
        except Exception:
            pass

    if fu not in _CONVERSIONS:
        return {"error": f"Unknown unit: '{from_unit}'"}
    if tu not in _CONVERSIONS:
        return {"error": f"Unknown unit: '{to_unit}'"}
    if not _same_family(fu, tu):
        return {"error": f"Cannot convert '{from_unit}' to '{to_unit}' – they are different unit types."}

    base_value = value * _CONVERSIONS[fu]
    result = base_value / _CONVERSIONS[tu]
    return {"result": round(result, 6), "from": f"{value} {from_unit}", "to": f"{result:.6g} {to_unit}"}


# ─────────────────────────────────────────────────────────────────────────────
#  Reminders
# ─────────────────────────────────────────────────────────────────────────────

def _reminder_to_dict(r: Reminder) -> dict:
    return {
        "id": r.id,
        "title": r.title,
        "remind_at": r.remind_at.isoformat(),
        "status": r.status.value,
        "created_at": r.created_at.isoformat(),
    }


async def set_reminder(
    db: AsyncSession,
    user_id: str,
    title: str,
    remind_at: str,
) -> dict:
    """
    Set a reminder for the user.

    Args:
        title: What to remind the user about.
        remind_at: Natural language or ISO datetime string
                   e.g. 'tomorrow at 9am', 'in 2 hours', '2025-06-15T08:00:00'.

    Returns:
        The created reminder or an error if the time could not be parsed.
    """
    parsed_time = dateparser.parse(
        remind_at,
        settings={"PREFER_DATES_FROM": "future", "RETURN_AS_TIMEZONE_AWARE": True},
    )
    if not parsed_time:
        return {"success": False, "error": f"Could not understand the time: '{remind_at}'. Try '2025-06-15 09:00' or 'tomorrow at 9am'."}

    reminder = Reminder(user_id=user_id, title=title.strip(), remind_at=parsed_time)
    db.add(reminder)
    await db.commit()
    await db.refresh(reminder)
    return {"success": True, "reminder": _reminder_to_dict(reminder)}


async def list_reminders(
    db: AsyncSession,
    user_id: str,
    status: Optional[str] = "active",
) -> dict:
    """
    List the user's reminders.

    Args:
        status: Filter by 'active', 'triggered', or 'cancelled'. Defaults to 'active'.

    Returns:
        A list of reminders.
    """
    try:
        st = ReminderStatus(status.lower()) if status else ReminderStatus.ACTIVE
    except ValueError:
        st = ReminderStatus.ACTIVE

    stmt = (
        select(Reminder)
        .where(Reminder.user_id == user_id, Reminder.status == st)
        .order_by(Reminder.remind_at.asc())
        .limit(20)
    )
    result = await db.execute(stmt)
    reminders = result.scalars().all()
    return {"reminders": [_reminder_to_dict(r) for r in reminders], "count": len(reminders)}


async def cancel_reminder(
    db: AsyncSession,
    user_id: str,
    reminder_id: str,
) -> dict:
    """
    Cancel an active reminder.

    Args:
        reminder_id: The ID of the reminder to cancel.

    Returns:
        Success flag.
    """
    result = await db.execute(
        select(Reminder).where(Reminder.id == reminder_id, Reminder.user_id == user_id)
    )
    reminder = result.scalar_one_or_none()
    if not reminder:
        return {"success": False, "error": f"Reminder '{reminder_id}' not found."}

    reminder.status = ReminderStatus.CANCELLED
    await db.commit()
    return {"success": True, "message": f"Reminder '{reminder.title}' cancelled."}
