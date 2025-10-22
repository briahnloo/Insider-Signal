"""Hourly data refresh job to keep cache and database current."""
import sys
from pathlib import Path
from datetime import datetime
from loguru import logger

# Add parent directory to path
sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from src.data_collection.form4_scraper import Form4Scraper
from src.data_collection.market_data_cache import get_market_cache
from src.analysis.short_interest import ShortInterestAnalyzer
from src.database import get_recent_transactions, get_database_stats
import config


def refresh_form4_data(days_back: int = 2):
    """
    Refresh Form 4 data by scraping recent filings.

    Args:
        days_back: Number of days to look back (default: 2)
    """
    logger.info("=" * 60)
    logger.info("Refreshing Form 4 Data")
    logger.info("=" * 60)
    
    try:
        scraper = Form4Scraper()
        df = scraper.scrape_recent_filings(days_back=days_back)
        
        logger.info(f"Scraped {len(df)} Form 4 transactions")
        return len(df)
        
    except Exception as e:
        logger.error(f"Error refreshing Form 4 data: {e}")
        return 0


def refresh_short_interest_data():
    """
    Refresh short interest data for all tickers in database.

    This is called weekly (Monday) to update SI data from yfinance.
    Updates are cached locally with TTL to avoid excessive API calls.

    Returns:
        Number of tickers with SI data refreshed
    """
    logger.info("=" * 60)
    logger.info("Refreshing Short Interest Data (Weekly)")
    logger.info("=" * 60)

    try:
        # Get unique tickers from database
        df = get_recent_transactions(days=90, min_value=0)

        if df.empty:
            logger.info("No tickers in database to refresh SI data")
            return 0

        tickers = df['ticker'].unique().tolist()
        logger.info(f"Found {len(tickers)} unique tickers to refresh SI data")

        # Fetch SI data for each ticker
        si_analyzer = ShortInterestAnalyzer()
        refreshed_count = 0

        for ticker in tickers:
            try:
                mult, details = si_analyzer.calculate_squeeze_potential(ticker)
                si_pct = details.get('short_interest_pct', 0)
                dtc = details.get('days_to_cover', 0)

                logger.debug(
                    f"{ticker}: SI={si_pct:.2f}%, DTC={dtc:.1f} days, "
                    f"Multiplier={mult:.2f}x"
                )
                refreshed_count += 1

            except Exception as e:
                logger.warning(f"Failed to refresh SI data for {ticker}: {e}")

        logger.info(f"Successfully refreshed SI data for {refreshed_count}/{len(tickers)} tickers")
        return refreshed_count

    except Exception as e:
        logger.error(f"Error refreshing short interest data: {e}")
        return 0


def refresh_market_cache():
    """Refresh market data cache for all tickers in database."""
    logger.info("=" * 60)
    logger.info("Refreshing Market Data Cache")
    logger.info("=" * 60)
    
    try:
        # Get unique tickers from database
        df = get_recent_transactions(days=90, min_value=0)
        
        if df.empty:
            logger.info("No tickers in database to refresh")
            return 0
        
        tickers = df['ticker'].unique().tolist()
        logger.info(f"Found {len(tickers)} unique tickers to refresh")
        
        # Bulk fetch market data
        cache = get_market_cache()
        results = cache.bulk_fetch_ticker_data(tickers)
        
        logger.info(f"Successfully refreshed cache for {len(results)} tickers")
        
        # Log cache stats
        stats = cache.get_cache_stats()
        logger.info(f"Cache stats: {stats}")
        
        return len(results)
        
    except Exception as e:
        logger.error(f"Error refreshing market cache: {e}")
        return 0


def refresh_all_data(include_weekly_si: bool = False):
    """
    Comprehensive data refresh job.

    Steps:
    1. Scrape recent Form 4 filings (last 2 days)
    2. Get unique tickers from database
    3. Bulk fetch yfinance data for all tickers
    4. Update cache timestamps
    5. Optionally refresh short interest (weekly)
    6. Log refresh statistics

    Args:
        include_weekly_si: If True, also refresh short interest data (called weekly)
    """
    start_time = datetime.now()
    logger.info("\n" + "=" * 60)
    logger.info("STARTING HOURLY DATA REFRESH JOB")
    logger.info(f"Time: {start_time.strftime('%Y-%m-%d %H:%M:%S')}")
    logger.info("=" * 60 + "\n")

    stats = {}

    # Step 1: Refresh Form 4 data
    try:
        form4_count = refresh_form4_data(days_back=2)
        stats['form4_transactions'] = form4_count
    except Exception as e:
        logger.error(f"Form 4 refresh failed: {e}")
        stats['form4_transactions'] = 0

    # Step 2: Refresh market data cache
    try:
        cache_count = refresh_market_cache()
        stats['cached_tickers'] = cache_count
    except Exception as e:
        logger.error(f"Market cache refresh failed: {e}")
        stats['cached_tickers'] = 0

    # Step 3: Optionally refresh short interest (weekly)
    if include_weekly_si:
        try:
            si_count = refresh_short_interest_data()
            stats['si_refreshed_tickers'] = si_count
        except Exception as e:
            logger.error(f"Short interest refresh failed: {e}")
            stats['si_refreshed_tickers'] = 0

    # Step 4: Get database stats
    try:
        db_stats = get_database_stats()
        stats['database_stats'] = db_stats
    except Exception as e:
        logger.error(f"Database stats failed: {e}")
        stats['database_stats'] = {}

    # Summary
    end_time = datetime.now()
    duration = (end_time - start_time).total_seconds()

    logger.info("\n" + "=" * 60)
    logger.info("REFRESH JOB COMPLETE")
    logger.info("=" * 60)
    logger.info(f"Duration: {duration:.2f} seconds")
    logger.info(f"Form 4 transactions: {stats.get('form4_transactions', 0)}")
    logger.info(f"Cached tickers: {stats.get('cached_tickers', 0)}")
    if include_weekly_si:
        logger.info(f"SI refreshed tickers: {stats.get('si_refreshed_tickers', 0)}")

    db_stats = stats.get('database_stats', {})
    if db_stats:
        logger.info(f"Total transactions in DB: {db_stats.get('total_transactions', 0)}")
        logger.info(f"Unique tickers in DB: {db_stats.get('unique_tickers', 0)}")

    logger.info("=" * 60 + "\n")

    return stats


def main():
    """Main entry point for the refresh job."""
    # Configure logging
    logger.remove()
    logger.add(
        sys.stderr,
        format="<green>{time:YYYY-MM-DD HH:mm:ss}</green> | <level>{level: <8}</level> | <level>{message}</level>",
        level="INFO"
    )
    
    # Also log to file
    log_file = Path(__file__).parent.parent.parent / "data" / "refresh.log"
    logger.add(
        log_file,
        format="{time:YYYY-MM-DD HH:mm:ss} | {level: <8} | {message}",
        level="DEBUG",
        rotation="1 week",
        retention="4 weeks"
    )
    
    try:
        stats = refresh_all_data()
        logger.success("Refresh job completed successfully")
        return 0
    except Exception as e:
        logger.error(f"Refresh job failed: {e}")
        return 1


if __name__ == "__main__":
    sys.exit(main())

