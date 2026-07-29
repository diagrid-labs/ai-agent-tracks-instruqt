"""Tests for the append-only durability-demo stage ledger."""

from __future__ import annotations

import ledger


def test_record_and_read_round_trip(tmp_path, monkeypatch):
    monkeypatch.setenv("AUDIT_OUTPUT_DIR", str(tmp_path))

    ledger.record_stage("gather_evidence", "dapr/dapr: fetched notes+diff")
    ledger.record_stage("analyze", "left-pad 1.3.0->1.3.1 verdict=block")

    entries = ledger.read_entries()
    assert [e.stage for e in entries] == ["gather_evidence", "analyze"]
    assert entries[1].detail == "left-pad 1.3.0->1.3.1 verdict=block"
    assert entries[0].timestamp  # non-empty ISO timestamp
    assert ledger.count() == 2


def test_count_is_zero_when_file_absent(tmp_path, monkeypatch):
    monkeypatch.setenv("AUDIT_OUTPUT_DIR", str(tmp_path))
    assert ledger.count() == 0
    assert ledger.read_entries() == []


def test_output_dir_defaults_to_audit_out(monkeypatch):
    monkeypatch.delenv("AUDIT_OUTPUT_DIR", raising=False)
    assert ledger.output_dir() == "audit-out"


def test_torn_final_line_is_skipped(tmp_path, monkeypatch):
    monkeypatch.setenv("AUDIT_OUTPUT_DIR", str(tmp_path))
    ledger.record_stage("analyze", "ok")
    # Simulate a hard crash mid-append leaving a partial line.
    with open(tmp_path / "audit-ledger.log", "a", encoding="utf-8") as fh:
        fh.write("2026-07-29T10:00:00Z\tgather")  # no newline, missing detail is fine
        fh.write("\n\x00 torn garbage")           # unparseable trailing line
    entries = ledger.read_entries()
    # The one well-formed line survives; garbage is skipped, no exception.
    assert any(e.stage == "analyze" for e in entries)


def test_detail_tabs_and_newlines_sanitized(tmp_path, monkeypatch):
    monkeypatch.setenv("AUDIT_OUTPUT_DIR", str(tmp_path))
    ledger.record_stage("analyze", "line1\twith\ttabs\nand newline")
    entry = ledger.read_entries()[0]
    assert "\t" not in entry.detail and "\n" not in entry.detail
