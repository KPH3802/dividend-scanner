# dividend-scanner

**Dividend Cut Signal Scanner** -- Live trading signal generator for the Grist Mill Capital Event Alpha sleeve.

Runs daily on PythonAnywhere. Detects dividend cuts from the FMP dividend calendar, scores each cut using a validated 5-factor composite system, and sends color-coded email alerts. Score 3+ alerts are wired to the IB autotrader for automated execution.

---

## What It Detects

- Dividend cuts of 20%+ from baseline (4-quarter trailing average)
- Composite scoring (0-5 scale) built from backtest-validated factors:
  - Severe cut (75%+): +1
  - Positive sector (Industrials, Financial Services, Energy, Technology): +1
  - Bear market regime (SPY -5%+ trailing 60d): +1
  - Q1 seasonality: +1
  - Cheap entry price (<=15): +1
  - Moderate cut (<50%): -1 (red flag)
  - Negative sector (Basic Materials): -1
  - Bull market regime (SPY +5%+ trailing 60d): -1
  - Expensive entry price (>30): -1
- Score 3+ events sent to IB autotrader for automated BUY entry

---

## Backtest Performance

Validated on 324 events, S&P 500 universe, 1995-2025.

| Bucket   | 60d Alpha | Win Rate |
|----------|-----------|----------|
| Score 3+ | +19.65%   | 74.3%    |
| Score 2  | +7.77%    | ~60%     |
| Score 0  | -5.14%    | ~35%     |

Exit rule: 60-day time-based exit only. No stop loss, no profit target. Derived from backtest: holding full 60 days beats every early-exit threshold.

---

## Architecture

```
dividend_scanner/
    dividend_scanner.py     # Main scanner -- FMP pull, cut detection, scoring, email
    config.py               # Live credentials (gitignored -- never commit)
    config_example.py       # Template -- copy to config.py and fill in values
    dividend_scanner.db     # SQLite signal log (gitignored)
```

---

## Setup

```bash
pip install requests
cp config_example.py config.py
# Edit config.py with your credentials

python3 dividend_scanner.py              # Normal daily scan
python3 dividend_scanner.py --test-email # Send test email
python3 dividend_scanner.py --backfill 30 # Check last 30 days
python3 dividend_scanner.py --status     # Show database stats
```

Schedule on PythonAnywhere at 23:30 UTC daily (Mon-Fri).

---

## IB Autotrader Integration

Score 3+ signals trigger a BUY email to the IB autotrader inbox. The autotrader parses the subject line and executes a 5% position with a 60-day time exit and -39.9% catastrophic breaker.

---

## Disclaimer

For personal research and educational purposes only. Not financial advice.

## License

MIT
