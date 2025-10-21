#!/usr/bin/env python3
"""
Test script to verify all live data sources are working.
Run this to validate the data integration before deploying to production.
"""
import sys
from datetime import datetime
from loguru import logger

# Configure logging
logger.remove()
logger.add(
    sys.stdout,
    format="<level>{level: <8}</level> | <cyan>{name}</cyan> - <level>{message}</level>",
    level="DEBUG"
)


def test_market_data():
    """Test market data fetching."""
    print("\n" + "="*60)
    print("TEST 1: Market Data (yfinance)")
    print("="*60)

    try:
        from src.data_collection.market_data_cache import get_market_cache

        cache = get_market_cache()
        tickers = ['AAPL', 'MSFT', 'GOOGL']

        print(f"Fetching market data for {tickers}...")
        data = cache.bulk_fetch_ticker_data(tickers)

        print(f"✓ Successfully fetched {len(data)} tickers")
        for ticker in tickers:
            if ticker in data:
                info = cache.get_cached_info(ticker)
                if info:
                    price = info.get('current_price', 0)
                    mkt_cap = info.get('market_cap', 0)
                    print(f"  {ticker}: ${price:.2f} (Market Cap: ${mkt_cap/1e9:.1f}B)")

        return True

    except Exception as e:
        logger.error(f"Market data test failed: {e}")
        return False


def test_earnings_sentiment():
    """Test earnings sentiment analysis."""
    print("\n" + "="*60)
    print("TEST 2: Earnings Sentiment Analysis")
    print("="*60)

    try:
        from src.data_collection.earnings_sentiment import get_earnings_sentiment_analyzer
        from datetime import datetime

        analyzer = get_earnings_sentiment_analyzer()
        ticker = "AAPL"

        print(f"Fetching earnings data for {ticker}...")
        sentiment, days_since, confidence = analyzer.analyze_recent_earnings_for_ticker(
            ticker, datetime.now()
        )

        print(f"✓ Earnings sentiment analysis complete")
        print(f"  Sentiment: {sentiment:.3f}")
        print(f"  Days since earnings: {days_since}")
        print(f"  Confidence: {confidence:.2%}")

        return True

    except Exception as e:
        logger.error(f"Earnings sentiment test failed: {e}")
        return False


def test_intraday_data():
    """Test intraday monitoring."""
    print("\n" + "="*60)
    print("TEST 3: Intraday Data & Momentum (5-minute)")
    print("="*60)

    try:
        from src.data_collection.intraday_monitor import get_intraday_monitor

        monitor = get_intraday_monitor('5m')
        ticker = 'AAPL'

        print(f"Fetching 5-minute intraday data for {ticker}...")
        data = monitor.fetch_intraday_data(ticker, '5m')

        if data is not None and len(data) > 0:
            print(f"✓ Got {len(data)} intraday candles")

            momentum = monitor.get_current_price_momentum(ticker)
            if momentum:
                print(f"  Current Price: ${momentum['current_price']:.2f}")
                print(f"  Change: {momentum['price_change_pct']:.2f}%")
                print(f"  Trend: {momentum['trend']}")
                print(f"  RSI: {momentum['rsi']:.1f}")

            signals = monitor.detect_price_action_signals(ticker)
            if signals:
                print(f"  Breakout High: {signals['breakout_high']}")
                print(f"  Breakout Low: {signals['breakout_low']}")

            return True
        else:
            logger.warning("No intraday data available")
            return False

    except Exception as e:
        logger.error(f"Intraday test failed: {e}")
        return False


def test_finnhub_data():
    """Test Finnhub integration."""
    print("\n" + "="*60)
    print("TEST 4: Finnhub API (Company News, Analyst Ratings)")
    print("="*60)

    try:
        from src.data_collection.finnhub_integrator import get_finnhub_integrator

        finnhub = get_finnhub_integrator()
        ticker = 'AAPL'

        print(f"Fetching Finnhub data for {ticker}...")

        # Company news
        news = finnhub.get_company_news(ticker, days_back=7, limit=5)
        print(f"✓ Company News: {len(news)} articles found")
        if news:
            print(f"  Latest: {news[0].get('headline', 'N/A')[:60]}...")

        # Analyst sentiment
        sentiment, analysis = finnhub.analyze_analyst_sentiment(ticker)
        print(f"✓ Analyst Sentiment: {sentiment:.3f}")
        if 'total_analysts' in analysis:
            print(f"  Analysts: {analysis['total_analysts']}")
            if 'average_rating' in analysis:
                print(f"  Avg Rating: {analysis['average_rating']:.1f}/5.0")

        return True

    except Exception as e:
        logger.warning(f"Finnhub test (may require API key): {e}")
        return False


