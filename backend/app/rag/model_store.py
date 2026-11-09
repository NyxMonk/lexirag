"""Locating, downloading and loading Hugging Face models without surprises.

By default models are never downloaded implicitly: ``resolve_model_path`` only
looks in the local cache and raises an actionable error if the model is absent.
``download_model`` is called explicitly (``python -m app.cli download-models``).
"""

import logging
import os
import threading
from pathlib import Path

from app.core.config import Settings
from app.rag.errors import ModelUnavailableError

logger = logging.getLogger("lexirag.models")

# Files that are not needed for dense embeddings / cross-encoder reranking with PyTorch.
_IGNORE_PATTERNS = [
    "onnx/*",
    "*.onnx",
    "*.onnx_data",
    "*.h5",
    "*.msgpack",
    "*.ot",
    "*.tflite",
    "imgs/*",
    "*.png",
    "*.jpg",
    "colbert_linear.pt",
    "sparse_linear.pt",
]

DOWNLOAD_HINT = "Download it with: python -m app.cli download-models (from the backend directory)"


def _hub_kwargs(settings: Settings) -> dict[str, object]:
    return {"cache_dir": settings.model_cache_path} if settings.model_cache_path else {}


def resolve_model_path(model_id: str, settings: Settings) -> Path:
    """Return a local directory for ``model_id``; download only if explicitly allowed."""
    if Path(model_id).is_dir():
        return Path(model_id)
    from huggingface_hub import snapshot_download
    from huggingface_hub.errors import LocalEntryNotFoundError

    try:
        return Path(snapshot_download(model_id, local_files_only=True, **_hub_kwargs(settings)))
    except LocalEntryNotFoundError:
        if not settings.models_allow_download:
            raise ModelUnavailableError(
                f"The model {model_id} is not downloaded. {DOWNLOAD_HINT}, "
                "or set MODELS_ALLOW_DOWNLOAD=true."
            ) from None
    return download_model(model_id, settings)


def download_model(model_id: str, settings: Settings) -> Path:
    from huggingface_hub import list_repo_files, snapshot_download

    ignore = list(_IGNORE_PATTERNS)
    try:
        files = list_repo_files(model_id)
        # Prefer safetensors; skip the duplicate PyTorch pickle when both are published.
        if any(f.endswith(".safetensors") for f in files):
            ignore += ["*.bin", "*.pt", "*.pth"]
    except Exception:  # noqa: BLE001 - offline listing failure; download will report the real error
        logger.debug("Could not list files for %s", model_id, exc_info=True)
    logger.info("Downloading %s (this can take a while)...", model_id)
    try:
        path = snapshot_download(model_id, ignore_patterns=ignore, **_hub_kwargs(settings))
    except Exception as exc:  # noqa: BLE001
        raise ModelUnavailableError(f"Downloading {model_id} failed: {exc.__class__.__name__}: {exc}") from exc
    return Path(path)


def model_is_downloaded(model_id: str, settings: Settings) -> bool:
    try:
        from huggingface_hub import snapshot_download

        snapshot_download(model_id, local_files_only=True, **_hub_kwargs(settings))
        return True
    except Exception:  # noqa: BLE001
        return Path(model_id).is_dir()


def model_disk_size(path: Path) -> int:
    total = 0
    for root, _dirs, files in os.walk(path):
        for name in files:
            try:
                total += os.path.getsize(os.path.realpath(os.path.join(root, name)))
            except OSError:
                pass
    return total


_device_lock = threading.Lock()


def select_device(preference: str) -> str:
    import torch

    preference = (preference or "auto").lower()
    with _device_lock:
        if preference == "cuda":
            if not torch.cuda.is_available():
                raise ModelUnavailableError("MODEL_DEVICE=cuda but no CUDA-enabled PyTorch/GPU is available.")
            return "cuda"
        if preference == "mps":
            if not (getattr(torch.backends, "mps", None) and torch.backends.mps.is_available()):
                raise ModelUnavailableError("MODEL_DEVICE=mps but Apple Metal (MPS) is not available.")
            return "mps"
        if preference == "cpu":
            return "cpu"
        if torch.cuda.is_available():
            return "cuda"
        # MPS is opt-in: some transformer ops are still slower or unsupported there.
        return "cpu"


def describe_load_error(model_id: str, exc: BaseException) -> ModelUnavailableError:
    text = str(exc).lower()
    if isinstance(exc, MemoryError) or "out of memory" in text or "not enough memory" in text:
        return ModelUnavailableError(
            f"Not enough memory to load {model_id}. Close other applications, use MODEL_DEVICE=cpu, "
            "or disable the reranker (RERANKER_ENABLED=false)."
        )
    return ModelUnavailableError(f"Could not load {model_id}: {exc.__class__.__name__}: {exc}")
