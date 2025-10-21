#!/usr/bin/env python
"""
Test script for Form 4 scraper and data validation.
"""
import sys
from pathlib import Path
from datetime import datetime, timedelta

# Add src to path
sys.path.insert(0, str(Path(__file__).parent))

from src.data_collection.form4_scraper import Form4Scraper
from src.database import get_recent_transactions, get_database_stats, initialize_database
from loguru import logger

# Configure logging
logger.remove()
logger.add(sys.stderr, format="<level>{level: <8}</level> | <cyan>{name}</cyan>:<cyan>{function}</cyan> - <level>{message}</level>")


def print_section(title: str):
    """Print a formatted section header."""
    print(f"\n{'='*60}")
    print(f"  {title}")
    print(f"{'='*60}")


def test_database_initialization():
    """Test database initialization."""
    print_section("Database Initialization")
    try:
        initialize_database()
        print("✓ Database initialized successfully")
        return True
    except Exception as e:
        print(f"✗ Database initialization failed: {e}")
        return False


def test_form4_scraper():
    """Test Form 4 scraper."""
    print_section("Form 4 Scraper Test")

    try:
        scraper = Form4Scraper()
        print("✓ Scraper initialized")

        # Scrape last 7 days of data
        print("\nScraping Form 4 filings (last 7 days)...")
        df = scraper.scrape_recent_filings(days_back=7)

        if df.empty:
            print("⚠ No transactions found in the last 7 days")
            print("  (This may be normal depending on market conditions)")
            return True

        print(f"✓ Found {len(df)} insider purchase transactions")

        print(f"\nTransaction Summary:")
        print(f"  - Total value: ${df['total_value'].sum():,.0f}")
        print(f"  - Average transaction value: ${df['total_value'].mean():,.0f}")
        print(f"  - Unique tickers: {df['ticker'].nunique()}")
        print(f"  - Unique insiders: {df['insider_name'].nunique()}")

        return True

    except Exception as e:
        print(f"✗ Scraper test failed: {e}")
        logger.exception("Scraper test error")
        return False


def test_database_queries():
    """Test database queries."""
    print_section("Database Query Tests")

    try:
        # Test recent transactions query
        df = get_recent_transactions(days=30, min_value=50000)

        if df.empty:
            print("⚠ No transactions in database yet")
            return True

        print(f"✓ Retrieved {len(df)} transactions from database")

        # Display top 10 largest purchases
        print("\nTop 10 Largest Insider Purchases:")
        print("-" * 60)

        top_10 = df.nlargest(10, 'total_value')
        for idx, (_, row) in enumerate(top_10.iterrows(), 1):
            filing_speed_indicator = "🔥 FAST" if row['filing_speed_days'] <= 1 else "   "
            print(f"{idx:2d}. {row['ticker']:6s} | ${row['total_value']:12,.0f} | "
                  f"Filing speed: {row['filing_speed_days']} days {filing_speed_indicator}")
            print(f"     {row['insider_name']} ({row['insider_title']})")

        return True

    except Exception as e:
        print(f"✗ Database query test failed: {e}")
        logger.exception("Database query error")
        return False


def test_filing_speed_analysis():
    """Test filing speed analysis."""
    print_section("Filing Speed Analysis")

    try:
        df = get_recent_transactions(days=90, min_value=50000)

        if df.empty:
            print("⚠ No data for analysis")
            return True

        print(f"Analyzed {len(df)} transactions from last 90 days")

        # Filing speed distribution
        speed_dist = df['filing_speed_days'].value_counts().sort_index()
        print(f"\nFiling Speed Distribution:")
        print("-" * 40)

        for days, count in speed_dist.items():
            pct = (count / len(df)) * 100
            bar = "█" * int(pct / 2)
            print(f"  {days} days: {count:3d} transactions ({pct:5.1f}%) {bar}")

        # Statistics
        print(f"\nStatistics:")
        print(f"  - Mean filing speed: {df['filing_speed_days'].mean():.1f} days")
        print(f"  - Median filing speed: {df['filing_speed_days'].median():.1f} days")
        print(f"  - Std deviation: {df['filing_speed_days'].std():.2f} days")

        # High conviction indicators (same or next-day filings)
        fast_filings = df[df['filing_speed_days'] <= 1]
        print(f"\n🔥 High Conviction Signals (≤1 day filing speed):")
        print(f"  - Count: {len(fast_filings)} ({len(fast_filings)/len(df)*100:.1f}%)")
        print(f"  - Average value: ${fast_filings['total_value'].mean():,.0f}")

        return True

    except Exception as e:
        print(f"✗ Filing speed analysis failed: {e}")
        logger.exception("Analysis error")
        return False


def test_database_stats():
    """Test database statistics."""
    print_section("Database Statistics")

    try:
        stats = get_database_stats()

        if not stats or stats.get('total_transactions', 0) == 0:
            print("⚠ No data in database yet")
            return True

        print(f"Total transactions: {stats['total_transactions']}")
        print(f"Unique tickers: {stats['unique_tickers']}")
        if stats.get('average_transaction_value'):
            print(f"Average transaction value: ${stats['average_transaction_value']:,.0f}")

        return True

    except Exception as e:
        print(f"✗ Database stats test failed: {e}")
        return False


def main():
    """Run all tests."""
    print("\n" + "=" * 60)
    print("  INSIDER TRADING SYSTEM - TEST SUITE")
    print("  Starting validation tests...")
    print("=" * 60)

    tests = [
        ("Database Initialization", test_database_initialization),
        ("Form 4 Scraper", test_form4_scraper),
        ("Database Queries", test_database_queries),
        ("Filing Speed Analysis", test_filing_speed_analysis),
        ("Database Statistics", test_database_stats),
    ]

    results = []
    for test_name, test_func in tests:
        try:
            result = test_func()
            results.append((test_name, result))
        except Exception as e:
            print(f"\n✗ Test '{test_name}' crashed: {e}")
            logger.exception(f"Test '{test_name}' failed")
            results.append((test_name, False))

    # Print summary
    print_section("Test Summary")
    passed = sum(1 for _, result in results if result)
    total = len(results)

    for test_name, result in results:
        status = "✓ PASS" if result else "✗ FAIL"
        print(f"{status:8s} - {test_name}")

    print(f"\nTotal: {passed}/{total} tests passed")

    if passed == total:
        print("\n🎉 All tests passed!")
        return 0
    else:
        print(f"\n⚠ {total - passed} test(s) failed")
        return 1


if __name__ == "__main__":
    sys.exit(main())
