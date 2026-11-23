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


@router.get("/metrics")
def metrics(db: Session = Depends(get_db)) -> dict:
    """SPEC 16 metrics computed from the audit trail (Application Insights in Phase C)."""
    from appeal_core.llm.base import CALL_LOG
    from appeal_core.privacy.leak_gate import blocks_count
    from sqlalchemy import func, text

    lat = dict(db.execute(select(AgentRun.agent, func.percentile_cont(0.5).within_group(AgentRun.latency_ms)).group_by(AgentRun.agent)).all())
    writer_runs = db.execute(text("SELECT case_id, count(*) FROM agent_run WHERE agent='writer' GROUP BY case_id")).all()
    total_cases = db.scalar(select(func.count()).select_from(Case)) or 0
    by_status = dict(db.execute(select(Case.status, func.count()).group_by(Case.status)).all())
    cls = db.execute(text("SELECT count(*) FILTER (WHERE (output->>'needs_user')::boolean), count(*) FROM agent_run WHERE agent='classifier'")).one()
    inj = db.scalar(text("SELECT count(*) FROM extraction WHERE jsonb_array_length(coalesce(injection->'flags','[]'::jsonb)) > 0"))
    cost = db.scalar(text("SELECT coalesce(avg(s), 0) FROM (SELECT sum(cost_usd) s FROM agent_run GROUP BY case_id) t"))
    return {
        "latency_ms_p50_by_agent": {k: float(v) for k, v in lat.items()},
        "revisions_per_case_avg": (sum(n for _, n in writer_runs) / len(writer_runs) - 1) if writer_runs else 0.0,
        "needs_human_rate": by_status.get("NEEDS_HUMAN", 0) / total_cases if total_cases else 0.0,
        "classifier_ask_user_rate": (cls[0] / cls[1]) if cls[1] else 0.0,
        "leak_gate_blocks_this_process": blocks_count(),
        "injection_detections": int(inj or 0),
        "cost_usd_per_case_avg": float(cost or 0.0),
        "provider_calls_this_process": len(CALL_LOG.records),
        "cases_by_status": by_status,
    }