def test_polygon_options():
    """Test Polygon options data."""
    print("\n" + "="*60)
    print("TEST 5: Polygon.io Options Data")
    print("="*60)

    try:
        from src.data_collection.polygon_options import get_polygon_options_analyzer

        analyzer = get_polygon_options_analyzer()
        ticker = 'AAPL'

        print(f"Fetching options data for {ticker}...")

        chain = analyzer.get_options_chain_data(ticker)
        print(f"✓ Options Chain:")
        print(f"  Calls: {len(chain['calls'])}")
        print(f"  Puts: {len(chain['puts'])}")

        flow_score, details = analyzer.analyze_options_flow(ticker)
        print(f"✓ Options Flow Score: {flow_score:.3f}")
        print(f"  Interpretation: {details.get('flow_interpretation', 'Unknown')}")
        if 'call_put_vol_ratio' in details:
            print(f"  Call/Put Vol Ratio: {details['call_put_vol_ratio']:.2f}")
        if 'call_put_oi_ratio' in details:
            print(f"  Call/Put OI Ratio: {details['call_put_oi_ratio']:.2f}")

        return True

    except Exception as e:
        logger.warning(f"Polygon options test (may require time for API): {e}")
        return False


def test_news_sentiment():
    """Test news sentiment analysis."""
    print("\n" + "="*60)
    print("TEST 6: News Sentiment Analysis (GDELT)")
    print("="*60)

    try:
        from src.data_collection.news_sentiment import get_news_sentiment_analyzer

        analyzer = get_news_sentiment_analyzer()
        ticker = 'AAPL'

        print(f"Fetching news for {ticker}...")

        sentiment, analysis = analyzer.get_ticker_sentiment_trend(ticker, days=7)
        print(f"✓ News Sentiment: {sentiment:.3f}")
        print(f"  Interpretation: {analysis.get('interpretation', 'Unknown')}")
        print(f"  Articles Analyzed: {analysis.get('articles_analyzed', 0)}")
        if 'trend' in analysis:
            print(f"  Trend: {analysis['trend'].upper()}")

        return True

    except Exception as e:
        logger.warning(f"News sentiment test failed: {e}")
        return False


def test_enhanced_scorer():
    """Test enhanced conviction scorer."""
    print("\n" + "="*60)
    print("TEST 7: Enhanced Conviction Scorer")
    print("="*60)

    try:
        from src.analysis.enhanced_conviction_scorer import get_enhanced_conviction_scorer
        from datetime import datetime

        scorer = get_enhanced_conviction_scorer()
        ticker = 'AAPL'

        print(f"Calculating enhanced conviction score for {ticker}...")

        result = scorer.calculate_enhanced_conviction_score(
            ticker=ticker,
            filing_speed_days=0,
            insider_name='Tim Cook',
            transaction_date=datetime.now(),
        )

        print(f"✓ Conviction Score: {result['conviction_score']:.3f}")
        print(f"  Signal Strength: {result['signal_strength']}")
        print(f"  Data Sources Used:")

        for source, available in result['data_sources_used'].items():
            status = "✓" if available else "✗"
            print(f"    {status} {source.replace('_', ' ').title()}")

        return True

    except Exception as e:
        logger.error(f"Enhanced scorer test failed: {e}")
        return False


def test_integration_hub():
    """Test the integration hub."""
    print("\n" + "="*60)
    print("TEST 8: Data Integration Hub")
    print("="*60)

    try:
        from src.data_collection.integration_hub import get_data_integration_hub

        hub = get_data_integration_hub()
        ticker = 'AAPL'

        print(f"Validating live data flow for {ticker}...")

        validation = hub.validate_live_data_flow(test_ticker=ticker)

        print(f"✓ Data Flow Validation Complete")
        print(f"\n  Source Status:")

        for source, result in validation['validations'].items():
            status_icon = "✓" if result['status'] == 'live' else "✗"
            print(f"    {status_icon} {source}: {result['status']}")

        print(f"\n  Summary:")
        print(f"    Live Sources: {validation['summary']['live_sources']}/7")
        print(f"    Data Flow Healthy: {validation['summary']['data_flow_healthy']}")

        return validation['summary']['data_flow_healthy']

    except Exception as e:
        logger.error(f"Integration hub test failed: {e}")
        return False


def main():
    """Run all tests."""
    print("\n" + "="*60)
    print("INTELLIGENT TRADER - LIVE DATA INTEGRATION TEST SUITE")
    print("="*60)
    print(f"Test started at: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")

    results = {
        'Market Data': test_market_data(),
        'Earnings Sentiment': test_earnings_sentiment(),
        'Intraday Data': test_intraday_data(),
        'Finnhub API': test_finnhub_data(),
        'Polygon Options': test_polygon_options(),
        'News Sentiment': test_news_sentiment(),
        'Enhanced Scorer': test_enhanced_scorer(),
        'Integration Hub': test_integration_hub(),
    }

    # Summary
    print("\n" + "="*60)
    print("TEST SUMMARY")
    print("="*60)

    passed = sum(1 for v in results.values() if v)
    total = len(results)

    for test_name, result in results.items():
        status = "✓ PASS" if result else "✗ FAIL"
        print(f"{status}: {test_name}")

    print(f"\nTotal: {passed}/{total} tests passed")
    print(f"Success Rate: {passed/total*100:.0f}%")

    if passed >= 6:  # At least 75% pass rate
        print("\n✓ Live data integration is working!")
        print("You can now use enhanced conviction scoring for trades.")
        return 0
    else:
        print("\n✗ Some data sources are not responding.")
        print("Check your internet connection and API keys.")
        return 1


if __name__ == "__main__":
    sys.exit(main())
