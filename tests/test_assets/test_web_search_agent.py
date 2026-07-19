"""P0-5 unit tests: web search agent (query planning + search + ingest)."""
from __future__ import annotations

import pytest

from vn_agent.assets import upload_store, web_search_agent
from vn_agent.assets.web_search_agent import (
    FetchedPage,
    IngestReport,
    SearchResult,
    StaticFixtureProvider,
    WebSearchError,
)


@pytest.fixture(autouse=True)
def _iso_upload_root(tmp_path, monkeypatch):
    monkeypatch.setenv(upload_store._DATA_UPLOAD_ROOT_ENV, str(tmp_path / "uploads"))
    yield


# ── plan_queries ────────────────────────────────────────────────────────────


class TestPlanQueries:
    @pytest.mark.asyncio
    async def test_empty_topic_returns_empty(self):
        assert await web_search_agent.plan_queries("") == []
        assert await web_search_agent.plan_queries("   ") == []

    @pytest.mark.asyncio
    async def test_llm_returns_list(self):
        async def fake_llm(system, user, **kw):  # noqa: ARG001
            return '["query one", "query two", "query three"]'
        out = await web_search_agent.plan_queries("Edo period", llm=fake_llm)
        assert out == ["query one", "query two", "query three"]

    @pytest.mark.asyncio
    async def test_max_queries_enforced(self):
        async def fake_llm(system, user, **kw):  # noqa: ARG001
            return '["a", "b", "c", "d", "e", "f", "g"]'
        out = await web_search_agent.plan_queries("topic", max_queries=3, llm=fake_llm)
        assert out == ["a", "b", "c"]

    @pytest.mark.asyncio
    async def test_llm_content_wrapped_object(self):
        # Simulates a langchain-style response with .content
        class Msg:
            content = 'prose ["only these", "count"] trailing'
        async def fake_llm(system, user, **kw):  # noqa: ARG001
            return Msg()
        out = await web_search_agent.plan_queries("topic", llm=fake_llm)
        assert out == ["only these", "count"]

    @pytest.mark.asyncio
    async def test_llm_parse_failure_falls_back(self):
        async def fake_llm(system, user, **kw):  # noqa: ARG001
            return "sorry, no queries today"
        out = await web_search_agent.plan_queries("shrine gardens", llm=fake_llm)
        assert out == ["shrine gardens"]

    @pytest.mark.asyncio
    async def test_llm_exception_falls_back(self):
        async def fake_llm(system, user, **kw):  # noqa: ARG001
            raise RuntimeError("network down")
        out = await web_search_agent.plan_queries("topic", llm=fake_llm)
        assert out == ["topic"]


# ── StaticFixtureProvider ──────────────────────────────────────────────────


class TestStaticFixtureProvider:
    def test_search_matches_by_substring(self):
        provider = StaticFixtureProvider(
            search_map={
                "edo": [SearchResult(url="https://x/edo1", title="Edo Life", snippet="s")],
                "meiji": [SearchResult(url="https://x/meiji1", title="Meiji", snippet="s")],
            },
            body_map={"https://x/edo1": "body"},
        )
        hits = provider.search("Edo period gardens")
        assert len(hits) == 1
        assert hits[0].url == "https://x/edo1"
        assert hits[0].query == "Edo period gardens"

    def test_search_no_match_returns_empty(self):
        provider = StaticFixtureProvider(
            search_map={"edo": [SearchResult(url="https://x/edo1", title="t", snippet="s")]},
        )
        assert provider.search("modern Tokyo") == []

    def test_fetch_missing_body_raises(self):
        provider = StaticFixtureProvider(
            search_map={},
            body_map={},
        )
        hit = SearchResult(url="https://x/none", title="t", snippet="s")
        with pytest.raises(WebSearchError):
            provider.fetch(hit)

    def test_fetch_returns_page(self):
        provider = StaticFixtureProvider(
            search_map={},
            body_map={"https://x/y": "hello world"},
        )
        hit = SearchResult(url="https://x/y", title="T", snippet="s", query="q")
        page = provider.fetch(hit)
        assert page.body == "hello world"
        assert page.query == "q"


# ── search_and_ingest ──────────────────────────────────────────────────────


def _fixture_provider() -> StaticFixtureProvider:
    return StaticFixtureProvider(
        search_map={
            "edo": [
                SearchResult(url="https://wiki/edo", title="Edo period", snippet="s", rank=0),
                SearchResult(url="https://wiki/meirin", title="Meirin school", snippet="s", rank=1),
            ],
            "sakura": [
                SearchResult(url="https://wiki/sakura", title="Cherry blossom", snippet="s", rank=0),
            ],
        },
        body_map={
            "https://wiki/edo": "The Edo period lasted from 1603 to 1867. Culture flourished under sakoku.",
            "https://wiki/meirin": "Meirin, or 'moral learning', was a Confucian pillar of Edo schooling.",
            "https://wiki/sakura": "The cherry blossom is a metaphor for the ephemerality of life.",
        },
    )


