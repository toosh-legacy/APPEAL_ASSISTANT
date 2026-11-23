"""Interfaces for every external dependency (hard rule 6). Local adapters live in appeal_core.adapters;
Azure adapters in appeal_core.adapters.azure. Choose with env vars (see .env.example)."""

from __future__ import annotations

from collections.abc import AsyncIterator
from dataclasses import dataclass
from datetime import datetime
from typing import Any, Protocol


@dataclass
class ClaimedJob:
    id: int
    topic: str
    payload: dict[str, Any]
    case_id: str | None
    attempts: int


class JobQueue(Protocol):
    def enqueue(self, session: Any, topic: str, payload: dict[str, Any], case_id: str | None = None) -> int: ...
    def claim(self, worker_id: str, lease_seconds: int = 60) -> ClaimedJob | None: ...
    def complete(self, job_id: int) -> None: ...
    def fail(self, job_id: int, error: str, max_attempts: int = 5) -> str: ...


class BlobStore(Protocol):
    def create_upload_url(self, blob_name: str, minutes: int = 10) -> tuple[str, datetime]: ...
    def put(self, blob_name: str, data: bytes) -> str: ...
    def get(self, blob_name: str) -> bytes: ...
    def delete(self, blob_name: str) -> None: ...
    def ping(self) -> bool: ...


class ProgressBus(Protocol):
    def publish(self, case_id: str, event: dict[str, Any]) -> None: ...
    def history(self, case_id: str, after_id: int = 0) -> list[dict[str, Any]]: ...
    def subscribe(self, case_id: str, after_id: int = 0) -> AsyncIterator[dict[str, Any]]: ...
    def ping(self) -> bool: ...


class LLMProvider(Protocol):
    name: str
    model: str

    def extract(self, tokenized_text: str, case_raw_values: list[str]) -> dict[str, Any]: ...
    def write(self, request: dict[str, Any], case_raw_values: list[str]) -> dict[str, Any]: ...
    def rewrite_query(self, query: str, case_raw_values: list[str]) -> list[str]: ...


class InjectionDetector(Protocol):
    def detect(self, text: str) -> list[str]: ...


class TextExtractor(Protocol):
    def extract(self, data: bytes, filename: str) -> tuple[str, int]: ...


class Embedder(Protocol):
    name: str
    dim: int

    def embed(self, texts: list[str]) -> Any: ...
