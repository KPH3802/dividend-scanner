"""Merged from PA production drift (2026-07-22): the live div-init scanner logged
each detected initiation to the shared signal_intelligence.db. Adopt that behavior,
but keep the repo's A13 key handling (config/env, never the command line) — do NOT
adopt the live script's ``sys.argv[1]`` key.

These tests assert both halves of that reconciliation.
"""
import dividend_initiation_scanner as div


def test_signal_log_failure_is_printed(capsys, monkeypatch):
    # A failed signal_log write must surface, not be swallowed.
    monkeypatch.setattr(div.os.path, "expanduser",
                        lambda p: "/does/not/exist/nope/signal_intelligence.db")
    div.log_signal_intelligence("2026-07-22", "DIV_INITIATION", "ABC", "BUY", 1)
    out = capsys.readouterr().out
    assert "[SIGNAL_LOG_FAIL]" in out
    assert "DIV_INITIATION" in out and "ABC" in out


def test_key_handling_stays_off_the_command_line():
    # A13: the reconciliation must NOT regress to reading the key from argv.
    assert hasattr(div, "get_api_key"), "get_api_key() must remain (A13 token-strip)"
    src = open(div.__file__).read()
    assert "api_key = sys.argv[1]" not in src, "key must not come from the command line"
