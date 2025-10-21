"""Earnings date tracking and sentiment analysis."""
from typing import Dict, Optional, Tuple
from datetime import datetime, timedelta
import yfinance as yf
from loguru import logger
import requests
import time
import os


class EarningsTracker:
    """Tracks earnings dates and analyzes call transcripts for sentiment."""

    GREEN_FLAGS = [
        'visibility',
        'momentum',
        'margin expansion',
        'record backlog',
        'strong demand',
        'guidance raise',
        'market share gain',
        'efficiency gain',
        'cash generation',
        'diversification',
    ]

    RED_FLAGS = [
        'uncertainty',
        'headwinds',
        'macro concerns',
        'competitive pressure',
        'margin pressure',
        'guidance cut',
        'inventory buildup',
        'cash burn',
        'market share loss',
        'geopolitical',
    ]

    def __init__(self):
        """Initialize earnings tracker."""
        self.cache = {}
        self.cache_time = {}
        self.cache_ttl = 86400  # 24 hours for earnings dates

    def _get_cached(self, key: str) -> Optional[Dict]:
        """Get cached data if valid."""
        if key in self.cache:
            if time.time() - self.cache_time.get(key, 0) < self.cache_ttl:
                return self.cache[key]
        return None

    def _set_cached(self, key: str, data):
        """Cache data with timestamp."""
        self.cache[key] = data
        self.cache_time[key] = time.time()

    def get_next_earnings_date(self, ticker: str) -> Optional[datetime]:
        """
        Get next earnings date for ticker.

        Args:
            ticker: Stock ticker

        Returns:
            Next earnings date or None
        """
        ticker = ticker.upper()
        cache_key = f"earnings_date_{ticker}"

        # Check cache
        cached = self._get_cached(cache_key)
        if cached:
            return cached

        try:
            stock = yf.Ticker(ticker)
            info = stock.info

            # yfinance provides earnings dates
            if 'earnings_dates' in info:
                earnings_dates = info['earnings_dates']
                if earnings_dates and len(earnings_dates) > 0:
                    # Get next upcoming earnings
                    now = datetime.now()
                    for date in earnings_dates:
                        if isinstance(date, (datetime, pd.Timestamp)):
                            if date > now:
                                result = date.to_pydatetime() if hasattr(date, 'to_pydatetime') else date
                                self._set_cached(cache_key, result)
                                return result

            # Fallback: try calendar field
            earnings_date = info.get('earnings_date')
            if earnings_date:
                if isinstance(earnings_date, (datetime, pd.Timestamp)):
                    result = earnings_date.to_pydatetime() if hasattr(earnings_date, 'to_pydatetime') else earnings_date
                    self._set_cached(cache_key, result)
                    return result

            logger.debug(f"No earnings date found for {ticker}")
            return None

        except Exception as e:
            logger.debug(f"Error getting earnings date for {ticker}: {e}")
            return None

    def is_in_blackout_period(
        self, ticker: str, transaction_date: datetime, blackout_days: int = 14
    ) -> bool:
        """
        Check if transaction is in blackout period before earnings.

        Insider buying close to earnings is a RED FLAG.

        Args:
            ticker: Stock ticker
            transaction_date: Date of insider purchase
            blackout_days: Days before earnings to flag (default 14)

        Returns:
            True if in blackout period
        """
        try:
            earnings_date = self.get_next_earnings_date(ticker)

            if not earnings_date:
                return False

            # Check if transaction is within blackout_days before earnings
            days_until_earnings = (earnings_date - transaction_date).days

            if 0 <= days_until_earnings <= blackout_days:
                logger.debug(
                    f"{ticker}: Transaction {days_until_earnings} days before earnings - BLACKOUT"
                )
                return True

            return False

        except Exception as e:
            logger.debug(f"Error checking blackout period: {e}")
            return False

    def analyze_recent_earnings_call(
        self, ticker: str, filing_date: datetime, lookback_days: int = 90
    ) -> Tuple[float, int, float]:
        """
        Analyze recent earnings call sentiment.

        If earnings call was POSITIVE within 5-30 days before insider buy,
        it's a strong signal that insider knows about good results.

        Args:
            ticker: Stock ticker
            filing_date: Date of insider filing
            lookback_days: Days back to search for earnings call

        Returns:
            Tuple of (sentiment_score, days_since_call, confidence)
            sentiment_score: -1.0 to 1.0 (negative to positive)
            days_since_call: Days between earnings and insider filing
            confidence: 0-1.0 (how confident in the analysis)
        """
        try:
            # Get recent earnings dates
            start_date = filing_date - timedelta(days=lookback_days)
            earnings_date = self.get_next_earnings_date(ticker)

            if not earnings_date:
                return 0.0, 0, 0.0

            # Check if earnings was within lookback window
            if earnings_date < start_date or earnings_date > filing_date:
                return 0.0, 0, 0.0

            days_since_call = (filing_date - earnings_date).days

            # Most valuable signal: 5-30 days between earnings and insider buy
            # Insider has time to execute after call but still fresh knowledge
            if not (5 <= days_since_call <= 30):
                return 0.0, days_since_call, 0.3  # Low confidence outside window

            # Try to get earnings transcript
            transcript = self._get_earnings_transcript(ticker, earnings_date)

            if not transcript:
                # Default: slightly positive confidence if earnings nearby
                return 0.1, days_since_call, 0.3

            # Analyze sentiment
            sentiment_score = self._analyze_sentiment(transcript)
            confidence = 0.8  # High confidence with actual transcript

            logger.debug(
                f"{ticker}: Earnings sentiment {sentiment_score:.2f} "
                f"({days_since_call} days before insider buy)"
            )

            return sentiment_score, days_since_call, confidence

        except Exception as e:
            logger.debug(f"Error analyzing earnings: {e}")
            return 0.0, 0, 0.0

    def _get_earnings_transcript(
        self, ticker: str, earnings_date: datetime
    ) -> Optional[str]:
        """Fetch earnings call transcript from SEC 8-K or alternative sources."""
        try:
            # This would require SEC EDGAR integration or API
            # For now, return None to indicate not available
            # In production, would fetch from SEC or use Seeking Alpha API

            logger.debug(f"Earnings transcript retrieval not implemented for {ticker}")
            return None

        except Exception as e:
            logger.debug(f"Error fetching earnings transcript: {e}")
            return None

    def _analyze_sentiment(self, transcript: str) -> float:
        """
        Analyze earnings call transcript for sentiment.

        Returns:
            Score -1.0 to 1.0 (negative to positive)
        """
        try:
            if not transcript:
                return 0.0

            transcript_lower = transcript.lower()

            # Count flags
            green_count = sum(
                transcript_lower.count(flag.lower()) for flag in self.GREEN_FLAGS
            )
            red_count = sum(
                transcript_lower.count(flag.lower()) for flag in self.RED_FLAGS
            )

            total = green_count + red_count + 1
            sentiment = (green_count - red_count) / total

            return max(-1.0, min(1.0, sentiment))

        except Exception as e:
            logger.debug(f"Error analyzing sentiment: {e}")
            return 0.0

    def get_earnings_multiplier(
        self, ticker: str, filing_date: datetime
    ) -> Tuple[float, str]:
        """
        Get earnings multiplier for conviction score.

        Args:
            ticker: Stock ticker
            filing_date: Date of insider filing

        Returns:
            Tuple of (multiplier 1.0-1.3x, reason)
        """
        try:
            sentiment, days_since, confidence = self.analyze_recent_earnings_call(
                ticker, filing_date
            )

            # Positive recent earnings + insider buy = 1.3x
            if sentiment > 0.3 and 5 <= days_since <= 30 and confidence > 0.5:
                reason = f"Positive earnings {days_since}d ago (sentiment={sentiment:.2f})"
                return 1.3, reason

            # Neutral or no recent earnings
            return 1.0, "No recent positive earnings"

        except Exception as e:
            logger.debug(f"Error getting earnings multiplier: {e}")
            return 1.0, f"Error: {str(e)}"


if __name__ == "__main__":
    import pandas as pd

    tracker = EarningsTracker()

    # Test earnings date
    ticker = "AAPL"
    earnings = tracker.get_next_earnings_date(ticker)
    print(f"\nNext earnings for {ticker}: {earnings}")

    # Test blackout period
    test_date = earnings - timedelta(days=7) if earnings else datetime.now()
    is_blackout = tracker.is_in_blackout_period(ticker, test_date)
    print(f"Is blackout period: {is_blackout}")

    # Test earnings multiplier
    mult, reason = tracker.get_earnings_multiplier(ticker, datetime.now())
    print(f"\nEarnings multiplier: {mult}x")
    print(f"Reason: {reason}")
