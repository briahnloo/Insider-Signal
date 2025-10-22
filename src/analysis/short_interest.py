"""Short interest analysis and squeeze potential scoring."""
from typing import Dict, Optional, Tuple
import yfinance as yf
from datetime import datetime
from loguru import logger
import time

from src.data_collection.market_data import get_short_interest
from src.data_collection.market_data_cache import get_market_cache


class ShortInterestAnalyzer:
    """Analyzes short interest for squeeze potential."""

    def __init__(self):
        self.market_cache = get_market_cache()
        self.cache = {}
        self.cache_time = {}
        self.cache_ttl = 3600  # 1 hour cache

    def fetch_short_interest(self, ticker: str) -> Dict:
        """
        Fetch short interest data for a ticker.

        Args:
            ticker: Stock ticker symbol

        Returns:
            Dict with short_interest_pct, days_to_cover
        """
        ticker = ticker.upper()

        # Try market cache first
        cached_si = self.market_cache.get_cached_short_interest(ticker)
        if cached_si:
            cached_si['ticker'] = ticker
            cached_si['days_to_cover'] = self._calculate_days_to_cover(
                cached_si.get('shares_short', 0),
                cached_si.get('avg_volume', 0)
            )
            logger.debug(f"Using cached SI data for {ticker}: {cached_si['short_interest_pct']:.2f}%")
            return cached_si

        # Check local cache
        if ticker in self.cache:
            if time.time() - self.cache_time.get(ticker, 0) < self.cache_ttl:
                return self.cache[ticker]

        try:
            # Fallback to direct yfinance if not in market cache
            stock = yf.Ticker(ticker)
            info = stock.info

            data = {
                'ticker': ticker,
                'short_interest_pct': info.get('shortPercentOfFloat', 0) * 100,
                'short_shares': info.get('sharesShort', 0),
                'shares_outstanding': info.get('sharesOutstanding', 0),
                'avg_volume': info.get('averageVolume', 0),
                'current_price': info.get('currentPrice', 0),
                'days_to_cover': self._calculate_days_to_cover(
                    info.get('sharesShort', 0),
                    info.get('averageVolume', 0)
                ),
            }

            # Cache the result locally
            self.cache[ticker] = data
            self.cache_time[ticker] = time.time()

            logger.debug(f"Fetched SI data for {ticker}: {data['short_interest_pct']:.2f}%")
            return data

        except Exception as e:
            logger.warning(f"Failed to fetch SI data for {ticker}: {e}")
            return {
                'ticker': ticker,
                'short_interest_pct': 0,
                'short_shares': 0,
                'shares_outstanding': 0,
                'avg_volume': 0,
                'current_price': 0,
                'days_to_cover': 0,
                'error': str(e)
            }

    def _calculate_days_to_cover(self, short_shares: int, avg_volume: int) -> float:
        """Calculate days to cover using short shares / daily volume."""
        if avg_volume <= 0:
            return 0
        return short_shares / avg_volume

    def calculate_short_interest_score(self, ticker: str) -> Tuple[float, Dict]:
        """
        Calculate short interest score (0.0 to 1.0) using real data.
        
        New scoring logic:
        - <5%: score 0.2 (was 0.0)
        - 5-10%: score 0.4
        - 10-20%: score 0.7
        - >20%: score 1.0

        Args:
            ticker: Stock ticker

        Returns:
            Tuple of (score, details_dict)
        """
        # Use the new market_data module for real short interest
        si_pct = get_short_interest(ticker)
        
        if si_pct is None:
            # Fallback to old method if new one fails
            si_data = self.fetch_short_interest(ticker)
            if 'error' in si_data:
                return 0.0, {'ticker': ticker, 'short_interest_pct': 0, 'error': 'No data available'}
            si_pct = si_data['short_interest_pct']

        # New scoring logic
        if si_pct >= 20:
            score = 1.0
            category = "Very High"
        elif si_pct >= 10:
            score = 0.7
            category = "High"
        elif si_pct >= 5:
            score = 0.4
            category = "Medium"
        else:
            score = 0.2
            category = "Low"

        details = {
            'ticker': ticker,
            'short_interest_pct': si_pct,
            'score': score,
            'category': category,
            'method': 'real_data'
        }

        logger.debug(f"Short interest score for {ticker}: {score:.2f} ({si_pct:.2f}% - {category})")
        return score, details

    def calculate_squeeze_potential(self, ticker: str) -> Tuple[float, Dict]:
        """
        Calculate squeeze potential multiplier (1.0 to 1.5x).

        High SI (>20%) + High DTC (>5 days) = strong squeeze potential

        Args:
            ticker: Stock ticker

        Returns:
            Tuple of (multiplier, details_dict)
        """
        si_data = self.fetch_short_interest(ticker)

        if 'error' in si_data:
            return 1.0, si_data

        si_pct = si_data['short_interest_pct']
        dtc = si_data['days_to_cover']

        # Scoring logic
        multiplier = 1.0
        factors = []

        if si_pct > 20:
            if dtc > 5:
                multiplier = 1.5  # Extreme squeeze potential
                factors.append(f"High SI {si_pct:.1f}% + High DTC {dtc:.1f}")
            elif dtc > 3:
                multiplier = 1.3  # Strong squeeze
                factors.append(f"High SI {si_pct:.1f}% + Medium DTC {dtc:.1f}")
            else:
                multiplier = 1.2  # Moderate
                factors.append(f"High SI {si_pct:.1f}% + Low DTC {dtc:.1f}")
        elif si_pct > 15:
            if dtc > 5:
                multiplier = 1.3
                factors.append(f"Medium-High SI {si_pct:.1f}% + High DTC {dtc:.1f}")
            else:
                multiplier = 1.1
                factors.append(f"Medium-High SI {si_pct:.1f}%")
        elif si_pct > 10:
            if dtc > 5:
                multiplier = 1.2
                factors.append(f"Medium SI {si_pct:.1f}% + High DTC {dtc:.1f}")
            else:
                multiplier = 1.05
        else:
            factors.append("Low or no squeeze potential")

        details = {
            'ticker': ticker,
            'short_interest_pct': si_pct,
            'days_to_cover': dtc,
            'squeeze_multiplier': multiplier,
            'squeeze_factors': factors,
        }

        logger.debug(f"Squeeze analysis for {ticker}: {multiplier}x")
        return multiplier, details


if __name__ == "__main__":
    analyzer = ShortInterestAnalyzer()

    # Test with a ticker
    ticker = "AAPL"
    mult, details = analyzer.calculate_squeeze_potential(ticker)
    print(f"\n{ticker}:")
    print(f"  SI: {details['short_interest_pct']:.2f}%")
    print(f"  DTC: {details['days_to_cover']:.1f} days")
    print(f"  Multiplier: {mult}x")
    print(f"  Factors: {', '.join(details['squeeze_factors'])}")
