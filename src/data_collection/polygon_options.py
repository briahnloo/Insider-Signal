"""
Polygon.io integration for free options market data.
Polygon provides free tier options data without API key requirement for basic queries.
"""
from typing import Dict, List, Optional, Tuple
from datetime import datetime, timedelta
import requests
from loguru import logger
import time
import os
import json

# Polygon.io endpoints
POLYGON_BASE_URL = "https://api.polygon.io/v3"


class PolygonOptionsAnalyzer:
    """Options market data analyzer using Polygon.io."""

    def __init__(self, api_key: Optional[str] = None):
        """
        Initialize Polygon options analyzer.

        Args:
            api_key: Polygon API key (optional, for better rate limits)
        """
        self.api_key = api_key or os.getenv("POLYGON_API_KEY", "")
        self.base_url = POLYGON_BASE_URL
        self.cache = {}
        self.cache_time = {}
        self.cache_ttl = 3600  # 1 hour
        self.user_agent = "Intelligent-Trader/1.0"

        if not self.api_key:
            logger.debug("Polygon API key not provided - using free tier with rate limits")

    def _make_request(self, endpoint: str, params: Dict) -> Optional[Dict]:
        """
        Make request to Polygon API.

        Args:
            endpoint: API endpoint
            params: Query parameters

        Returns:
            Response JSON or None
        """
        try:
            if self.api_key:
                params['apiKey'] = self.api_key

            url = f"{self.base_url}/{endpoint}"
            headers = {'User-Agent': self.user_agent}

            response = requests.get(url, params=params, headers=headers, timeout=10)

            if response.status_code == 200:
                return response.json()
            elif response.status_code == 429:
                logger.warning("Polygon rate limit exceeded")
                return None
            else:
                logger.debug(f"Polygon error {response.status_code}")
                return None

        except Exception as e:
            logger.debug(f"Error making Polygon request: {e}")
            return None

    def get_options_chain_data(
        self, ticker: str, expiration_date: Optional[str] = None
    ) -> Dict[str, List[Dict]]:
        """
        Get options chain data for a ticker.

        Args:
            ticker: Stock ticker
            expiration_date: Specific expiration (YYYY-MM-DD format), or None for all

        Returns:
            Dict with 'calls' and 'puts' lists
        """
        ticker = ticker.upper()
        cache_key = f"chain_{ticker}_{expiration_date or 'all'}"

        # Check cache
        if cache_key in self.cache:
            if time.time() - self.cache_time.get(cache_key, 0) < self.cache_ttl:
                return self.cache[cache_key]

        try:
            # Try to get options contracts
            params = {
                'underlying_ticker.gte': ticker,
                'underlying_ticker.lt': chr(ord(ticker[0]) + 1),  # Crude filtering
                'order': 'desc',
                'sort': 'expiration_date',
                'limit': 1000,
            }

            if expiration_date:
                params['expiration_date'] = expiration_date

            data = self._make_request('snapshot/options', params)

            if data and 'results' in data:
                results = data['results']

                # Organize by calls and puts
                chain = {
                    'calls': [r for r in results if r.get('details', {}).get('contract_type') == 'call'],
                    'puts': [r for r in results if r.get('details', {}).get('contract_type') == 'put'],
                }

                self.cache[cache_key] = chain
                self.cache_time[cache_key] = time.time()

                logger.debug(f"Got options chain for {ticker}: {len(chain['calls'])} calls, {len(chain['puts'])} puts")
                return chain

            return {'calls': [], 'puts': []}

        except Exception as e:
            logger.debug(f"Error getting options chain for {ticker}: {e}")
            return {'calls': [], 'puts': []}

    def analyze_options_flow(
        self, ticker: str, expiration_date: Optional[str] = None
    ) -> Tuple[float, Dict]:
        """
        Analyze options flow and market positioning.

        Args:
            ticker: Stock ticker
            expiration_date: Specific expiration date

        Returns:
            Tuple of (flow_score -1.0 to 1.0 where 1.0 = bullish, analysis_details)
        """
        try:
            chain = self.get_options_chain_data(ticker, expiration_date)

            if not chain['calls'] and not chain['puts']:
                return 0.0, {'status': 'no_data'}

            # Analyze call vs put volume and open interest
            call_volume = sum(c.get('last_quote', {}).get('size', 0) for c in chain['calls'])
            put_volume = sum(p.get('last_quote', {}).get('size', 0) for p in chain['puts'])

            call_oi = sum(c.get('open_interest', 0) for c in chain['calls'])
            put_oi = sum(p.get('open_interest', 0) for p in chain['puts'])

            # Calculate ratios
            call_put_vol_ratio = call_volume / put_volume if put_volume > 0 else 1.0
            call_put_oi_ratio = call_oi / put_oi if put_oi > 0 else 1.0

            # Analyze ITM vs OTM for calls and puts
            calls_itm = sum(
                1 for c in chain['calls']
                if c.get('last_quote', {}).get('ask', 0) > 0  # Simple proxy
            )
            calls_total = len(chain['calls']) if chain['calls'] else 1

            puts_itm = sum(
                1 for p in chain['puts']
                if p.get('last_quote', {}).get('ask', 0) > 0
            )
            puts_total = len(chain['puts']) if chain['puts'] else 1

            # Calculate bullish score
            # Ratios > 1.2 indicate bullish positioning
            vol_score = (call_put_vol_ratio - 1.0) / 2.0  # Normalize
            oi_score = (call_put_oi_ratio - 1.0) / 2.0

            # Combine into flow score
            flow_score = (vol_score + oi_score) / 2.0
            flow_score = max(-1.0, min(1.0, flow_score))

            return flow_score, {
                'call_volume': int(call_volume),
                'put_volume': int(put_volume),
                'call_put_vol_ratio': float(call_put_vol_ratio),
                'call_oi': int(call_oi),
                'put_oi': int(put_oi),
                'call_put_oi_ratio': float(call_put_oi_ratio),
                'calls_itm_pct': float(calls_itm / calls_total * 100 if calls_total > 0 else 0),
                'puts_itm_pct': float(puts_itm / puts_total * 100 if puts_total > 0 else 0),
                'flow_interpretation': self._interpret_flow(flow_score),
            }

        except Exception as e:
            logger.debug(f"Error analyzing options flow for {ticker}: {e}")
            return 0.0, {'error': str(e)}

    def _interpret_flow(self, score: float) -> str:
        """Interpret options flow score."""
        if score > 0.5:
            return "Very Bullish"
        elif score > 0.2:
            return "Bullish"
        elif score > -0.2:
            return "Neutral"
        elif score > -0.5:
            return "Bearish"
        else:
            return "Very Bearish"

    def get_unusual_options_activity(
        self, ticker: str, lookback_days: int = 5
    ) -> List[Dict]:
        """
        Identify unusual options activity (volume/OI spikes).

        Args:
            ticker: Stock ticker
            lookback_days: Number of days to analyze

        Returns:
            List of unusual activity events
        """
        try:
            # This requires historical options data which has limited free tier support
            # Alternative: use recent options chain to detect OI concentration

            chain = self.get_options_chain_data(ticker)
            unusual_activities = []

            # Find contracts with unusually high open interest
            all_options = chain['calls'] + chain['puts']
            if not all_options:
                return []

            # Sort by open interest
            sorted_options = sorted(all_options, key=lambda x: x.get('open_interest', 0), reverse=True)

            # Get top 5 OI concentrations
            avg_oi = sum(o.get('open_interest', 0) for o in all_options) / len(all_options)

            for option in sorted_options[:10]:
                oi = option.get('open_interest', 0)
                if oi > avg_oi * 3:  # 3x average = unusual
                    contract_type = option.get('details', {}).get('contract_type', 'unknown')
                    strike = option.get('details', {}).get('strike_price', 'N/A')
                    expiration = option.get('details', {}).get('expiration_date', 'N/A')

                    unusual_activities.append({
                        'ticker': ticker,
                        'type': contract_type,
                        'strike': strike,
                        'expiration': expiration,
                        'open_interest': int(oi),
                        'oi_ratio_to_avg': float(oi / avg_oi if avg_oi > 0 else 1),
                        'severity': 'high' if oi > avg_oi * 5 else 'medium',
                    })

            return unusual_activities

        except Exception as e:
            logger.debug(f"Error detecting unusual activity for {ticker}: {e}")
            return []

    def get_options_iv_rank(self, ticker: str) -> Optional[Dict]:
        """
        Get implied volatility metrics for a ticker.

        Args:
            ticker: Stock ticker

        Returns:
            IV rank and percentile data or None
        """
        try:
            # Polygon API may not directly expose IV rank in free tier
            # This would typically require real-time options data
            logger.debug(f"IV rank calculation requires premium Polygon tier")
            return None

        except Exception as e:
            logger.debug(f"Error getting IV rank for {ticker}: {e}")
            return None

    def analyze_exp_dates(self, ticker: str) -> List[Dict]:
        """
        Analyze options activity across different expiration dates.

        Args:
            ticker: Stock ticker

        Returns:
            List of expiration analysis
        """
        try:
            # Get options data for various expirations
            chain = self.get_options_chain_data(ticker)

            # Group by expiration date
            expirations = {}

            for option in chain['calls'] + chain['puts']:
                exp_date = option.get('details', {}).get('expiration_date', 'unknown')
                if exp_date not in expirations:
                    expirations[exp_date] = {'calls': 0, 'puts': 0, 'total_oi': 0}

                contract_type = option.get('details', {}).get('contract_type', 'call')
                oi = option.get('open_interest', 0)

                if contract_type == 'call':
                    expirations[exp_date]['calls'] += oi
                else:
                    expirations[exp_date]['puts'] += oi

                expirations[exp_date]['total_oi'] += oi

            # Convert to sorted list
            exp_analysis = []
            for exp_date, data in sorted(expirations.items()):
                call_put_ratio = data['calls'] / data['puts'] if data['puts'] > 0 else 1.0
                exp_analysis.append({
                    'expiration_date': exp_date,
                    'call_oi': data['calls'],
                    'put_oi': data['puts'],
                    'call_put_ratio': float(call_put_ratio),
                    'total_oi': data['total_oi'],
                })

            return exp_analysis

        except Exception as e:
            logger.debug(f"Error analyzing expirations for {ticker}: {e}")
            return []


