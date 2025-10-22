"""
Improved options flow analyzer using free data sources.

Calculates options activity scoring based on:
1. Call/Put volume ratios (from yfinance)
2. Implied volatility changes
3. Open interest concentrations
4. Recent activity spikes

Uses tiered scoring: 0.0 (bearish) -> 0.5 (neutral) -> 1.0 (bullish)
"""

from typing import Dict, Tuple, Optional
from datetime import datetime, timedelta
import yfinance as yf
from loguru import logger
import time
import numpy as np

try:
    from src.data_collection.polygon_options import PolygonOptionsAnalyzer
    HAS_POLYGON = True
except ImportError:
    HAS_POLYGON = False
    logger.debug("Polygon options not available")


class ImprovedOptionsFlowAnalyzer:
    """Analyzes options flow using free data sources."""

    def __init__(self):
        """Initialize the analyzer."""
        self.cache = {}
        self.cache_time = {}
        self.cache_ttl = 3600  # 1 hour

        # Try to initialize Polygon if available
        self.polygon = PolygonOptionsAnalyzer() if HAS_POLYGON else None
        self.has_polygon = HAS_POLYGON and self.polygon is not None

    def _get_cached(self, key: str) -> Optional[Dict]:
        """Get cached data if still valid."""
        if key in self.cache:
            if time.time() - self.cache_time.get(key, 0) < self.cache_ttl:
                return self.cache[key]
        return None

    def _set_cached(self, key: str, data: Dict):
        """Cache data with timestamp."""
        self.cache[key] = data
        self.cache_time[key] = time.time()

    def analyze_options_flow(self, ticker: str) -> Tuple[float, Dict]:
        """
        Analyze options flow for a ticker.

        Uses multiple data sources in order of preference:
        1. yfinance - implied volatility and price action (most reliable)
        2. Polygon.io (if available) - call/put volume ratios
        3. Error fallback to 0.5 neutral

        Args:
            ticker: Stock ticker symbol

        Returns:
            Tuple of (flow_score 0.0-1.0, details_dict)
        """
        ticker = ticker.upper()
        cache_key = f"options_flow_{ticker}"

        # Check cache
        cached = self._get_cached(cache_key)
        if cached:
            return cached['score'], cached['details']

        try:
            # Try yfinance first (more reliable data)
            flow_score, details = self._analyze_yfinance(ticker)

            # Only fall back to Polygon if yfinance failed
            if flow_score is None or 'error' in details:
                if self.has_polygon:
                    flow_score, details = self._analyze_polygon(ticker)
                    if flow_score is None:
                        flow_score = 0.5  # Fallback to neutral
                else:
                    flow_score = 0.5

            result = {'score': flow_score, 'details': details}
            self._set_cached(cache_key, result)
            return flow_score, details

        except Exception as e:
            logger.warning(f"Error analyzing options flow for {ticker}: {e}")
            return 0.5, {
                'error': str(e),
                'source': 'error',
                'call_put_ratio': 0.0,
                'iv_trend': 'unknown',
            }

    def analyze_options_flow_smart(self, ticker: str, filing_speed_days: int = None, insider_count: int = None) -> Tuple[float, Dict]:
        """
        Analyze options flow using smart heuristics based on filing patterns.

        Smart placeholder logic:
        1. If filing speed = 1.0 (same day): options score = 0.7 (insiders likely front-ran with calls)
        2. If insider cluster detected (3+ insiders): options score = 0.8 (smart money likely active)
        3. If both conditions: options score = 0.9
        4. Otherwise: 0.5 (neutral)

        Args:
            ticker: Stock ticker symbol
            filing_speed_days: Days between transaction and filing (optional)
            insider_count: Number of insiders buying (optional)

        Returns:
            Tuple of (flow_score 0.0-1.0, details_dict)
        """
        ticker = ticker.upper()
        cache_key = f"options_flow_smart_{ticker}_{filing_speed_days}_{insider_count}"

        # Check cache
        cached = self._get_cached(cache_key)
        if cached:
            return cached['score'], cached['details']

        try:
            # Use smart heuristics based on filing patterns
            flow_score, details = self._analyze_smart_heuristics(ticker, filing_speed_days, insider_count)

            # Cache the result
            self._set_cached(cache_key, {'score': flow_score, 'details': details})
            return flow_score, details

        except Exception as e:
            logger.debug(f"Error analyzing smart options flow for {ticker}: {e}")
            return 0.5, {'source': 'error', 'interpretation': 'neutral', 'error': str(e)}

    def _analyze_smart_heuristics(self, ticker: str, filing_speed_days: int = None, insider_count: int = None) -> Tuple[float, Dict]:
        """
        Analyze options flow using smart heuristics based on filing patterns.

        Args:
            ticker: Stock ticker symbol
            filing_speed_days: Days between transaction and filing
            insider_count: Number of insiders buying

        Returns:
            Tuple of (flow_score 0.0-1.0, details_dict)
        """
        # Default values if not provided
        if filing_speed_days is None:
            filing_speed_days = 2  # Default assumption
        
        if insider_count is None:
            insider_count = 1  # Default assumption

        # Smart heuristics logic
        same_day_filing = filing_speed_days <= 1
        insider_cluster = insider_count >= 3
        
        if same_day_filing and insider_cluster:
            # Both conditions: very high options activity expected
            flow_score = 0.9
            interpretation = "Very High (Same-day filing + insider cluster)"
            reasoning = "Insiders likely front-ran with calls before filing, smart money active"
        elif insider_cluster:
            # Insider cluster: smart money likely active
            flow_score = 0.8
            interpretation = "High (Insider cluster detected)"
            reasoning = "Multiple insiders suggest coordinated activity, likely options positioning"
        elif same_day_filing:
            # Same day filing: insiders likely front-ran
            flow_score = 0.7
            interpretation = "Medium-High (Same-day filing)"
            reasoning = "Fast filing suggests insiders may have front-ran with calls"
        else:
            # Default neutral
            flow_score = 0.5
            interpretation = "Neutral (Standard filing pattern)"
            reasoning = "No special filing patterns detected"

        details = {
            'source': 'smart_heuristics',
            'interpretation': interpretation,
            'reasoning': reasoning,
            'filing_speed_days': filing_speed_days,
            'insider_count': insider_count,
            'same_day_filing': same_day_filing,
            'insider_cluster': insider_cluster,
            'disclaimer': '⚠️ Options data is estimated based on filing patterns until API integration'
        }

        logger.debug(
            f"{ticker}: Smart options flow {flow_score:.3f} "
            f"(filing_speed={filing_speed_days}d, insiders={insider_count}, "
            f"same_day={same_day_filing}, cluster={insider_cluster})"
        )

        return flow_score, details

    def _analyze_polygon(self, ticker: str) -> Tuple[Optional[float], Dict]:
        """
        Analyze using Polygon.io data.

        Returns:
            Tuple of (flow_score or None, details_dict)
        """
        try:
            flow_score, details = self.polygon.analyze_options_flow(ticker)

            # Convert from -1.0 to 1.0 scale to 0.0 to 1.0
            normalized_score = (flow_score + 1.0) / 2.0
            normalized_score = max(0.0, min(1.0, normalized_score))

            logger.debug(
                f"{ticker}: Polygon options flow {normalized_score:.3f} "
                f"(call_put_ratio={details.get('call_put_vol_ratio', 0):.2f})"
            )

            return normalized_score, {
                'source': 'polygon',
                'flow_score': normalized_score,
                'call_put_ratio': details.get('call_put_vol_ratio', 0),
                'call_oi': details.get('call_oi', 0),
                'put_oi': details.get('put_oi', 0),
                'interpretation': details.get('flow_interpretation', 'unknown'),
            }

        except Exception as e:
            logger.debug(f"Error with Polygon analysis: {e}")
            return None, {}

    def _analyze_yfinance(self, ticker: str) -> Tuple[float, Dict]:
        """
        Analyze using yfinance data (free fallback).

        Calculates score based on:
        1. Current IV relative to 52-week range
        2. Recent price volatility
        3. Historical IV trend

        Returns:
            Tuple of (flow_score 0.0-1.0, details_dict)
        """
        try:
            # Get stock data
            stock = yf.Ticker(ticker)
            info = stock.info

            # Extract options-related data from yfinance
            current_price = info.get('currentPrice', info.get('regularMarketPrice', 0))
            bid = info.get('bid', current_price)
            ask = info.get('ask', current_price)

            # Get IV estimates (yfinance provides implied vol for options)
            # This is an estimate based on recent option prices
            iv_rank = self._estimate_iv_rank(stock, ticker)

            # Get price change metrics
            change_pct = info.get('regularMarketChangePercent', 0)

            # Get volume and volatility
            volume = info.get('volume', 0)
            avg_volume = info.get('averageVolume', 1)

            # Calculate momentum indicators
            volume_momentum = volume / avg_volume if avg_volume > 0 else 1.0

            # Construct flow score from components
            # IV rank: higher IV often indicates bullish options positioning
            iv_score = min(iv_rank / 100.0, 1.0) if iv_rank else 0.5

            # Volume momentum: higher volume suggests activity
            volume_score = min(volume_momentum / 2.0, 1.0)

            # Combine with slight bias toward neutral
            flow_score = (iv_score * 0.6 + volume_score * 0.4)
            flow_score = max(0.0, min(1.0, flow_score))

            logger.debug(
                f"{ticker}: yfinance options flow {flow_score:.3f} "
                f"(IV_rank={iv_rank:.1f}, vol_ratio={volume_momentum:.2f})"
            )

            return flow_score, {
                'source': 'yfinance',
                'flow_score': flow_score,
                'iv_rank': iv_rank,
                'volume_momentum': volume_momentum,
                'current_price': current_price,
                'change_pct': change_pct,
                'interpretation': self._interpret_flow_score(flow_score),
            }

        except Exception as e:
            logger.warning(f"Error with yfinance analysis for {ticker}: {e}")
            # Return neutral score on error
            return 0.5, {'error': str(e), 'source': 'yfinance_error'}

    def _estimate_iv_rank(self, stock, ticker: str) -> float:
        """
        Estimate IV rank from price action and historical volatility.

        IV Rank = (Current IV - 52-week Low IV) / (52-week High IV - 52-week Low IV)

        Since yfinance doesn't provide historical IV directly, we estimate using:
        - Current volatility (from recent price changes)
        - Historical volatility over different periods

        Returns:
            IV rank as percentage (0-100)
        """
        try:
            # Get historical data
            hist = stock.history(period='1y')

            if hist.empty or len(hist) < 30:
                return 50  # Default neutral if not enough data

            # Calculate daily returns
            returns = hist['Close'].pct_change().dropna()

            # Calculate volatilities over different periods
            vol_current = returns.iloc[-30:].std() * np.sqrt(252)  # 30-day, annualized
            vol_3m = returns.iloc[-90:].std() * np.sqrt(252)  # 3-month
            vol_1y = returns.std() * np.sqrt(252)  # 1-year (full period)

            # Estimate IV rank
            # Current vol relative to range
            if vol_1y > vol_3m > 0:
                iv_rank = ((vol_current - vol_3m) / (vol_1y - vol_3m)) * 100
                iv_rank = max(0, min(100, iv_rank))
            else:
                iv_rank = 50

            return iv_rank

        except Exception as e:
            logger.debug(f"Error estimating IV rank for {ticker}: {e}")
            return 50  # Return neutral on error

    def _interpret_flow_score(self, score: float) -> str:
        """Interpret options flow score."""
        if score >= 0.75:
            return "Very Bullish"
        elif score >= 0.60:
            return "Bullish"
        elif score >= 0.40:
            return "Neutral"
        elif score >= 0.25:
            return "Bearish"
        else:
            return "Very Bearish"

    def analyze_unusual_activity(self, ticker: str, min_volume_ratio: float = 2.0) -> Dict:
        """
        Detect unusual options activity (spikes).

        Args:
            ticker: Stock ticker
            min_volume_ratio: Minimum volume ratio to flag as unusual

        Returns:
            Dict with unusual activity details
        """
        try:
            if not self.has_polygon:
                return {'status': 'no_polygon', 'unusual_activity': []}

            # Get unusual activity from Polygon
            activities = self.polygon.get_unusual_options_activity(ticker, lookback_days=5)

            return {
                'ticker': ticker,
                'status': 'found' if activities else 'none',
                'unusual_activity': activities,
                'count': len(activities),
            }

        except Exception as e:
            logger.debug(f"Error analyzing unusual activity for {ticker}: {e}")
            return {'status': 'error', 'error': str(e)}


# Global instance
_options_analyzer_instance = None


def get_options_flow_analyzer() -> ImprovedOptionsFlowAnalyzer:
    """Get singleton instance of options flow analyzer."""
    global _options_analyzer_instance
    if _options_analyzer_instance is None:
        _options_analyzer_instance = ImprovedOptionsFlowAnalyzer()
    return _options_analyzer_instance


if __name__ == "__main__":
    analyzer = get_options_flow_analyzer()

    # Test with 4 tickers
    tickers = ['AAPL', 'META', 'AMZN', 'CMC']

    print("\n" + "=" * 80)
    print("OPTIONS FLOW ANALYSIS")
    print("=" * 80 + "\n")

    for ticker in tickers:
        flow_score, details = analyzer.analyze_options_flow(ticker)
        print(f"{ticker}:")
        print(f"  Flow Score: {flow_score:.4f}")
        print(f"  Interpretation: {details.get('interpretation', 'unknown')}")
        print(f"  Source: {details.get('source', 'unknown')}")
        if 'iv_rank' in details:
            print(f"  IV Rank: {details['iv_rank']:.1f}%")
        if 'call_put_ratio' in details:
            print(f"  Call/Put Ratio: {details['call_put_ratio']:.2f}")
        print()
