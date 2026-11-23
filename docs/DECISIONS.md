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
- **Drop the 39 exact-duplicate IMR rows, then enforce unique ReferenceID** — the duplicates are byte-identical (0 conflicting); the uniqueness check still stops the load on conflicting duplicates — treat any duplicate as a failed load (would force the synthetic fallback and lose the real data).
- **IMR download uses a non-default User-Agent and plain GET** — S3 pre-signed URL rejects HEAD (403) — none.
- **PII scan of 42k Findings uses regex recognizers only; Presidio is used at runtime on letters** — spaCy NER over ~12M words would take ~20 min overnight — run Presidio over the whole dataset (Phase B).
- **Precedent chunks drop the reviewer "Credentials/Qualifications" boilerplate** — it is identical across cases and would dominate keyword/vector similarity — keep full text.
- **Precedent chunks split at ~300 words (≈400 tokens) with 40-word overlap** — SPEC says ~400 tokens — token-exact splitting with a tokenizer.
- **eCFR chunks merge short sibling paragraphs within the same top-level paragraph; median chunk is below 150 tokens for some sections** — many CFR paragraphs are short and merging across top-level paragraphs would blur citations — strict 150-token minimum.
- **eCFR fetched sections for 45 CFR 149: 149.110, 149.120, 149.130, 149.410, 149.420** — SPEC asks for "emergency services and patient protections" only — whole Part 149 (mostly IDR procedure text).
- **GovInfo bulk XML fallback is not automated** — different volume-level structure; the eCFR API worked — automate it in Phase B.
- **Deadline rules resolve their citation by a required phrase (`must_contain`) instead of hard-coding chunk IDs** — chunk IDs depend on parser details; a rule whose phrase is not found is disabled — hard-coded IDs.
- **Deadline trigger = the date printed on the notice** — regulations count from receipt; the notice date is the earliest (most conservative) reading — assume a mailing delay.
- **Medicare Advantage reconsideration window = 60 calendar days** — that is the current text of 42 CFR 422.582(b) as fetched (an older 65-day figure was not used) — n/a.
- **Synthetic letters use fictional insurers ("Example Health Plan", ...), Testville, ZIP 00000** — hard rule 8 and no impersonation of real organizations — realistic insurer names.
- **Gold letters use a different template family and reason-phrase bank from train/validation** — SPEC D4 generalization requirement — same templates.
