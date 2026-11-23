"""Engine and session helpers."""

from __future__ import annotations

from collections.abc import Iterator
from contextlib import contextmanager
from functools import lru_cache

from sqlalchemy import Select, create_engine
from sqlalchemy.engine import Engine
from sqlalchemy.orm import Session, sessionmaker

from appeal_core.settings import get_settings

_engines: dict[str, Engine] = {}


def get_engine(url: str | None = None) -> Engine:
    url = url or get_settings().database_url
    if url not in _engines:
        _engines[url] = create_engine(url, pool_pre_ping=True, pool_size=10, max_overflow=10, future=True)
    return _engines[url]


@lru_cache
def _factory(url: str) -> sessionmaker[Session]:
    return sessionmaker(bind=get_engine(url), expire_on_commit=False, future=True)


def session_factory(url: str | None = None) -> sessionmaker[Session]:
    return _factory(url or get_settings().database_url)


@contextmanager
def session_scope(url: str | None = None) -> Iterator[Session]:
    s = session_factory(url)()
    try:
        yield s
        s.commit()
    except Exception:
        s.rollback()
        raise
    finally:
        s.close()


class MissingRow(LookupError):
    """A row the code relies on does not exist (e.g. the case was deleted while its job was running)."""


def must_get[T](s: Session, model: type[T], key: object) -> T:
    obj = s.get(model, key)
    if obj is None:
        raise MissingRow(f"{model.__name__} {key} not found")
    return obj


def must_scalar[T](s: Session, stmt: Select[T], what: str) -> T:
    obj = s.scalar(stmt)
    if obj is None:
        raise MissingRow(f"{what} not found")
    return obj
