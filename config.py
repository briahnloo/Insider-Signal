import os
from pathlib import Path
from dotenv import load_dotenv

# Load environment variables
load_dotenv()

# Project paths
PROJECT_ROOT = Path(__file__).parent
DATA_DIR = PROJECT_ROOT / "data"
SRC_DIR = PROJECT_ROOT / "src"

# Ensure data directory exists
DATA_DIR.mkdir(exist_ok=True)

# SEC EDGAR configuration
SEC_USER_AGENT = os.getenv("SEC_USER_AGENT")
if not SEC_USER_AGENT:
    raise ValueError("SEC_USER_AGENT must be set in .env file")

# Database
DATABASE_URL = os.getenv("DATABASE_URL", "sqlite:///data/insider_trades.db")

# Trading parameters
MIN_PURCHASE_AMOUNT = 50000  # Minimum $50k purchase
MIN_CONVICTION_SCORE = 0.6   # Minimum score to consider
MAX_POSITION_SIZE = 0.045    # Maximum 4.5% position
BASE_POSITION_SIZE = 0.025   # Standard 2.5% position

# Analysis windows
ACCUMULATION_WINDOW_DAYS = 30
FILING_SPEED_THRESHOLD_DAYS = 2

# Data refresh settings
CACHE_TTL_HOURS = 4
REFRESH_INTERVAL_HOURS = 1
MAX_FORM4_DAYS_BACK = 90

# Intraday monitoring settings (new)
INTRADAY_INTERVAL = "5m"  # 5-minute candles
INTRADAY_LOOKBACK_DAYS = 1
INTRADAY_ALERT_THRESHOLD_PCT = 2.0  # Alert on 2%+ moves
INTRADAY_CACHE_MAX_POINTS = 288  # 24 hours of 5-minute candles

# News and sentiment settings (new)
NEWS_LOOKBACK_DAYS = 7
NEWS_ARTICLES_LIMIT = 20
NEWS_CACHE_TTL_HOURS = 4

# Options analysis settings (new)
OPTIONS_CACHE_TTL_HOURS = 1
OPTIONS_UNUSUAL_THRESHOLD_MULTIPLIER = 3.0  # Flag OI > 3x average

# Earnings transcript settings (new)
EARNINGS_LOOKBACK_DAYS = 90
EARNINGS_CACHE_TTL_HOURS = 24

# Analyst sentiment settings (new)
ANALYST_CACHE_TTL_HOURS = 24

# SEC RSS Feeds
SEC_RSS_FEEDS = {
    'form4': 'https://www.sec.gov/cgi-bin/browse-edgar?action=getcurrent&type=4&output=atom',
    'form8k': 'https://www.sec.gov/cgi-bin/browse-edgar?action=getcurrent&type=8-K&output=atom',
    'form13d': 'https://www.sec.gov/cgi-bin/browse-edgar?action=getcurrent&type=SC%2013D&output=atom',
    'form13g': 'https://www.sec.gov/cgi-bin/browse-edgar?action=getcurrent&type=SC%2013G&output=atom',
}

# Optional API Keys (loaded from .env)
FINNHUB_API_KEY = os.getenv("FINNHUB_API_KEY")
POLYGON_API_KEY = os.getenv("POLYGON_API_KEY")
UNUSUAL_WHALES_API_KEY = os.getenv("UNUSUAL_WHALES_API_KEY")
