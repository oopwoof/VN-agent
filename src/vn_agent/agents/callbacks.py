"""Progress callback protocol for pipeline events."""
from __future__ import annotations

from collections.abc import Awaitable, Callable

# A callback receives (node_name, message) and optionally is async
ProgressCallback = Callable[[str, str], None] | Callable[[str, str], Awaitable[None]]


def noop_callback(node_name: str, message: str) -> None:
    """Default no-op callback."""
    pass
