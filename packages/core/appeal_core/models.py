"""SQLAlchemy 2.0 models for SPEC section 12."""

from __future__ import annotations

import uuid
from datetime import UTC, date, datetime
from typing import Any

from pgvector.sqlalchemy import Vector
from sqlalchemy import (
    JSON,
    BigInteger,
    Boolean,
    Computed,
    Date,
    DateTime,
    Float,
    ForeignKey,
    Index,
    Integer,
    LargeBinary,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.dialects.postgresql import JSONB, TSVECTOR
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column
from sqlalchemy.sql import expression

EMBED_DIM = 384
JSONType = JSON().with_variant(JSONB(), "postgresql")


def utcnow() -> datetime:
    return datetime.now(UTC)


def new_id() -> str:
    return str(uuid.uuid4())


class Base(DeclarativeBase):
    pass


class Case(Base):
    __tablename__ = "case"
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    status: Mapped[str] = mapped_column(String(32), index=True)
    version: Mapped[int] = mapped_column(Integer, default=1)
    plan_type: Mapped[str | None] = mapped_column(String(64))
    state: Mapped[str | None] = mapped_column(String(8))
    category: Mapped[str | None] = mapped_column(String(64))
    degraded: Mapped[bool] = mapped_column(Boolean, default=False, server_default=expression.false())
    idempotency_key: Mapped[str | None] = mapped_column(String(128), unique=True)
    error: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, onupdate=utcnow)
    expires_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    __mapper_args__ = {"version_id_col": version}


class Document(Base):
    __tablename__ = "document"
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    case_id: Mapped[str] = mapped_column(ForeignKey("case.id", ondelete="CASCADE"), index=True)
    kind: Mapped[str] = mapped_column(String(16))  # pasted | pdf | txt
    blob_uri: Mapped[str | None] = mapped_column(Text)
    sha256: Mapped[str | None] = mapped_column(String(64))
    pages: Mapped[int | None] = mapped_column(Integer)
    # Pasted text is stored encrypted (restricted data class).
    text_encrypted: Mapped[bytes | None] = mapped_column(LargeBinary)
    retention_until: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class Extraction(Base):
    __tablename__ = "extraction"
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    case_id: Mapped[str] = mapped_column(ForeignKey("case.id", ondelete="CASCADE"), unique=True)
    fields: Mapped[dict[str, Any]] = mapped_column(JSONType, default=dict)
    field_confidence: Mapped[dict[str, Any]] = mapped_column(JSONType, default=dict)
    user_corrections: Mapped[dict[str, Any]] = mapped_column(JSONType, default=dict)
    redacted_text: Mapped[str | None] = mapped_column(Text)
    injection: Mapped[dict[str, Any]] = mapped_column(JSONType, default=dict)
    confirmed: Mapped[bool] = mapped_column(Boolean, default=False)


class AgentRun(Base):
    __tablename__ = "agent_run"
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    case_id: Mapped[str] = mapped_column(ForeignKey("case.id", ondelete="CASCADE"), index=True)
    agent: Mapped[str] = mapped_column(String(32))
    attempt: Mapped[int] = mapped_column(Integer, default=1)
    input_hash: Mapped[str] = mapped_column(String(64))
    output: Mapped[dict[str, Any] | None] = mapped_column(JSONType)
    prompt_id: Mapped[str | None] = mapped_column(String(64))
    prompt_version: Mapped[str | None] = mapped_column(String(16))
    provider: Mapped[str | None] = mapped_column(String(32))
    model: Mapped[str | None] = mapped_column(String(64))
    tokens_in: Mapped[int] = mapped_column(Integer, default=0)
    tokens_out: Mapped[int] = mapped_column(Integer, default=0)
    cost_usd: Mapped[float] = mapped_column(Float, default=0.0)
    latency_ms: Mapped[int] = mapped_column(Integer, default=0)
    status: Mapped[str] = mapped_column(String(16), default="ok")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    __table_args__ = (UniqueConstraint("case_id", "agent", "input_hash", name="uq_agent_run_step"),)


