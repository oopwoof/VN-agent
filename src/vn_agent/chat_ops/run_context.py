"""Per-request context for chat-ops executors.

`mock_mode_var` tells an executor whether any paid call is allowed at all.
`text_only_var` tells it something narrower and just as important: this
job was configured to never spend on images. The pipeline honors that by
routing straight past asset generation, but a chat-ops turn arrives after
the pipeline is done and has no such edge to follow — without this flag an
`edit_asset` confirm on a text-only project would happily call the image
provider the project was set up to avoid.

Set per request (the same way the chat endpoints set `mock_mode_var`),
because ContextVars do not propagate across ASGI requests.
"""
from __future__ import annotations

from contextvars import ContextVar

text_only_var: ContextVar[bool] = ContextVar("vn_agent_chat_text_only", default=False)


def images_allowed() -> bool:
    """True when this job may make a real image-generation call."""
    from vn_agent.services.llm import mock_mode_var

    return not mock_mode_var.get() and not text_only_var.get()


def no_images_reason() -> str:
    """Why images are off, phrased for the creator."""
    from vn_agent.services.llm import mock_mode_var

    if mock_mode_var.get():
        return "mock mode makes no image calls"
    return "this project is text-only, so it generates no images"
