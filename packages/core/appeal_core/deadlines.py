"""Deadline calculator. Only rules with a resolved citation are used (hard rule 3)."""

from __future__ import annotations

from datetime import date, timedelta
from typing import Any

from appeal_core.kb import deadline_rules


def compute_deadlines(plan_type: str | None, notice_date: date | None, today: date | None = None) -> list[dict[str, Any]]:
    if not plan_type or not notice_date:
        return []
    out = []
    for r in deadline_rules()["rules"]:
        if not r["enabled"] or plan_type not in r["plan_types"]:
            continue
        if r["trigger"] != "notice_date":
            continue
        due = notice_date + timedelta(days=int(r["days"]))
        item = {
            "kind": r["kind"],
            "label": r["label"],
            "rule_id": r["id"],
            "days": int(r["days"]),
            "trigger_date": notice_date.isoformat(),
            "due_date": due.isoformat(),
            "basis_chunk_id": r["basis_chunk_id"],
            "basis_citation": r["basis_citation"],
            "also_chunk_id": r.get("also_chunk_id"),
            "letter_text": r.get("letter_text"),
        }
        if today is not None:
            item["days_remaining"] = (due - today).days
        out.append(item)
    return out


def next_level_options(plan_type: str | None) -> list[dict[str, Any]]:
    if not plan_type:
        return []
    return [
        {
            "kind": r["kind"],
            "label": r["label"],
            "window_text": r["window_text"],
            "rule_id": r["id"],
            "basis_chunk_id": r["basis_chunk_id"],
            "basis_citation": r["basis_citation"],
        }
        for r in deadline_rules()["next_levels"]
        if r["enabled"] and plan_type in r["plan_types"]
    ]


def ics_for(deadline: dict[str, Any], uid: str) -> str:
    """RFC 5545 calendar (the `ics` library): an all-day event on the due date with reminders 7 days and
    1 day before."""
    from datetime import timedelta

    from ics import Calendar, DisplayAlarm, Event

    ev = Event(
        name=f"Appeal deadline: {deadline['label']}",
        begin=date.fromisoformat(deadline["due_date"]),
        uid=f"{uid}@appeal-assistant.local",
        description=f"Based on {deadline.get('basis_citation') or 'cited rule'}. Check your notice for the exact date.",
    )
    ev.make_all_day()
    label = f"Appeal deadline: {deadline['label']}"
    ev.alarms = [DisplayAlarm(trigger=timedelta(days=-7), display_text=f"In 7 days: {label}"), DisplayAlarm(trigger=timedelta(days=-1), display_text=f"Tomorrow: {label}")]
    cal = Calendar(creator="-//Appeal Assistant//local//EN")
    cal.events.add(ev)
    # ics 0.7 omits DTSTAMP, which RFC 5545 requires on every VEVENT
    stamp = f"DTSTAMP:{date.today().strftime('%Y%m%d')}T000000Z"
    return cal.serialize().replace("BEGIN:VEVENT\r\n", "BEGIN:VEVENT\r\n" + stamp + "\r\n", 1)
