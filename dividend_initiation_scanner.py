#!/usr/bin/env python3
"""
Dividend Initiation Scanner — Live Daily Scanner
=================================================
Detects FIRST-EVER dividend initiations from S&P 500 universe.
Scores each initiation based on backtested edge factors.
Stores all events in SQLite. Sends HTML email alerts.

Backtested Edge (n=229, updated Feb 14 2026):
  First-ever initiations: +2.89% alpha at 60d (p=0.009)
  Resumptions: NO edge (flat across all windows)
  
Key scoring factors from backtest:
  - First-ever only (resumptions filtered out)
  - High initial dividend >= $0.14 (all windows significant)
  - Target sectors: Healthcare, Tech, Industrials, FinServices
  - Bull market regime enhances signal
  - 2000s/2020s decades show strongest alpha

Schedule: PythonAnywhere 23:30 UTC daily
Usage:   python3 dividend_initiation_scanner.py <FMP_API_KEY>

FMP Endpoints Used:
  - /stable/dividends-calendar (recent dividend declarations)
  - /stable/dividends (for dividend history check)
  - /stable/profile (for sector data)
"""

import sys
import os
import json
import sqlite3
import smtplib
import requests
import time
from datetime import datetime, timedelta
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart

# ============================================================
# CONFIGURATION
# ============================================================
FMP_BASE = "https://financialmodelingprep.com/stable"
DB_FILE = "/home/KPH3802/dividend_scanner/dividend_initiation_scanner.db"
SLEEP_BETWEEN_CALLS = 1.5  # seconds between FMP API calls

# Email config — sourced from config.py (gitignored, never committed)
import config as _cfg
EMAIL_FROM     = _cfg.EMAIL_SENDER
EMAIL_TO       = _cfg.EMAIL_RECIPIENT
EMAIL_PASSWORD = _cfg.EMAIL_PASSWORD

# Scoring thresholds from backtest
HIGH_DIVIDEND_THRESHOLD = 0.14  # median split from backtest
TARGET_SECTORS = {
    "Healthcare": 3,       # 20d +4.23% p=0.017, 73% WR
    "Technology": 2,       # 5d +1.55% p=0.043, 40d +3.20% p=0.024
    "Industrials": 2,      # 40d +4.42% p=0.088
    "Financial Services": 2,  # 60d +7.04% p=0.036
    "Communication Services": 1,  # 60d +5.58% (small n=9)
    "Consumer Defensive": 1,  # 60d +4.55% (small n=8)
    "Utilities": 1,        # 20d +6.62% (small n=10, but large)
}

# ETF/Fund filters — exclude non-individual stocks
ETF_FUND_KEYWORDS = [
    "ETF", "Fund", "Trust", "Index", "Portfolio", "ProShares",
    "Direxion", "iShares", "SPDR", "Vanguard", "Schwab",
    "Invesco", "WisdomTree", "VanEck", "Global X", "First Trust",
    "ARK ", "PIMCO", "Nuveen", "BlackRock", "JPMorgan",
    "Fidelity", "T. Rowe", "American Century", "Franklin",
]

# S&P 500 universe (same approach as other scanners — hardcoded fallback)
# We scan the dividend calendar broadly, then filter
SCAN_DAYS_BACK = 7  # Look at dividends declared in last 7 days
SCAN_DAYS_FORWARD = 30  # And upcoming 30 days