class Job(Base):
    """Local queue + transactional outbox (one table: rows are inserted in the same transaction as the state change)."""

    __tablename__ = "job"
    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    topic: Mapped[str] = mapped_column(String(64))
    payload: Mapped[dict[str, Any]] = mapped_column(JSONType, default=dict)
    case_id: Mapped[str | None] = mapped_column(String(36), index=True)
    status: Mapped[str] = mapped_column(String(16), default="ready")  # ready | running | done | dead
    attempts: Mapped[int] = mapped_column(Integer, default=0)
    last_error: Mapped[str | None] = mapped_column(Text)
    available_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    locked_by: Mapped[str | None] = mapped_column(String(64))
    locked_until: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    __table_args__ = (Index("ix_job_claim", "status", "available_at"),)


class Citation(Base):
    __tablename__ = "citation"
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    case_id: Mapped[str] = mapped_column(ForeignKey("case.id", ondelete="CASCADE"), index=True)
    cite_id: Mapped[str] = mapped_column(String(8))  # R1, P2 ...
    chunk_id: Mapped[str] = mapped_column(String(128))
    kind: Mapped[str] = mapped_column(String(1))
    score: Mapped[float] = mapped_column(Float, default=0.0)
    used_in_letter: Mapped[bool] = mapped_column(Boolean, default=False)


class Letter(Base):
    __tablename__ = "letter"
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    case_id: Mapped[str] = mapped_column(ForeignKey("case.id", ondelete="CASCADE"), index=True)
    version: Mapped[int] = mapped_column(Integer, default=1)
    body_encrypted: Mapped[bytes] = mapped_column(LargeBinary)
    sentences: Mapped[list[Any]] = mapped_column(JSONType, default=list)  # tokenized sentences + citation IDs
    placeholders_remaining: Mapped[int] = mapped_column(Integer, default=0)
    review_score: Mapped[float] = mapped_column(Float, default=0.0)
    review: Mapped[dict[str, Any]] = mapped_column(JSONType, default=dict)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    __table_args__ = (UniqueConstraint("case_id", "version", name="uq_letter_version"),)


class Deadline(Base):
    __tablename__ = "deadline"
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    case_id: Mapped[str] = mapped_column(ForeignKey("case.id", ondelete="CASCADE"), index=True)
    kind: Mapped[str] = mapped_column(String(64))
    due_date: Mapped[date] = mapped_column(Date)
    rule_id: Mapped[str] = mapped_column(String(64))
    basis_chunk_id: Mapped[str] = mapped_column(String(128))


class TokenVault(Base):
    __tablename__ = "token_vault"
    case_id: Mapped[str] = mapped_column(ForeignKey("case.id", ondelete="CASCADE"), primary_key=True)
    wrapped_data_key: Mapped[bytes] = mapped_column(LargeBinary)
    encrypted_map: Mapped[bytes] = mapped_column(LargeBinary)


class KbSource(Base):
    __tablename__ = "kb_source"
    id: Mapped[str] = mapped_column(String(128), primary_key=True)
    url: Mapped[str] = mapped_column(Text)
    citation_path: Mapped[str] = mapped_column(String(128))
    sha256: Mapped[str] = mapped_column(String(64))
    effective_date: Mapped[str | None] = mapped_column(String(16))
    version: Mapped[str | None] = mapped_column(String(32))
    kind: Mapped[str] = mapped_column(String(16))  # regulation | summary


class KbChunk(Base):
    __tablename__ = "kb_chunk"
    id: Mapped[str] = mapped_column(String(128), primary_key=True)
    source_id: Mapped[str] = mapped_column(String(128), index=True)
    source_kind: Mapped[str] = mapped_column(String(16))  # regulation | summary
    citation_path: Mapped[str] = mapped_column(String(160))
    heading: Mapped[str | None] = mapped_column(Text)
    text: Mapped[str] = mapped_column(Text)
    plan_types: Mapped[list[str]] = mapped_column(JSONType, default=list)
    topics: Mapped[list[str]] = mapped_column(JSONType, default=list)
    effective_date: Mapped[str | None] = mapped_column(String(16))
    url: Mapped[str | None] = mapped_column(Text)
    status: Mapped[str | None] = mapped_column(String(32))
    tsv = mapped_column(
        TSVECTOR,
        Computed("to_tsvector('english', coalesce(citation_path,'') || ' ' || coalesce(heading,'') || ' ' || text)", persisted=True),
    )
    embedding = mapped_column(Vector(EMBED_DIM), nullable=True)


