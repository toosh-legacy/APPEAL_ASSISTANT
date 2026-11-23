from datetime import date, timedelta

from appeal_core.deadlines import compute_deadlines, ics_for, next_level_options
from appeal_core.kb import PLAN_TYPES
from hypothesis import given, settings
from hypothesis import strategies as st

DAYS = {"employer_self_funded": 180, "employer_fully_insured": 180, "individual_marketplace": 180, "medicare_advantage": 60, "medicaid_managed_care": 60}


@settings(max_examples=200, deadline=None)
@given(notice=st.dates(min_value=date(2000, 1, 1), max_value=date(2100, 12, 31)), plan=st.sampled_from(PLAN_TYPES))
def test_due_date_is_notice_plus_cited_days(notice, plan):
    out = compute_deadlines(plan, notice)
    assert len(out) == 1
    d = out[0]
    assert date.fromisoformat(d["due_date"]) - notice == timedelta(days=DAYS[plan])
    assert d["basis_chunk_id"].startswith("reg:")  # never a deadline without a cited rule
    assert d["trigger_date"] == notice.isoformat()


@settings(max_examples=100, deadline=None)
@given(notice=st.dates(min_value=date(2020, 1, 1), max_value=date(2030, 12, 31)), today=st.dates(min_value=date(2020, 1, 1), max_value=date(2031, 12, 31)), plan=st.sampled_from(PLAN_TYPES))
def test_days_remaining_consistent(notice, today, plan):
    d = compute_deadlines(plan, notice, today=today)[0]
    assert date.fromisoformat(d["due_date"]) - today == timedelta(days=d["days_remaining"])


@given(plan=st.text(max_size=20))
def test_unknown_plan_type_gives_no_deadline(plan):
    if plan not in PLAN_TYPES:
        assert compute_deadlines(plan, date(2025, 1, 1)) == []
        assert next_level_options(plan) == []


def test_ics_is_all_day_event_on_due_date():
    d = compute_deadlines("medicaid_managed_care", date(2025, 3, 1))[0]
    ics = ics_for(d, "case-1")
    assert "DTSTART;VALUE=DATE:20250430" in ics and ics.startswith("BEGIN:VCALENDAR") and "\r\n" in ics
