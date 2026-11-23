# All targets delegate to tasks.py so the same commands work on Windows (no WSL) and Linux.
RUN := uv run python tasks.py

.PHONY: setup up down migrate data train evaluate-models eval eval-fast test test-fast demo lint obs api worker retention

setup:
	uv sync --extra nlp
	$(RUN) setup
up:
	$(RUN) up
down:
	$(RUN) down
migrate:
	$(RUN) migrate
data:
	$(RUN) data
train:
	$(RUN) train
evaluate-models:
	$(RUN) evaluate-models
eval:
	$(RUN) eval
eval-fast:
	$(RUN) eval-fast
test:
	$(RUN) test
test-fast:
	$(RUN) test-fast
demo:
	$(RUN) demo
lint:
	$(RUN) lint
obs:
	$(RUN) obs
api:
	$(RUN) api
worker:
	$(RUN) worker
retention:
	$(RUN) retention
