"""License gate — block exports containing assets with unknown provenance.

Design decisions:
- Whitelist not blacklist. Only accepted values pass; anything else (typo,
  new license, "cc-by" lowercase mismatch, "public domain" str) needs
  explicit review. Better to nag the curator than to accidentally ship
  a non-redistributable asset.
- Report-first mode. `audit(...)` returns a structured report so callers
  (Web export button, CLI export command, tests) can render/log without
  raising. `enforce(...)` raises `LicenseGateError` — use it in the
  export path.
- Sources of provenance in v4 P0:
    1. UserUpload chunks   — via AnnotatedSession.source_meta["license"]
    2. Library assets      — via library_hits.jsonl in output_dir
    3. LLM-generated art   — implicit "derived" (Anthropic/OpenAI TOS
                             allows generated-output use)
    4. Web-search chunks   — via source_meta["license"] (best-effort;
                             gate flags "unknown" and asks reviewer)
"""
from __future__ import annotations

import json
import logging
from dataclasses import dataclass, field
from pathlib import Path

logger = logging.getLogger(__name__)

# Whitelist. Add new SPDX-ish values here only after confirming
# redistribution is legal for the intended distribution channel
# (Ren'Py package, itch.io upload, hosted web preview).
ACCEPTED_LICENSES: frozenset[str] = frozenset({
    "CC0",
    "CC-BY",
    "CC-BY-SA",
    "user_owned",       # creator uploaded their own; they signed the ToS
    "derived",          # LLM/image-model output; provider ToS covers reuse
})


class LicenseGateError(RuntimeError):
    """Raised when enforce() finds violations."""


@dataclass
class LicenseViolation:
    source: str                              # "user_upload" | "library" | "web_search" | "unknown"
    identifier: str                          # filename / asset_id / url
    license: str
    reason: str


@dataclass
class LicenseReport:
    total: int = 0
    accepted: int = 0
    violations: list[LicenseViolation] = field(default_factory=list)
    by_license: dict[str, int] = field(default_factory=dict)

    @property
    def ok(self) -> bool:
        return not self.violations

    def summary(self) -> str:
        lines = [
            f"License audit — {self.accepted}/{self.total} assets accepted",
            f"By license: {dict(sorted(self.by_license.items()))}",
        ]
        if self.violations:
            lines.append(f"Violations ({len(self.violations)}):")
            for v in self.violations:
                lines.append(
                    f"  - [{v.source}] {v.identifier}: license={v.license!r} — {v.reason}"
                )
        return "\n".join(lines)


def _normalize_license(raw: str | None) -> str:
    """Fold common variants → canonical whitelist form.

    Returns "unknown" for None / empty / unrecognizable inputs so the
    caller can gate on that single sentinel.
    """
    if not raw:
        return "unknown"
    s = str(raw).strip()
    # Case-insensitive match against the whitelist.
    for accepted in ACCEPTED_LICENSES:
        if s.casefold() == accepted.casefold():
            return accepted
    # Common alternate spellings.
    mapping = {
        "cc0-1.0": "CC0",
        "cc0 1.0": "CC0",
        "cc-by-4.0": "CC-BY",
        "cc-by 4.0": "CC-BY",
        "cc-by-sa-4.0": "CC-BY-SA",
        "public domain": "CC0",
        "publicdomain": "CC0",
    }
    return mapping.get(s.casefold(), "unknown")


def audit(
    *,
    upload_chunks: list = None,
    library_hits_path: Path | None = None,
) -> LicenseReport:
    """Walk all provenance sources and return a structured report.

    `upload_chunks` accepts a list of AnnotatedSession-ish objects with
    `source_meta` dict access (kept loose so tests can pass dicts, too).
    `library_hits_path` is `{output_dir}/library_hits.jsonl` produced by
    `library.record_library_hit`.
    """
    report = LicenseReport()

    def _tally(source: str, identifier: str, raw_license: str, reason_if_bad: str = "not in whitelist"):
        report.total += 1
        normalized = _normalize_license(raw_license)
        report.by_license[normalized] = report.by_license.get(normalized, 0) + 1
        if normalized in ACCEPTED_LICENSES:
            report.accepted += 1
        else:
            report.violations.append(LicenseViolation(
                source=source,
                identifier=identifier,
                license=raw_license or "(missing)",
                reason=reason_if_bad,
            ))

    # ── User uploads ────────────────────────────────────────────────────────
    for ch in (upload_chunks or []):
        meta = getattr(ch, "source_meta", None) or (ch.get("source_meta", {}) if isinstance(ch, dict) else {})
        raw_lic = meta.get("license") if isinstance(meta, dict) else None
        # Identifier prefers filename for uploads, url for web_search.
        ident = (meta or {}).get("filename") or (meta or {}).get("source_url") or "(unknown chunk)"
        src = (meta or {}).get("source", "user_upload")
        _tally(src if src in {"user_upload", "web_search", "local_library"} else "user_upload", ident, raw_lic or "unknown")

    # ── Library hits ────────────────────────────────────────────────────────
    if library_hits_path is not None and library_hits_path.exists():
        with library_hits_path.open(encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                try:
                    row = json.loads(line)
                except json.JSONDecodeError:
                    continue
                _tally(
                    "library",
                    row.get("asset_id") or row.get("target_id") or "(unknown)",
                    row.get("license") or "unknown",
                )

    return report


def enforce(**kwargs) -> LicenseReport:
    """Same as audit(), but raises LicenseGateError when violations exist."""
    report = audit(**kwargs)
    if not report.ok:
        raise LicenseGateError(report.summary())
    return report
