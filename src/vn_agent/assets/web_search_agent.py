"""Web search agent: topic → planned queries → search → fetch → chunk → RAG.

Design decisions
---------------
- Provider protocol, not a hardcoded backend. Serper is the M0 production
  path (generous free tier, one env var), StaticFixtureProvider is the
  test double, GeminiGroundingProvider is a stub that raises with an
  actionable message until the Gemini MCP wire is done in M1. Callers
  don't rebuild flow when a provider changes.
- Query planning uses Haiku, not Sonnet. The task is "topic → 3-5 search
  queries" — that's classification-flavored, not narrative-flavored, and
  Haiku costs ~5× less. Matches `feedback_model_selection`.
- Hard cost gates at the entry point. Both query count (default 5) and
  aggregate result token size (default 8k tokens ≈ 32k chars) are
  capped so a runaway topic doesn't blow the budget silently. The caps
  are keyword-only args on `search_and_ingest` so callers can tune them
  per job.
- Every chunk carries source_url + retrieved_at + search_query in
  source_meta — the export gate (P0-4) and diversity index (P0-6)
  already know how to read these.
- Same-job dedup piped through `dedup_chunks` — web search results
  overlap heavily (Wikipedia + Fandom + Reddit all mirror content) and
  we don't want the RAG pool to over-index near-duplicates.

M0 boundary
-----------
- Real network I/O happens only in SerperProvider. All other units are
  offline-testable via StaticFixtureProvider (or callers passing their
  own provider). This keeps the pipeline flow provable without hitting
  external services in CI.
- Gemini grounding provider is intentionally left as a stub; wiring it
  in requires MCP session-level integration that's out of P0 scope.
"""
from __future__ import annotations

import json
import logging
import os
import re
import time
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Iterable, Protocol

from vn_agent.eval.corpus import AnnotatedSession

logger = logging.getLogger(__name__)

# Cost gates ---------------------------------------------------------------
_DEFAULT_MAX_QUERIES = 5
_DEFAULT_MAX_TOTAL_CHARS = 32_000     # ~ 8k tokens
_DEFAULT_MAX_RESULTS_PER_QUERY = 3
_DEFAULT_HAIKU_MAX_QUERIES_TOKENS = 400  # response cap for planning call

_ACCEPTED_LICENSES_FOR_WEB = "unknown"  # web results are best-effort; audited later


# ---------------------------------------------------------------------------
# Data model
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class SearchResult:
    """One raw search hit — before the body is fetched."""
    url: str
    title: str
    snippet: str
    rank: int = 0
    query: str = ""


@dataclass
class FetchedPage:
    """A page pulled from a URL. body is plaintext; caller passes it to chunker."""
    url: str
    title: str
    body: str
    query: str = ""
    fetched_at: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())


@dataclass
class IngestReport:
    """Per-run diagnostics for the web-search flow."""
    topic: str = ""
    provider: str = ""
    queries: list[str] = field(default_factory=list)
    hits: int = 0
    fetched_pages: int = 0
    chunks_ingested: int = 0
    chunks_deduped: int = 0
    total_chars_fetched: int = 0
    stopped_reason: str = ""  # "ok" | "char_cap" | "query_cap" | "empty_result" | "error:xxx"
    errors: list[str] = field(default_factory=list)

    def to_dict(self) -> dict:
        return {
            "topic": self.topic,
            "provider": self.provider,
            "queries": self.queries,
            "hits": self.hits,
            "fetched_pages": self.fetched_pages,
            "chunks_ingested": self.chunks_ingested,
            "chunks_deduped": self.chunks_deduped,
            "total_chars_fetched": self.total_chars_fetched,
            "stopped_reason": self.stopped_reason,
            "errors": self.errors,
        }


# ---------------------------------------------------------------------------
# Provider protocol + concrete providers
# ---------------------------------------------------------------------------


class WebSearchProvider(Protocol):
    """Two ops: search returns SearchResult[]; fetch returns FetchedPage.

    Implementations may raise `WebSearchError` for retriable outages;
    callers convert those to `IngestReport.errors` entries and continue.
    """

    name: str

    def search(self, query: str, k: int = 3) -> list[SearchResult]: ...

    def fetch(self, hit: SearchResult) -> FetchedPage: ...