def init_database():
    """Initialize SQLite database for storing initiation events."""
    conn = sqlite3.connect(DB_FILE)
    c = conn.cursor()

    c.execute("""
        CREATE TABLE IF NOT EXISTS initiations (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            ticker TEXT NOT NULL,
            detected_date TEXT NOT NULL,
            declaration_date TEXT,
            ex_date TEXT,
            payment_date TEXT,
            dividend_amount REAL,
            frequency TEXT,
            sector TEXT,
            market_cap REAL,
            company_name TEXT,
            event_type TEXT,
            score INTEGER DEFAULT 0,
            score_details TEXT,
            is_first_ever INTEGER DEFAULT 0,
            prior_dividend_history TEXT,
            created_at TEXT DEFAULT CURRENT_TIMESTAMP,
            UNIQUE(ticker, ex_date)
        )
    """)

    c.execute("""
        CREATE TABLE IF NOT EXISTS scan_log (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            scan_date TEXT NOT NULL,
            dividends_checked INTEGER DEFAULT 0,
            initiations_found INTEGER DEFAULT 0,
            first_ever_found INTEGER DEFAULT 0,
            errors TEXT,
            duration_seconds REAL,
            created_at TEXT DEFAULT CURRENT_TIMESTAMP
        )
    """)

    conn.commit()
    return conn


def fetch_dividend_calendar(api_key, from_date, to_date):
    """Fetch dividend calendar from FMP for date range."""
    url = f"{FMP_BASE}/dividends-calendar"
    params = {
        "from": from_date,
        "to": to_date,
        "apikey": api_key
    }
    try:
        resp = requests.get(url, params=params, timeout=30)
        resp.raise_for_status()
        data = resp.json()
        if isinstance(data, list):
            return data
        return []
    except Exception as e:
        print(f"  ERROR fetching dividend calendar: {e}")
        return []


def fetch_dividend_history(ticker, api_key):
    """Fetch full dividend history for a ticker to check if first-ever.

    Stable endpoint returns a flat list of dividend records (one per ex-date),
    not the {historical: [...]} wrapper that v3 used.
    """
    url = f"{FMP_BASE}/dividends"
    params = {"symbol": ticker, "apikey": api_key}
    try:
        resp = requests.get(url, params=params, timeout=30)
        resp.raise_for_status()
        data = resp.json()
        if isinstance(data, list):
            return data
        return []
    except Exception as e:
        print(f"    {ticker} dividend history error: {e}")
        return []


def fetch_company_profile(ticker, api_key):
    """Fetch company profile for sector and market cap.

    Stable endpoint takes ?symbol= query param instead of /{ticker} path.
    """
    url = f"{FMP_BASE}/profile"
    params = {"symbol": ticker, "apikey": api_key}
    try:
        resp = requests.get(url, params=params, timeout=30)
        resp.raise_for_status()
        data = resp.json()
        if isinstance(data, list) and len(data) > 0:
            return data[0]
        return {}
    except Exception as e:
        print(f"    {ticker} profile error: {e}")
        return {}


def is_etf_or_fund(name, ticker):
    """Filter out ETFs, funds, and non-individual stocks."""
    if not name:
        return False
    name_upper = name.upper()
    for kw in ETF_FUND_KEYWORDS:
        if kw.upper() in name_upper:
            return True
    # Additional pattern checks
    if len(ticker) > 5:  # Most ETFs have longer tickers
        return True
    return False


def detect_frequency(history):
    """Detect dividend frequency from history."""
    if len(history) < 2:
        return "Unknown"

    # Sort by date descending
    sorted_hist = sorted(history, key=lambda x: x.get("date", ""), reverse=True)

    # Calculate average gap between recent dividends
    gaps = []
    for i in range(min(4, len(sorted_hist) - 1)):
        try:
            d1 = datetime.strptime(sorted_hist[i]["date"], "%Y-%m-%d")
            d2 = datetime.strptime(sorted_hist[i + 1]["date"], "%Y-%m-%d")
            gaps.append((d1 - d2).days)
        except (ValueError, KeyError):
            continue

    if not gaps:
        return "Unknown"

    avg_gap = sum(gaps) / len(gaps)

    if avg_gap < 45:
        return "Monthly"
    elif avg_gap < 120:
        return "Quarterly"
    elif avg_gap < 250:
        return "Semi-Annual"
    else:
        return "Annual"


