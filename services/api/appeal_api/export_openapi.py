"""Export the OpenAPI spec to packages/schemas/openapi.json (the TS client is generated from it)."""

import json
from pathlib import Path

from appeal_api.main import app

if __name__ == "__main__":
    out = Path(__file__).resolve().parents[3] / "packages" / "schemas" / "openapi.json"
    out.write_text(json.dumps(app.openapi(), indent=2), encoding="utf-8")
    print(f"wrote {out}")
