"""A13 token-strip: the FMP API key must be read from config/env, never from
the task command line.

These tests pin the contract that `dividend_initiation_scanner` resolves its
FMP API key through `get_api_key()` (config-sourced, env-fallback baked into
config) and rejects an unconfigured/placeholder key with a clear error. No
key value is ever placed on argv.
"""
import types

import dividend_initiation_scanner as scanner


def _fake_cfg(value):
    m = types.ModuleType("config")
    m.FMP_API_KEY = value
    return m


def test_get_api_key_reads_from_config():
    cfg = _fake_cfg("REALKEY1234567890REALKEY12345678")
    assert scanner.get_api_key(cfg=cfg) == "REALKEY1234567890REALKEY12345678"


def test_get_api_key_rejects_placeholder():
    cfg = _fake_cfg("your_fmp_api_key_here")
    try:
        scanner.get_api_key(cfg=cfg)
    except SystemExit as e:
        # error message must not be empty and must not echo a key
        assert "FMP_API_KEY" in str(e)
    else:
        raise AssertionError("placeholder key should raise SystemExit")


def test_get_api_key_rejects_empty():
    for empty in ("", "   ", None):
        cfg = _fake_cfg(empty)
        try:
            scanner.get_api_key(cfg=cfg)
        except SystemExit:
            pass
        else:
            raise AssertionError("empty key should raise SystemExit")


def test_main_does_not_require_token_on_argv(monkeypatch):
    """main() must resolve the key via get_api_key(), not sys.argv[1]."""
    captured = {}

    def fake_get_api_key(cfg=None):
        captured["called"] = True
        return "REALKEY1234567890REALKEY12345678"

    # Stop execution right after key resolution so we don't hit the network.
    class _Stop(Exception):
        pass

    def boom(*a, **k):
        raise _Stop()

    monkeypatch.setattr(scanner, "get_api_key", fake_get_api_key)
    monkeypatch.setattr(scanner, "init_database", boom)
    monkeypatch.setattr(scanner.sys, "argv", ["dividend_initiation_scanner.py"])

    try:
        scanner.main()
    except _Stop:
        pass
    assert captured.get("called") is True
