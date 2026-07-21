"""Test scaffolding: make dividend_initiation_scanner importable offline.

The scanner imports `requests` and `config` at module load time. In an
offline test environment neither may be present, so provide minimal stubs
(only when the real module is unavailable). No real credentials are ever
introduced here — the stub config carries the harmless placeholder value.
"""
import os
import sys
import types

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if REPO_ROOT not in sys.path:
    sys.path.insert(0, REPO_ROOT)

# Stub `requests` if the real library isn't installed.
if "requests" not in sys.modules:
    try:  # pragma: no cover
        import requests  # noqa: F401
    except ImportError:
        sys.modules["requests"] = types.ModuleType("requests")

# Provide a minimal `config` so top-level `import config as _cfg` succeeds.
if "config" not in sys.modules:
    try:  # pragma: no cover
        import config  # noqa: F401
    except ImportError:
        _cfg = types.ModuleType("config")
        _cfg.EMAIL_SENDER = "placeholder@example.com"
        _cfg.EMAIL_RECIPIENT = "placeholder@example.com"
        _cfg.EMAIL_PASSWORD = ""
        _cfg.FMP_API_KEY = "your_fmp_api_key_here"  # placeholder, not a secret
        sys.modules["config"] = _cfg
