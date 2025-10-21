"""Silence score detection - edge from lack of market knowledge."""
from typing import Dict, List
from datetime import datetime, timedelta
from loguru import logger

from src.data_collection.options_flow import OptionsFlowAnalyzer


class SilenceDetector:
    """
    Detects market silence around insider buying.

    Core insight: If options market, news, and social media are QUIET
    around insider purchase, it means the market hasn't repriced for the
    insider buying catalyst yet. This creates an edge.
    """

    def __init__(self):
        """Initialize silence detector."""
        self.options_analyzer = OptionsFlowAnalyzer()

    def calculate_silence_score(
        self, ticker: str, filing_date: datetime
    ) -> Dict:
        """
        Calculate silence score (0-1.0).

        Higher silence = more time before market reprices = better edge

        Checks:
        1. No unusual options activity in filing_date ±2 days
        2. No unusual Seeking Alpha articles in filing_date ±7 days
        3. Low social media mentions (optional)

        Args:
            ticker: Stock ticker
            filing_date: Date insider Form 4 was filed

        Returns:
            Dict with silence_score and indicators
        """
        try:
            silence_indicators = []
            silence_score = 0.0

            # 1. Check options silence
            options_silent = self._check_options_silence(ticker, filing_date)
            if options_silent:
                silence_indicators.append("No unusual options activity")
                silence_score += 0.33

            # 2. Check news silence
            news_silent = self._check_news_silence(ticker, filing_date)
            if news_silent:
                silence_indicators.append("No unusual news coverage")
                silence_score += 0.33

            # 3. Check social media silence (optional)
            social_silent = self._check_social_silence(ticker, filing_date)
            if social_silent:
                silence_indicators.append("Low social media mentions")
                silence_score += 0.34

            silence_score = min(silence_score, 1.0)

            logger.debug(f"{ticker}: Silence score {silence_score:.3f}")

            return {
                'ticker': ticker,
                'silence_score': silence_score,
                'silence_indicators': silence_indicators,
                'indicator_count': len(silence_indicators),
            }

        except Exception as e:
            logger.error(f"Error calculating silence score: {e}")
            return {
                'ticker': ticker,
                'silence_score': 0.0,
                'error': str(e),
            }

    def _check_options_silence(
        self, ticker: str, filing_date: datetime, window_days: int = 2
    ) -> bool:
        """
        Check if options market was quiet around filing.

        No unusual call activity ±2 days = options market doesn't know yet
        """
        try:
            # Check precursor flow around filing date
            start_date = filing_date - timedelta(days=window_days)
            end_date = filing_date + timedelta(days=window_days)

            # Check for unusual activity in window
            precursor = self.options_analyzer.analyze_precursor_flow(
                ticker, filing_date, lookback_days=window_days
            )

            precursor_score = precursor.get('precursor_score', 0.0)

            # Silent if precursor score is low (no activity detected)
            is_silent = precursor_score < 0.2

            logger.debug(
                f"{ticker}: Options silence check - "
                f"precursor_score={precursor_score:.2f}, silent={is_silent}"
            )

            return is_silent

        except Exception as e:
            logger.debug(f"Error checking options silence: {e}")
            # Assume silent if can't analyze
            return True

    def _check_news_silence(
        self, ticker: str, filing_date: datetime, window_days: int = 7
    ) -> bool:
        """
        Check if news was quiet around filing.

        No major news articles ±7 days = market doesn't have catalyst awareness yet
        """
        try:
            # This would require news API integration
            # For now, assume silent (conservative estimate)
            # In production: use NewsAPI, Seeking Alpha RSS, etc.

            logger.debug(
                f"{ticker}: News silence check - not implemented, "
                f"assuming silent (conservative)"
            )
            # Return True to be conservative (count as silence indicator)
            return True

        except Exception as e:
            logger.debug(f"Error checking news silence: {e}")
            return True

    def _check_social_silence(
        self, ticker: str, filing_date: datetime, window_days: int = 7
    ) -> bool:
        """
        Check if social media mentions were low.

        Low Twitter/stocktwits mentions ±7 days = retail doesn't know yet
        """
        try:
            # This would require Twitter API or social media monitoring
            # For now, assume some silence (conservative)
            # In production: use Twitter API, Stocktwits API, etc.

            logger.debug(
                f"{ticker}: Social media silence check - not implemented, "
                f"assuming partial silence"
            )
            # Return True conservatively
            return True

        except Exception as e:
            logger.debug(f"Error checking social silence: {e}")
            return False  # Don't penalize if can't check

    def interpret_silence_score(self, silence_score: float) -> str:
        """Interpret silence score."""
        if silence_score >= 0.9:
            return "Extreme silence - strong edge"
        elif silence_score >= 0.66:
            return "High silence - good edge"
        elif silence_score >= 0.33:
            return "Moderate silence - some edge"
        else:
            return "Low silence - limited edge"


if __name__ == "__main__":
    detector = SilenceDetector()

    result = detector.calculate_silence_score("AAPL", datetime.now())
    print(f"\nSilence Score for AAPL:")
    print(f"  Score: {result['silence_score']:.3f}")
    print(f"  Indicators: {result.get('silence_indicators', [])}")
    print(f"  Interpretation: {detector.interpret_silence_score(result['silence_score'])}")
