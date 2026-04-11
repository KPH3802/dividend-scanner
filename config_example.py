#!/usr/bin/env python3
"""
Configuration for Dividend Cut Scanner — EXAMPLE.
Copy this file to config.py and fill in your values.
NEVER commit config.py to GitHub.
"""
import os

# ============================================================
# EMAIL SETTINGS
# ============================================================
SMTP_SERVER = "smtp.gmail.com"
SMTP_PORT = 587
EMAIL_SENDER = "your_email@gmail.com"
EMAIL_PASSWORD = "your_gmail_app_password"   # Gmail App Password
EMAIL_RECIPIENT = "your_email@gmail.com"

# ============================================================
# FMP API
# ============================================================
FMP_API_KEY = os.environ.get('FMP_API_KEY', 'your_fmp_api_key_here')

# ============================================================
# COMPOSITE SCORING PARAMETERS (from backtest)
# ============================================================
# Positive factors (each worth +1 point)
CUT_SWEET_SPOT_MIN = 75          # 75-90% cut range = sweet spot
CUT_SEVERE_MIN = 50              # Minimum cut % to consider tradeable
POSITIVE_SECTORS = {'Industrials', 'Financial Services', 'Energy', 'Technology'}
BEAR_MARKET_THRESHOLD = -5       # SPY trailing 60d return < -5%
Q1_MONTHS = {1, 2, 3}           # Q1 seasonality bonus
CHEAP_PRICE_MAX = 15             # Entry price <= $15

# Negative factors (red flags)
MODERATE_CUT_MAX = 50            # Cuts < 50% = moderate (red flag)
NEGATIVE_SECTORS = {'Basic Materials'}
BULL_MARKET_THRESHOLD = 5        # SPY trailing 60d return > +5%
EXPENSIVE_PRICE_MIN = 30         # Entry price > $30

# Minimum cut to track at all
MIN_CUT_PCT = 20

# How many days back to check for new declarations
LOOKBACK_DAYS = 3

# Database
DB_NAME = "dividend_scanner.db"
