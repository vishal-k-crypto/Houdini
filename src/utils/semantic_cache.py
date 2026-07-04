"""
SemanticCache - Cache successful plans keyed by task embedding similarity.

Uses lightweight ONNX BGE embeddings via Optimum/ONNX runtime when available,
otherwise falls back to a tiny hash-based representation so the module has no
heavy dependencies.

Design goals:
- Fast plan reuse for visually/semantically similar tasks.
- Disk-backed persistence with TTL/expiration and confidence weighting.
- Optional integration with pattern_store for learned action sequences.
"""

from __future__ import annotations

import json
import hashlib
import time
from dataclasses import dataclass, field, asdict
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

from .logging import logger

# ============================================================
# CONFIGURATION
# ============================================================

DEFAULT_CACHE_DIR = Path(__file__).parent.parent.parent / "data" / "semantic_cache"
DEFAULT_SIMILARITY_THRESHOLD = 0.85
DEFAULT_TTL_DAYS = 30
DEFAULT_MAX_ENTRIES = 2000


# ============================================================
# EMBEDDING BACKENDS
# ============================================================

class EmbeddingBackend:
    """Base class for embedding implementations."""

    def embed(self, texts: List[str]) -> List[List[float]]:
        raise NotImplementedError


class OnnxBgeBackend(EmbeddingBackend):
    """
    ONNX BGE-Micro/v2 or similar lightweight model via sentence-transformers.
    Falls back to a tiny bag-of-words hash embedding if the model is missing.
    """

    def __init__(self, model_name: str = "BAAI/bge-small-en-v1.5"):
        self.model_name = model_name
        self._model = None
        self._fallback = False

        try:
            from sentence_transformers import SentenceTransformer
            self._model = SentenceTransformer(model_name, device="cpu")
            logger.info(f"SemanticCache: loaded embedding model {model_name}")
        except Exception as e:
            logger.debug(f"Could not load sentence-transformers model: {e}")
            self._fallback = True

    def embed(self, texts: List[str]) -> List[List[float]]:
        if not self._fallback and self._model is not None:
            try:
                embeddings = self._model.encode(texts, normalize_embeddings=True)
                return [emb.tolist() for emb in embeddings]
            except Exception as e:
                logger.debug(f"Embedding model failed: {e}, using fallback")
                self._fallback = True
        return self._fallback_embed(texts)

    @staticmethod
    def _fallback_embed(texts: List[str]) -> List[List[float]]:
        """Deterministic, normalized hash-based embedding (very lightweight)."""
        dim = 384
        results = []
        for text in texts:
            vec = [0.0] * dim
            lowered = text.lower()
            # Character n-gram hash embedding
            for i in range(len(lowered) - 2):
                gram = lowered[i : i + 3]
                idx = int(hashlib.md5(gram.encode()).hexdigest(), 16) % dim
                vec[idx] += 1.0
            # Normalize
            norm = sum(v * v for v in vec) ** 0.5 or 1.0
            vec = [v / norm for v in vec]
            results.append(vec)
        return results


class HashEmbeddingBackend(EmbeddingBackend):
    """Always use hash-based embedding. No external deps."""

    def __init__(self, dim: int = 384):
        self.dim = dim

    def embed(self, texts: List[str]) -> List[List[float]]:
        return OnnxBgeBackend._fallback_embed(texts)


def get_embedding_backend(prefer_onnx: bool = True) -> EmbeddingBackend:
    if prefer_onnx:
        backend = OnnxBgeBackend()
        if not backend._fallback:
            return backend
    return HashEmbeddingBackend()


# ============================================================
# CACHE ENTRY
# ============================================================

@dataclass
class CacheEntry:
    """A single cached plan entry."""

    key: str
    task_text: str
    embedding: List[float]
    macro_steps: List[Dict[str, Any]]
    expected_outcome: str
    success_criteria: str
    success_count: int = 0
    fail_count: int = 0
    avg_confidence: float = 0.0
    created_at: str = field(default_factory=lambda: datetime.now().isoformat())
    last_used: str = field(default_factory=lambda: datetime.now().isoformat())
    ttl_days: int = DEFAULT_TTL_DAYS

    @property
    def hit_rate(self) -> float:
        total = self.success_count + self.fail_count
        return self.success_count / max(total, 1)

    @property
    def is_expired(self) -> bool:
        try:
            last = datetime.fromisoformat(self.last_used)
        except Exception:
            last = datetime.now()
        return datetime.now() - last > timedelta(days=self.ttl_days)

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "CacheEntry":
        return cls(**data)


