"""Local text embeddings with fastembed (ONNX), loaded once per process.

Default model: `BAAI/bge-small-en-v1.5`, 384 dimensions, about 67 MB fetched
once from the Hugging Face Hub (no account or key) into fastembed's cache
(`FASTEMBED_CACHE_PATH`, a named volume under Docker Compose).

Device: picked at load time. CUDA when onnxruntime reports
`CUDAExecutionProvider` (install `fastembed-gpu` for that), else CPU.
onnxruntime has no Apple MPS provider, so Apple silicon falls back CUDA -> CPU;
the model is small enough that CPU is the intended path everywhere.
"""

import logging
from threading import Lock

logger = logging.getLogger(__name__)

CUDA = "CUDAExecutionProvider"
CPU = "CPUExecutionProvider"


def select_providers() -> list[str]:
    """First available of CUDA -> CPU (no MPS provider exists for onnxruntime)."""
    try:
        import onnxruntime

        available = onnxruntime.get_available_providers()
    except Exception:  # an import failure must not stop CPU inference
        available = []
    return [CUDA, CPU] if CUDA in available else [CPU]


class FastEmbedder:
    """`EmbedderPort` over fastembed. Thread-safe lazy load; one model per process."""

    def __init__(self, model_name: str) -> None:
        self.model_name = model_name
        self._model = None
        self._dim: int | None = None
        self._lock = Lock()

    def _load(self):
        if self._model is None:
            with self._lock:
                if self._model is None:
                    from fastembed import TextEmbedding

                    providers = select_providers()
                    logger.info(
                        "Loading embedding model %s on %s",
                        self.model_name,
                        "CUDA" if providers[0] == CUDA else "CPU",
                    )
                    self._model = TextEmbedding(model_name=self.model_name, providers=providers)
        return self._model

    def vector_size(self) -> int:
        if self._dim is None:
            self._dim = len(self.embed_query("dimension probe"))
        return self._dim

    def embed(self, texts: list[str]) -> list[list[float]]:
        if not texts:
            return []
        return [vector.tolist() for vector in self._load().passage_embed(texts)]

    def embed_query(self, text: str) -> list[float]:
        return next(iter(self._load().query_embed(text))).tolist()


_embedders: dict[str, FastEmbedder] = {}
_registry_lock = Lock()


def get_embedder(model_name: str) -> FastEmbedder:
    with _registry_lock:
        if model_name not in _embedders:
            _embedders[model_name] = FastEmbedder(model_name)
        return _embedders[model_name]
