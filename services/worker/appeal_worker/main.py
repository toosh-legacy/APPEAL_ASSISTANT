"""Worker process entry point: `python -m appeal_worker.main` (WORKER_MODE=separate)."""

from __future__ import annotations

import os
import socket

from appeal_worker.orchestrator import run_worker

if __name__ == "__main__":
    from appeal_core.llm.gateway import verify_models

    verify_models()
    run_worker(worker_id=f"{socket.gethostname()}-{os.getpid()}")
