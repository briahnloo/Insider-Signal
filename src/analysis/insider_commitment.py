"""
Insider Commitment Analyzer

Tracks insider buying vs selling activity to identify:
1. Net insider sentiment (buys vs sells)
2. Insiders who are "conflicted" (buying and selling simultaneously)
3. Buy/sell ratios by ticker and insider
4. Insider confidence levels (pure buying vs mixed activity)
"""

from typing import Dict, List, Tuple, Optional
from datetime import datetime, timedelta
import pandas as pd
import numpy as np
from loguru import logger

try:
    from src.database import get_recent_transactions
except ImportError:
    # Fallback for testing without database
    def get_recent_transactions(days=90, min_value=0):
        return pd.DataFrame()


class InsiderCommitmentAnalyzer:
    """Analyzes insider buying vs selling patterns to assess commitment."""

    def __init__(self):
        """Initialize the insider commitment analyzer."""
        self.cache = {}
        self.cache_time = {}
        self.cache_ttl = 3600  # 1 hour cache

    def calculate_insider_commitment_score(
        self,
        ticker: str,
        days_lookback: int = 90,
    ) -> Tuple[float, Dict]:
        """
        Calculate insider commitment score based on buy/sell activity.

        Score is 1.0 if pure buying, 0.5 if mixed, 0.0 if net selling.

        Args:
            ticker: Stock ticker symbol
            days_lookback: Days of history to analyze (default: 90)

        Returns:
            Tuple of (commitment_score 0.0-1.0, details_dict)
        """
        ticker = ticker.upper()
        cache_key = f"commitment_{ticker}_{days_lookback}"

        # Check cache
        if cache_key in self.cache:
            import time
            if time.time() - self.cache_time.get(cache_key, 0) < self.cache_ttl:
                result = self.cache[cache_key]
                return result['score'], result['details']

        try:
            # Get recent transactions
            df = get_recent_transactions(days=days_lookback, min_value=0)

            if df.empty:
                logger.warning(f"No transaction data for {ticker}")
                return 0.5, {
                    'source': 'error',
                    'error': 'No data available',
                    'buy_count': 0,
                    'sell_count': 0,
                    'buy_sell_ratio': 0.0,
                    'net_sentiment': 0.0,
                    'interpretation': 'Insufficient Data'
                }

            # Filter by ticker
            ticker_df = df[df['ticker'] == ticker]

            if ticker_df.empty:
                logger.warning(f"No transactions found for {ticker}")
                return 0.5, {
                    'source': 'no_data',
                    'buy_count': 0,
                    'sell_count': 0,
                    'buy_sell_ratio': 0.0,
                    'net_sentiment': 0.0,
                    'interpretation': 'No Data'
                }

            # Count buys and sells
            buy_count = len(ticker_df[ticker_df['transaction_type'].isin(['BUY', 'EXERCISE', 'PURCHASE', 'BUY EXERCISE'])])
            sell_count = len(ticker_df[ticker_df['transaction_type'].isin(['SALE', 'SALE - COVERED CALL'])])

            # Calculate buy/sell value totals
            buy_value = ticker_df[ticker_df['transaction_type'].isin(['BUY', 'EXERCISE', 'PURCHASE', 'BUY EXERCISE'])][
                'total_value'
            ].sum()
            sell_value = ticker_df[ticker_df['transaction_type'].isin(['SALE', 'SALE - COVERED CALL'])]['total_value'].sum()

            # Calculate net sentiment: (buys - sells) / (buys + sells)
            total_transactions = buy_count + sell_count
            total_value = buy_value + sell_value

            if total_transactions == 0:
                net_sentiment = 0.0
                buy_sell_ratio = 0.0
            else:
                net_sentiment = (buy_count - sell_count) / total_transactions

            if sell_count == 0 and buy_count > 0:
                buy_sell_ratio = float('inf')
            elif sell_count > 0:
                buy_sell_ratio = buy_count / sell_count
            else:
                buy_sell_ratio = 0.0

            # Calculate commitment score
            # 1.0 = pure buying (no sells)
            # 0.5 = mixed (equal buys and sells)
            # 0.0 = net selling (more sells than buys)
            commitment_score = (net_sentiment + 1.0) / 2.0
            commitment_score = max(0.0, min(1.0, commitment_score))

            # Identify "conflicted" insiders (buying and selling same ticker)
            conflicted_insiders = []
            if buy_count > 0 and sell_count > 0:
                for insider in ticker_df['insider_name'].unique():
                    insider_df = ticker_df[ticker_df['insider_name'] == insider]
                    if (
                        any(insider_df['transaction_type'].isin(['BUY', 'EXERCISE']))
                        and any(insider_df['transaction_type'] == 'SALE')
                    ):
                        conflicted_insiders.append(insider)

            # Interpretation
            if commitment_score >= 0.85:
                interpretation = 'Very Bullish (Pure Buying)'
            elif commitment_score >= 0.70:
                interpretation = 'Bullish (Mostly Buying)'
            elif commitment_score >= 0.55:
                interpretation = 'Mixed Signals'
            elif commitment_score >= 0.30:
                interpretation = 'Bearish (More Selling)'
            else:
                interpretation = 'Very Bearish (Net Selling)'

            details = {
                'source': 'form4_analysis',
                'ticker': ticker,
                'days_lookback': days_lookback,
                'buy_count': int(buy_count),
                'sell_count': int(sell_count),
                'total_transactions': int(total_transactions),
                'buy_value': float(buy_value),
                'sell_value': float(sell_value),
                'total_value': float(total_value),
                'buy_sell_ratio': float(buy_sell_ratio) if buy_sell_ratio != float('inf') else 'infinite',
                'net_sentiment': float(net_sentiment),
                'commitment_score': float(commitment_score),
                'conflicted_insiders': conflicted_insiders,
                'conflicted_count': len(conflicted_insiders),
                'interpretation': interpretation,
            }

            # Cache result
            import time
            self.cache[cache_key] = {'score': commitment_score, 'details': details}
            self.cache_time[cache_key] = time.time()

            logger.info(
                f"{ticker}: Insider commitment {commitment_score:.3f} "
                f"(Buys: {buy_count}, Sells: {sell_count}, "
                f"Conflicted: {len(conflicted_insiders)})"
            )

            return commitment_score, details

        except Exception as e:
            logger.warning(f"Error calculating insider commitment for {ticker}: {e}")
            return 0.5, {
                'source': 'error',
                'error': str(e),
                'interpretation': 'Analysis Error'
            }

    def get_insider_activity_balance(
        self,
        days_lookback: int = 90,
    ) -> Dict:
        """
        Get insider activity balance for all tickers.

        Returns dictionary with buy/sell statistics by ticker.

        Args:
            days_lookback: Days of history to analyze

        Returns:
            Dict with activity balance by ticker
        """
        try:
            df = get_recent_transactions(days=days_lookback, min_value=0)

            if df.empty:
                return {}

            activity_balance = {}

            for ticker in df['ticker'].unique():
                ticker_df = df[df['ticker'] == ticker]

                buy_count = len(ticker_df[ticker_df['transaction_type'].isin(['BUY', 'EXERCISE', 'PURCHASE', 'BUY EXERCISE'])])
                sell_count = len(ticker_df[ticker_df['transaction_type'].isin(['SALE', 'SALE - COVERED CALL'])])

                buy_value = ticker_df[ticker_df['transaction_type'].isin(['BUY', 'EXERCISE', 'PURCHASE', 'BUY EXERCISE'])][
                    'total_value'
                ].sum()
                sell_value = ticker_df[ticker_df['transaction_type'].isin(['SALE', 'SALE - COVERED CALL'])][
                    'total_value'
                ].sum()

                activity_balance[ticker] = {
                    'buy_count': int(buy_count),
                    'sell_count': int(sell_count),
                    'buy_value': float(buy_value),
                    'sell_value': float(sell_value),
                    'buy_pct': (buy_count / (buy_count + sell_count) * 100)
                    if (buy_count + sell_count) > 0
                    else 0,
                    'sell_pct': (sell_count / (buy_count + sell_count) * 100)
                    if (buy_count + sell_count) > 0
                    else 0,
                }

            return activity_balance

        except Exception as e:
            logger.warning(f"Error getting activity balance: {e}")
            return {}

    def get_conflicted_insiders(
        self,
        ticker: str,
        days_lookback: int = 90,
    ) -> List[Dict]:
        """
        Get list of insiders who are both buying and selling same ticker.

        Args:
            ticker: Stock ticker symbol
            days_lookback: Days of history to analyze

        Returns:
            List of conflicted insider dictionaries
        """
        try:
            df = get_recent_transactions(days=days_lookback, min_value=0)

            if df.empty:
                return []

            ticker_df = df[df['ticker'] == ticker]

            if ticker_df.empty:
                return []

            conflicted = []

            for insider in ticker_df['insider_name'].unique():
                insider_df = ticker_df[ticker_df['insider_name'] == insider]

                has_buys = any(insider_df['transaction_type'].isin(['BUY', 'EXERCISE']))
                has_sells = any(insider_df['transaction_type'] == 'SALE')

                if has_buys and has_sells:
                    buy_count = len(insider_df[insider_df['transaction_type'].isin(['BUY', 'EXERCISE', 'PURCHASE', 'BUY EXERCISE'])])
                    sell_count = len(insider_df[insider_df['transaction_type'].isin(['SALE', 'SALE - COVERED CALL'])])

                    buy_value = insider_df[
                        insider_df['transaction_type'].isin(['BUY', 'EXERCISE'])
                    ]['total_value'].sum()
                    sell_value = insider_df[insider_df['transaction_type'].isin(['SALE', 'SALE - COVERED CALL'])][
                        'total_value'
                    ].sum()

                    # Get most recent transaction date
                    most_recent = insider_df['transaction_date'].max()

                    conflicted.append({
                        'insider_name': insider,
                        'ticker': ticker,
                        'buy_count': int(buy_count),
                        'sell_count': int(sell_count),
                        'buy_value': float(buy_value),
                        'sell_value': float(sell_value),
                        'most_recent_date': most_recent,
                        'note': 'Buying AND selling - signal is mixed/conflicted'
                    })

            return conflicted

        except Exception as e:
            logger.warning(f"Error getting conflicted insiders for {ticker}: {e}")
            return []

    def get_insider_sentiment_trend(
        self,
        ticker: str,
        days_lookback: int = 90,
        period_days: int = 30,
    ) -> List[Dict]:
        """
        Get insider sentiment trend over time periods.

        Args:
            ticker: Stock ticker symbol
            days_lookback: Total days of history to analyze
            period_days: Number of days per period for trend analysis

        Returns:
            List of period dictionaries with sentiment metrics
        """
        try:
            df = get_recent_transactions(days=days_lookback, min_value=0)

            if df.empty:
                return []

            ticker_df = df[df['ticker'] == ticker]

            if ticker_df.empty:
                return []

            # Create time periods
            now = datetime.now()
            periods = []

            for i in range(0, days_lookback, period_days):
                period_start = now - timedelta(days=i + period_days)
                period_end = now - timedelta(days=i)

                period_df = ticker_df[
                    (ticker_df['transaction_date'] >= period_start.date())
                    & (ticker_df['transaction_date'] <= period_end.date())
                ]

                if not period_df.empty:
                    buy_count = len(
                        period_df[period_df['transaction_type'].isin(['BUY', 'EXERCISE', 'PURCHASE', 'BUY EXERCISE'])]
                    )
                    sell_count = len(period_df[period_df['transaction_type'].isin(['SALE', 'SALE - COVERED CALL'])])

                    net_sentiment = (buy_count - sell_count) / (buy_count + sell_count) if (
                        buy_count + sell_count
                    ) > 0 else 0

                    periods.append({
                        'period_start': period_start.date(),
                        'period_end': period_end.date(),
                        'buy_count': int(buy_count),
                        'sell_count': int(sell_count),
                        'net_sentiment': float(net_sentiment),
                    })

            return periods

        except Exception as e:
            logger.warning(f"Error getting sentiment trend for {ticker}: {e}")
            return []


# Global instance
_insider_commitment_instance = None


def get_insider_commitment_analyzer() -> InsiderCommitmentAnalyzer:
    """Get singleton instance of insider commitment analyzer."""
    global _insider_commitment_instance
    if _insider_commitment_instance is None:
        _insider_commitment_instance = InsiderCommitmentAnalyzer()
    return _insider_commitment_instance


if __name__ == '__main__':
    analyzer = get_insider_commitment_analyzer()

    # Test with 4 tickers
    tickers = ['AAPL', 'META', 'AMZN', 'MSFT']

    print('\n' + '=' * 80)
    print('INSIDER COMMITMENT ANALYSIS')
    print('=' * 80 + '\n')

    for ticker in tickers:
        score, details = analyzer.calculate_insider_commitment_score(ticker)
        print(f'{ticker}:')
        print(f'  Commitment Score: {score:.4f}')
        print(f'  Interpretation: {details.get("interpretation", "N/A")}')
        print(f'  Buys: {details.get("buy_count", 0)}, Sells: {details.get("sell_count", 0)}')
        print(f'  Conflicted Insiders: {details.get("conflicted_count", 0)}')
        print()
