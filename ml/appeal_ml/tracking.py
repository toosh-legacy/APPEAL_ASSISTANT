"""MLflow experiment tracking and model registry (local SQLite backend + file artifacts in var/mlflow/).

Every `python -m appeal_ml.train` run logs one MLflow run per model (params from training_config.json,
flattened numeric metrics from metrics.json, the model card and plots as artifacts) and registers the model
as `appeal-<m1|m2|m3>`. A model that passes the promotion check gets the registry alias `champion`.
Optuna studies log one nested run per trial. Point MLFLOW_TRACKING_URI at an Azure ML workspace to use the
same code against a hosted registry.

    uv run mlflow ui --backend-store-uri sqlite:///var/mlflow/mlflow.db
"""

from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any

from appeal_ml.common import ROOT, artifact_dir

MLFLOW_DIR = ROOT / "var" / "mlflow"
EXPERIMENT = "appeal-assistant-models"


def setup() -> Any:
    import mlflow

    MLFLOW_DIR.mkdir(parents=True, exist_ok=True)
    uri = os.environ.get("MLFLOW_TRACKING_URI") or f"sqlite:///{(MLFLOW_DIR / 'mlflow.db').as_posix()}"
    mlflow.set_tracking_uri(uri)
    if mlflow.get_experiment_by_name(EXPERIMENT) is None:
        mlflow.create_experiment(EXPERIMENT, artifact_location=(MLFLOW_DIR / "artifacts").as_uri())
    mlflow.set_experiment(EXPERIMENT)
    return mlflow


def _flat(d: Any, prefix: str = "") -> dict[str, float]:
    out: dict[str, float] = {}
    if isinstance(d, dict):
        for k, v in d.items():
            out.update(_flat(v, f"{prefix}{k}." if not isinstance(v, (int, float)) or isinstance(v, bool) else f"{prefix}{k}"))
    elif isinstance(d, (int, float)) and not isinstance(d, bool):
        out[prefix.rstrip(".")] = float(d)
    return {k.replace("@", "_at_"): v for k, v in out.items() if k}


def log_training(model: str, version: str, promoted: bool, why: str) -> str | None:
    """Log the artifacts a training run just wrote; register the model; alias it `champion` if promoted."""
    try:
        setup()
        import joblib
        import mlflow
        import mlflow.sklearn
        from mlflow import MlflowClient
    except Exception as e:  # tracking is never allowed to break training
        print(f"(mlflow tracking skipped: {type(e).__name__}: {e})")
        return None
    d: Path = artifact_dir(model, version)
    metrics = json.loads((d / "metrics.json").read_text(encoding="utf-8"))
    cfg = json.loads((d / "training_config.json").read_text(encoding="utf-8"))
    with mlflow.start_run(run_name=f"{model}-{version}") as run:
        mlflow.set_tags({"model": model, "version": version, "git_sha": cfg.get("git_sha", ""), "promoted": str(promoted), "promotion_reason": why[:250]})
        mlflow.log_params({k: (json.dumps(v) if not isinstance(v, (str, int, float)) else v) for k, v in cfg.items() if k != "git_sha"})
        mlflow.log_metrics(_flat(metrics))
        for f in d.iterdir():
            if f.suffix in (".md", ".png", ".json"):
                mlflow.log_artifact(str(f))
        name = f"appeal-{model}"
        mlflow.sklearn.log_model(joblib.load(d / "model.joblib"), name="model", registered_model_name=name, serialization_format="cloudpickle")
        if promoted:
            client = MlflowClient()
            latest = max(client.search_model_versions(f"name='{name}'"), key=lambda mv: int(mv.version))
            client.set_registered_model_alias(name, "champion", latest.version)
        return run.info.run_id


def log_optuna_study(model: str, study: Any) -> None:
    try:
        mlflow = setup()
    except Exception:
        return
    with mlflow.start_run(run_name=f"{model}-optuna"):
        mlflow.log_metric("best_value", float(study.best_value))
        mlflow.log_params({f"best_{k}": v for k, v in study.best_params.items()})
        for t in study.trials:
            with mlflow.start_run(run_name=f"trial-{t.number}", nested=True):
                mlflow.log_params(t.params)
                if t.value is not None:
                    mlflow.log_metric("grouped_cv_macro_f1", float(t.value))