class WebSearchError(RuntimeError):
    """Provider-level failure (network, quota, parse). Caller decides recover-or-abort."""


class StaticFixtureProvider:
    """Deterministic fixture provider for tests + offline demos.

    Constructed with a `{query_substring: [SearchResult]}` map + a
    `{url: body}` map. Any query not matched returns [] (empty result).
    """

    name = "static"

    def __init__(
        self,
        search_map: dict[str, list[SearchResult]] | None = None,
        body_map: dict[str, str] | None = None,
    ):
        self._search_map = search_map or {}
        self._body_map = body_map or {}

    def search(self, query: str, k: int = 3) -> list[SearchResult]:
        q_lower = query.lower()
        for key, hits in self._search_map.items():
            if key.lower() in q_lower:
                return [SearchResult(**{**h.__dict__, "query": query}) for h in hits[:k]]
        return []

    def fetch(self, hit: SearchResult) -> FetchedPage:
        body = self._body_map.get(hit.url, "")
        if not body:
            raise WebSearchError(f"static fixture has no body for {hit.url!r}")
        return FetchedPage(url=hit.url, title=hit.title, body=body, query=hit.query)


class SerperProvider:
    """Real Serper.dev search + best-effort httpx fetch. Requires SERPER_API_KEY.

    Serper is a Google search proxy — generous free tier, JSON output,
    much simpler than raw scrape. Choice reasoning: Bing/Brave are also
    solid; Serper picked because their API shape maps 1:1 to what we
    need (no oauth, no per-query auth handshake).

    Fetch uses httpx with a 10s timeout and a browser-like user-agent to
    reduce trivial 403s. HTML → text is deliberately shallow (regex tag
    strip); a proper parser would add BeautifulSoup and yet more deps
    for M0. Good enough for wikipedia/wikia/reddit which dominate the
    result mix; obvious upgrade path when the pipeline grows.
    """

    name = "serper"
    _SEARCH_URL = "https://google.serper.dev/search"
    _USER_AGENT = (
        "Mozilla/5.0 (compatible; VN-Agent/1.0; +https://github.com/oopwoof/VN-agent)"
    )

    def __init__(self, api_key: str | None = None, timeout: float = 10.0):
        self.api_key = api_key or os.environ.get("SERPER_API_KEY")
        if not self.api_key:
            raise WebSearchError(
                "SERPER_API_KEY not set. Get a free key at https://serper.dev "
                "or pass a different provider (StaticFixtureProvider for tests)."
            )
        self.timeout = timeout

    def search(self, query: str, k: int = 3) -> list[SearchResult]:
        import httpx

        try:
            resp = httpx.post(
                self._SEARCH_URL,
                headers={"X-API-KEY": self.api_key, "Content-Type": "application/json"},
                json={"q": query, "num": k},
                timeout=self.timeout,
            )
            resp.raise_for_status()
            data = resp.json()
        except httpx.HTTPError as e:
            raise WebSearchError(f"Serper search failed: {e}") from e

        organic = data.get("organic") or []
        out: list[SearchResult] = []
        for i, item in enumerate(organic[:k]):
            url = item.get("link")
            if not url:
                continue
            out.append(SearchResult(
                url=url,
                title=str(item.get("title") or "")[:200],
                snippet=str(item.get("snippet") or "")[:500],
                rank=i,
                query=query,
            ))
        return out

    def fetch(self, hit: SearchResult) -> FetchedPage:
        import httpx

        try:
            resp = httpx.get(
                hit.url,
                headers={"User-Agent": self._USER_AGENT},
                timeout=self.timeout,
                follow_redirects=True,
            )
            resp.raise_for_status()
        except httpx.HTTPError as e:
            raise WebSearchError(f"fetch failed for {hit.url}: {e}") from e

        content_type = resp.headers.get("content-type", "")
        if "text/html" not in content_type and "text/plain" not in content_type:
            raise WebSearchError(f"unsupported content-type {content_type!r} at {hit.url}")

        body = _html_to_text(resp.text)
        return FetchedPage(url=hit.url, title=hit.title, body=body, query=hit.query)


