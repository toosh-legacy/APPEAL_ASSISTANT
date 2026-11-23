"""Cross-platform task runner. The Makefile delegates here so Windows (no WSL) and Linux behave the same.

Usage: uv run python tasks.py <setup|up|down|migrate|data|train|evaluate-models|eval|eval-fast|test|test-fast|demo|lint|obs|api|worker|retention>
"""

from __future__ import annotations

import base64
import os
import secrets
import subprocess
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent
PY = sys.executable


def run(cmd: list[str], check: bool = True, env: dict | None = None) -> int:
    print("+", " ".join(cmd), flush=True)
    merged = {**os.environ, **(env or {})}
    rc = subprocess.call(cmd, cwd=ROOT, env=merged)
    if check and rc != 0:
        sys.exit(rc)
    return rc


def setup() -> None:
    env_path = ROOT / ".env"
    if not env_path.exists():
        example = (ROOT / ".env.example").read_text(encoding="utf-8")
        key = base64.b64encode(secrets.token_bytes(32)).decode()
        example = example.replace("MASTER_KEY=generate-me-at-setup", f"MASTER_KEY={key}")
        example = example.replace("CASE_TOKEN_SECRET=generate-me-at-setup", f"CASE_TOKEN_SECRET={secrets.token_hex(32)}")
        example = example.replace("ADMIN_TOKEN=generate-me-at-setup", f"ADMIN_TOKEN={secrets.token_hex(16)}")
        env_path.write_text(example, encoding="utf-8")
        print("wrote .env with freshly generated local keys (git-ignored)")
    for d in ["var/blobs", "var/logs", "data/raw", "data/processed", "data/reports"]:
        (ROOT / d).mkdir(parents=True, exist_ok=True)


def _wait_for_postgres(timeout: float = 90) -> None:
    import psycopg
    from appeal_core.settings import get_settings

    url = get_settings().database_url.replace("postgresql+psycopg://", "postgresql://")
    deadline = time.time() + timeout
    while time.time() < deadline:
        try:
            with psycopg.connect(url, connect_timeout=3) as conn:
                conn.execute("select 1")
            return
        except Exception:
            time.sleep(2)
    raise SystemExit("postgres did not become ready")


def up() -> None:
    setup()
    run(["docker", "compose", "up", "-d", "postgres", "redis", "azurite"])
    _wait_for_postgres()
    migrate()


def down() -> None:
    run(["docker", "compose", "down"])


def migrate() -> None:
    run([PY, "-m", "alembic", "upgrade", "head"])


def data() -> None:
    run([PY, "-m", "appeal_data.cli", "all"])


def train() -> None:
    run([PY, "-m", "appeal_ml.train", "all"])


def evaluate_models() -> None:
    run([PY, "-m", "appeal_ml.report"])


def eval_() -> None:
    run([PY, "-m", "appeal_evals.run", "--all"])


def eval_fast() -> None:
    run([PY, "-m", "appeal_evals.run", "--fast"])


def test() -> None:
    run([PY, "-m", "pytest"])


def test_fast() -> None:
    run([PY, "-m", "pytest", "-m", "not full and not slow"])


def lint() -> None:
    run([PY, "-m", "ruff", "check", "."])


def api() -> None:
    run([PY, "-m", "uvicorn", "appeal_api.main:app", "--host", "127.0.0.1", "--port", "8000"])


def worker() -> None:
    run([PY, "-m", "appeal_worker.main"])


def demo() -> None:
    up()
    print("\nStarting API (worker runs in-process) on http://127.0.0.1:8000")
    print("Demo page:  http://127.0.0.1:8000/demo")
    web = ROOT / "apps" / "web"
    procs = []
    procs.append(
        subprocess.Popen(
            [PY, "-m", "uvicorn", "appeal_api.main:app", "--host", "127.0.0.1", "--port", "8000"],
            cwd=ROOT,
            env={**os.environ, "WORKER_MODE": "inprocess"},
        )
    )
    npm = "npm.cmd" if os.name == "nt" else "npm"
    if not (web / "node_modules").exists():
        subprocess.call([npm, "install", "--no-audit", "--no-fund"], cwd=web, env={**os.environ, "PLAYWRIGHT_SKIP_BROWSER_DOWNLOAD": "1"})
    if (web / "node_modules").exists():
        script = "start" if (web / ".next" / "BUILD_ID").exists() else "dev"
        procs.append(subprocess.Popen([npm, "run", script], cwd=web))
        print("Web app:    http://localhost:3100   <- open this")
    try:
        for p in procs:
            p.wait()
    except KeyboardInterrupt:
        for p in procs:
            p.terminate()


def retention() -> None:
    run([PY, "-m", "appeal_worker.retention"])


def obs() -> None:
    run(["docker", "compose", "--profile", "obs", "up", "-d", "jaeger"])


TASKS = {
    "setup": setup,
    "up": up,
    "down": down,
    "migrate": migrate,
    "data": data,
    "train": train,
    "evaluate-models": evaluate_models,
    "eval": eval_,
    "eval-fast": eval_fast,
    "test": test,
    "test-fast": test_fast,
    "lint": lint,
    "demo": demo,
    "obs": obs,
    "retention": retention,
    "api": api,
    "worker": worker,
}

if __name__ == "__main__":
    if len(sys.argv) != 2 or sys.argv[1] not in TASKS:
        print(__doc__)
        sys.exit(2)
    TASKS[sys.argv[1]]()