# Global instance
_polygon_instance = None


def get_polygon_options_analyzer(api_key: Optional[str] = None) -> PolygonOptionsAnalyzer:
    """Get singleton instance of Polygon options analyzer."""
    global _polygon_instance
    if _polygon_instance is None:
        _polygon_instance = PolygonOptionsAnalyzer(api_key=api_key)
    return _polygon_instance


if __name__ == "__main__":
    analyzer = get_polygon_options_analyzer()

    ticker = "AAPL"
    print(f"\n=== Testing Polygon Options Analysis for {ticker} ===")

    # Test options chain
    print(f"\n1. Options Chain Data:")
    chain = analyzer.get_options_chain_data(ticker)
    print(f"   Calls: {len(chain['calls'])}")
    print(f"   Puts: {len(chain['puts'])}")

    # Test options flow
    print(f"\n2. Options Flow Analysis:")
    flow_score, details = analyzer.analyze_options_flow(ticker)
    print(f"   Flow Score: {flow_score:.3f}")
    print(f"   Interpretation: {details.get('flow_interpretation', 'Unknown')}")
    if 'call_put_vol_ratio' in details:
        print(f"   Call/Put Vol Ratio: {details['call_put_vol_ratio']:.2f}")
    if 'call_put_oi_ratio' in details:
        print(f"   Call/Put OI Ratio: {details['call_put_oi_ratio']:.2f}")

    # Test unusual activity
    print(f"\n3. Unusual Options Activity:")
    unusual = analyzer.get_unusual_options_activity(ticker)
    if unusual:
        print(f"   Found {len(unusual)} unusual positions")
        for activity in unusual[:3]:
            print(f"   - {activity['type'].upper()} ${activity['strike']} "
                  f"({activity['expiration']}) - {activity['severity']} "
                  f"({activity['oi_ratio_to_avg']:.1f}x avg)")
    else:
        print("   No unusual activity detected")

    # Test expiration analysis
    print(f"\n4. Expiration Date Analysis:")
    exp_analysis = analyzer.analyze_exp_dates(ticker)
    if exp_analysis:
        for exp in exp_analysis[:5]:
            print(f"   {exp['expiration_date']}: "
                  f"{exp['call_oi']} calls / {exp['put_oi']} puts "
                  f"(Ratio: {exp['call_put_ratio']:.2f})")
    else:
        print("   No expiration data available")
