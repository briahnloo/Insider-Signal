# Quick Start Guide - Live Data Pipeline

## Prerequisites

Ensure you have a `.env` file in the project root with:
```bash
SEC_USER_AGENT="YourName youremail@example.com"
```

This is required by the SEC for API access.

## Step 1: Initialize the System

Run the initialization script to populate the database with historical Form 4 data:

```bash
python scripts/initialize_data.py
```

This will:
- Initialize the database schema
- Scrape last 30 days of Form 4 filings from SEC
- Populate the market data cache with yfinance data
- Validate the setup

**Expected time:** 5-10 minutes depending on network speed

## Step 2: Launch the Dashboard

Start the Streamlit web interface:

```bash
streamlit run streamlit_app.py
```

The dashboard will open at `http://localhost:8501` and display:
- Current trading signals with conviction scores
- Historical analysis and backtests
- Component breakdown for each signal
- Database statistics

### Dashboard Features:
- **Auto-refresh:** Data refreshes every hour automatically
- **Manual refresh:** Click "🔄 Refresh Data" button in sidebar
- **Cache stats:** Monitor cache health in sidebar
- **Filters:** Adjust date range, conviction threshold, and transaction size

## Step 3: Set Up Hourly Data Refresh (Optional)

To keep data current, run the refresh job periodically:

```bash
# Manual refresh
python -m src.jobs.data_refresh

# Or set up a cron job (Linux/Mac)
crontab -e
# Add: 0 * * * * cd /path/to/Intelligent\ Trader && python -m src.jobs.data_refresh
```

The refresh job:
- Scrapes new Form 4 filings (last 2 days)
- Updates market data cache for all tickers
- Takes ~2-5 minutes to complete

## System Architecture

### Data Flow:
1. **Form 4 Scraper** → Fetches insider transactions from SEC RSS feeds
2. **Database** → Stores transactions with SQLite
3. **Market Cache** → Pre-fetches yfinance data for all tickers (4-hour TTL)
4. **Analysis Components** → Use cached data to score conviction
5. **Trade Signals** → Generated with position sizing and entry strategies
6. **Streamlit UI** → Displays results with auto-refresh

### Free Data Sources Used:
- SEC EDGAR RSS feeds (Form 4, 8-K, 13D/G)
- Yahoo Finance via yfinance (prices, short interest, fundamentals)
- No paid APIs required!

## Clearing the Database

If you want to remove all data and start fresh:

```bash
python scripts/clear_database.py
```

This will:
- Show current database contents
- Ask for confirmation
- Delete all transactions
- Leave tables intact for repopulation

## Troubleshooting

### No data showing in UI?
- Run `python scripts/initialize_data.py` to populate database
- Check `.env` file has `SEC_USER_AGENT` set
- Verify internet connection for SEC/Yahoo Finance access

### Want to remove old/test data?
- Run `python scripts/clear_database.py` to wipe the database
- Then run `python scripts/initialize_data.py` to get fresh data

### Slow performance?
- Market cache may be empty - wait for initialization to complete
- Check cache stats in sidebar - refresh if many stale entries
- Reduce date range in sidebar filters

### SEC rate limiting errors?
- The scraper includes built-in rate limiting (0.2-0.5s between requests)
- Wait a few minutes and try again
- SEC allows reasonable access for research purposes

## What's Next?

1. **Test the conviction scorer:**
   ```bash
   python full_system_test.py
   ```

2. **Explore the notebooks:**
   - Analysis examples in `notebooks/` directory

3. **Customize conviction weights:**
   - Edit `src/analysis/conviction_scorer.py`
   - Adjust weights for filing speed, short interest, accumulation, etc.

4. **Add your own signals:**
   - Create new analyzers in `src/analysis/`
   - Integrate into conviction scorer

## Support

For issues or questions:
1. Check the logs in `data/refresh.log`
2. Review the documentation files:
   - `SETUP.md` - Detailed setup instructions
   - `PHASE_2_COMPLETE.md` - Feature documentation
   - `NETWORK_INTELLIGENCE.md` - Advanced features

---

**Important:** This system is for research and educational purposes. Always conduct your own due diligence before making any investment decisions.