def classify_initiation(history, current_div):
    """
    Classify whether this is a first-ever initiation or a resumption.
    Returns: (event_type, gap_years, prior_last_date)
    """
    if not history or len(history) == 0:
        return "first_ever", None, None

    # Current dividend date
    try:
        current_date = datetime.strptime(
            current_div.get("date") or current_div.get("exDate", ""),
            "%Y-%m-%d"
        )
    except (ValueError, TypeError):
        return "first_ever", None, None

    # Sort history by date, exclude current
    current_str = current_date.strftime("%Y-%m-%d")
    prior = [
        h for h in history
        if h.get("date", "") < current_str
    ]

    if not prior:
        return "first_ever", None, None

    # Has prior dividends — this is a resumption if there was a gap
    prior_sorted = sorted(prior, key=lambda x: x.get("date", ""), reverse=True)
    last_prior_date_str = prior_sorted[0].get("date", "")

    try:
        last_prior = datetime.strptime(last_prior_date_str, "%Y-%m-%d")
        gap_days = (current_date - last_prior).days

        # If gap > 2 years, it's a resumption (long gap)
        # If gap <= 2 years, it's just a regular dividend (not an initiation)
        if gap_days > 730:  # > 2 years
            gap_years = round(gap_days / 365.25, 1)
            return "resumption", gap_years, last_prior_date_str
        else:
            # Not an initiation at all — regular ongoing dividend
            return "regular", None, None
    except (ValueError, TypeError):
        return "first_ever", None, None


def get_market_regime():
    """
    Determine current market regime (bull/bear/neutral).
    Uses SPY 200-day SMA approach.
    """
    try:
        import yfinance as yf
        spy = yf.Ticker("SPY")
        hist = spy.history(period="1y")
        if len(hist) < 200:
            return "unknown"

        current_price = hist['Close'].iloc[-1]
        sma_200 = hist['Close'].rolling(200).mean().iloc[-1]

        if current_price > sma_200 * 1.05:
            return "bull"
        elif current_price < sma_200 * 0.95:
            return "bear"
        else:
            return "neutral"
    except Exception:
        return "unknown"


def score_initiation(event_type, sector, dividend_amount, market_regime):
    """
    Score an initiation based on backtested factors.
    Higher score = stronger expected alpha.

    Returns: (total_score, details_dict)
    """
    score = 0
    details = {}

    # Factor 1: Event type (MUST be first_ever for any score)
    if event_type != "first_ever":
        details["event_type"] = "RESUMPTION — no edge (0 pts)"
        return 0, details
    else:
        score += 1
        details["event_type"] = "First-ever initiation (+1)"

    # Factor 2: Sector bonus
    sector_bonus = TARGET_SECTORS.get(sector, 0)
    if sector_bonus > 0:
        score += sector_bonus
        details["sector"] = f"{sector} (+{sector_bonus})"
    else:
        details["sector"] = f"{sector} (0 — no backtested edge)"

    # Factor 3: High initial dividend
    if dividend_amount and dividend_amount >= HIGH_DIVIDEND_THRESHOLD:
        score += 2
        details["dividend_size"] = f"${dividend_amount:.4f} >= $0.14 threshold (+2)"
    elif dividend_amount:
        details["dividend_size"] = f"${dividend_amount:.4f} < $0.14 threshold (0)"
    else:
        details["dividend_size"] = "Unknown amount (0)"

    # Factor 4: Market regime
    if market_regime == "bull":
        score += 1
        details["market_regime"] = "Bull market (+1)"
    elif market_regime == "bear":
        score += 1  # Bear also showed strong alpha (10d +2.88% p=0.022)
        details["market_regime"] = "Bear market (+1)"
    else:
        details["market_regime"] = f"{market_regime} (0)"

    return score, details


