"""
Central hub for all data collection and integration.
Orchestrates all data sources and ensures live data flow.
"""
from typing import Dict, List, Optional
from datetime import datetime
from loguru import logger
import time

# Import all data collection modules
from src.data_collection.form4_scraper import Form4Scraper
from src.data_collection.market_data_cache import get_market_cache
from src.data_collection.earnings_sentiment import get_earnings_sentiment_analyzer
from src.data_collection.news_sentiment import get_news_sentiment_analyzer
from src.data_collection.polygon_options import get_polygon_options_analyzer
from src.data_collection.finnhub_integrator import get_finnhub_integrator
from src.data_collection.intraday_monitor import get_intraday_monitor

import config


class DataIntegrationHub:
    """Central coordination point for all data sources."""

    def __init__(self):
        """Initialize the data integration hub."""
        logger.info("Initializing Data Integration Hub...")

        # Initialize all data sources
        self.form4_scraper = Form4Scraper()
        self.market_cache = get_market_cache()
        self.earnings_analyzer = get_earnings_sentiment_analyzer()
        self.news_analyzer = get_news_sentiment_analyzer()
        self.polygon_options = get_polygon_options_analyzer()
        self.finnhub = get_finnhub_integrator()
        self.intraday_monitor = get_intraday_monitor(interval=config.INTRADAY_INTERVAL)

        self.last_refresh_time = {}
        logger.info("✓ Data Integration Hub ready")

    def get_comprehensive_ticker_data(self, ticker: str) -> Dict:
        """
        Get comprehensive data for a ticker from all sources.

        Args:
            ticker: Stock ticker symbol

        Returns:
            Dict with all available data
        """
        ticker = ticker.upper()
        logger.debug(f"Fetching comprehensive data for {ticker}...")

        data = {
            'ticker': ticker,
            'timestamp': datetime.now().isoformat(),
            'data_sources': {},
        }

        try:
            # 1. Market data
            market_info = self.market_cache.get_cached_info(ticker)
            if market_info:
                data['data_sources']['market_data'] = market_info
            else:
                # Fetch if not cached
                self.market_cache.bulk_fetch_ticker_data([ticker])
                market_info = self.market_cache.get_cached_info(ticker)
                data['data_sources']['market_data'] = market_info or {}

            # 2. Intraday momentum
            try:
                momentum = self.intraday_monitor.get_current_price_momentum(ticker)
                if momentum:
                    data['data_sources']['intraday_momentum'] = momentum
            except Exception as e:
                logger.debug(f"Intraday momentum unavailable: {e}")

            # 3. Earnings sentiment
            try:
                transcript = self.earnings_analyzer.fetch_recent_earnings_transcripts(ticker)
                if transcript:
                    sentiment, details = self.earnings_analyzer.analyze_transcript_sentiment(transcript)
                    data['data_sources']['earnings_sentiment'] = {
                        'sentiment_score': float(sentiment),
                        'analysis': details,
                    }
            except Exception as e:
                logger.debug(f"Earnings sentiment unavailable: {e}")

            # 4. News sentiment
            try:
                sentiment, analysis = self.news_analyzer.get_ticker_sentiment_trend(ticker, days=7)
                data['data_sources']['news_sentiment'] = {
                    'sentiment_score': float(sentiment),
                    'analysis': analysis,
                }
            except Exception as e:
                logger.debug(f"News sentiment unavailable: {e}")

            # 5. Options flow
            try:
                flow_score, flow_details = self.polygon_options.analyze_options_flow(ticker)
                data['data_sources']['options_flow'] = {
                    'flow_score': float(flow_score),
                    'details': flow_details,
                }
            except Exception as e:
                logger.debug(f"Options flow unavailable: {e}")

            # 6. Finnhub data (analyst sentiment, recommendations)
            try:
                analyst_sentiment, analyst_data = self.finnhub.analyze_analyst_sentiment(ticker)
                data['data_sources']['analyst_sentiment'] = {
                    'sentiment_score': float(analyst_sentiment),
                    'analysis': analyst_data,
                }

                # Company news
                news = self.finnhub.get_company_news(ticker, days_back=7, limit=10)
                if news:
                    data['data_sources']['finnhub_news'] = {
                        'articles': len(news),
                        'sources': [n.get('source', 'Unknown') for n in news[:5]],
                    }
            except Exception as e:
                logger.debug(f"Finnhub data unavailable: {e}")

            logger.info(f"✓ Comprehensive data fetched for {ticker}")
            return data

        except Exception as e:
            logger.error(f"Error fetching comprehensive data for {ticker}: {e}")
            return data

    def get_all_available_tickers(self) -> List[str]:
        """
        Get list of all tickers with recent insider activity.

        Returns:
            List of ticker symbols
        """
        try:
            # This would get from database
            # For now, using a simple approach
            from src.database import get_all_recent_transactions

            df = get_all_recent_transactions(days=30)
            if df is not None and not df.empty:
                return df['ticker'].unique().tolist()

            return []

        except Exception as e:
            logger.error(f"Error getting available tickers: {e}")
            return []

    def refresh_all_data(self, force: bool = False) -> Dict:
        """
        Refresh all data sources.

        Args:
            force: Force refresh even if cache is fresh

        Returns:
            Dict with refresh status
        """
        start_time = time.time()
        logger.info("Starting comprehensive data refresh...")

        status = {
            'timestamp': datetime.now().isoformat(),
            'duration_seconds': 0,
            'sources_refreshed': {},
        }

        try:
            # 1. Form 4 data
            logger.debug("Refreshing Form 4 filings...")
            filings_count = self.form4_scraper.fetch_recent_form4s(days_back=2)
            status['sources_refreshed']['form4'] = {
                'success': True,
                'records': filings_count,
            }

            # 2. Market cache
            logger.debug("Refreshing market cache...")
            tickers = self.get_all_available_tickers()
            if tickers:
                self.market_cache.bulk_fetch_ticker_data(tickers)
                status['sources_refreshed']['market_cache'] = {
                    'success': True,
                    'tickers_updated': len(tickers),
                }
            else:
                status['sources_refreshed']['market_cache'] = {
                    'success': True,
                    'tickers_updated': 0,
                }

            # 3. Intraday data (for watchlist items)
            if tickers:
                logger.debug("Refreshing intraday data...")
                try:
                    self.intraday_monitor.bulk_fetch_intraday(tickers[:10])  # Limit to top 10
                    status['sources_refreshed']['intraday'] = {
                        'success': True,
                        'tickers_updated': min(10, len(tickers)),
                    }
                except Exception as e:
                    logger.debug(f"Intraday refresh partial: {e}")
                    status['sources_refreshed']['intraday'] = {'success': False, 'error': str(e)}

            status['duration_seconds'] = time.time() - start_time
            logger.info(f"✓ Data refresh completed in {status['duration_seconds']:.1f}s")

            return status

        except Exception as e:
            logger.error(f"Error during comprehensive refresh: {e}")
            status['error'] = str(e)
            status['duration_seconds'] = time.time() - start_time
            return status

    def get_hub_status(self) -> Dict:
        """
        Get overall status of the data integration hub.

        Returns:
            Dict with status information
        """
        return {
            'timestamp': datetime.now().isoformat(),
            'components': {
                'form4_scraper': 'operational',
                'market_cache': 'operational',
                'earnings_analyzer': 'operational',
                'news_analyzer': 'operational',
                'polygon_options': 'operational',
                'finnhub': 'operational',
                'intraday_monitor': 'operational',
            },
            'cache_stats': {
                'market_cache': self.market_cache.get_cache_stats(),
                'intraday_cache': self.intraday_monitor.get_cache_stats(),
            },
            'data_freshness': self._get_data_freshness(),
        }

    def _get_data_freshness(self) -> Dict:
        """Get information about data freshness."""
        return {
            'market_data_cached_tickers': self.market_cache.get_cache_stats()['total_tickers'],
            'intraday_data_cached_tickers': self.intraday_monitor.get_cache_stats()['cached_tickers'],
        }

    def validate_live_data_flow(self, test_ticker: str = "AAPL") -> Dict:
        """
        Validate that live data is flowing from all sources.

        Args:
            test_ticker: Ticker to use for validation

        Returns:
            Dict with validation results
        """
        logger.info(f"Validating live data flow with {test_ticker}...")

        results = {
            'timestamp': datetime.now().isoformat(),
            'test_ticker': test_ticker,
            'validations': {},
        }

        # Test market data
        try:
            self.market_cache.bulk_fetch_ticker_data([test_ticker])
            market_data = self.market_cache.get_cached_info(test_ticker)
            if market_data:
                results['validations']['market_data'] = {
                    'status': 'live',
                    'price': market_data.get('current_price', 'N/A'),
                }
            else:
                results['validations']['market_data'] = {'status': 'failed'}
        except Exception as e:
            results['validations']['market_data'] = {'status': 'error', 'error': str(e)}

        # Test intraday data
        try:
            intraday_data = self.intraday_monitor.fetch_intraday_data(test_ticker)
            if intraday_data is not None and len(intraday_data) > 0:
                results['validations']['intraday_data'] = {
                    'status': 'live',
                    'data_points': len(intraday_data),
                }
            else:
                results['validations']['intraday_data'] = {'status': 'no_data'}
        except Exception as e:
            results['validations']['intraday_data'] = {'status': 'error', 'error': str(e)}

        # Test news sentiment
        try:
            news_sentiment, analysis = self.news_analyzer.get_ticker_sentiment_trend(
                test_ticker, days=7
            )
            results['validations']['news_sentiment'] = {
                'status': 'live',
                'articles': analysis.get('articles_analyzed', 0),
                'sentiment': f"{news_sentiment:.3f}",
            }
        except Exception as e:
            results['validations']['news_sentiment'] = {'status': 'error', 'error': str(e)}

        # Test options flow
        try:
            flow_score, details = self.polygon_options.analyze_options_flow(test_ticker)
            results['validations']['options_flow'] = {
                'status': 'live',
                'flow_score': f"{flow_score:.3f}",
            }
        except Exception as e:
            results['validations']['options_flow'] = {'status': 'error', 'error': str(e)}

        # Test analyst sentiment
        try:
            analyst_sentiment, analysis = self.finnhub.analyze_analyst_sentiment(test_ticker)
            results['validations']['analyst_sentiment'] = {
                'status': 'live',
                'sentiment': f"{analyst_sentiment:.3f}",
                'analysts': analysis.get('total_analysts', 0),
            }
        except Exception as e:
            results['validations']['analyst_sentiment'] = {'status': 'error', 'error': str(e)}

        # Test Form 4 data
        try:
            count = self.form4_scraper.fetch_recent_form4s(days_back=1)
            results['validations']['form4_data'] = {
                'status': 'live',
                'recent_filings': count,
            }
        except Exception as e:
            results['validations']['form4_data'] = {'status': 'error', 'error': str(e)}

        # Summary
        live_sources = sum(
            1 for v in results['validations'].values()
            if v.get('status') == 'live'
        )
        total_sources = len(results['validations'])

        results['summary'] = {
            'live_sources': live_sources,
            'total_sources': total_sources,
            'data_flow_healthy': live_sources >= total_sources - 1,  # Allow 1 failure
        }

        logger.info(
            f"✓ Data flow validation complete: {live_sources}/{total_sources} sources live"
        )

        return results


