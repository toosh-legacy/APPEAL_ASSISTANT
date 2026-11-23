"""Extraction must not depend on one letter layout (Phase B: EOB-style statements)."""

from appeal_core.llm.offline import _table_fields, offline_extract

EOB = """EXPLANATION OF BENEFITS - THIS IS NOT A BILL
Example Health Plan
Questions? Call 555-0100

Statement date  June 10, 2025
CLAIM DETAIL
Date of service | What you received | Billed | Plan paid
April 13, 2025 | outpatient physical therapy | $82.00 | $0.00

Why this claim was not paid
Your plan does not include outpatient physical therapy as a benefit.
"""


def test_document_title_is_not_the_insurer():
    assert offline_extract(EOB)["fields"]["insurer"]["value"] == "Example Health Plan"


def test_claim_table_gives_service_and_date():
    f = offline_extract(EOB)["fields"]
    assert f["service"]["value"] == "outpatient physical therapy"
    assert f["date_of_service"]["value"] == "2025-04-13"


def test_reason_under_a_heading():
    assert offline_extract(EOB)["fields"]["denial_reason"]["value"].startswith("Your plan does not include")


def test_table_needs_matching_row_width():
    assert _table_fields(["Date of service | Service | Billed", "April 13, 2025 | MRI"]) == {}
    assert _table_fields(["Service\tDate of service\tBilled", "MRI\t04/13/2025\t$5"]) == {"service": "MRI", "date_of_service": "04/13/2025"}