class GeminiGroundingProvider:
    """Placeholder — wiring gemini-cli grounding into a running vn-agent
    process needs MCP session integration that's deferred to M1.
    """

    name = "gemini_grounding"

    def search(self, query: str, k: int = 3) -> list[SearchResult]:  # noqa: ARG002
        raise WebSearchError(
            "Gemini grounding provider is a stub in M0 — use SerperProvider "
            "with SERPER_API_KEY, or StaticFixtureProvider in tests. "
            "See docs/v4/PRODUCT_v4.md §5.③ for the M1 wire plan."
        )

    def fetch(self, hit: SearchResult) -> FetchedPage:  # noqa: ARG002
        raise WebSearchError("Gemini grounding fetch: not implemented in M0.")


# ---------------------------------------------------------------------------
# Query planning (Haiku)
# ---------------------------------------------------------------------------


async def plan_queries(
    topic: str,
    max_queries: int = _DEFAULT_MAX_QUERIES,
    *,
    llm=None,
) -> list[str]:
    """Turn a topic sentence into `max_queries` targeted search queries.

    Uses Haiku by default (query planning is classification-flavored, not
    narrative). Callers may inject an alternate `llm` callable for tests
    that don't want to touch the API — signature is
    `(system, user, schema=None, model=None, caller=None) -> T | str`.

    Falls back to a single naive query = topic when the LLM output can't
    be parsed as a JSON list. The pipeline continues; the report notes
    the fallback so we can catch prompt-drift regressions.
    """
    if not topic or not topic.strip():
        return []

    max_queries = max(1, min(max_queries, 10))

    system = (
        "You plan web search queries for a creative-writing assistant. "
        "Given a topic, output exactly the requested number of distinct queries "
        "that would return material a visual-novel writer could reuse "
        "(worldbuilding, character archetypes, locations, cultural details). "
        "Prefer queries that surface reference material over queries that surface opinion."
    )
    user = (
        f"Topic: {topic.strip()}\n\n"
        f"Output a JSON array of {max_queries} search queries (strings). "
        "No prose, no numbering, no keys — just the raw JSON array."
    )

    if llm is None:
        from vn_agent.services.llm import ainvoke_llm as _ainvoke
        try:
            from vn_agent.config import get_settings
            model = getattr(get_settings(), "llm_haiku_model", None) or "claude-haiku-4-5-20251001"
        except Exception:  # noqa: BLE001
            model = "claude-haiku-4-5-20251001"
        llm = _ainvoke
    else:
        model = None

    try:
        raw = await llm(system, user, model=model, caller="web_search/plan_queries")
        content = getattr(raw, "content", raw) if not isinstance(raw, str) else raw
    except Exception as e:  # noqa: BLE001
        logger.warning(f"plan_queries LLM call failed ({e}); falling back to single query")
        return [topic.strip()]

    return _parse_query_list(str(content), fallback=topic.strip(), max_queries=max_queries)


def _parse_query_list(raw: str, fallback: str, max_queries: int) -> list[str]:
    """Best-effort JSON-list extract. Falls back to `[fallback]` when parse fails."""
    text = raw.strip()
    match = re.search(r"\[.*?\]", text, flags=re.DOTALL)
    if match:
        try:
            data = json.loads(match.group(0))
            if isinstance(data, list):
                queries = [str(q).strip() for q in data if str(q).strip()]
                if queries:
                    return queries[:max_queries]
        except json.JSONDecodeError:
            pass
    logger.debug(f"plan_queries: could not parse JSON array from {text[:200]!r}; using fallback")
    return [fallback]


# ---------------------------------------------------------------------------
# Main flow: search → fetch → chunk → dedup → persist
# ---------------------------------------------------------------------------


