"""Sprint 12-3b: transparent-background sprite post-processing.

Runs rembg (u2net ONNX) locally over generated sprite bytes so Ren'Py
sprites composite over scene backgrounds without a visible rectangle.
The generation prompts request a clean silhouette on flat background
— rembg handles the actual alpha cutout deterministically.

Why u2net_human_seg (not generic u2net): it's the human-specific head
from the u2net family, trained on portrait mattes. Cleaner edges on
hair, less halo on light backgrounds. Fallback to u2net for non-human
characters (creatures, monsters) if u2net_human_seg eats them.

Why optional dependency: onnxruntime is ~100MB and the u2net weights
are another ~170MB on first use. Many environments (CI, dev laptops
without GPU) don't need it, and the pipeline still produces usable
sprites without cutout — just with a visible background.
"""
from __future__ import annotations

import logging
from pathlib import Path

logger = logging.getLogger(__name__)

_session: object | None = None  # lazy-init rembg session
_unavailable_reason: str | None = None


def _get_session(model_name: str = "u2net_human_seg"):
    """Lazy-load and cache the rembg session (first call downloads ~170MB)."""
    global _session, _unavailable_reason
    if _session is not None:
        return _session
    if _unavailable_reason is not None:
        return None
    try:
        from rembg import new_session  # type: ignore
    except ImportError as e:
        _unavailable_reason = (
            f"rembg not installed ({e}). "
            "Install with: uv sync --extra cutout"
        )
        logger.warning(_unavailable_reason)
        return None
    try:
        _session = new_session(model_name)
        logger.info(f"rembg session ready: model={model_name}")
        return _session
    except Exception as e:
        _unavailable_reason = f"rembg session failed for model={model_name}: {e}"
        logger.warning(_unavailable_reason)
        return None


def is_available() -> bool:
    """Cheap check used at startup to warn if cutout is enabled but unavailable."""
    try:
        import rembg  # noqa: F401
        return True
    except ImportError:
        return False


def cutout_png(path: Path, model_name: str = "u2net_human_seg") -> bool:
    """Convert path in-place from solid-bg PNG → transparent-bg PNG.

    Returns True on success, False if rembg is unavailable or inference
    failed (caller keeps the original file and logs). Safe to call on
    any PNG — rembg re-reads bytes, applies u2net mask, writes alpha.
    """
    session = _get_session(model_name)
    if session is None:
        return False
    try:
        from rembg import remove  # type: ignore
    except ImportError:
        return False
    try:
        raw = path.read_bytes()
    except OSError as e:
        logger.warning(f"cutout: can't read {path}: {e}")
        return False
    try:
        cut = remove(raw, session=session)
    except Exception as e:
        logger.warning(f"cutout: rembg failed on {path}: {e}")
        return False
    if not cut or len(cut) < 256:
        logger.warning(f"cutout: empty/tiny output for {path} (kept original)")
        return False
    try:
        path.write_bytes(cut)
    except OSError as e:
        logger.warning(f"cutout: can't write {path}: {e}")
        return False
    logger.debug(f"cutout: {path.name} {len(raw)}B → {len(cut)}B (alpha)")
    return True