class TestSearchAndIngest:
    @pytest.mark.asyncio
    async def test_end_to_end_persists_chunks(self):
        provider = _fixture_provider()
        report = await web_search_agent.search_and_ingest(
            topic="Edo period culture",
            job_id="job-1",
            provider=provider,
            query_planner=_planner(["edo culture", "sakura symbolism"]),
        )
        assert report.stopped_reason == "ok"
        assert report.hits >= 1
        assert report.fetched_pages >= 1
        assert report.chunks_ingested >= 1

        # Chunks land in upload_store with web_search provenance.
        chunks = upload_store.load_chunks("job-1")
        assert chunks
        assert all(c.scope == "user_upload" for c in chunks)
        assert all(c.source_meta["source"] == "web_search" for c in chunks)
        assert all("source_url" in c.source_meta for c in chunks)
        assert all("search_query" in c.source_meta for c in chunks)

    @pytest.mark.asyncio
    async def test_char_cap_stops_early(self):
        # Force a tiny cap so the first page trips it.
        provider = _fixture_provider()
        report = await web_search_agent.search_and_ingest(
            topic="Edo period",
            job_id="job-cap",
            provider=provider,
            query_planner=_planner(["edo"]),
            max_total_chars=50,   # smaller than any single body
        )
        assert report.stopped_reason == "char_cap"
        assert report.total_chars_fetched <= 50

    @pytest.mark.asyncio
    async def test_empty_query_plan_bails(self):
        report = await web_search_agent.search_and_ingest(
            topic="anything",
            job_id="job-empty",
            provider=_fixture_provider(),
            query_planner=_planner([]),
        )
        assert report.stopped_reason == "empty_result"
        assert report.chunks_ingested == 0

    @pytest.mark.asyncio
    async def test_provider_search_error_is_recorded(self):
        class BustedProvider(StaticFixtureProvider):
            def search(self, query: str, k: int = 3):
                raise WebSearchError("quota exceeded")

        report = await web_search_agent.search_and_ingest(
            topic="topic",
            job_id="job-err",
            provider=BustedProvider(),
            query_planner=_planner(["q1"]),
        )
        assert report.hits == 0
        assert any("quota exceeded" in e for e in report.errors)
        assert report.stopped_reason == "empty_result"

    @pytest.mark.asyncio
    async def test_dedup_across_queries(self):
        # Two different queries surface the SAME URL — same body → dedup collapses.
        provider = StaticFixtureProvider(
            search_map={
                "alpha": [SearchResult(url="https://x/same", title="t", snippet="s")],
                "beta":  [SearchResult(url="https://x/same", title="t", snippet="s")],
            },
            body_map={"https://x/same": "Identical body content that repeats across queries."},
        )
        report = await web_search_agent.search_and_ingest(
            topic="tt",
            job_id="job-dedup",
            provider=provider,
            query_planner=_planner(["alpha", "beta"]),
        )
        # Both hits fetched, but the second's chunks fold into the first via dedup.
        assert report.chunks_deduped >= 1


# ── HTML → text ────────────────────────────────────────────────────────────


class TestHtmlToText:
    def test_removes_script_and_style(self):
        html = "<html><head><style>a{}</style></head><body>Hello<script>evil()</script></body></html>"
        out = web_search_agent._html_to_text(html)
        assert "evil" not in out
        assert "a{}" not in out
        assert "Hello" in out

    def test_normalizes_entities(self):
        assert "AT&T" in web_search_agent._html_to_text("<p>AT&amp;T</p>")

    def test_empty_input_safe(self):
        assert web_search_agent._html_to_text("") == ""


# ── URL → filename ─────────────────────────────────────────────────────────


class TestUrlToFilename:
    def test_https_stripped(self):
        assert web_search_agent._url_to_filename("https://en.wikipedia.org/wiki/Sakura").startswith(
            "en.wikipedia.org-wiki-Sakura"
        )

    def test_empty_url_gets_placeholder(self):
        assert web_search_agent._url_to_filename("").endswith(".html")


# ── SerperProvider guardrails ──────────────────────────────────────────────


class TestSerperProvider:
    def test_missing_api_key_raises_with_actionable_message(self, monkeypatch):
        monkeypatch.delenv("SERPER_API_KEY", raising=False)
        with pytest.raises(WebSearchError) as exc:
            web_search_agent.SerperProvider()
        assert "SERPER_API_KEY" in str(exc.value)


# ── Gemini stub ────────────────────────────────────────────────────────────


class TestGeminiGroundingStub:
    def test_search_raises_actionable(self):
        with pytest.raises(WebSearchError) as exc:
            web_search_agent.GeminiGroundingProvider().search("x")
        assert "M0" in str(exc.value)


# ── Helpers ────────────────────────────────────────────────────────────────


def _planner(queries: list[str]):
    """Test-only planner that returns a fixed list without touching an LLM."""
    async def _plan(topic, max_queries=5):  # noqa: ARG001
        return list(queries[:max_queries])
    return _plan