async def search_and_ingest(
    topic: str,
    job_id: str,
    provider: WebSearchProvider,
    *,
    max_queries: int = _DEFAULT_MAX_QUERIES,
    results_per_query: int = _DEFAULT_MAX_RESULTS_PER_QUERY,
    max_total_chars: int = _DEFAULT_MAX_TOTAL_CHARS,
    license: str = _ACCEPTED_LICENSES_FOR_WEB,
    query_planner=None,
) -> IngestReport:
    """Run one search-agent pass and persist new chunks to upload_store.

    Cost gates:
      - max_queries: hard cap on planned queries (default 5)
      - results_per_query: how many URLs to fetch per query (default 3)
      - max_total_chars: aggregate body-char cap; further pages are
                         skipped once this is exceeded (default 32k)

    Provenance: every persisted chunk carries source="web_search",
    source_url, search_query, retrieved_at. license defaults to
    "unknown" (Serper/wiki results are best-effort; the export
    license_gate will surface these for reviewer approval before
    publishing anything derived from them).
    """
    from vn_agent.assets import dedup, text_ingest, upload_store

    report = IngestReport(topic=topic, provider=getattr(provider, "name", "?"))

    if query_planner is None:
        queries = await plan_queries(topic, max_queries=max_queries)
    else:
        queries = await query_planner(topic, max_queries=max_queries)
    if not queries:
        report.stopped_reason = "empty_result"
        return report
    report.queries = queries

    fresh_chunks: list[AnnotatedSession] = []
    total_chars = 0
    for q in queries:
        try:
            hits = provider.search(q, k=results_per_query)
        except WebSearchError as e:
            report.errors.append(f"search[{q!r}]: {e}")
            continue
        report.hits += len(hits)

        for hit in hits:
            if total_chars >= max_total_chars:
                report.stopped_reason = "char_cap"
                break
            try:
                page = provider.fetch(hit)
            except WebSearchError as e:
                report.errors.append(f"fetch[{hit.url}]: {e}")
                continue

            body = page.body.strip()
            if not body:
                continue
            # Trim the page so any single mega-page can't monopolize the budget.
            take = min(len(body), max_total_chars - total_chars)
            body = body[:take]
            total_chars += len(body)
            report.fetched_pages += 1

            chunks = text_ingest.chunk_text(
                body,
                filename=_url_to_filename(page.url),
                source="web_search",
                license=license,
                source_url=page.url,
                search_query=page.query or q,
            )
            fresh_chunks.extend(chunks)

        if total_chars >= max_total_chars:
            report.stopped_reason = "char_cap"
            break

    report.total_chars_fetched = total_chars
    if not fresh_chunks:
        report.stopped_reason = report.stopped_reason or "empty_result"
        return report

    # Dedup against nothing (fresh set) is fine — dedup_chunks only checks
    # its own accumulator. A future upgrade would seed the DedupIndex from
    # existing per-job uploads so re-runs don't re-persist duplicates; M0
    # keeps it simple.
    kept, dropped = dedup.dedup_chunks(fresh_chunks)
    upload_store.save_chunks(job_id, kept)

    report.chunks_ingested = len(kept)
    report.chunks_deduped = len(dropped)
    if not report.stopped_reason:
        report.stopped_reason = "ok"
    return report


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


_TAG_STRIP_RE = re.compile(r"<[^>]+>")
_WHITESPACE_RE = re.compile(r"[ \t]+")
_MULTI_NEWLINE_RE = re.compile(r"\n{3,}")


def _html_to_text(html: str) -> str:
    """Shallow HTML-to-text stripper.

    Enough for wikipedia/wikia/reddit which dominate the mix; deliberately
    not a full parser to avoid a BeautifulSoup dep for M0. Order matters:
    kill script/style bodies first, then strip remaining tags, then
    normalize whitespace so downstream chunkers see clean prose.
    """
    if not html:
        return ""
    text = re.sub(r"<script[^>]*>.*?</script>", " ", html, flags=re.DOTALL | re.IGNORECASE)
    text = re.sub(r"<style[^>]*>.*?</style>", " ", text, flags=re.DOTALL | re.IGNORECASE)
    text = _TAG_STRIP_RE.sub(" ", text)
    text = text.replace("&nbsp;", " ").replace("&amp;", "&").replace("&lt;", "<").replace("&gt;", ">")
    text = _WHITESPACE_RE.sub(" ", text)
    text = _MULTI_NEWLINE_RE.sub("\n\n", text)
    return text.strip()


def _url_to_filename(url: str) -> str:
    """Short human-readable filename for provenance display. Not filesystem-safe
    on its own — text_ingest normalizes further before hitting disk."""
    stripped = re.sub(r"^https?://", "", url).split("?", 1)[0]
    stripped = stripped.strip("/").replace("/", "-")
    return (stripped[:80] + ".html") if stripped else "web_page.html"
