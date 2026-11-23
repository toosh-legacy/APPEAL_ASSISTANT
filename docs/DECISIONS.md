# Decisions log

One line each: **decision** — reason — alternative considered.

- **Full mode (Docker stack)** — `docker info` responds, so SPEC 0.5 says full mode — lite mode (SQLite adapters).
- **Run on native Windows, not WSL** — Claude Code was started from Git Bash on Windows; installing/using WSL was out of scope (no admin) — move repo into WSL later for speed.
- **Remapped host ports (Postgres 55432, Redis 56379, web 3100)** — 5432 and 3000 were already in use by other local projects — stop the user's other containers (rejected: not ours).
- **API and worker run as host Python processes against Docker services** — faster iteration on Windows; compose also defines `api`/`worker` services under the `apps` profile — run everything in containers.
- **Single root `pyproject.toml` with hatch-mapped packages instead of a multi-member uv workspace** — one lockfile, one venv, less overhead in a 4 h run; package boundaries are still the SPEC 19 folders — one pyproject per package.
- **Python 3.12 via `uv python pin 3.12`** — system Python is 3.13; SPEC requires 3.12 — use 3.13.
- **Makefile delegates to `tasks.py`** — same commands on Windows and Linux; `make` exists here but scripts must be portable — shell recipes.
- **mypy non-strict in this run** — time; strict mode is a Phase B task — strict now.
- **Azurite's well-known public dev key is in `.env.example`** — it is Microsoft's documented emulator key, not a secret — generate a custom Azurite account.
