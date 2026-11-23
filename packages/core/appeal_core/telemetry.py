"""Structured JSON logging with a scrubbing processor, and OpenTelemetry tracing (console exporter locally,
Azure Monitor in Phase C). Never log document text or identifiers: every log record and span attribute
passes through `scrub()` first."""

from __future__ import annotations

import json
import logging
import re
import sys
from contextlib import contextmanager
from typing import Any

from appeal_core.privacy.pii import regex_detect

_SENSITIVE: set[str] = set()
_ZZ = re.compile(r"ZZTEST[\s-]?[A-Z0-9][A-Z0-9\s-]{2,14}", re.I)


def register_sensitive(values: list[str]) -> None:
    """Known raw identifiers (e.g. for the case being processed) that must never appear in logs."""
    for v in values:
        if v and len(v) >= 4:
            _SENSITIVE.add(v)


def scrub(value: Any) -> Any:
    if isinstance(value, dict):
        return {k: scrub(v) for k, v in value.items()}
    if isinstance(value, (list, tuple)):
        return [scrub(v) for v in value]
    if not isinstance(value, str):
        return value
    out = value
    for raw in sorted(_SENSITIVE, key=len, reverse=True):
        out = out.replace(raw, "[REDACTED]")
    for sp in sorted(regex_detect(out), key=lambda s: s.start, reverse=True):
        out = out[: sp.start] + f"[{sp.entity}]" + out[sp.end :]
    return _ZZ.sub("[MEMBER_ID]", out)


_STD = set(vars(logging.LogRecord("", 0, "", 0, "", (), None)).keys()) | {"message", "asctime"}


class ScrubbingJsonFormatter(logging.Formatter):
    def format(self, record: logging.LogRecord) -> str:
        payload = {"level": record.levelname, "logger": record.name, "msg": record.getMessage()}
        for k, v in record.__dict__.items():
            if k not in _STD:
                payload[k] = v
        if record.exc_info:
            payload["exc_type"] = record.exc_info[0].__name__ if record.exc_info[0] else None
        return json.dumps(scrub(payload), default=str)


_configured = False


def configure_logging(stream=None) -> None:
    global _configured
    root = logging.getLogger("appeal")
    if _configured and stream is None:
        return
    h = logging.StreamHandler(stream or sys.stderr)
    h.setFormatter(ScrubbingJsonFormatter())
    root.handlers = [h]
    root.setLevel(logging.INFO)
    root.propagate = False
    _configured = True


def get_logger(name: str) -> logging.Logger:
    configure_logging()
    return logging.getLogger(f"appeal.{name}")


# ---------------------------------------------------------------- tracing
_tracer = None


def _get_tracer():
    global _tracer
    if _tracer is None:
        from opentelemetry import trace
        from opentelemetry.sdk.resources import Resource
        from opentelemetry.sdk.trace import TracerProvider
        from opentelemetry.sdk.trace.export import ConsoleSpanExporter, SimpleSpanProcessor

        from appeal_core.settings import get_settings

        provider = TracerProvider(resource=Resource.create({"service.name": "appeal-assistant"}))
        exp = get_settings().telemetry_exporter
        if exp == "console":
            provider.add_span_processor(SimpleSpanProcessor(ConsoleSpanExporter(out=open(_trace_path(), "a", encoding="utf-8"))))
        trace.set_tracer_provider(provider)
        _tracer = trace.get_tracer("appeal")
    return _tracer


def _trace_path() -> str:
    from appeal_core.settings import ROOT

    p = ROOT / "var" / "logs"
    p.mkdir(parents=True, exist_ok=True)
    return str(p / "traces.jsonl")


@contextmanager
def span(name: str, **attrs: Any):
    tracer = _get_tracer()
    with tracer.start_as_current_span(name) as sp:
        for k, v in scrub(attrs).items():
            if v is not None:
                sp.set_attribute(k, v if isinstance(v, (str, int, float, bool)) else str(v))
        yield sp
