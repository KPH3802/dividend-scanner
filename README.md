# dividend-scanner

**Dividend Signal Scanners** — Live trading signal generators for the Grist Mill Capital Event Alpha sleeve.

This repository contains two complementary FMP-driven scanners that run daily on PythonAnywhere:

1. **DIV_CUT** (`dividend_scanner.py`) — Detects severe dividend cuts; scored 0-5 with backtest-validated factors; Score 3+ wired to IB autotrader.
2. **DIV_INITIATION** (`dividend_initiation_scanner.py`) — Detects first-ever dividend declarations and resumptions after long gaps; scored 0-5 with sector + size factors.

---

## What They Detect

### DIV_CUT (`dividend_scanner.py`)
- Dividend cuts of 20%+ from baseline (4-quarter trailing average)
- Composite scoring (0-5):
  - +1 each: severe cut 75%+, good sector (Industrials/Financial Services/Energy/Technology), bear market regime (SPY -5%+ TTM 60d), Q1 seasonality, cheap entry (<=$15)
  - -1 each: moderate cut (<50%), bad sector (Basic Materials), bull regime (SPY +5%+ TTM 60d), expensive entry (>$30)
- Score 3+ events sent to IB autotrader for automated BUY entry

### DIV_INITIATION (`dividend_initiation_scanner.py`)
- First-ever dividend declarations OR resumptions after multi-year gaps
- Tier-based scoring with sector edge weights:
  - Healthcare +3, Tech / Industrials / Financial Services +2, Comm Svcs / Consumer Defensive / Utilities +1
  - High-yield first dividend (>=14%) bonus
- Filters out ETFs/funds via name regex + FMP `isEtf` / `isFund` flags
- Tier 1 (Score 4+) and Tier 2 (Score 3) reported as actionable; Tier 3 logged for archival

---

## Backtest Performance

### DIV_CUT — 324 events, S&P 500, 1995-2025
| Bucket   | 60d Alpha | Win Rate |
|----------|-----------|----------|
| Score 3+ | +19.65%   | 74.3%    |
| Score 2  | +7.77%    | ~60%     |
| Score 0  | -5.14%    | ~35%     |

Exit rule: 60-day time-based exit only. No stop loss, no profit target.

### DIV_INITIATION — first-ever dividend backtest
- Best edge: First-ever dividend events at 60-day horizon, +2.89% alpha
- Sector concentration: Healthcare and Technology lead the table; small-cap and resumption events show weaker (often negative) edge
- Currently running for data collection and signal accumulation; **not yet wired to IB autotrader** pending forward validation

---

## Architecture

```
dividend_scanner/
    dividend_scanner.py                 # DIV_CUT — daily scan, FMP pull, scoring, email
    dividend_initiation_scanner.py      # DIV_INITIATION — daily scan, history check, scoring, email
    config.py                           # Live credentials (gitignored — never commit)
    config_example.py                   # Template — copy to config.py and fill in values
    dividend_scanner.db                 # DIV_CUT SQLite signal log (gitignored)
    dividend_initiation_scanner.db      # DIV_INITIATION SQLite signal log (gitignored)
    .gitignore                          # Protects config.py and *.db
    README.md
```

---

## FMP API — `/stable/` endpoint set

Both scanners use the **`/stable/`** endpoint family, NOT the deprecated `/api/v3/`. FMP retired v3 endpoints on August 31, 2025; v3 calls now return HTTP 403 with a `Legacy Endpoint` message.

Endpoints used:
- `/stable/dividends-calendar?from={d}&to={d}` — declared dividend calendar
- `/stable/dividends?symbol={t}` — full historical dividend list per ticker (flat array, not `{historical: [...]}` wrapper)
- `/stable/profile?symbol={t}` — sector / market cap / ETF flags
- `/stable/historical-price-eod/full?symbol=SPY` — SPY history for regime calculation (DIV_CUT only)

Response field names follow stable schema (e.g. `marketCap` not `mktCap`, flat dividend list not nested under `historical`).

---

## Setup

```bash
pip install requests
cp config_example.py config.py
# Edit config.py with your credentials (EMAIL_SENDER, EMAIL_PASSWORD, EMAIL_RECIPIENT, FMP_API_KEY)
```

### DIV_CUT
```bash
python3 dividend_scanner.py              # Normal daily scan
python3 dividend_scanner.py --test-email # Send test email
python3 dividend_scanner.py --backfill 30 # Check last 30 days
python3 dividend_scanner.py --status     # Show database stats
```

### DIV_INITIATION
```bash
python3 dividend_initiation_scanner.py <FMP_API_KEY>
# Note: API key is passed as a CLI argument rather than read from config (legacy interface)
# Runtime ~100 minutes due to per-ticker history fetches with 1.5s rate-limit sleep
```

PythonAnywhere schedule:
- DIV_CUT — 23:30 UTC daily
- DIV_INITIATION — 23:45 UTC daily

---

## IB Autotrader Integration

**DIV_CUT** Score 3+ signals trigger a BUY email to the IB autotrader inbox. The autotrader parses the subject line and executes a 5% position with a 60-day time exit and -39.9% catastrophic breaker.

**DIV_INITIATION** is **not wired** to IB autotrader as of the current commit. Signals are logged for forward validation and possible future integration once live edge is confirmed.

---

## Operational Notes

- `dividend_scanner.py` writes to `~/signal_intelligence.db` (`signal_log` table) for centralized signal aggregation.
- `dividend_initiation_scanner.py` runtime is ~100 minutes due to per-ticker FMP rate limiting; output buffered until completion. The script is long-running by design, not stuck.
- Both scripts emit HTML email reports with score-tiered formatting.

---

## Disclaimer

For personal research and educational purposes only. Not financial advice. Use at your own risk.

## License

MIT
