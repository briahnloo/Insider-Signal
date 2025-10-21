"""Market data caching layer for efficient yfinance API usage."""
from typing import Dict, List, Optional, Tuple
from datetime import datetime, timedelta
import yfinance as yf
import pandas as pd
from loguru import logger
import time
import threading

import config


class MarketDataCache:
    """Centralized cache for market data from yfinance."""

    def __init__(self):
        """Initialize the market data cache."""
        self.price_cache = {}
        self.short_interest_cache = {}
        self.options_cache = {}
        self.info_cache = {}
        
        self.price_ttl = config.CACHE_TTL_HOURS * 3600  # 4 hours default
        self.info_ttl = 86400  # 24 hours for fundamental data
        
        self.cache_timestamps = {}
        self.lock = threading.Lock()
        
        logger.info("Market data cache initialized")

    def bulk_fetch_ticker_data(self, tickers: List[str]) -> Dict[str, Dict]:
        """
        Bulk fetch market data for multiple tickers.

        Args:
            tickers: List of ticker symbols

        Returns:
            Dict mapping ticker to data dict
        """
        logger.info(f"Bulk fetching data for {len(tickers)} tickers")
        results = {}
        
        for ticker in tickers:
            try:
                data = self._fetch_ticker_data(ticker)
                if data:
                    results[ticker] = data
                    self._cache_ticker_data(ticker, data)
                
                # Rate limiting: 0.5 second between requests
                time.sleep(0.5)
                
            except Exception as e:
                logger.debug(f"Failed to fetch data for {ticker}: {e}")
                continue

        logger.info(f"Successfully fetched data for {len(results)} tickers")
        return results

    def _fetch_ticker_data(self, ticker: str) -> Optional[Dict]:
        """
        Fetch all relevant data for a single ticker.

        Args:
            ticker: Stock ticker symbol

        Returns:
            Dict with price, short interest, and info data
        """
        try:
            stock = yf.Ticker(ticker)
            info = stock.info
            
            # Get price history (60 days for technical analysis)
            hist = stock.history(period='60d')
            
            data = {
                'ticker': ticker,
                'current_price': info.get('currentPrice', 0),
                'volume': info.get('volume', 0),
                'avg_volume': info.get('averageVolume', 0),
                'short_interest_pct': info.get('shortPercentOfFloat', 0) * 100,
                'shares_short': info.get('sharesShort', 0),
                'shares_outstanding': info.get('sharesOutstanding', 0),
                'market_cap': info.get('marketCap', 0),
                'price_history': hist,
                'sector': info.get('sector', 'Unknown'),
                'industry': info.get('industry', 'Unknown'),
                'earnings_date': info.get('earningsDate'),
                'fetched_at': datetime.now(),
            }
            
            return data
            
        except Exception as e:
            logger.debug(f"Error fetching data for {ticker}: {e}")
            return None

    def _cache_ticker_data(self, ticker: str, data: Dict):
        """
        Cache ticker data with timestamp.

        Args:
            ticker: Stock ticker symbol
            data: Data dict to cache
        """
        with self.lock:
            # Cache price data
            if 'price_history' in data:
                self.price_cache[ticker] = data['price_history']
            
            # Cache short interest
            self.short_interest_cache[ticker] = {
                'short_interest_pct': data.get('short_interest_pct', 0),
                'shares_short': data.get('shares_short', 0),
                'shares_outstanding': data.get('shares_outstanding', 0),
                'avg_volume': data.get('avg_volume', 0),
            }
            
            # Cache info
            self.info_cache[ticker] = {
                'current_price': data.get('current_price', 0),
                'market_cap': data.get('market_cap', 0),
                'sector': data.get('sector', 'Unknown'),
                'industry': data.get('industry', 'Unknown'),
                'earnings_date': data.get('earnings_date'),
            }
            
            # Update timestamp
            self.cache_timestamps[ticker] = time.time()

    def get_cached_short_interest(self, ticker: str) -> Optional[Dict]:
        """
        Get cached short interest data.

        Args:
            ticker: Stock ticker symbol

        Returns:
            Short interest dict or None if not cached/stale
        """
        with self.lock:
            if ticker not in self.short_interest_cache:
                return None
            
            # Check if cache is stale
            cache_time = self.cache_timestamps.get(ticker, 0)
            if time.time() - cache_time > self.info_ttl:
                return None
            
            return self.short_interest_cache[ticker]

    def get_cached_price_history(self, ticker: str, days: int = 60) -> Optional[pd.DataFrame]:
        """
        Get cached price history.

        Args:
            ticker: Stock ticker symbol
            days: Number of days requested

        Returns:
            DataFrame with price history or None
        """
        with self.lock:
            if ticker not in self.price_cache:
                return None
            
            # Check if cache is stale
            cache_time = self.cache_timestamps.get(ticker, 0)
            if time.time() - cache_time > self.price_ttl:
                return None
            
            hist = self.price_cache[ticker]
            
            # Filter to requested days
            if len(hist) > 0:
                cutoff = datetime.now() - timedelta(days=days)
                return hist[hist.index >= cutoff]
            
            return hist

    def get_cached_info(self, ticker: str) -> Optional[Dict]:
        """
        Get cached ticker info.

        Args:
            ticker: Stock ticker symbol

        Returns:
            Info dict or None if not cached/stale
        """
        with self.lock:
            if ticker not in self.info_cache:
                return None
            
            # Check if cache is stale
            cache_time = self.cache_timestamps.get(ticker, 0)
            if time.time() - cache_time > self.info_ttl:
                return None
            
            return self.info_cache[ticker]

    def refresh_cache(self, tickers: Optional[List[str]] = None):
        """
        Refresh stale cache entries.

        Args:
            tickers: List of tickers to refresh (None = refresh all stale)
        """
        if tickers is None:
            # Find stale tickers
            with self.lock:
                now = time.time()
                tickers = [
                    ticker for ticker, cache_time in self.cache_timestamps.items()
                    if now - cache_time > self.price_ttl
                ]
        
        if tickers:
            logger.info(f"Refreshing cache for {len(tickers)} tickers")
            self.bulk_fetch_ticker_data(tickers)

    def get_cache_stats(self) -> Dict:
        """
        Get cache statistics.

        Returns:
            Dict with cache stats
        """
        with self.lock:
            now = time.time()
            fresh = sum(
                1 for cache_time in self.cache_timestamps.values()
                if now - cache_time <= self.price_ttl
            )
            stale = len(self.cache_timestamps) - fresh
            
            return {
                'total_tickers': len(self.cache_timestamps),
                'fresh_entries': fresh,
                'stale_entries': stale,
                'price_cache_size': len(self.price_cache),
                'si_cache_size': len(self.short_interest_cache),
                'info_cache_size': len(self.info_cache),
            }

    def clear_cache(self):
        """Clear all cached data."""
        with self.lock:
            self.price_cache.clear()
            self.short_interest_cache.clear()
            self.options_cache.clear()
            self.info_cache.clear()
            self.cache_timestamps.clear()
            logger.info("Cache cleared")


# Global cache instance
_cache_instance = None


def get_market_cache() -> MarketDataCache:
    """
    Get the global market cache instance.

    Returns:
        MarketDataCache singleton
    """
    global _cache_instance
    if _cache_instance is None:
        _cache_instance = MarketDataCache()
    return _cache_instance


if __name__ == "__main__":
    # Test the cache
    cache = get_market_cache()
    
    # Test with a few tickers
    test_tickers = ['AAPL', 'MSFT', 'GOOGL']
    results = cache.bulk_fetch_ticker_data(test_tickers)
    
    print(f"\nFetched data for {len(results)} tickers")
    print(f"Cache stats: {cache.get_cache_stats()}")
    
    # Test retrieval
    for ticker in test_tickers:
        si = cache.get_cached_short_interest(ticker)
        if si:
            print(f"{ticker} short interest: {si['short_interest_pct']:.2f}%")

