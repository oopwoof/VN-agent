"""P0-4 unit tests: license gate."""
from __future__ import annotations

import json
from pathlib import Path

import pytest

from vn_agent.assets import license_gate, text_ingest


class TestNormalize:
    def test_canonical_forms_pass_through(self):
        for lic in ["CC0", "CC-BY", "CC-BY-SA", "user_owned", "derived"]:
            assert license_gate._normalize_license(lic) == lic

    def test_case_insensitive(self):
        assert license_gate._normalize_license("cc0") == "CC0"
        assert license_gate._normalize_license("cc-by") == "CC-BY"
        assert license_gate._normalize_license("USER_OWNED") == "user_owned"

    def test_common_variants(self):
        assert license_gate._normalize_license("CC0-1.0") == "CC0"
        assert license_gate._normalize_license("cc-by-4.0") == "CC-BY"
        assert license_gate._normalize_license("public domain") == "CC0"

    def test_unknown_returns_unknown(self):
        assert license_gate._normalize_license("") == "unknown"
        assert license_gate._normalize_license(None) == "unknown"
        assert license_gate._normalize_license("MyCustomLicense") == "unknown"
        assert license_gate._normalize_license("GPL-3.0") == "unknown"


class TestAuditUploads:
    def test_all_accepted(self):
        chunks = [
            *text_ingest.chunk_text("A.", "a.md", license="user_owned"),
            *text_ingest.chunk_text("B.", "b.md", license="CC-BY"),
        ]
        report = license_gate.audit(upload_chunks=chunks)
        assert report.ok is True
        assert report.total == 2
        assert report.accepted == 2
        assert report.by_license == {"user_owned": 1, "CC-BY": 1}

    def test_unknown_license_flagged(self):
        chunks = [
            *text_ingest.chunk_text("A.", "a.md", license="user_owned"),
            *text_ingest.chunk_text("B.", "b.md", license="MyCustomLicense"),
        ]
        report = license_gate.audit(upload_chunks=chunks)
        assert report.ok is False
        assert len(report.violations) == 1
        v = report.violations[0]
        assert v.identifier == "b.md"
        assert v.license == "MyCustomLicense"

    def test_web_search_chunk_flagged_by_source(self):
        chunks = text_ingest.chunk_text(
            "Wiki excerpt.",
            "wiki.html",
            source="web_search",
            license="unknown",
            source_url="https://x/y",
        )
        report = license_gate.audit(upload_chunks=chunks)
        assert report.ok is False
        assert report.violations[0].source == "web_search"
        # For web_search, identifier prefers filename (present) then falls to URL.
        assert report.violations[0].identifier == "wiki.html"

    def test_dict_input_accepted(self):
        # Callers passing raw dicts (e.g. from JSONL) should also work.
        chunks = [{"source_meta": {"license": "CC0", "filename": "x.md", "source": "user_upload"}}]
        report = license_gate.audit(upload_chunks=chunks)
        assert report.ok is True
        assert report.by_license == {"CC0": 1}


class TestAuditLibraryHits:
    def test_reads_jsonl(self, tmp_path):
        p = tmp_path / "library_hits.jsonl"
        p.write_text("\n".join([
            json.dumps({"asset_id": "bg_school", "license": "CC0"}),
            json.dumps({"asset_id": "bg_forest", "license": "CC-BY"}),
            json.dumps({"asset_id": "bg_odd", "license": "GPL-2.0"}),
        ]), encoding="utf-8")
        report = license_gate.audit(library_hits_path=p)
        assert report.total == 3
        assert report.accepted == 2
        assert len(report.violations) == 1
        assert report.violations[0].identifier == "bg_odd"

    def test_missing_file_treated_as_empty(self, tmp_path):
        report = license_gate.audit(library_hits_path=tmp_path / "nonexistent.jsonl")
        assert report.total == 0
        assert report.ok is True

    def test_corrupt_line_skipped(self, tmp_path):
        p = tmp_path / "library_hits.jsonl"
        p.write_text("not json\n" + json.dumps({"asset_id": "ok", "license": "CC0"}), encoding="utf-8")
        report = license_gate.audit(library_hits_path=p)
        assert report.total == 1
        assert report.accepted == 1


class TestCombined:
    def test_uploads_and_library_combined(self, tmp_path):
        chunks = text_ingest.chunk_text("A.", "a.md", license="CC-BY")
        p = tmp_path / "library_hits.jsonl"
        p.write_text(json.dumps({"asset_id": "bg1", "license": "CC0"}), encoding="utf-8")
        report = license_gate.audit(upload_chunks=chunks, library_hits_path=p)
        assert report.total == 2
        assert report.accepted == 2
        assert report.by_license == {"CC-BY": 1, "CC0": 1}


class TestEnforce:
    def test_pass_returns_report(self):
        chunks = text_ingest.chunk_text("A.", "a.md", license="CC0")
        report = license_gate.enforce(upload_chunks=chunks)
        assert report.ok is True

    def test_fail_raises(self):
        chunks = text_ingest.chunk_text("A.", "a.md", license="GPL")
        with pytest.raises(license_gate.LicenseGateError) as exc_info:
            license_gate.enforce(upload_chunks=chunks)
        # Error message includes the violating identifier for actionability.
        assert "a.md" in str(exc_info.value)
        assert "GPL" in str(exc_info.value)


class TestReportSummary:
    def test_summary_format_readable(self):
        chunks = [
            *text_ingest.chunk_text("A.", "a.md", license="CC-BY"),
            *text_ingest.chunk_text("B.", "b.md", license="Unknown"),
        ]
        report = license_gate.audit(upload_chunks=chunks)
        s = report.summary()
        assert "License audit" in s
        assert "1/2" in s or "2/2" in s  # tolerant to counter order
        assert "b.md" in s
