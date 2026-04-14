"""Single source of truth for the emotion vocabulary.

Writer emits one of these in DialogueLine.emotion. Reviewer validates
against the same set. Compiler emits Ren'Py `image` alias declarations
for each emotion that isn't present as a real PNG (so `show sable
thoughtful` always resolves to a file, never Ren'Py's built-in
label-over-silhouette placeholder).

Previously this list was duplicated in two places (reviewer._VALID_EMOTIONS
and renpy_compiler._ALL_EMOTIONS). Both consumers now import from here.

Invariant: ordering matters for documentation / iteration stability in
the compiler's alias emission, so we keep a tuple here and build a
frozenset beside it for the reviewer's O(1) membership check.
"""
from __future__ import annotations

VALID_EMOTIONS: tuple[str, ...] = (
    "neutral", "happy", "sad", "angry", "surprised",
    "scared", "thoughtful", "loving", "determined",
)

VALID_EMOTIONS_SET: frozenset[str] = frozenset(VALID_EMOTIONS)
