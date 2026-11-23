# Infrastructure (Phase C — stubs only)

Nothing in this folder has been deployed. Phases A and B never create cloud resources (hard rule 5). Each Azure
service replaces a local adapter by **configuration only**: set the backend env var and the service's variables.
Selecting an Azure backend without its variables raises `NotConfigured` naming the variables to set
(`packages/core/appeal_core/adapters/azure.py`); `tests/test_azure_contracts.py` checks that, and its contract tests
run only when the variables are set.

Regenerate the stubs with `uv run python infra/generate_stubs.py`.

| Azure resource (SPEC 7.2) | Bicep module | Replaces (local) | Switch | Env vars the adapter needs |
|---|---|---|---|---|
| Virtual network + private endpoints | `modules/network.bicep` | — | — | — |
| Application Insights + Log Analytics | `modules/monitoring.bicep` | OTel console exporter | `TELEMETRY_EXPORTER=azure_monitor` | `APPLICATIONINSIGHTS_CONNECTION_STRING` |
| Managed identities + role assignments | `modules/identity.bicep` | `.env` | — | `AZURE_CLIENT_ID` (workload identity) |
| Key Vault | `modules/keyvault.bicep` | `.env` master key | Key Vault reference for `MASTER_KEY` | `AZURE_KEYVAULT_URL` |
| App Configuration | `modules/appconfig.bicep` | `.env` | — | `AZURE_APPCONFIG_ENDPOINT` |
| PostgreSQL Flexible Server + pgvector | `modules/postgres.bicep` | Postgres container | `DATABASE_URL` | `DATABASE_URL` (Entra auth) |
| Blob Storage | `modules/storage.bicep` | Azurite | `BLOB_BACKEND=azure` | `AZURE_STORAGE_ACCOUNT_URL` |
| Azure Managed Redis | `modules/redis.bicep` | Redis container | `PROGRESS_BACKEND=azure` | `REDIS_URL` |
| Service Bus (sessions keyed by case ID, DLQ) | `modules/servicebus.bicep` | Postgres job table | `QUEUE_BACKEND=servicebus` | `AZURE_SERVICEBUS_NAMESPACE` |
| Container Registry | `modules/acr.bicep` | local images | — | — |
| Container Apps (api, worker + KEDA, web) | `modules/containerapps.bicep` | host processes | — | all of the above |
| Azure OpenAI (pinned deployments) | `modules/openai.bicep` | offline provider | `LLM_PROVIDER=azure_openai`, `EMBEDDER=azure` | `AZURE_OPENAI_ENDPOINT`, `AZURE_OPENAI_DEPLOYMENT` |
| Azure AI Search (hybrid + semantic ranker) | `modules/search.bicep` | Postgres FTS + pgvector | `RETRIEVER_BACKEND=azure` | `AZURE_SEARCH_ENDPOINT` |
| Document Intelligence | `modules/docintel.bicep` | pypdf | `OCR_BACKEND=azure` | `AZURE_DOCINTEL_ENDPOINT` |
| Azure AI Language PII | `modules/language.bicep` | regex + Presidio | `PII_BACKEND=azure` | `AZURE_LANGUAGE_ENDPOINT` |
| Content Safety Prompt Shields | `modules/contentsafety.bicep` | heuristic detector | `INJECTION_BACKEND=azure` | `AZURE_CONTENT_SAFETY_ENDPOINT` |
| Azure ML (registry + managed online endpoint) | `modules/ml.bicep` | joblib files | `MODEL_REGISTRY=azure` | `AZURE_ML_ENDPOINT` |
| Functions (data refresh, retention, nightly evals) | `modules/functions.bicep` | `make data` / `make eval` by hand | — | — |
| Front Door + WAF | `modules/frontdoor.bicep` | — | — | — |
| Entra External ID | tenant configuration (not Bicep) | signed case-access tokens | — | `ENTRA_TENANT_ID`, `ENTRA_CLIENT_ID` |

## TODO (Phase C)
1. Budget alert first; one resource group per environment (`parameters/*.parameters.json`).
2. Fill each module; `az bicep build` + what-if in CI (no deploy from pull requests).
3. GitHub Actions OIDC federation (no stored cloud secrets).
4. Implement each Azure adapter behind its existing interface, one at a time; run `make eval` against the cloud after each switch and record before/after numbers.
