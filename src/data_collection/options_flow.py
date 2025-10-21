"""Options flow analysis for precursor signals."""
from typing import Dict, List, Tuple, Optional
from datetime import datetime, timedelta
import os
import yfinance as yf
from loguru import logger
import requests
import time


class OptionsFlowAnalyzer:
    """Analyzes options flow for precursor bullish signals."""

    def __init__(self):
        """Initialize options flow analyzer."""
        self.cache = {}
        self.cache_time = {}
        self.cache_ttl = 3600  # 1 hour

        # Optional API keys
        self.unusual_whales_key = os.getenv("UNUSUAL_WHALES_KEY")
        self.flowalgo_key = os.getenv("FLOWALGO_KEY")

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

    def analyze_precursor_flow(
        self, ticker: str, filing_date: datetime, lookback_days: int = 10
    ) -> Dict:
        """
        Analyze unusual options activity BEFORE insider filing.

        Precursor score indicates if options market was pricing in buying activity
        before it was disclosed via Form 4.

        Args:
            ticker: Stock ticker
            filing_date: Date Form 4 was filed
            lookback_days: Days before filing to analyze (default 10)

        Returns:
            Dict with precursor_score and details
        """
        ticker = ticker.upper()
        cache_key = f"precursor_{ticker}_{filing_date.strftime('%Y%m%d')}"

        # Check cache
        cached = self._get_cached(cache_key)
        if cached:
            return cached

        try:
            # Try paid API first
            if self.unusual_whales_key:
                return self._analyze_precursor_api(ticker, filing_date, lookback_days)

            # Fallback to free yfinance data
            return self._analyze_precursor_free(ticker, filing_date, lookback_days)

        except Exception as e:
            logger.error(f"Error analyzing precursor flow for {ticker}: {e}")
            return {
                'ticker': ticker,
                'precursor_score': 0.0,
                'error': str(e),
                'source': 'error',
            }

    def _analyze_precursor_api(
        self, ticker: str, filing_date: datetime, lookback_days: int
    ) -> Dict:
        """Analyze using paid API (Unusual Whales, FlowAlgo, etc)."""
        try:
            # Unusual Whales API example
            start_date = filing_date - timedelta(days=lookback_days)
            url = f"https://api.unusualwhales.com/v1/options/{ticker}/flow"

            headers = {
                "Authorization": f"Bearer {self.unusual_whales_key}",
                "Accept": "application/json",
            }

            params = {
                "from_date": start_date.strftime('%Y-%m-%d'),
                "to_date": filing_date.strftime('%Y-%m-%d'),
                "sentiment": "bullish",
            }

            response = requests.get(url, headers=headers, params=params, timeout=10)
            response.raise_for_status()

            data = response.json()
            calls = data.get('calls', [])

            # Count large calls
            large_calls = [c for c in calls if c.get('premium_paid', 0) > 25000]
            large_call_count = len(large_calls)

            # Calculate OI increase z-score
            oi_values = [c.get('open_interest', 0) for c in calls]
            oi_mean = sum(oi_values) / len(oi_values) if oi_values else 0
            oi_std = (
                sum((x - oi_mean) ** 2 for x in oi_values) / len(oi_values)
            ) ** 0.5
            oi_increase_zscore = (oi_values[-1] - oi_mean) / (oi_std + 1e-6) if oi_values else 0

            # Call/Put ratio
            puts = data.get('puts', [])
            cp_ratio = len(calls) / (len(puts) + 1) if puts else len(calls)

            # Calculate precursor score
            precursor_score = 0.0
            factors = []

            if large_call_count >= 5:
                precursor_score += 0.4
                factors.append(f"{large_call_count} large calls (>$25k)")
            elif large_call_count >= 3:
                precursor_score += 0.25
                factors.append(f"{large_call_count} large calls (>$25k)")

            if oi_increase_zscore > 2.0:
                precursor_score += 0.3
                factors.append(f"OI increase {oi_increase_zscore:.1f}σ above mean")

            if cp_ratio > 2.0:
                precursor_score += 0.3
                factors.append(f"Call/Put ratio {cp_ratio:.2f}")

            precursor_score = min(precursor_score, 1.0)

            result = {
                'ticker': ticker,
                'precursor_score': precursor_score,
                'large_call_count': large_call_count,
                'oi_increase_zscore': oi_increase_zscore,
                'call_put_ratio': cp_ratio,
                'factors': factors,
                'source': 'unusual_whales_api',
            }

            self._set_cached(f"precursor_{ticker}_{filing_date.strftime('%Y%m%d')}", result)
            logger.debug(f"API precursor flow for {ticker}: {precursor_score:.3f}")

            return result

        except Exception as e:
            logger.debug(f"API analysis failed, falling back to free data: {e}")
            return self._analyze_precursor_free(ticker, filing_date, lookback_days)

    def _analyze_precursor_free(
        self, ticker: str, filing_date: datetime, lookback_days: int
    ) -> Dict:
        """
        Free fallback: analyze using yfinance options data.

        Looks for unusual volume and OI spikes before filing date.
        """
        try:
            stock = yf.Ticker(ticker)

            # Get options chains for dates near filing
            precursor_score = 0.0
            factors = []
            large_call_count = 0
            avg_cp_ratio = 1.0

            start_date = filing_date - timedelta(days=lookback_days)
            analysis_dates = pd.date_range(start=start_date, end=filing_date, freq='D')

            call_volumes = []
            put_volumes = []

            # Analyze recent options data (yfinance has 1 month of options)
            try:
                options = stock.options[-10:] if stock.options else []

                for exp_date in options:
                    try:
                        opt_chain = stock.option_chain(exp_date)

                        # Calls analysis
                        calls = opt_chain.calls
                        puts = opt_chain.puts

                        # Find unusual call volume
                        high_vol_calls = calls[calls['volume'] > calls['volume'].quantile(0.75)]
                        large_calls = high_vol_calls[high_vol_calls['lastPrice'] > 1.0]

                        if len(large_calls) > 0:
                            large_call_count += len(large_calls)
                            call_volumes.extend(large_calls['volume'].tolist())

                        put_volumes.extend(puts['volume'].tolist())

                    except Exception as e:
                        logger.debug(f"Error getting options for {exp_date}: {e}")
                        continue

                # Score based on yfinance data
                if large_call_count >= 3:
                    precursor_score += 0.25
                    factors.append(f"{large_call_count} high-volume calls detected")

                if call_volumes and put_volumes:
                    avg_call_vol = sum(call_volumes) / len(call_volumes)
                    avg_put_vol = sum(put_volumes) / len(put_volumes)
                    avg_cp_ratio = avg_call_vol / (avg_put_vol + 1e-6)

                    if avg_cp_ratio > 2.0:
                        precursor_score += 0.15
                        factors.append(f"Call volume {avg_cp_ratio:.1f}x put volume")

                    # Check for volume spikes
                    if avg_call_vol > 50000:
                        precursor_score += 0.15
                        factors.append("Unusual call volume spike detected")

            except Exception as e:
                logger.debug(f"Error analyzing options chain: {e}")

            precursor_score = min(precursor_score, 0.6)  # Cap free score lower

            result = {
                'ticker': ticker,
                'precursor_score': precursor_score,
                'large_call_count': large_call_count,
                'call_put_ratio': avg_cp_ratio,
                'factors': factors,
                'source': 'yfinance_free',
                'note': 'Free data - paid API would provide more accuracy',
            }

            self._set_cached(f"precursor_{ticker}_{filing_date.strftime('%Y%m%d')}", result)
            logger.debug(f"Free precursor flow for {ticker}: {precursor_score:.3f}")

            return result

        except Exception as e:
            logger.error(f"Error in free precursor analysis: {e}")
            return {
                'ticker': ticker,
                'precursor_score': 0.0,
                'factors': ['Free analysis unavailable'],
                'source': 'yfinance_free',
                'error': str(e),
            }

    def get_current_flow(self, ticker: str) -> Dict:
        """Get real-time options flow (last 24 hours)."""
        ticker = ticker.upper()
        cache_key = f"current_flow_{ticker}"

        # Check cache
        cached = self._get_cached(cache_key)
        if cached:
            return cached

        try:
            if self.unusual_whales_key:
                return self._get_current_flow_api(ticker)
            else:
                return self._get_current_flow_free(ticker)

        except Exception as e:
            logger.error(f"Error getting current flow for {ticker}: {e}")
            return {
                'ticker': ticker,
                'current_bullish_flow': 0.0,
                'error': str(e),
            }

    def _get_current_flow_api(self, ticker: str) -> Dict:
        """Get real-time flow from API."""
        try:
            url = f"https://api.unusualwhales.com/v1/options/{ticker}/flow"
            headers = {"Authorization": f"Bearer {self.unusual_whales_key}"}

            response = requests.get(url, headers=headers, timeout=10)
            response.raise_for_status()

            data = response.json()
            bullish_count = data.get('bullish_count', 0)
            bearish_count = data.get('bearish_count', 0)
            neutral_count = data.get('neutral_count', 0)

            total = bullish_count + bearish_count + neutral_count
            bullish_ratio = bullish_count / total if total > 0 else 0.5

            result = {
                'ticker': ticker,
                'current_bullish_flow': bullish_ratio,
                'bullish_count': bullish_count,
                'bearish_count': bearish_count,
                'source': 'api',
            }

            self._set_cached(f"current_flow_{ticker}", result)
            return result

        except Exception as e:
            logger.debug(f"API current flow failed: {e}")
            return self._get_current_flow_free(ticker)

    def _get_current_flow_free(self, ticker: str) -> Dict:
        """Free fallback for current flow."""
        try:
            stock = yf.Ticker(ticker)

            # Check latest options for volume
            if not stock.options:
                return {
                    'ticker': ticker,
                    'current_bullish_flow': 0.5,
                    'note': 'No options data available',
                }

            latest_exp = stock.options[-1]
            opt_chain = stock.option_chain(latest_exp)

            calls = opt_chain.calls
            puts = opt_chain.puts

            call_volume = calls['volume'].sum()
            put_volume = puts['volume'].sum()

            total_volume = call_volume + put_volume
            bullish_ratio = call_volume / total_volume if total_volume > 0 else 0.5

            result = {
                'ticker': ticker,
                'current_bullish_flow': bullish_ratio,
                'call_volume': call_volume,
                'put_volume': put_volume,
                'source': 'yfinance_free',
            }

            self._set_cached(f"current_flow_{ticker}", result)
            return result

        except Exception as e:
            logger.debug(f"Error getting current flow: {e}")
            return {
                'ticker': ticker,
                'current_bullish_flow': 0.5,
                'error': str(e),
            }


if __name__ == "__main__":
    import pandas as pd

    analyzer = OptionsFlowAnalyzer()

    # Test precursor analysis
    filing_date = datetime.now()
    result = analyzer.analyze_precursor_flow("AAPL", filing_date)
    print(f"\nPrecursor Flow for AAPL:")
    print(f"  Score: {result['precursor_score']:.3f}")
    print(f"  Factors: {result.get('factors', [])}")
    print(f"  Source: {result.get('source', 'unknown')}")

    # Test current flow
    flow = analyzer.get_current_flow("AAPL")
    print(f"\nCurrent Flow for AAPL:")
    print(f"  Bullish Ratio: {flow['current_bullish_flow']:.2%}")
