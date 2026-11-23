"""Admin views (F10). Locally protected by the admin token from .env; Entra roles in Phase C."""

from __future__ import annotations

from appeal_core.models import AgentRun, Case, DatasetManifest, EvalRun, Extraction
from appeal_core.settings import ROOT
from fastapi import APIRouter, Depends
from sqlalchemy import select
from sqlalchemy.orm import Session

from appeal_api.deps import get_db, require_admin

router = APIRouter(prefix="/admin/v1", dependencies=[Depends(require_admin)])


@router.get("/traces")
def traces(limit: int = 20, db: Session = Depends(get_db)) -> dict:
    cases = db.scalars(select(Case).order_by(Case.created_at.desc()).limit(limit)).all()
    out = []
    for c in cases:
        ex = db.scalar(select(Extraction).where(Extraction.case_id == c.id))
        runs = db.scalars(select(AgentRun).where(AgentRun.case_id == c.id).order_by(AgentRun.created_at)).all()
        out.append(
            {
                "case_id": c.id,
                "status": c.status,
                "degraded": c.degraded,
                "redacted_input": ex.redacted_text if ex else None,  # tokenized; never raw
                "steps": [
                    {
                        "agent": r.agent,
                        "latency_ms": r.latency_ms,
                        "prompt_id": r.prompt_id,
                        "prompt_version": r.prompt_version,
                        "provider": r.provider,
                        "model": r.model,
                        "tokens_in": r.tokens_in,
                        "tokens_out": r.tokens_out,
                        "cost_usd": r.cost_usd,
                        "output": r.output if r.agent != "intake" else {"extracted": (r.output or {}).get("extracted")},
                    }
                    for r in runs
                ],
            }
        )
    return {"cases": out}


@router.get("/evals")
def evals(db: Session = Depends(get_db)) -> dict:
    rows = db.scalars(select(EvalRun).order_by(EvalRun.created_at.desc()).limit(200)).all()
    report = ROOT / "evals" / "reports" / "latest.md"
    return {
        "runs": [{"suite": r.suite, "passed": r.passed, "metrics": r.metrics, "git_sha": r.git_sha, "at": r.created_at} for r in rows],
        "latest_report": report.read_text(encoding="utf-8") if report.exists() else None,
    }


@router.get("/datasets")
def datasets(db: Session = Depends(get_db)) -> dict:
    import json

    m = json.loads((ROOT / "data" / "manifest.json").read_text(encoding="utf-8"))
    rows = db.scalars(select(DatasetManifest)).all()
    return {
        "manifest": m["datasets"],
        "loaded": [{"name": r.name, "rows": r.rows, "sha256": r.sha256, "downloaded_at": r.downloaded_at, "schema_ok": r.schema_ok, "source": r.source} for r in rows],
    }