# ============================================================
# SEMANTIC CACHE
# ============================================================

class SemanticCache:
    """
    Cache successful macro plans keyed by task embedding similarity.

    Features:
    - Cosine-similarity lookup with configurable threshold.
    - Confidence-weighted hit-rate scoring (Thompson-like posterior mean).
    - TTL-based expiration and LRU eviction.
    - Persistence to JSONL.
    - Graceful fallback to zero-dependency hash embeddings.
    """

    def __init__(
        self,
        cache_dir: Optional[Path] = None,
        similarity_threshold: float = DEFAULT_SIMILARITY_THRESHOLD,
        ttl_days: int = DEFAULT_TTL_DAYS,
        max_entries: int = DEFAULT_MAX_ENTRIES,
        embedding_backend: Optional[EmbeddingBackend] = None,
    ):
        self.cache_dir = cache_dir or DEFAULT_CACHE_DIR
        self.cache_dir.mkdir(parents=True, exist_ok=True)
        self.similarity_threshold = similarity_threshold
        self.ttl_days = ttl_days
        self.max_entries = max_entries
        self.embedding_backend = embedding_backend or get_embedding_backend()
        self.storage_path = self.cache_dir / "semantic_cache.jsonl"
        self._entries: Dict[str, CacheEntry] = {}
        self._load()

    # --------------------------------------------------------
    # Storage
    # --------------------------------------------------------

    def _load(self):
        if not self.storage_path.exists():
            return
        try:
            with open(self.storage_path, "r", encoding="utf-8") as f:
                for line in f:
                    line = line.strip()
                    if not line:
                        continue
                    try:
                        entry = CacheEntry.from_dict(json.loads(line))
                        if entry.is_expired:
                            continue
                        self._entries[entry.key] = entry
                    except Exception as e:
                        logger.debug(f"Skipping malformed cache line: {e}")
        except Exception as e:
            logger.warning(f"Could not load semantic cache: {e}")

    def _save(self):
        try:
            self.cache_dir.mkdir(parents=True, exist_ok=True)
            with open(self.storage_path, "w", encoding="utf-8") as f:
                for entry in self._entries.values():
                    f.write(json.dumps(entry.to_dict()) + "\n")
        except Exception as e:
            logger.warning(f"Could not save semantic cache: {e}")

    def _evict_if_needed(self):
        if len(self._entries) <= self.max_entries:
            return
        # Evict expired first, then lowest weighted score
        expired = [k for k, e in self._entries.items() if e.is_expired]
        for k in expired:
            del self._entries[k]
        if len(self._entries) <= self.max_entries:
            return
        sorted_keys = sorted(
            self._entries.keys(),
            key=lambda k: self._entries[k].hit_rate * self._entries[k].avg_confidence,
        )
        to_remove = len(self._entries) - self.max_entries
        for k in sorted_keys[:to_remove]:
            del self._entries[k]

    # --------------------------------------------------------
    # Similarity
    # --------------------------------------------------------

    @staticmethod
    def cosine_similarity(a: List[float], b: List[float]) -> float:
        dot = sum(x * y for x, y in zip(a, b))
        norm_a = sum(x * x for x in a) ** 0.5 or 1.0
        norm_b = sum(x * x for x in b) ** 0.5 or 1.0
        return dot / (norm_a * norm_b)

    # --------------------------------------------------------
    # Public API
    # --------------------------------------------------------

    def lookup(self, task: str, top_k: int = 3) -> Optional[Tuple[CacheEntry, float]]:
        """
        Find a cached plan for a task based on embedding similarity.
        Returns the best match above threshold, or None.
        """
        if not self._entries:
            return None

        query_embedding = self.embedding_backend.embed([task])[0]

        best_match: Optional[Tuple[CacheEntry, float]] = None
        for entry in self._entries.values():
            sim = self.cosine_similarity(query_embedding, entry.embedding)
            if sim < self.similarity_threshold:
                continue
            if best_match is None or sim > best_match[1]:
                best_match = (entry, sim)

        if best_match:
            entry = best_match[0]
            entry.last_used = datetime.now().isoformat()
            self._save()
            logger.debug(f"SemanticCache hit: {task[:60]} -> {entry.task_text[:60]} (sim={best_match[1]:.3f})")
            return best_match

        return None

    def store(
        self,
        task: str,
        macro_steps: List[Dict[str, Any]],
        expected_outcome: str = "",
        success_criteria: str = "",
        success: bool = True,
        confidence: float = 0.0,
    ):
        """
        Store or update a cached plan for a task.
        """
        embedding = self.embedding_backend.embed([task])[0]
        key = hashlib.md5(task.lower().strip().encode()).hexdigest()[:16]

        entry = self._entries.get(key)
        if entry:
            entry.last_used = datetime.now().isoformat()
            if success:
                entry.success_count += 1
            else:
                entry.fail_count += 1
            # Running average confidence
            n = entry.success_count + entry.fail_count
            entry.avg_confidence = (entry.avg_confidence * (n - 1) + confidence) / max(n, 1)
        else:
            entry = CacheEntry(
                key=key,
                task_text=task,
                embedding=embedding,
                macro_steps=macro_steps,
                expected_outcome=expected_outcome,
                success_criteria=success_criteria,
                success_count=1 if success else 0,
                fail_count=0 if success else 1,
                avg_confidence=confidence,
                ttl_days=self.ttl_days,
            )
            self._entries[key] = entry

        self._evict_if_needed()
        self._save()
        logger.debug(f"SemanticCache stored: {task[:60]} (success={success})")

    def record_outcome(self, task: str, success: bool, confidence: float = 0.0):
        """Record whether a cached plan succeeded or failed."""
        key = hashlib.md5(task.lower().strip().encode()).hexdigest()[:16]
        entry = self._entries.get(key)
        if entry:
            if success:
                entry.success_count += 1
            else:
                entry.fail_count += 1
            n = entry.success_count + entry.fail_count
            entry.avg_confidence = (entry.avg_confidence * (n - 1) + confidence) / max(n, 1)
            entry.last_used = datetime.now().isoformat()
            self._save()

    def invalidate(self, task: str):
        """Remove a cached entry by task text."""
        key = hashlib.md5(task.lower().strip().encode()).hexdigest()[:16]
        if key in self._entries:
            del self._entries[key]
            self._save()

    def get_stats(self) -> Dict[str, Any]:
        return {
            "entries": len(self._entries),
            "threshold": self.similarity_threshold,
            "ttl_days": self.ttl_days,
            "max_entries": self.max_entries,
            "avg_hit_rate": (
                sum(e.hit_rate for e in self._entries.values()) / len(self._entries)
                if self._entries else 0.0
            ),
        }

    def clear(self):
        self._entries.clear()
        self._save()


# Global singleton
semantic_cache = SemanticCache()


# Convenience functions
def lookup_plan(task: str, threshold: float = DEFAULT_SIMILARITY_THRESHOLD) -> Optional[Dict[str, Any]]:
    match = semantic_cache.lookup(task)
    if match and match[1] >= threshold:
        entry, sim = match
        return {
            "macro_steps": entry.macro_steps,
            "expected_outcome": entry.expected_outcome,
            "success_criteria": entry.success_criteria,
            "similarity": sim,
            "hit_rate": entry.hit_rate,
            "avg_confidence": entry.avg_confidence,
        }
    return None


def store_plan(
    task: str,
    macro_steps: List[Dict[str, Any]],
    expected_outcome: str = "",
    success_criteria: str = "",
    success: bool = True,
    confidence: float = 0.0,
):
    semantic_cache.store(
        task=task,
        macro_steps=macro_steps,
        expected_outcome=expected_outcome,
        success_criteria=success_criteria,
        success=success,
        confidence=confidence,
    )