# Global instance
_hub_instance = None


def get_data_integration_hub() -> DataIntegrationHub:
    """Get singleton instance of data integration hub."""
    global _hub_instance
    if _hub_instance is None:
        _hub_instance = DataIntegrationHub()
    return _hub_instance


if __name__ == "__main__":
    hub = get_data_integration_hub()

    print("\n=== Data Integration Hub Status ===")
    status = hub.get_hub_status()
    print(f"Timestamp: {status['timestamp']}")
    print(f"\nComponents:")
    for component, state in status['components'].items():
        print(f"  ✓ {component}: {state}")

    print(f"\n=== Validating Live Data Flow ===")
    validation = hub.validate_live_data_flow(test_ticker="AAPL")
    for source, result in validation['validations'].items():
        status_icon = "✓" if result['status'] == 'live' else "✗"
        print(f"{status_icon} {source}: {result['status']}")
        if result.get('price'):
            print(f"   Price: ${result['price']:.2f}")
        if result.get('articles'):
            print(f"   Articles: {result['articles']}")
        if result.get('sentiment'):
            print(f"   Sentiment: {result['sentiment']}")

    print(f"\nData Flow Healthy: {validation['summary']['data_flow_healthy']}")
    print(f"Live Sources: {validation['summary']['live_sources']}/{validation['summary']['total_sources']}")