def build_html_email(initiations, scan_stats):
    """Build color-coded HTML email report."""
    today = datetime.now().strftime("%Y-%m-%d")

    # Separate first-ever from resumptions
    first_ever = [i for i in initiations if i["event_type"] == "first_ever"]
    resumptions = [i for i in initiations if i["event_type"] == "resumption"]

    html = f"""
    <html>
    <head>
        <style>
            body {{ font-family: 'Segoe UI', Arial, sans-serif; margin: 20px; background: #f5f5f5; }}
            .container {{ max-width: 800px; margin: 0 auto; background: white; padding: 20px; border-radius: 8px; box-shadow: 0 2px 4px rgba(0,0,0,0.1); }}
            h1 {{ color: #1a5276; border-bottom: 3px solid #2ecc71; padding-bottom: 10px; }}
            h2 {{ color: #2c3e50; margin-top: 25px; }}
            .stats {{ background: #eaf2f8; padding: 12px; border-radius: 6px; margin: 15px 0; font-size: 14px; }}
            .signal-high {{ background: #d4efdf; border-left: 5px solid #27ae60; padding: 15px; margin: 12px 0; border-radius: 4px; }}
            .signal-med {{ background: #fef9e7; border-left: 5px solid #f39c12; padding: 15px; margin: 12px 0; border-radius: 4px; }}
            .signal-low {{ background: #fbeee6; border-left: 5px solid #e67e22; padding: 15px; margin: 12px 0; border-radius: 4px; }}
            .signal-info {{ background: #f2f4f4; border-left: 5px solid #95a5a6; padding: 15px; margin: 12px 0; border-radius: 4px; }}
            .ticker {{ font-size: 20px; font-weight: bold; color: #1a5276; }}
            .score {{ display: inline-block; padding: 3px 10px; border-radius: 12px; font-weight: bold; font-size: 13px; }}
            .score-high {{ background: #27ae60; color: white; }}
            .score-med {{ background: #f39c12; color: white; }}
            .score-low {{ background: #e67e22; color: white; }}
            .detail {{ font-size: 13px; color: #555; margin: 4px 0; }}
            .backtest-ref {{ font-size: 12px; color: #888; margin-top: 8px; font-style: italic; }}
            .no-signals {{ color: #7f8c8d; font-style: italic; padding: 20px; text-align: center; }}
            .footer {{ font-size: 11px; color: #aaa; margin-top: 30px; text-align: center; border-top: 1px solid #eee; padding-top: 10px; }}
        </style>
    </head>
    <body>
    <div class="container">
        <h1>Dividend Initiation Scanner — {today}</h1>

        <div class="stats">
            Dividends checked: {scan_stats['checked']} |
            Initiations detected: {scan_stats['initiations']} |
            First-ever: {scan_stats['first_ever']} |
            Resumptions: {scan_stats['resumptions']} |
            Runtime: {scan_stats['duration']:.1f}s
        </div>
    """

    # FIRST-EVER INITIATIONS (the tradeable signal)
    if first_ever:
        html += "<h2>FIRST-EVER INITIATIONS (Tradeable Signal)</h2>"
        html += '<p class="backtest-ref">Backtest: n=166, 20d +1.98% (p=0.003), 40d +3.10% (p=0.001), 60d +2.89% (p=0.009)</p>'

        for init in sorted(first_ever, key=lambda x: x["score"], reverse=True):
            if init["score"] >= 5:
                css_class = "signal-high"
                score_class = "score-high"
                tier = "TIER 1"
            elif init["score"] >= 3:
                css_class = "signal-med"
                score_class = "score-med"
                tier = "TIER 2"
            else:
                css_class = "signal-low"
                score_class = "score-low"
                tier = "TIER 3"

            details_html = ""
            for factor, detail in init["score_details"].items():
                details_html += f'<div class="detail">• {detail}</div>'

            html += f"""
            <div class="{css_class}">
                <span class="ticker">{init['ticker']}</span>
                <span class="score {score_class}">{tier} — Score {init['score']}</span>
                <div class="detail"><strong>{init.get('company_name', 'N/A')}</strong> | {init.get('sector', 'Unknown')} | Mkt Cap: ${init.get('market_cap_fmt', 'N/A')}</div>
                <div class="detail">Dividend: ${init.get('dividend_amount', 0):.4f} | Frequency: {init.get('frequency', 'Unknown')} | Ex-Date: {init.get('ex_date', 'N/A')}</div>
                {details_html}
            </div>
            """
    else:
        html += '<h2>FIRST-EVER INITIATIONS</h2>'
        html += '<div class="no-signals">No first-ever initiations detected today.</div>'

    # RESUMPTIONS (logged for data collection, not tradeable)
    if resumptions:
        html += "<h2>RESUMPTIONS (Data Only — No Edge)</h2>"
        for init in resumptions:
            html += f"""
            <div class="signal-info">
                <span class="ticker">{init['ticker']}</span>
                <span style="color: #95a5a6; font-size: 13px;">RESUMPTION — no tradeable edge</span>
                <div class="detail">{init.get('company_name', 'N/A')} | {init.get('sector', 'Unknown')} | Gap: {init.get('gap_years', '?')} years</div>
                <div class="detail">Dividend: ${init.get('dividend_amount', 0):.4f} | Ex-Date: {init.get('ex_date', 'N/A')}</div>
            </div>
            """

    html += f"""
        <div class="footer">
            Dividend Initiation Scanner v1.0 | Scheduled: 23:30 UTC daily<br>
            Signal: First-ever initiations only | Backtest: n=229 (166 first-ever, 63 resumptions)<br>
            Data source: FMP API | Database: {DB_FILE}
        </div>
    </div>
    </body>
    </html>
    """

    return html


