"""SCANNER-HYGIENE (legacy_estate_audit for dividend):
  * add a shared scan_runs heartbeat to BOTH live scanners (Cut + Initiation) — neither
    wrote a shared run-level row, so a dead run was invisible in the cross-scanner monitor;
  * make the dividend_scanner (Cut) per-signal signal_log write failure loud.
"""
import sys
import sqlite3

# dividend_scanner reads config.DB_NAME at import; the conftest stub omits it.
sys.modules["config"].DB_NAME = "test_dividend.db"

import dividend_scanner as ds  # noqa: E402
import dividend_initiation_scanner as di  # noqa: E402


def test_ds_log_scan_run_writes_one_row(tmp_path):
    db = tmp_path / "intel.db"
    ds.log_scan_run("DIV_CUT", "OK", 7, 1, note="x", db_path=str(db))
    rows = sqlite3.connect(str(db)).execute(
        "SELECT scanner, source_status, n_evaluated, n_fired, note FROM scan_runs").fetchall()
    assert rows == [("DIV_CUT", "OK", 7, 1, "x")]


def test_ds_log_scan_run_loud(capsys):
    ds.log_scan_run("DIV_CUT", "OK", 1, 0, db_path="/does/not/exist/nope/intel.db")
    assert "[SCAN_RUN_FAIL]" in capsys.readouterr().out


def test_ds_signal_log_loud(monkeypatch, capsys):
    monkeypatch.setattr(ds.os.path, "expanduser",
                        lambda p: "/does/not/exist/nope/signal_intelligence.db")
    ds.log_signal_intelligence("2026-07-22", "DIV_CUT", "ABC", "BUY", 1)
    out = capsys.readouterr().out
    assert "[SIGNAL_LOG_FAIL]" in out and "DIV_CUT" in out and "ABC" in out


def test_di_log_scan_run_writes_one_row(tmp_path):
    db = tmp_path / "intel2.db"
    di.log_scan_run("DIV_INITIATION", "OK", 9, 3, note="y", db_path=str(db))
    rows = sqlite3.connect(str(db)).execute(
        "SELECT scanner, source_status, n_evaluated, n_fired, note FROM scan_runs").fetchall()
    assert rows == [("DIV_INITIATION", "OK", 9, 3, "y")]


def test_di_log_scan_run_loud(capsys):
    di.log_scan_run("DIV_INITIATION", "OK", 1, 0, db_path="/does/not/exist/nope/intel.db")
    assert "[SCAN_RUN_FAIL]" in capsys.readouterr().out
