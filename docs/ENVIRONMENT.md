# Environment detection (SPEC section 0.5)

Detected at the start of the overnight run: 2026-11-23 01:05 CST.

| Item | Result |
|---|---|
| OS | Windows 11 Pro 10.0.26200 (x86_64) |
| Inside WSL? | **No.** Claude Code ran under Git Bash / MSYS (MINGW64) on native Windows. Repo is on the Windows file system (`C:\Users\...`). |
| docker | Docker 29.6.1 (Docker Desktop, context `desktop-linux`) |
| docker daemon | **Responds** (`docker info` OK, server 29.6.1, ~11.5 GB memory available to Docker) |
| docker compose | v5.2.0 |
| python | 3.13.7 system (`C:\Python313`); **3.12.12 available via `uv python`** (used for the project) |
| uv | 0.9.22 |
| node / npm | v22.19.0 / 11.6.2 |
| git | 2.51.0.windows.1 |
| make | GNU Make 4.4.1 (MSYS2 ucrt64) |
| curl | 8.15.0 |
| CPU cores | 16 |

## Port conflicts found
- `5432` is already used by another local Postgres container (`hackutafaze-db-1`) and a native Postgres.
- `3000` is used by another local process.

So the stack uses non-default host ports: Postgres `55432`, Redis `56379`, Azurite `10000-10002`, API `8000`, web `3100`.

## Network checks
- DMHC IMR CSV: reachable (HTTP 200, ~85 MB). The plain `HEAD` request returns 403 from S3 (pre-signed GET URL); a normal `GET` works.
- eCFR API: reachable.

## Mode chosen: **FULL MODE**
Docker works, so the local stack from SPEC 7.1 / 7.3 is used: Postgres 16 + pgvector, Redis, Azurite.

Caveats (see DECISIONS.md):
- Not in WSL, so the repo lives on the Windows file system. Paths use `pathlib`; no shell scripts are required (Make targets call Python).
- The API and worker run as host Python processes against the Docker services (the compose file also defines `api`/`worker`/`web` services for later container use).