class ImrCase(Base):
    __tablename__ = "imr_case"
    reference_id: Mapped[str] = mapped_column(String(32), primary_key=True)
    year: Mapped[int] = mapped_column(Integer, index=True)
    diagnosis_category: Mapped[str | None] = mapped_column(String(128))
    diagnosis_subcategory: Mapped[str | None] = mapped_column(String(160))
    treatment_category: Mapped[str | None] = mapped_column(String(128), index=True)
    treatment_subcategory: Mapped[str | None] = mapped_column(String(160))
    type: Mapped[str | None] = mapped_column(String(64))
    imr_type: Mapped[str | None] = mapped_column(String(64))
    age_range: Mapped[str | None] = mapped_column(String(32))
    patient_gender: Mapped[str | None] = mapped_column(String(32))
    overturned: Mapped[bool] = mapped_column(Boolean)
    determination_text: Mapped[str] = mapped_column(String(128))
    findings: Mapped[str | None] = mapped_column(Text)
    days_to_review: Mapped[float | None] = mapped_column(Float)


class PrecedentChunk(Base):
    __tablename__ = "precedent_chunk"
    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    reference_id: Mapped[str] = mapped_column(String(32), index=True)
    text: Mapped[str] = mapped_column(Text)
    year: Mapped[int] = mapped_column(Integer)
    treatment_category: Mapped[str | None] = mapped_column(String(128))
    treatment_subcategory: Mapped[str | None] = mapped_column(String(160))
    diagnosis_category: Mapped[str | None] = mapped_column(String(128))
    type: Mapped[str | None] = mapped_column(String(64))
    overturned: Mapped[bool] = mapped_column(Boolean)
    tsv = mapped_column(
        TSVECTOR,
        Computed(
            "to_tsvector('english', coalesce(treatment_category,'') || ' ' || coalesce(treatment_subcategory,'') || ' ' || coalesce(diagnosis_category,'') || ' ' || text)",
            persisted=True,
        ),
    )
    embedding = mapped_column(Vector(EMBED_DIM), nullable=True)


class ImrStats(Base):
    __tablename__ = "imr_stats"
    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    treatment_category: Mapped[str | None] = mapped_column(String(128), index=True)
    treatment_subcategory: Mapped[str | None] = mapped_column(String(160))
    diagnosis_category: Mapped[str | None] = mapped_column(String(128))
    type: Mapped[str | None] = mapped_column(String(64))
    year: Mapped[int] = mapped_column(Integer)
    n: Mapped[int] = mapped_column(Integer)
    overturned_n: Mapped[int] = mapped_column(Integer)


class InsurerStats(Base):
    __tablename__ = "insurer_stats"
    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    plan_year: Mapped[int] = mapped_column(Integer)
    state: Mapped[str] = mapped_column(String(8))
    issuer: Mapped[str] = mapped_column(String(256))
    claims_received: Mapped[int | None] = mapped_column(BigInteger)
    claims_denied: Mapped[int | None] = mapped_column(BigInteger)
    appeals_filed: Mapped[int | None] = mapped_column(BigInteger)
    appeals_overturned: Mapped[int | None] = mapped_column(BigInteger)


class DatasetManifest(Base):
    __tablename__ = "dataset_manifest"
    name: Mapped[str] = mapped_column(String(64), primary_key=True)
    url: Mapped[str] = mapped_column(Text)
    sha256: Mapped[str] = mapped_column(String(64))
    rows: Mapped[int] = mapped_column(Integer)
    downloaded_at: Mapped[str] = mapped_column(String(40))
    schema_ok: Mapped[bool] = mapped_column(Boolean)
    source: Mapped[str] = mapped_column(String(16))


class EvalRun(Base):
    __tablename__ = "eval_run"
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    suite: Mapped[str] = mapped_column(String(64))
    git_sha: Mapped[str | None] = mapped_column(String(64))
    prompt_versions: Mapped[dict[str, Any]] = mapped_column(JSONType, default=dict)
    model_versions: Mapped[dict[str, Any]] = mapped_column(JSONType, default=dict)
    metrics: Mapped[dict[str, Any]] = mapped_column(JSONType, default=dict)
    passed: Mapped[bool] = mapped_column(Boolean)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class AuditEvent(Base):
    __tablename__ = "audit_event"
    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    actor: Mapped[str] = mapped_column(String(64))
    action: Mapped[str] = mapped_column(String(64))
    entity: Mapped[str] = mapped_column(String(128))
    at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
