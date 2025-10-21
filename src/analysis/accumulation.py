"""Accumulation pattern detection."""
from typing import Dict, List
from datetime import datetime, timedelta
import pandas as pd
from loguru import logger

from src.database import get_transactions_by_ticker


class AccumulationDetector:
    """Detects accumulation patterns from insider buying."""

    def detect_multi_insider_accumulation(
        self, ticker: str, window_days: int = 14
    ) -> Dict:
        """
        Detect 2+ insiders buying same stock in time window.

        Args:
            ticker: Stock ticker
            window_days: Time window to check (default 14 days)

        Returns:
            Dict with pattern info and multiplier (1.0-1.5x)
        """
        try:
            df = get_transactions_by_ticker(ticker, days=window_days)

            if df.empty:
                return {
                    'ticker': ticker,
                    'pattern': 'none',
                    'multiplier': 1.0,
                    'insider_count': 0,
                    'transactions': 0,
                }

            # Count unique insiders
            insider_count = df['insider_name'].nunique()
            transaction_count = len(df)
            total_value = df['total_value'].sum()
            avg_value = df['total_value'].mean()

            # Determine pattern and multiplier
            pattern = 'none'
            multiplier = 1.0

            if insider_count >= 3:
                pattern = 'strong_accumulation'
                multiplier = 1.5
            elif insider_count == 2:
                pattern = 'dual_accumulation'
                multiplier = 1.3
            else:
                pattern = 'single_buyer'
                multiplier = 1.0

            logger.debug(
                f"{ticker}: {insider_count} insiders, "
                f"{transaction_count} buys in {window_days} days"
            )

            return {
                'ticker': ticker,
                'pattern': pattern,
                'multiplier': multiplier,
                'insider_count': insider_count,
                'transactions': transaction_count,
                'total_value': total_value,
                'avg_value': avg_value,
                'insiders': df['insider_name'].unique().tolist(),
            }

        except Exception as e:
            logger.error(f"Error detecting accumulation for {ticker}: {e}")
            return {
                'ticker': ticker,
                'pattern': 'error',
                'multiplier': 1.0,
                'error': str(e),
            }

    def detect_sustained_accumulation(
        self, ticker: str, insider_name: str, days: int = 90
    ) -> Dict:
        """
        Detect sustained buying by same insider over time.

        Args:
            ticker: Stock ticker
            insider_name: Name of insider
            days: Time period to check

        Returns:
            Dict with sustained buying pattern
        """
        try:
            df = get_transactions_by_ticker(ticker, days=days)

            if df.empty:
                return {
                    'ticker': ticker,
                    'insider_name': insider_name,
                    'sustained': False,
                    'multiplier': 1.0,
                    'transaction_count': 0,
                }

            # Filter to specific insider
            insider_df = df[df['insider_name'] == insider_name]

            if len(insider_df) < 2:
                return {
                    'ticker': ticker,
                    'insider_name': insider_name,
                    'sustained': False,
                    'multiplier': 1.0,
                    'transaction_count': len(insider_df),
                }

            # Check if transactions are spread across time (not all in one day)
            transactions = len(insider_df)
            total_value = insider_df['total_value'].sum()
            first_buy = insider_df['transaction_date'].min()
            last_buy = insider_df['transaction_date'].max()
            days_span = (last_buy - first_buy).days

            sustained = days_span > 30  # Spread over 30+ days
            multiplier = 1.2 if sustained else 1.0

            logger.debug(
                f"{insider_name} ({ticker}): "
                f"{transactions} buys over {days_span} days"
            )

            return {
                'ticker': ticker,
                'insider_name': insider_name,
                'sustained': sustained,
                'multiplier': multiplier,
                'transaction_count': transactions,
                'total_value': total_value,
                'days_span': days_span,
            }

        except Exception as e:
            logger.error(
                f"Error detecting sustained accumulation for {ticker}: {e}"
            )
            return {
                'ticker': ticker,
                'insider_name': insider_name,
                'error': str(e),
                'multiplier': 1.0,
            }

    def detect_officer_buying(self, ticker: str, days: int = 30) -> Dict:
        """
        Detect buying by officers (CEO, CFO, COO, etc).

        Args:
            ticker: Stock ticker
            days: Time window

        Returns:
            Dict with officer buying info
        """
        try:
            df = get_transactions_by_ticker(ticker, days=days)

            if df.empty:
                return {
                    'ticker': ticker,
                    'officer_buying': False,
                    'multiplier': 1.0,
                    'officers': [],
                }

            # Officer titles to flag
            officer_titles = ['CEO', 'CFO', 'COO', 'CTO', 'President', 'Chairman']

            # Filter to officers
            officer_df = df[
                df['insider_title'].str.contains(
                    '|'.join(officer_titles), case=False, na=False
                )
            ]

            if officer_df.empty:
                return {
                    'ticker': ticker,
                    'officer_buying': False,
                    'multiplier': 1.0,
                    'officers': [],
                }

            # Get unique officers and their totals
            officers = {}
            for _, row in officer_df.iterrows():
                name = row['insider_name']
                title = row['insider_title']
                if name not in officers:
                    officers[name] = {'title': title, 'buys': 0, 'value': 0}
                officers[name]['buys'] += 1
                officers[name]['value'] += row['total_value']

            # Multiplier based on number of officers buying
            officer_count = len(officers)
            if officer_count >= 2:
                multiplier = 1.3
            elif officer_count == 1:
                multiplier = 1.15
            else:
                multiplier = 1.0

            logger.debug(f"{ticker}: {officer_count} officers buying")

            return {
                'ticker': ticker,
                'officer_buying': len(officers) > 0,
                'officer_count': officer_count,
                'multiplier': multiplier,
                'officers': officers,
            }

        except Exception as e:
            logger.error(f"Error detecting officer buying for {ticker}: {e}")
            return {
                'ticker': ticker,
                'error': str(e),
                'multiplier': 1.0,
            }


if __name__ == "__main__":
    detector = AccumulationDetector()
    result = detector.detect_multi_insider_accumulation("AAPL", window_days=30)
    print(f"Accumulation pattern: {result}")