def format_market_cap(cap):
    """Format market cap for display."""
    if not cap or cap == 0:
        return "N/A"
    if cap >= 1e12:
        return f"{cap/1e12:.1f}T"
    elif cap >= 1e9:
        return f"{cap/1e9:.1f}B"
    elif cap >= 1e6:
        return f"{cap/1e6:.0f}M"
    else:
        return f"{cap:,.0f}"


def send_email(subject, html_body):
    """Send HTML email alert."""
    if not EMAIL_PASSWORD:
        print("  WARNING: No email password set. Skipping email.")
        print("  Set SCANNER_EMAIL_PASSWORD environment variable.")
        return False

    try:
        msg = MIMEMultipart("alternative")
        msg["Subject"] = subject
        msg["From"] = EMAIL_FROM
        msg["To"] = EMAIL_TO
        msg.attach(MIMEText(html_body, "html"))

        with smtplib.SMTP_SSL("smtp.gmail.com", 465) as server:
            server.login(EMAIL_FROM, EMAIL_PASSWORD)
            server.sendmail(EMAIL_FROM, EMAIL_TO, msg.as_string())
        print("  Email sent successfully.")
        return True
    except Exception as e:
        print(f"  ERROR sending email: {e}")
        return False


def main():
    if len(sys.argv) < 2:
        print("Usage: python3 dividend_initiation_scanner.py <FMP_API_KEY>")
        sys.exit(1)

    api_key = sys.argv[1]
    start_time = time.time()

    print("=" * 70)
    print("DIVIDEND INITIATION SCANNER — DAILY SCAN")
    print(f"Started: {datetime.utcnow().strftime('%Y-%m-%d %H:%M:%S')} UTC")
    print("=" * 70)

    # Initialize database
    print("\n[1/6] INITIALIZING DATABASE...")
    conn = init_database()
    cursor = conn.cursor()
    print(f"  Database: {DB_FILE}")

    # Determine date range to scan
    print("\n[2/6] FETCHING DIVIDEND CALENDAR...")
    today = datetime.utcnow()
    from_date = (today - timedelta(days=SCAN_DAYS_BACK)).strftime("%Y-%m-%d")
    to_date = (today + timedelta(days=SCAN_DAYS_FORWARD)).strftime("%Y-%m-%d")
    print(f"  Date range: {from_date} to {to_date}")

    calendar = fetch_dividend_calendar(api_key, from_date, to_date)
    print(f"  Dividend calendar entries: {len(calendar)}")

    if not calendar:
        print("  No dividend calendar data. Exiting.")
        duration = time.time() - start_time
        cursor.execute(
            "INSERT INTO scan_log (scan_date, dividends_checked, initiations_found, first_ever_found, errors, duration_seconds) VALUES (?, 0, 0, 0, 'Empty calendar', ?)",
            (today.strftime("%Y-%m-%d"), duration)
        )
        conn.commit()
        conn.close()
        return

    # Filter out ETFs/funds and deduplicate by ticker
    print("\n[3/6] FILTERING & DEDUPLICATING...")
    seen_tickers = set()
    candidates = []

    for entry in calendar:
        ticker = entry.get("symbol", "")
        label = entry.get("label", "") or entry.get("name", "") or ""

        if not ticker or ticker in seen_tickers:
            continue

        # Skip obvious ETFs/funds
        if is_etf_or_fund(label, ticker):
            continue

        # Skip if already in our database
        cursor.execute(
            "SELECT 1 FROM initiations WHERE ticker = ? AND ex_date = ?",
            (ticker, entry.get("date", ""))
        )
        if cursor.fetchone():
            continue

        seen_tickers.add(ticker)
        candidates.append(entry)

    print(f"  Unique stock candidates to check: {len(candidates)}")

    # Check each candidate for first-ever status
    print(f"\n[4/6] CHECKING DIVIDEND HISTORY FOR {len(candidates)} CANDIDATES...")
    market_regime = get_market_regime()
    print(f"  Current market regime: {market_regime}")

    initiations = []
    checked = 0
    errors = []

    for i, entry in enumerate(candidates):
        ticker = entry.get("symbol", "")
        ex_date = entry.get("date", "")
        div_amount = entry.get("dividend", 0) or entry.get("adjDividend", 0) or 0

        try:
            div_amount = float(div_amount)
        except (ValueError, TypeError):
            div_amount = 0

        checked += 1

        # Fetch full dividend history
        history = fetch_dividend_history(ticker, api_key)
        time.sleep(SLEEP_BETWEEN_CALLS)

        # Classify the event
        event_type, gap_years, prior_last_date = classify_initiation(history, entry)

        if event_type == "regular":
            # Not an initiation, skip
            continue

        # This IS an initiation (first-ever or resumption)
        print(f"  [{checked}] {ticker}: {event_type.upper()}" +
              (f" (gap: {gap_years}y)" if gap_years else ""))

        # Fetch company profile for sector/market cap
        profile = fetch_company_profile(ticker, api_key)
        time.sleep(SLEEP_BETWEEN_CALLS)

        sector = profile.get("sector", "Unknown")
        market_cap = profile.get("marketCap", 0) or 0
        company_name = profile.get("companyName", ticker)

        # Check for ETF/fund in profile
        if is_etf_or_fund(company_name, ticker):
            print(f"    Filtered: {company_name} (ETF/Fund)")
            continue
        if profile.get("isEtf") or profile.get("isFund"):
            print(f"    Filtered: {company_name} (ETF/Fund flag)")
            continue

        # Detect frequency
        frequency = detect_frequency(history) if history else "Unknown"

        # Score the initiation
        score, score_details = score_initiation(
            event_type, sector, div_amount, market_regime
        )

        init_record = {
            "ticker": ticker,
            "detected_date": today.strftime("%Y-%m-%d"),
            "declaration_date": entry.get("declarationDate", ""),
            "ex_date": ex_date,
            "payment_date": entry.get("paymentDate", ""),
            "dividend_amount": div_amount,
            "frequency": frequency,
            "sector": sector,
            "market_cap": market_cap,
            "market_cap_fmt": format_market_cap(market_cap),
            "company_name": company_name,
            "event_type": event_type,
            "gap_years": gap_years,
            "prior_last_date": prior_last_date,
            "score": score,
            "score_details": score_details,
            "is_first_ever": 1 if event_type == "first_ever" else 0,
        }

        initiations.append(init_record)

        # Store in database
        try:
            cursor.execute("""
                INSERT OR IGNORE INTO initiations
                (ticker, detected_date, declaration_date, ex_date, payment_date,
                 dividend_amount, frequency, sector, market_cap, company_name,
                 event_type, score, score_details, is_first_ever, prior_dividend_history)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, (
                ticker, today.strftime("%Y-%m-%d"),
                entry.get("declarationDate", ""), ex_date,
                entry.get("paymentDate", ""),
                div_amount, frequency, sector, market_cap, company_name,
                event_type, score, json.dumps(score_details),
                1 if event_type == "first_ever" else 0,
                json.dumps({
                    "gap_years": gap_years,
                    "prior_last_date": prior_last_date,
                    "total_prior_dividends": len(history) - 1 if history else 0
                })
            ))
        except Exception as e:
            errors.append(f"{ticker}: DB insert error: {e}")

    conn.commit()

    # Summary
    first_ever_count = sum(1 for i in initiations if i["event_type"] == "first_ever")
    resumption_count = sum(1 for i in initiations if i["event_type"] == "resumption")

    print(f"\n[5/6] SCAN RESULTS...")
    print(f"  Dividends checked: {checked}")
    print(f"  Initiations found: {len(initiations)}")
    print(f"  First-ever: {first_ever_count}")
    print(f"  Resumptions: {resumption_count}")

    if initiations:
        print("\n  DETECTED INITIATIONS:")
        for init in sorted(initiations, key=lambda x: x["score"], reverse=True):
            tier = "T1" if init["score"] >= 5 else ("T2" if init["score"] >= 3 else "T3")
            fe_tag = "FIRST-EVER" if init["event_type"] == "first_ever" else "RESUMPTION"
            print(f"    {init['ticker']:6s} | {fe_tag:12s} | Score {init['score']} ({tier}) | "
                  f"${init['dividend_amount']:.4f} | {init['sector']} | {init['company_name']}")

    # Log scan
    duration = time.time() - start_time
    cursor.execute("""
        INSERT INTO scan_log
        (scan_date, dividends_checked, initiations_found, first_ever_found, errors, duration_seconds)
        VALUES (?, ?, ?, ?, ?, ?)
    """, (
        today.strftime("%Y-%m-%d"), checked, len(initiations),
        first_ever_count, json.dumps(errors) if errors else None, duration
    ))
    conn.commit()

    # Send email
    print(f"\n[6/6] SENDING EMAIL REPORT...")
    scan_stats = {
        "checked": checked,
        "initiations": len(initiations),
        "first_ever": first_ever_count,
        "resumptions": resumption_count,
        "duration": duration
    }

    subject_parts = []
    if first_ever_count > 0:
        high_score = [i for i in initiations if i["event_type"] == "first_ever" and i["score"] >= 5]
        if high_score:
            tickers = ", ".join(i["ticker"] for i in high_score[:3])
            subject_parts.append(f"T1: {tickers}")
        subject = f"DIV INITIATION: {first_ever_count} First-Ever"
        if subject_parts:
            subject += f" | {' | '.join(subject_parts)}"
    else:
        subject = "DIV INITIATION: No new initiations detected"

    html = build_html_email(initiations, scan_stats)
    send_email(subject, html)

    conn.close()

    print(f"\n{'=' * 70}")
    print(f"  SCAN COMPLETE — {duration:.1f}s")
    print(f"  Database: {DB_FILE}")
    print(f"{'=' * 70}")


if __name__ == "__main__":
    main()
