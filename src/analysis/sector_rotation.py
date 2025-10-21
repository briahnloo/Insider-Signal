"""
Sector Rotation Detection Module

This module provides functionality to detect unusual insider buying patterns
across sectors using statistical Z-score anomaly detection. It helps identify
sectors experiencing rotation (increased insider interest) and calculates
conviction multipliers based on sector-wide activity.

Classes:
    SectorRotationDetector: Main class for sector rotation analysis
"""

import logging
from typing import Dict, List, Tuple, Optional
from datetime import datetime, timedelta
from collections import defaultdict
import statistics

import yfinance as yf
from cachetools import TTLCache

from src.database import get_all_recent_transactions


# Configure logging
logger = logging.getLogger(__name__)


class SectorRotationDetector:
    """
    Detects sector rotation patterns using insider trading activity.

    Uses Z-score anomaly detection to identify sectors with unusual
    insider buying patterns, providing conviction multipliers for
    scoring systems.

    Attributes:
        cache: TTL cache for sector data (1-hour expiration)
        sector_peers: Pre-defined sector peer groups
    """

    def __init__(self):
        """Initialize the SectorRotationDetector with cache and sector mappings."""
        # Cache with 1-hour TTL (3600 seconds)
        self.cache = TTLCache(maxsize=100, ttl=3600)

        # Pre-defined sector peer groups for major stocks
        self.sector_peers = {
            # Technology
            'AAPL': ['MSFT', 'GOOGL', 'META', 'NVDA', 'AMD', 'INTC'],
            'MSFT': ['AAPL', 'GOOGL', 'META', 'NVDA', 'AMD', 'INTC'],
            'GOOGL': ['AAPL', 'MSFT', 'META', 'AMZN', 'NFLX'],
            'META': ['GOOGL', 'SNAP', 'PINS', 'TWTR', 'SPOT'],
            'NVDA': ['AMD', 'INTC', 'QCOM', 'AVGO', 'MU'],
            'AMD': ['NVDA', 'INTC', 'QCOM', 'AVGO', 'MU'],

            # Finance
            'JPM': ['BAC', 'WFC', 'C', 'GS', 'MS'],
            'BAC': ['JPM', 'WFC', 'C', 'USB', 'PNC'],
            'GS': ['MS', 'JPM', 'C', 'BLK', 'SCHW'],
            'V': ['MA', 'AXP', 'PYPL', 'SQ'],
            'MA': ['V', 'AXP', 'PYPL', 'SQ'],

            # Healthcare
            'JNJ': ['PFE', 'UNH', 'ABT', 'MRK', 'LLY'],
            'PFE': ['JNJ', 'MRK', 'LLY', 'ABBV', 'BMY'],
            'UNH': ['CVS', 'CI', 'HUM', 'ANTM'],

            # Energy
            'XOM': ['CVX', 'COP', 'EOG', 'SLB', 'PSX'],
            'CVX': ['XOM', 'COP', 'EOG', 'SLB', 'PSX'],

            # Consumer Discretionary
            'AMZN': ['WMT', 'TGT', 'HD', 'LOW', 'NKE'],
            'TSLA': ['F', 'GM', 'NIO', 'RIVN', 'LCID'],
            'NKE': ['ADDYY', 'LULU', 'UAA', 'CROX'],

            # Consumer Staples
            'PG': ['KO', 'PEP', 'WMT', 'COST', 'CL'],
            'KO': ['PEP', 'PG', 'MNST', 'DPS'],

            # Industrials
            'BA': ['LMT', 'RTX', 'GD', 'NOC', 'HON'],
            'CAT': ['DE', 'CMI', 'ETN', 'EMR'],

            # Telecommunications
            'T': ['VZ', 'TMUS', 'CMCSA', 'CHTR'],
            'VZ': ['T', 'TMUS', 'CMCSA', 'CHTR'],
        }

    def _get_sector_for_ticker(self, ticker: str) -> Optional[str]:
        """
        Get the sector classification for a ticker.

        Args:
            ticker: Stock ticker symbol

        Returns:
            Sector name or None if not found
        """
        cache_key = f"sector_{ticker}"
        if cache_key in self.cache:
            return self.cache[cache_key]

        try:
            stock = yf.Ticker(ticker)
            info = stock.info
            sector = info.get('sector')

            if sector:
                self.cache[cache_key] = sector

            return sector
        except Exception as e:
            logger.warning(f"Failed to get sector for {ticker}: {e}")
            return None

    def _get_peer_group(self, ticker: str) -> List[str]:
        """
        Get the peer group for a ticker.

        Args:
            ticker: Stock ticker symbol

        Returns:
            List of peer tickers (including the original ticker)
        """
        if ticker in self.sector_peers:
            return [ticker] + self.sector_peers[ticker]

        # Fallback to sector-based peer discovery
        sector = self._get_sector_for_ticker(ticker)
        if not sector:
            return [ticker]

        # For now, just return the ticker itself if no peers defined
        # In production, could query database for all tickers in same sector
        return [ticker]

    def _calculate_z_score(self, value: float, values: List[float]) -> float:
        """
        Calculate Z-score for anomaly detection.

        Args:
            value: The value to score
            values: Historical values for baseline

        Returns:
            Z-score (standardized distance from mean)
        """
        if len(values) < 2:
            return 0.0

        mean = statistics.mean(values)
        try:
            stdev = statistics.stdev(values)
            if stdev == 0:
                return 0.0
            return (value - mean) / stdev
        except statistics.StatisticsError:
            return 0.0

    def detect_sector_rotation(
        self,
        lookback_days: int = 30,
        min_insiders: int = 3
    ) -> Dict[str, any]:
        """
        Detect sectors with unusual insider buying patterns.

        Analyzes insider transactions across sectors to identify
        statistically significant increases in buying activity.

        Args:
            lookback_days: Days to look back for transaction history
            min_insiders: Minimum number of insiders for sector to qualify

        Returns:
            Dictionary containing:
                - anomalies: List of sectors with unusual activity
                - scores: Z-scores for each sector
                - details: Transaction counts and insider counts
        """
        cache_key = f"rotation_{lookback_days}_{min_insiders}"
        if cache_key in self.cache:
            return self.cache[cache_key]

        try:
            # Get recent transactions from database
            cutoff_date = datetime.now() - timedelta(days=lookback_days)
            transactions = get_all_recent_transactions(days=lookback_days)

            # Aggregate by sector
            sector_data = defaultdict(lambda: {
                'buy_count': 0,
                'sell_count': 0,
                'insiders': set(),
                'tickers': set()
            })

            for txn in transactions:
                ticker = txn.get('ticker', '').upper()
                insider = txn.get('insider_name', '')
                txn_type = txn.get('transaction_type', '').lower()

                if not ticker or not insider:
                    continue

                sector = self._get_sector_for_ticker(ticker)
                if not sector:
                    continue

                sector_data[sector]['insiders'].add(insider)
                sector_data[sector]['tickers'].add(ticker)

                if 'buy' in txn_type or 'purchase' in txn_type:
                    sector_data[sector]['buy_count'] += 1
                elif 'sell' in txn_type or 'sale' in txn_type:
                    sector_data[sector]['sell_count'] += 1

            # Filter sectors with minimum insider threshold
            qualified_sectors = {
                sector: data for sector, data in sector_data.items()
                if len(data['insiders']) >= min_insiders
            }

            if not qualified_sectors:
                result = {
                    'anomalies': [],
                    'scores': {},
                    'details': {}
                }
                self.cache[cache_key] = result
                return result

            # Calculate baseline (mean buy count)
            buy_counts = [data['buy_count'] for data in qualified_sectors.values()]

            # Calculate Z-scores for each sector
            scores = {}
            anomalies = []
            details = {}

            for sector, data in qualified_sectors.items():
                z_score = self._calculate_z_score(data['buy_count'], buy_counts)
                scores[sector] = z_score

                details[sector] = {
                    'buy_count': data['buy_count'],
                    'sell_count': data['sell_count'],
                    'insider_count': len(data['insiders']),
                    'ticker_count': len(data['tickers']),
                    'z_score': z_score
                }

                # Flag as anomaly if Z-score > 1.5 (significant deviation)
                if z_score > 1.5:
                    anomalies.append({
                        'sector': sector,
                        'z_score': z_score,
                        'buy_count': data['buy_count'],
                        'insider_count': len(data['insiders'])
                    })

            # Sort anomalies by Z-score
            anomalies.sort(key=lambda x: x['z_score'], reverse=True)

            result = {
                'anomalies': anomalies,
                'scores': scores,
                'details': details
            }

            self.cache[cache_key] = result
            return result

        except Exception as e:
            logger.error(f"Failed to detect sector rotation: {e}")
            return {
                'anomalies': [],
                'scores': {},
                'details': {}
            }

    def get_sector_rotation_score(
        self,
        ticker: str,
        lookback_days: int = 30
    ) -> float:
        """
        Get the rotation score for a ticker's sector.

        The rotation score indicates how unusual the sector's insider
        buying activity is compared to baseline. Score ranges from 0-1.

        Args:
            ticker: Stock ticker symbol
            lookback_days: Days to look back for analysis

        Returns:
            Rotation score (0-1), where higher values indicate stronger rotation
        """
        ticker = ticker.upper()
        sector = self._get_sector_for_ticker(ticker)

        if not sector:
            return 0.0

        rotation_data = self.detect_sector_rotation(lookback_days=lookback_days)
        z_score = rotation_data['scores'].get(sector, 0.0)

        # Normalize Z-score to 0-1 range (divide by 3.0 as ~99.7% of data within 3 std devs)
        rotation_score = min(max(z_score / 3.0, 0.0), 1.0)

        return rotation_score

    def get_relative_sector_strength(
        self,
        ticker: str,
        lookback_days: int = 60
    ) -> Dict[str, any]:
        """
        Compare insider momentum vs price momentum for sector context.

        RSR (Relative Strength Ratio) helps identify if insider buying
        is leading, confirming, or contradicting price movements.

        Args:
            ticker: Stock ticker symbol
            lookback_days: Days to look back for momentum calculation

        Returns:
            Dictionary containing:
                - rsr: Relative strength ratio
                - insider_momentum: Insider buying trend
                - price_momentum: Price change percentage
                - interpretation: Text description of the signal
        """
        ticker = ticker.upper()

        try:
            # Calculate price momentum
            stock = yf.Ticker(ticker)
            end_date = datetime.now()
            start_date = end_date - timedelta(days=lookback_days)

            hist = stock.history(start=start_date, end=end_date)

            if hist.empty or len(hist) < 2:
                return {
                    'rsr': 0.0,
                    'insider_momentum': 0.0,
                    'price_momentum': 0.0,
                    'interpretation': 'insufficient_data'
                }

            # Price momentum as percentage change
            start_price = hist['Close'].iloc[0]
            end_price = hist['Close'].iloc[-1]
            price_momentum = ((end_price - start_price) / start_price) * 100

            # Calculate insider momentum
            cutoff_date = datetime.now() - timedelta(days=lookback_days)
            transactions = get_all_recent_transactions(days=lookback_days)

            ticker_txns = [
                txn for txn in transactions
                if txn.get('ticker', '').upper() == ticker
            ]

            buy_count = sum(
                1 for txn in ticker_txns
                if 'buy' in txn.get('transaction_type', '').lower()
                or 'purchase' in txn.get('transaction_type', '').lower()
            )

            sell_count = sum(
                1 for txn in ticker_txns
                if 'sell' in txn.get('transaction_type', '').lower()
                or 'sale' in txn.get('transaction_type', '').lower()
            )

            # Insider momentum: net buying as percentage
            total_txns = buy_count + sell_count
            if total_txns == 0:
                insider_momentum = 0.0
            else:
                insider_momentum = ((buy_count - sell_count) / total_txns) * 100

            # Calculate RSR
            if price_momentum == 0:
                rsr = 0.0
            else:
                rsr = insider_momentum / abs(price_momentum)

            # Interpret the signal
            interpretation = self._interpret_rsr(
                rsr, insider_momentum, price_momentum
            )

            return {
                'rsr': rsr,
                'insider_momentum': insider_momentum,
                'price_momentum': price_momentum,
                'interpretation': interpretation
            }

        except Exception as e:
            logger.error(f"Failed to calculate RSR for {ticker}: {e}")
            return {
                'rsr': 0.0,
                'insider_momentum': 0.0,
                'price_momentum': 0.0,
                'interpretation': 'error'
            }

    def _interpret_rsr(
        self,
        rsr: float,
        insider_momentum: float,
        price_momentum: float
    ) -> str:
        """
        Interpret the RSR signal.

        Args:
            rsr: Relative strength ratio
            insider_momentum: Insider buying trend
            price_momentum: Price change percentage

        Returns:
            Interpretation string
        """
        # Strong insider buying
        if insider_momentum > 50:
            if price_momentum < -5:
                return 'leading_edge'  # Buying into weakness
            elif price_momentum > 5:
                return 'good_timing'  # Confirming strength
            else:
                return 'accumulation'  # Neutral price action

        # Moderate insider buying
        elif insider_momentum > 0:
            if price_momentum < -10:
                return 'contrarian_opportunity'
            elif price_momentum > 10:
                return 'weak_momentum'  # Insiders not as confident
            else:
                return 'neutral'

        # No insider buying or net selling
        else:
            if price_momentum > 10:
                return 'no_strength'  # Price up without insider support
            else:
                return 'no_signal'

    def get_sector_multiplier(self, ticker: str) -> Tuple[float, str]:
        """
        Calculate conviction multiplier based on sector rotation.

        Provides a multiplier (1.0-1.2x) to boost conviction scores
        when the ticker's sector is experiencing rotation.

        Args:
            ticker: Stock ticker symbol

        Returns:
            Tuple of (multiplier, reason):
                - multiplier: Float between 1.0 and 1.2
                - reason: Explanation for the multiplier
        """
        ticker = ticker.upper()

        try:
            # Get sector rotation score
            rotation_score = self.get_sector_rotation_score(ticker)

            # Get relative sector strength
            rsr_data = self.get_relative_sector_strength(ticker)
            interpretation = rsr_data['interpretation']

            # Base multiplier
            multiplier = 1.0
            reasons = []

            # Rotation bonus (up to 0.1x)
            if rotation_score > 0.5:
                rotation_bonus = rotation_score * 0.1
                multiplier += rotation_bonus
                reasons.append(f"sector_rotation_detected ({rotation_score:.2f})")

            # RSR bonus (up to 0.1x)
            if interpretation == 'leading_edge':
                multiplier += 0.1
                reasons.append("leading_edge_buying")
            elif interpretation == 'good_timing':
                multiplier += 0.08
                reasons.append("good_timing")
            elif interpretation == 'contrarian_opportunity':
                multiplier += 0.05
                reasons.append("contrarian_buy")

            # Cap at 1.2x
            multiplier = min(multiplier, 1.2)

            # Format reason
            if reasons:
                reason = ', '.join(reasons)
            else:
                reason = 'no_sector_rotation'

            return (multiplier, reason)

        except Exception as e:
            logger.error(f"Failed to calculate sector multiplier for {ticker}: {e}")
            return (1.0, 'error')


# Convenience function for external use
def get_sector_rotation_detector() -> SectorRotationDetector:
    """
    Get a singleton instance of SectorRotationDetector.

    Returns:
        SectorRotationDetector instance
    """
    if not hasattr(get_sector_rotation_detector, '_instance'):
        get_sector_rotation_detector._instance = SectorRotationDetector()
    return get_sector_rotation_detector._instance
