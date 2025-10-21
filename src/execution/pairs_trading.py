"""Pairs trading generator - market-neutral long/short opportunities."""
from typing import Dict, List, Optional, Tuple
from datetime import datetime, timedelta
import yfinance as yf
import pandas as pd
import numpy as np
from loguru import logger

from src.database import get_transactions_by_ticker, get_all_recent_transactions


class PairsTradeGenerator:
    """Generates market-neutral pairs trading opportunities."""

    def __init__(self):
        """Initialize pairs trading generator."""
        self.cache = {}
        self.cache_time = {}
        self.cache_ttl = 3600  # 1 hour cache

        # Sector peer groups for finding pairs
        self.sector_peers = {
            "AAPL": ["MSFT", "GOOGL", "META", "AMZN", "NVDA"],
            "MSFT": ["AAPL", "GOOGL", "AMZN", "META"],
            "GOOGL": ["AAPL", "MSFT", "META", "AMZN"],
            "META": ["AAPL", "MSFT", "GOOGL", "AMZN"],
            "AMZN": ["AAPL", "MSFT", "GOOGL", "META"],
            "NVDA": ["AMD", "INTC", "QCOM", "AVGO"],
            "AMD": ["NVDA", "INTC", "QCOM"],
            "INTC": ["NVDA", "AMD", "QCOM"],
            "JPM": ["BAC", "WFC", "GS", "MS", "C"],
            "BAC": ["JPM", "WFC", "C", "GS"],
            "WFC": ["JPM", "BAC", "C"],
            "TSLA": ["GM", "F", "RIVN"],
            "XOM": ["CVX", "COP", "PSX"],
            "JNJ": ["PFE", "ABBV", "MRK", "LLY"],
        }

    def _get_cached(self, key: str) -> Optional[Dict]:
        """Get cached data if valid."""
        import time
        if key in self.cache:
            if time.time() - self.cache_time.get(key, 0) < self.cache_ttl:
                return self.cache[key]
        return None

    def _set_cached(self, key: str, data):
        """Cache data with timestamp."""
        import time
        self.cache[key] = data
        self.cache_time[key] = time.time()

    def _calculate_price_correlation(
        self,
        ticker1: str,
        ticker2: str,
        window_days: int = 60
    ) -> float:
        """Calculate price correlation between two tickers."""
        try:
            # Fetch price data
            stock1 = yf.Ticker(ticker1)
            stock2 = yf.Ticker(ticker2)

            hist1 = stock1.history(period=f"{window_days}d")
            hist2 = stock2.history(period=f"{window_days}d")

            if len(hist1) < 20 or len(hist2) < 20:
                return 0.0

            # Align dates
            df = pd.DataFrame({
                ticker1: hist1['Close'],
                ticker2: hist2['Close']
            }).dropna()

            if len(df) < 20:
                return 0.0

            # Calculate correlation
            correlation = df[ticker1].corr(df[ticker2])
            return float(correlation) if not pd.isna(correlation) else 0.0

        except Exception as e:
            logger.debug(f"Could not calculate correlation for {ticker1}/{ticker2}: {e}")
            return 0.0

    def _get_conviction_score(self, ticker: str) -> float:
        """
        Get conviction score for a ticker.

        This is a simplified version that uses transaction data.
        In production, would integrate with ConvictionScorerV2.
        """
        try:
            # Get recent transactions
            transactions = get_transactions_by_ticker(ticker, days=30)

            if not transactions:
                return 0.0

            # Simple heuristic: count purchases vs sales
            purchases = 0
            sales = 0
            total_value = 0

            for txn in transactions:
                txn_type = txn.get('transaction_type', '').lower()
                value = txn.get('value', 0) or 0

                if 'purchase' in txn_type or 'buy' in txn_type:
                    purchases += 1
                    total_value += value
                elif 'sale' in txn_type or 'sell' in txn_type:
                    sales += 1
                    total_value -= value

            if purchases == 0 and sales == 0:
                return 0.0

            # Simple conviction: purchases / total transactions
            total_txns = purchases + sales
            purchase_ratio = purchases / total_txns if total_txns > 0 else 0

            # Boost by transaction count (more activity = more conviction)
            activity_boost = min(total_txns / 10, 1.0)

            # Combine: 70% ratio, 30% activity
            conviction = (purchase_ratio * 0.7) + (activity_boost * 0.3)

            return min(conviction, 1.0)

        except Exception as e:
            logger.debug(f"Could not get conviction for {ticker}: {e}")
            return 0.0

    def find_pairs_opportunities(
        self,
        high_conviction_ticker: str,
        window_days: int = 14,
        correlation_threshold: float = 0.7,
        min_conviction_spread: float = 0.15
    ) -> Dict:
        """
        Find pairs trading opportunities for a high-conviction long.

        Strategy: LONG high_conviction_ticker + SHORT correlated ticker with lower conviction

        Returns dict with:
        - pairs_opportunities: list of dicts with pair details
        - best_pair: dict or None
        - total_pairs: int
        """
        cache_key = f"pairs_{high_conviction_ticker}_{window_days}"
        cached = self._get_cached(cache_key)
        if cached:
            return cached

        try:
            # Get conviction for long ticker
            long_conviction = self._get_conviction_score(high_conviction_ticker)

            if long_conviction < 0.60:
                logger.debug(f"{high_conviction_ticker} conviction too low for pairs: {long_conviction:.3f}")
                return {
                    'pairs_opportunities': [],
                    'best_pair': None,
                    'total_pairs': 0,
                    'reason': f'Long conviction too low ({long_conviction:.3f})'
                }

            # Get peer tickers
            peers = self.sector_peers.get(high_conviction_ticker, [])
            if not peers:
                logger.debug(f"No peers found for {high_conviction_ticker}")
                return {
                    'pairs_opportunities': [],
                    'best_pair': None,
                    'total_pairs': 0,
                    'reason': 'No sector peers available'
                }

            # Evaluate each peer as potential short
            pairs = []

            for peer in peers:
                # Get conviction for potential short
                short_conviction = self._get_conviction_score(peer)

                # Check conviction spread (long must be significantly higher)
                conviction_spread = long_conviction - short_conviction

                if conviction_spread < min_conviction_spread:
                    continue

                # Don't short stocks with very low conviction (might be oversold)
                if short_conviction > 0.75:
                    continue

                # Calculate price correlation
                correlation = self._calculate_price_correlation(
                    high_conviction_ticker,
                    peer,
                    window_days=window_days * 4  # Use longer window for correlation
                )

                if correlation < correlation_threshold:
                    continue

                # Calculate pair quality score
                # Components: conviction spread (40%), long quality (30%), correlation (30%)
                conviction_component = min(conviction_spread / 0.5, 1.0) * 0.4
                long_component = min(long_conviction, 1.0) * 0.3
                correlation_component = ((correlation - correlation_threshold) / (1.0 - correlation_threshold)) * 0.3

                pair_quality = conviction_component + long_component + correlation_component

                pairs.append({
                    'long_ticker': high_conviction_ticker,
                    'short_ticker': peer,
                    'long_conviction': long_conviction,
                    'short_conviction': short_conviction,
                    'conviction_spread': conviction_spread,
                    'correlation': correlation,
                    'pair_quality_score': pair_quality,
                    'strategy': f'LONG {high_conviction_ticker} / SHORT {peer}',
                })

            # Sort by pair quality descending
            pairs.sort(key=lambda x: x['pair_quality_score'], reverse=True)

            result = {
                'pairs_opportunities': pairs,
                'best_pair': pairs[0] if pairs else None,
                'total_pairs': len(pairs),
            }

            self._set_cached(cache_key, result)
            return result

        except Exception as e:
            logger.error(f"Error finding pairs for {high_conviction_ticker}: {e}")
            return {
                'pairs_opportunities': [],
                'best_pair': None,
                'total_pairs': 0,
                'error': str(e)
            }

    def generate_hedge_trades(
        self,
        long_ticket: str,  # Note: typo preserved from test file
        long_conviction: float,
        hedge_ratio: float = 0.5,
        max_hedges: int = 5
    ) -> Dict:
        """
        Generate hedging strategy using correlated stocks.

        Args:
            long_ticket: Ticker being longed (typo from test preserved)
            long_conviction: Conviction score of long position
            hedge_ratio: Portion of position to hedge (0-1)
            max_hedges: Maximum number of hedge candidates

        Returns dict with:
        - hedges: list of short candidates
        - total_hedges: int
        - suggested_allocation: dict
        """
        # Handle typo parameter
        long_ticker = long_ticket

        try:
            # Get peers for hedging
            peers = self.sector_peers.get(long_ticker, [])

            if not peers:
                return {
                    'hedges': [],
                    'total_hedges': 0,
                    'suggested_allocation': {},
                    'reason': 'No peers available for hedging'
                }

            hedges = []

            for peer in peers[:max_hedges]:
                # Get conviction
                conviction = self._get_conviction_score(peer)

                # Prefer lower conviction shorts (but not too low)
                if conviction > 0.70 or conviction < 0.20:
                    continue

                # Get correlation
                correlation = self._calculate_price_correlation(long_ticker, peer)

                if correlation < 0.6:  # Lower threshold for hedging
                    continue

                # Hedge quality: high correlation + low conviction
                hedge_quality = (correlation * 0.6) + ((1.0 - conviction) * 0.4)

                hedges.append({
                    'ticker': peer,
                    'conviction': conviction,
                    'correlation': correlation,
                    'hedge_quality': hedge_quality,
                    'recommended_action': 'SHORT',
                })

            # Sort by hedge quality
            hedges.sort(key=lambda x: x['hedge_quality'], reverse=True)

            # Calculate suggested allocation
            if hedges:
                # Distribute hedge ratio across top hedges
                num_hedges = min(len(hedges), 3)  # Use top 3
                allocation_per_hedge = hedge_ratio / num_hedges

                allocation = {
                    long_ticker: 1.0,  # 100% long
                }

                for i, hedge in enumerate(hedges[:num_hedges]):
                    allocation[hedge['ticker']] = -allocation_per_hedge  # Negative = short

                suggested_allocation = allocation
            else:
                suggested_allocation = {long_ticker: 1.0}

            return {
                'hedges': hedges,
                'total_hedges': len(hedges),
                'suggested_allocation': suggested_allocation,
            }

        except Exception as e:
            logger.error(f"Error generating hedges for {long_ticker}: {e}")
            return {
                'hedges': [],
                'total_hedges': 0,
                'suggested_allocation': {},
                'error': str(e)
            }

    def get_pairs_multiplier(
        self,
        ticker: str,
        window_days: int = 14
    ) -> Tuple[float, str]:
        """
        Get pairs trading multiplier for conviction scoring.

        If high-quality pair exists, boost conviction.
        Multiplier range: 1.0x - 1.15x

        Returns: (multiplier, reason_string)
        """
        try:
            # Find pairs
            pairs_data = self.find_pairs_opportunities(
                high_conviction_ticker=ticker,
                window_days=window_days
            )

            best_pair = pairs_data.get('best_pair')

            if not best_pair:
                return (1.0, "No viable pairs found")

            # Get pair quality score
            pair_quality = best_pair.get('pair_quality_score', 0.0)

            # Convert to multiplier
            # Max boost: 1.15x for perfect pair (quality = 1.0)
            multiplier = 1.0 + (pair_quality * 0.15)

            # Generate reason
            short_ticker = best_pair.get('short_ticker')
            correlation = best_pair.get('correlation', 0.0)
            conviction_spread = best_pair.get('conviction_spread', 0.0)

            if multiplier > 1.10:
                reason = f"Strong pair opportunity: SHORT {short_ticker} (corr={correlation:.2f})"
            elif multiplier > 1.05:
                reason = f"Moderate pair: SHORT {short_ticker} (spread={conviction_spread:.2f})"
            else:
                reason = f"Weak pair quality with {short_ticker}"

            return (multiplier, reason)

        except Exception as e:
            logger.error(f"Error calculating pairs multiplier for {ticker}: {e}")
            return (1.0, "Error calculating pairs effect")

    def analyze_pair_performance(
        self,
        long_ticker: str,
        short_ticker: str,
        lookback_days: int = 30
    ) -> Dict:
        """
        Analyze historical performance of a pairs trade.

        Returns dict with:
        - total_return: float (%)
        - long_return: float (%)
        - short_return: float (%)
        - pair_return: float (%)
        - volatility: float
        - sharpe_ratio: float
        """
        try:
            # Fetch historical data
            stock_long = yf.Ticker(long_ticker)
            stock_short = yf.Ticker(short_ticker)

            hist_long = stock_long.history(period=f"{lookback_days}d")
            hist_short = stock_short.history(period=f"{lookback_days}d")

            if len(hist_long) < 2 or len(hist_short) < 2:
                return {
                    'error': 'Insufficient data',
                    'total_return': 0.0,
                }

            # Calculate returns
            long_start = hist_long['Close'].iloc[0]
            long_end = hist_long['Close'].iloc[-1]
            long_return = ((long_end - long_start) / long_start) * 100

            short_start = hist_short['Close'].iloc[0]
            short_end = hist_short['Close'].iloc[-1]
            short_return = ((short_end - short_start) / short_start) * 100

            # Pair return: long return - short return (we're short the second)
            pair_return = long_return - short_return

            # Calculate daily returns for volatility
            df = pd.DataFrame({
                'long': hist_long['Close'].pct_change(),
                'short': hist_short['Close'].pct_change()
            }).dropna()

            df['pair'] = df['long'] - df['short']

            volatility = float(df['pair'].std() * 100)  # Convert to %
            mean_return = float(df['pair'].mean() * 100)

            # Sharpe ratio (simplified, assuming 0% risk-free rate)
            sharpe_ratio = (mean_return / volatility) if volatility > 0 else 0.0

            return {
                'long_ticker': long_ticker,
                'short_ticker': short_ticker,
                'long_return': long_return,
                'short_return': short_return,
                'pair_return': pair_return,
                'volatility': volatility,
                'sharpe_ratio': sharpe_ratio,
                'days': lookback_days,
            }

        except Exception as e:
            logger.error(f"Error analyzing pair performance {long_ticker}/{short_ticker}: {e}")
            return {
                'error': str(e),
                'total_return': 0.0,
            }
