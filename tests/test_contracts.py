"""Contract tests: agent JSON Schemas and the exported OpenAPI spec stay in sync with the code."""

import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def test_openapi_export_is_current():
    from appeal_api.main import app

    on_disk = json.loads((ROOT / "packages" / "schemas" / "openapi.json").read_text(encoding="utf-8"))
    assert on_disk == json.loads(json.dumps(app.openapi())), "run: uv run python -m appeal_api.export_openapi && (cd apps/web && npm run gen:api)"


def test_agent_schemas_are_current(tmp_path):
    from appeal_core.schemas import export_json_schemas

    for name in export_json_schemas(tmp_path):
        assert json.loads((tmp_path / name).read_text()) == json.loads((ROOT / "packages" / "schemas" / name).read_text()), name


def test_agent_outputs_validate():
    from appeal_core.schemas import Classification, LetterDraft, Review

    Classification(category="medical_necessity", probability=0.9, rationale="x", source="model")
    LetterDraft(sections=[{"id": "intro", "title": "Intro", "sentences": [{"text": "Hi", "citations": ["R1"], "kind": "legal"}]}])
    Review(score=1.0)
