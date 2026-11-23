"""Embedder interface: all-MiniLM-L6-v2 (384-d) via sentence-transformers; fallback TF-IDF + truncated SVD
(LSA) to the same 384 dimensions if the model download fails."""

from __future__ import annotations

from functools import lru_cache
from pathlib import Path

import numpy as np

from appeal_core.settings import ROOT, get_settings

DIM = 384
MODEL_NAME = "sentence-transformers/all-MiniLM-L6-v2"
LSA_PATH = ROOT / "ml" / "artifacts" / "embedder" / "lsa.joblib"


class MiniLMEmbedder:
    name = "minilm"
    dim = DIM

    def __init__(self) -> None:
        from sentence_transformers import SentenceTransformer

        self.model = SentenceTransformer(MODEL_NAME, device="cpu")

    def embed(self, texts: list[str], batch_size: int = 64) -> np.ndarray:
        return np.asarray(self.model.encode(texts, batch_size=batch_size, normalize_embeddings=True, show_progress_bar=False), dtype=np.float32)


class LSAEmbedder:
    name = "lsa"
    dim = DIM

    def __init__(self, path: Path = LSA_PATH):
        import joblib

        self.pipe = joblib.load(path)

    @staticmethod
    def fit(corpus: list[str], path: Path = LSA_PATH) -> LSAEmbedder:
        import joblib
        from sklearn.decomposition import TruncatedSVD
        from sklearn.feature_extraction.text import TfidfVectorizer
        from sklearn.pipeline import make_pipeline

        pipe = make_pipeline(TfidfVectorizer(sublinear_tf=True, min_df=2, max_features=100_000, stop_words="english"), TruncatedSVD(DIM, random_state=0))
        pipe.fit(corpus)
        path.parent.mkdir(parents=True, exist_ok=True)
        joblib.dump(pipe, path)
        return LSAEmbedder(path)

    def embed(self, texts: list[str], batch_size: int = 0) -> np.ndarray:
        v = self.pipe.transform(texts).astype(np.float32)
        n = np.linalg.norm(v, axis=1, keepdims=True)
        return v / np.maximum(n, 1e-9)


@lru_cache
def get_embedder():
    s = get_settings()
    if s.embedder == "azure":
        from appeal_core.adapters.azure import AzureOpenAIEmbedder

        return AzureOpenAIEmbedder()
    if s.embedder == "lsa":
        return LSAEmbedder()
    try:
        return MiniLMEmbedder()
    except Exception:
        if LSA_PATH.exists():
            return LSAEmbedder()
        raise
