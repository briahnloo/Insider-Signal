"""Red flag detection and penalty system."""
from typing import Dict, Tuple
from datetime import datetime, timedelta
import pandas as pd
from loguru import logger

from src.database import get_transactions_by_ticker
from src.data_collection.market_data_cache import get_market_cache

try:
    from src.data_collection.earnings_tracker import EarningsTracker
    EARNINGS_AVAILABLE = True
except:
    EARNINGS_AVAILABLE = False


class RedFlagDetector:
    """Detects red flags that reduce conviction."""

    BLACKOUT_PERIOD_DAYS = 30  # Typical blackout period
    RECENT_RUNUP_DAYS = 60
    MIN_PURCHASE_AMOUNT = 50000
    EARNINGS_BLACKOUT_DAYS = 14  # Insider buying close to earnings = RED FLAG

    def __init__(self):
        """Initialize red flag detector."""
        self.earnings_tracker = EarningsTracker() if EARNINGS_AVAILABLE else None
        self.market_cache = get_market_cache()

    def detect_all_flags(self, ticker: str, transaction_date: datetime) -> Dict:
        """
        Comprehensive red flag check.

        Args:
            ticker: Stock ticker
            transaction_date: Date of insider purchase

        Returns:
            Dict with flags and penalty multiplier (0.5-1.0x)
        """
        flags = []
        penalty = 1.0

        # Check each flag type
        if self._is_blackout_period(ticker, transaction_date):
            flags.append('blackout_period')
            penalty *= 0.7

        if self._is_recent_runup(ticker, transaction_date):
            flags.append('recent_runup')
            penalty *= 0.8

        if self._is_small_purchase(ticker, transaction_date):
            flags.append('small_purchase')
            penalty *= 0.85

        # NEW: Check if buying close to earnings (earnings blackout)
        if EARNINGS_AVAILABLE and self.earnings_tracker:
            if self._is_earnings_blackout(ticker, transaction_date):
                flags.append('earnings_blackout')
                penalty *= 0.3  # Heavy penalty

        penalty = max(penalty, 0.5)  # Floor at 0.5x

        logger.debug(f"{ticker}: Flags={flags}, Penalty={penalty:.2f}x")

        return {
            'ticker': ticker,
            'flags': flags,
            'penalty_multiplier': penalty,
            'flag_count': len(flags),
        }

    def _is_blackout_period(self, ticker: str, transaction_date: datetime) -> bool:
        """
        Check if purchase is during typical blackout period.
        (Usually 30-60 days before earnings or near ex-dividend date)
        """
        # This would require earnings calendar data
        # For now, return False (no earnings data available)
        return False

    def _is_recent_runup(
        self, ticker: str, transaction_date: datetime, runup_pct: float = 30
    ) -> bool:
        """
        Check if stock had recent runup (possible insider dumping later).

        Args:
            ticker: Stock ticker
            transaction_date: Date of purchase
            runup_pct: Runup threshold (default 30%)

        Returns:
            True if stock had 30%+ runup in 60 days before purchase
        """
        try:
            # Try cache first
            hist = self.market_cache.get_cached_price_history(ticker, days=60)
            
            if hist is None or len(hist) < 5:
                # Fallback to direct yfinance
                import yfinance as yf
                stock = yf.Ticker(ticker)
                start_date = transaction_date - timedelta(days=60)
                end_date = transaction_date
                hist = stock.history(start=start_date, end=end_date)

            if len(hist) < 5:
                return False

            # Calculate return from 60 days ago to transaction date
            old_price = hist.iloc[0]['Close']
            new_price = hist.iloc[-1]['Close']

            if old_price <= 0:
                return False

            runup = ((new_price - old_price) / old_price) * 100

            return runup > runup_pct

        except Exception as e:
            logger.debug(f"Could not check runup for {ticker}: {e}")
            return False

    def _is_small_purchase(self, ticker: str, transaction_date: datetime) -> bool:
        """
        Check if purchase is unusually small for this insider.

        Args:
            ticker: Stock ticker
            transaction_date: Date of purchase

        Returns:
            True if purchase is significantly smaller than insider's average
        """
        try:
            df = get_transactions_by_ticker(ticker, days=180)

            if df.empty or len(df) < 3:
                return False

            avg_value = df['total_value'].mean()

            # Get most recent transaction value
            recent = df[df['transaction_date'] <= transaction_date]
            if recent.empty:
                return False

            recent_value = recent.iloc[0]['total_value']

            # Flag if < 50% of average
            is_small = recent_value < (avg_value * 0.5)

            return is_small

        except Exception as e:
            logger.debug(f"Could not check purchase size for {ticker}: {e}")
            return False

    def check_for_dump(
        self, ticker: str, insider_name: str, days_after: int = 30
    ) -> Dict:
        """
        Check if insider dumped shares soon after buying.

        Args:
            ticker: Stock ticker
            insider_name: Name of insider
            days_after: Days after purchase to check

        Returns:
            Dict with dump info and penalty
        """
        try:
            df = get_transactions_by_ticker(ticker, days=180)

            if df.empty:
                return {
                    'ticker': ticker,
                    'insider_name': insider_name,
                    'dumped': False,
                    'penalty': 1.0,
                }

            # Filter to this insider
            insider_df = df[df['insider_name'] == insider_name].sort_values(
                'transaction_date'
            )

            if len(insider_df) < 2:
                return {
                    'ticker': ticker,
                    'insider_name': insider_name,
                    'dumped': False,
                    'penalty': 1.0,
                }

            # Check if sold within days_after of buying
            recent_buy = insider_df[insider_df['transaction_type'] == 'PURCHASE']

            if recent_buy.empty:
                return {
                    'ticker': ticker,
                    'insider_name': insider_name,
                    'dumped': False,
                    'penalty': 1.0,
                }

            last_buy_date = recent_buy.iloc[-1]['transaction_date']
            window_end = last_buy_date + timedelta(days=days_after)

            # Check for sales in the window
            sales = df[
                (df['insider_name'] == insider_name)
                & (df['transaction_type'] == 'SALE')
                & (df['transaction_date'] >= last_buy_date)
                & (df['transaction_date'] <= window_end)
            ]

            dumped = len(sales) > 0
            penalty = 0.5 if dumped else 1.0

            return {
                'ticker': ticker,
                'insider_name': insider_name,
                'dumped': dumped,
                'dump_count': len(sales),
                'penalty': penalty,
            }

        except Exception as e:
            logger.error(f"Error checking for dump: {e}")
            return {
                'ticker': ticker,
                'insider_name': insider_name,
                'error': str(e),
                'penalty': 1.0,
            }

    def _is_earnings_blackout(
        self, ticker: str, transaction_date: datetime
    ) -> bool:
        """
        Check if insider is buying close to earnings announcement.

        This is a RED FLAG because:
        - Could be trading on material non-public information
        - Insiders typically cannot buy in blackout periods
        - If they do, it suggests risk they know about

        Args:
            ticker: Stock ticker
            transaction_date: Date of insider purchase

        Returns:
            True if buying within EARNINGS_BLACKOUT_DAYS of earnings
        """
        if not self.earnings_tracker:
            return False

        try:
            is_blackout = self.earnings_tracker.is_in_blackout_period(
                ticker, transaction_date, blackout_days=self.EARNINGS_BLACKOUT_DAYS
            )
            return is_blackout
        except Exception as e:
            logger.debug(f"Error checking earnings blackout: {e}")
            return False


if __name__ == "__main__":
    detector = RedFlagDetector()
    flags = detector.detect_all_flags("AAPL", datetime.now())
    print(f"Red flags: {flags}")
