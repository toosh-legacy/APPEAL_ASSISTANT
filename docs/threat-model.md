# Threat model (STRIDE) — local build

| Threat | Example | Mitigation in this build | Where |
|---|---|---|---|
| Spoofing | Opening another person's case | Random UUIDv4 case IDs + HMAC-signed case-access token required on every case endpoint (404 on mismatch) | `services/api/appeal_api/deps.py` |
| Tampering | Swapped upload | Write-only, single-blob SAS valid 10 minutes; SHA-256 stored on the document row | `adapters/blob_azurite.py`, `cases.create_case` |
| Repudiation | "I never deleted that" | Append-only `audit_event` rows for create, corrections, edits, regenerate, delete, every state transition | `models.AuditEvent` |
| Information disclosure | Identifiers in prompts, logs or traces; injection exfiltrating data | Tokenization before any model call; fail-closed leak gate; scrubbing JSON log formatter and span attributes; no outbound tools; agents only see their own case | `privacy/`, `telemetry.py` |
| Denial of service | Huge files, endless regenerate | 10 MB / 10 pages / 20,000 characters; 64 KB JSON body limit; token-bucket limits on case creation and regenerate (Redis) | `cases.py`, `main.py` |
| Elevation of privilege | Admin pages exposed | Admin token from `.env` (Entra roles + Front Door rules in Phase C) | `deps.require_admin` |

## Prompt injection and the lethal trifecta
The "lethal trifecta" is private data + untrusted content + a way to send data out. This design keeps the first two
(the user's letter is both) but removes the third leg: no agent has a tool that can send messages, fetch URLs or read
another case, and outputs are structured (sentences + citation IDs) that the user reviews before anything leaves the
app — and the user sends the letter themselves. Delimiters alone fail because a model can still be persuaded to treat
text inside them as instructions; the injection detector is defense in depth, not the control.

Red-team results: `evals/reports/latest.md` (suite `red_team`).
