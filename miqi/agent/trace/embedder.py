"""Optional local embeddings for trace search."""

from __future__ import annotations

from loguru import logger


class Embedder:
    """Lazy-loaded local embedding model. Singleton per model name."""

    _instances: dict[str, "Embedder"] = {}

    def __init__(self, model_name: str):
        self.model_name = model_name
        self._model = None
        self._dim = 384
        self.available = self._try_load()

    def _try_load(self) -> bool:
        try:
            import fastembed  # noqa: F401
            import numpy  # noqa: F401

            return True
        except ImportError:
            return False

    @classmethod
    def get(cls, model_name: str) -> "Embedder":
        if model_name not in cls._instances:
            cls._instances[model_name] = cls(model_name)
        return cls._instances[model_name]

    def encode_one(self, text: str) -> bytes | None:
        """Return float32 little-endian bytes, or None if embedding is unavailable."""
        if not self.available or not text.strip():
            return None
        if self._model is None:
            logger.info("Loading embedding model {}...", self.model_name)
            from fastembed import TextEmbedding

            self._model = TextEmbedding(model_name=self.model_name)
        import numpy as np

        vec = next(iter(self._model.embed([text])))
        return np.asarray(vec, dtype=np.float32).tobytes()

    @staticmethod
    def cosine(a_bytes: bytes, b_bytes: bytes) -> float:
        import numpy as np

        a = np.frombuffer(a_bytes, dtype=np.float32)
        b = np.frombuffer(b_bytes, dtype=np.float32)
        denom = (np.linalg.norm(a) * np.linalg.norm(b)) or 1.0
        return float(np.dot(a, b) / denom)
