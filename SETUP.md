# Quick Setup Guide

## Prerequisites
- Python 3.9+
- pip package manager

## Installation Steps

### 1. Install Dependencies
```bash
pip install -r requirements.txt
```

### 2. Set Up Environment Variables
```bash
# Copy the example file
cp .env.example .env

# Edit .env and add your information
# Replace "YourName your.email@example.com" with your actual name and email
# The email is required for SEC EDGAR to identify your requests
```

Example `.env` file:
```
SEC_USER_AGENT=BZ Liu bzliu@gmail.com
DATABASE_URL=sqlite:///data/insider_trades.db
```

### 3. Initialize Database
```bash
python -c "from src.database import initialize_database; initialize_database()"
```

### 4. Test the Setup
```bash
python test_scraper.py
```

## What Was Created

### Directory Structure
```
├── src/
│   ├── database.py              # Database models and utilities
│   ├── data_collection/
│   │   └── form4_scraper.py    # SEC Form 4 scraper
│   ├── analysis/               # (Phase 2: Signal detection)
│   └── execution/              # (Phase 3: Trade logic)
├── data/                       # SQLite database storage
├── tests/                      # Unit tests
├── config.py                   # Configuration
├── requirements.txt            # Dependencies
└── test_scraper.py             # Main test script
```

### Key Files

**config.py**: Central configuration with all trading parameters
- `MIN_PURCHASE_AMOUNT`: Minimum $50k insider purchase threshold
- `MIN_CONVICTION_SCORE`: Minimum scoring threshold for trades
- `ACCUMULATION_WINDOW_DAYS`: 30-day accumulation analysis window

**src/database.py**: Database utilities
- `InsiderTransaction`: SQLAlchemy ORM model
- `insert_transaction()`: Add new transactions
- `get_recent_transactions()`: Query database
- `get_database_stats()`: Database overview

**src/data_collection/form4_scraper.py**: Form 4 data collection
- `Form4Scraper`: Main scraper class
- Fetches SEC Form 4 filings
- Parses insider transaction details
- Filters for >$50k purchases
- Calculates filing speed metrics

**test_scraper.py**: Validation script
- Tests database initialization
- Validates scraper functionality
- Tests database queries
- Analyzes filing speed distribution
- Displays top insider purchases

## Running Your First Scrape

```bash
# Run the test script (includes scraping)
python test_scraper.py

# Or directly use the scraper
python -c "
from src.data_collection.form4_scraper import Form4Scraper
scraper = Form4Scraper()
results = scraper.scrape_recent_filings(days_back=7)
print(f'Found {len(results)} insider purchases in last 7 days')
"
```

## Next Steps

### Phase 1 Complete: Foundation
- ✅ Form 4 data collection working
- ✅ Database schema ready
- ✅ Filing speed calculation functional

### Phase 2 (Next):
- Filing speed multiplier system
- Short interest data integration
- Accumulation pattern detection

### To Continue Development:
See the README.md for the full development roadmap and use Claude Code with iterative prompts to build each component.

## Troubleshooting

### SEC User Agent Error
If you get "SEC_USER_AGENT must be set in .env file":
- Check that `.env` file exists in the project root (same level as `config.py`)
- Ensure `SEC_USER_AGENT=YourName youremail@example.com` is set
- Restart your Python environment

### Database Errors
If you get database connection errors:
```bash
# Remove old database and reinitialize
rm data/insider_trades.db
python -c "from src.database import initialize_database; initialize_database()"
```

### No Transactions Found
This can happen if:
- SEC EDGAR servers are temporarily unavailable
- No insider purchases met your filtering criteria in the time period
- Check the logs for specific error messages

Run with more days to see more data:
```bash
python test_scraper.py  # Automatically tries 7-30 days of data
```

## API Rate Limiting
SEC EDGAR respects normal HTTP rate limiting. If you get rate-limited:
- Wait a few minutes before retrying
- The system includes backoff logic automatically
- For production use, consider spreading requests over time

## Support
Check the main README.md for more information about the project structure and strategy.
