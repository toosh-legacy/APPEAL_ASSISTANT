# One Python image for both the API and the worker (the worker overrides the command).
#   docker build -f services/api/Dockerfile -t appeal-api .
#   docker run -p 8000:8000 --env-file .env appeal-api
#   docker run --env-file .env appeal-api python -m appeal_worker.main
# Needs the trained model files in ml/artifacts/ (git-ignored; run `make train` first, or restore them in CI).
FROM python:3.12-slim AS base
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1 \
    UV_COMPILE_BYTECODE=1 UV_LINK_MODE=copy UV_PROJECT_ENVIRONMENT=/app/.venv \
    HF_HOME=/app/.cache/hf PATH="/app/.venv/bin:$PATH"
COPY --from=ghcr.io/astral-sh/uv:0.8 /uv /usr/local/bin/uv
WORKDIR /app

# Dependencies first (cached unless the lockfile changes). PyTorch comes from the CPU-only index: the locked
# Linux wheel pulls ~4 GB of CUDA libraries that a CPU container never uses.
COPY pyproject.toml uv.lock ./
RUN --mount=type=cache,target=/root/.cache/uv \
    uv venv /app/.venv \
 && uv export --frozen --no-dev --extra nlp --no-emit-project --no-hashes -o /tmp/req.txt \
 && TORCH=$(grep -E '^torch==' /tmp/req.txt | cut -d' ' -f1) \
 && grep -vE '^(torch|nvidia-|triton)' /tmp/req.txt > /tmp/req-cpu.txt \
 && uv pip install --python /app/.venv "$TORCH" --index-url https://download.pytorch.org/whl/cpu \
 && uv pip install --python /app/.venv -r /tmp/req-cpu.txt

# The two small local models (embedder ~90 MB, reranker ~90 MB), baked in so containers start offline.
RUN python -c "from sentence_transformers import SentenceTransformer, CrossEncoder; \
SentenceTransformer('sentence-transformers/all-MiniLM-L6-v2'); CrossEncoder('cross-encoder/ms-marco-MiniLM-L-6-v2')"

COPY . .
RUN uv pip install --python /app/.venv --no-deps -e . \
 && test -f ml/artifacts/m1/v1/model.joblib || (echo "ml/artifacts/*/v1/model.joblib missing: run make train" && exit 1)

RUN useradd --uid 10001 --create-home app && mkdir -p /app/var && chown -R app /app/var /app/.cache
USER app
ENV HF_HUB_OFFLINE=1 TRANSFORMERS_OFFLINE=1
EXPOSE 8000
HEALTHCHECK --interval=30s --timeout=5s --start-period=60s \
  CMD python -c "import urllib.request; urllib.request.urlopen('http://127.0.0.1:8000/healthz', timeout=4)" || exit 1
CMD ["uvicorn", "appeal_api.main:app", "--host", "0.0.0.0", "--port", "8000", "--proxy-headers"]
