"""LangChain `BaseRetriever`s over the hybrid search (keyword + vector, RRF, rerank, diversification).

The Research agent retrieves through these, and Ragas reads the same Documents as RAG contexts, so the
production retrieval path and the evaluated one are identical.
"""

from __future__ import annotations

from typing import Any

from langchain_core.callbacks import CallbackManagerForRetrieverRun
from langchain_core.documents import Document
from langchain_core.retrievers import BaseRetriever


def _doc(row: dict[str, Any]) -> Document:
    return Document(id=row["id"], page_content=row["text"], metadata={k: v for k, v in row.items() if k != "text"})


def rows(docs: list[Document]) -> list[dict[str, Any]]:
    return [{**d.metadata, "id": d.id, "text": d.page_content} for d in docs]


class RulesRetriever(BaseRetriever):
    """Regulation paragraphs and rights summaries. `extra_queries` are the rewrites (vector side only)."""

    hybrid: Any
    plan_type: str | None = None
    k: int = 8
    required_ids: list[str] = []
    extra_queries: list[str] = []

    def _get_relevant_documents(self, query: str, *, run_manager: CallbackManagerForRetrieverRun) -> list[Document]:
        found = self.hybrid.search_rules([query, *self.extra_queries], plan_type=self.plan_type, k=self.k, required_ids=self.required_ids)
        return [_doc(r) for r in found]


class PrecedentRetriever(BaseRetriever):
    """Real IMR decisions, filtered by treatment category and IMR type (relaxed when too few match)."""

    hybrid: Any
    treatment_category: str | None = None
    treatment_subcategory: str | None = None
    imr_type: str | None = None
    k: int = 5
    extra_queries: list[str] = []

    def _get_relevant_documents(self, query: str, *, run_manager: CallbackManagerForRetrieverRun) -> list[Document]:
        found = self.hybrid.search_precedents(
            [query, *self.extra_queries],
            treatment_category=self.treatment_category,
            treatment_subcategory=self.treatment_subcategory,
            imr_type=self.imr_type,
            k=self.k,
        )
        return [_doc(r) for r in found]
