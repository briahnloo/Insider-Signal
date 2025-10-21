"""
Real earnings transcript fetching and sentiment analysis.
Fetches actual earnings call transcripts from SEC filings and performs NLP-based sentiment analysis.
"""
from typing import Dict, Optional, Tuple
from datetime import datetime, timedelta
import re
import yfinance as yf
from loguru import logger
import requests
import time
from urllib.parse import quote
import json

try:
    from textblob import TextBlob
    HAS_TEXTBLOB = True
except ImportError:
    HAS_TEXTBLOB = False
    logger.warning("TextBlob not installed. Install with: pip install textblob")

try:
    import feedparser
    HAS_FEEDPARSER = True
except ImportError:
    HAS_FEEDPARSER = False
    logger.warning("feedparser not installed. Install with: pip install feedparser")


class EarningsSentimentAnalyzer:
    """Fetches and analyzes real earnings call transcripts for sentiment."""

    # Keywords for financial sentiment
    POSITIVE_KEYWORDS = {
        'strong': 2.0, 'growth': 2.0, 'exceed': 2.5, 'record': 2.5,
        'expand': 1.5, 'momentum': 2.0, 'outperform': 2.0, 'beat': 2.5,
        'uplift': 2.0, 'upgrade': 2.0, 'strength': 1.5, 'opportunity': 1.5,
        'margin expansion': 3.0, 'market share gain': 2.5, 'efficiency': 1.5,
        'cash generation': 2.0, 'guidance raise': 3.0, 'visibility': 2.0,
        'confidence': 1.5, 'positive': 1.5, 'excellent': 2.0, 'remarkable': 2.0,
        'accelerating': 2.0, 'diversification': 1.5, 'integration': 1.5,
        'synergy': 2.0, 'expansion': 1.5, 'leading': 1.5,
    }

    NEGATIVE_KEYWORDS = {
        'weakness': -2.0, 'decline': -1.5, 'miss': -2.5, 'challenged': -2.0,
        'headwind': -2.0, 'uncertainty': -2.0, 'pressure': -1.5, 'difficult': -1.5,
        'guidance cut': -3.0, 'lower': -1.5, 'concern': -1.5, 'risk': -1.0,
        'macro concerns': -2.5, 'competitive pressure': -2.0, 'margin pressure': -2.0,
        'inventory buildup': -2.0, 'cash burn': -2.5, 'market share loss': -2.5,
        'geopolitical': -2.0, 'downside': -2.0, 'challenge': -1.5, 'caution': -1.0,
        'unfavorable': -1.5, 'deteriorate': -2.0, 'slowdown': -1.5, 'contraction': -1.5,
    }

    def __init__(self):
        """Initialize earnings sentiment analyzer."""
        self.cache = {}
        self.cache_time = {}
        self.cache_ttl = 86400  # 24 hours
        self.sec_filings_url = "https://www.sec.gov/cgi-bin/browse-edgar"
        self.user_agent = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"

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

    def fetch_recent_earnings_transcripts(
        self, ticker: str, max_days_back: int = 90
    ) -> Optional[str]:
        """
        Fetch the most recent earnings call transcript from SEC filings.

        Args:
            ticker: Stock ticker symbol
            max_days_back: Maximum days to look back for earnings

        Returns:
            Transcript text or None if not found
        """
        ticker = ticker.upper()
        cache_key = f"transcript_{ticker}"

        # Check cache first
        cached = self._get_cached(cache_key)
        if cached:
            return cached

        try:
            # Get CIK (Central Index Key) for the company
            cik = self._get_cik_number(ticker)
            if not cik:
                logger.debug(f"Could not find CIK for {ticker}")
                return None

            # Fetch 8-K filings (current reports - often contain earnings transcripts)
            transcript = self._fetch_from_sec_8k(cik, ticker, max_days_back)
            if transcript:
                self._set_cached(cache_key, transcript)
                return transcript

            # Fallback: Try to get from Yahoo Finance or earnings.com equivalent
            transcript = self._fetch_from_alternative_sources(ticker)
            if transcript:
                self._set_cached(cache_key, transcript)
                return transcript

            return None

        except Exception as e:
            logger.debug(f"Error fetching earnings transcript for {ticker}: {e}")
            return None

    def _get_cik_number(self, ticker: str) -> Optional[str]:
        """
        Look up SEC CIK number for a ticker.

        Args:
            ticker: Stock ticker symbol

        Returns:
            CIK number or None
        """
        try:
            # Try SEC EDGAR lookup
            search_url = f"https://www.sec.gov/cgi-bin/browse-edgar?company={quote(ticker)}&owner=exclude&action=getcompany"
            headers = {"User-Agent": self.user_agent}

            response = requests.get(search_url, headers=headers, timeout=10)
            if response.status_code == 200:
                # Extract CIK from response - look for /cgi-bin/browse-edgar?action=getcompany&CIK=
                match = re.search(r'CIK=(\d+)', response.text)
                if match:
                    cik = match.group(1).lstrip('0') or '0'
                    return cik

        except Exception as e:
            logger.debug(f"Error looking up CIK for {ticker}: {e}")

        return None

    def _fetch_from_sec_8k(
        self, cik: str, ticker: str, max_days_back: int
    ) -> Optional[str]:
        """
        Fetch earnings transcript from SEC 8-K filings.

        Args:
            cik: SEC CIK number
            ticker: Stock ticker
            max_days_back: Maximum days back to search

        Returns:
            Transcript text or None
        """
        try:
            # Query SEC EDGAR for 8-K filings
            base_url = "https://www.sec.gov/cgi-bin/browse-edgar"
            params = {
                "action": "getcompany",
                "CIK": cik,
                "type": "8-K",
                "dateb": "",
                "owner": "exclude",
                "count": "10",
                "output": "atom"
            }

            headers = {"User-Agent": self.user_agent}
            response = requests.get(base_url, params=params, headers=headers, timeout=10)

            if response.status_code != 200:
                return None

            # Parse RSS feed
            if not HAS_FEEDPARSER:
                logger.debug("feedparser required to parse SEC filings")
                return None

            feed = feedparser.parse(response.content)
            if not feed.entries:
                return None

            # Get most recent filing
            for entry in feed.entries[:5]:  # Check first 5 filings
                filing_url = entry.link
                transcript = self._extract_transcript_from_filing(filing_url)
                if transcript and len(transcript) > 500:  # Minimum length check
                    return transcript

            return None

        except Exception as e:
            logger.debug(f"Error fetching from SEC 8-K: {e}")
            return None

    def _extract_transcript_from_filing(self, filing_url: str) -> Optional[str]:
        """
        Extract transcript text from SEC filing document.

        Args:
            filing_url: URL of SEC filing

        Returns:
            Extracted transcript text or None
        """
        try:
            # Get the document from SEC
            # SEC filings often use 0000950123-XX-XXXXX format
            # Replace -index.html with .txt to get full text version
            text_url = filing_url.replace('-index.html', '.txt').replace('browse-edgar', 'viewer')

            headers = {"User-Agent": self.user_agent}
            response = requests.get(text_url, headers=headers, timeout=10)

            if response.status_code == 200:
                text = response.text

                # Extract conference call section if it exists
                # Look for common markers in earnings transcripts
                markers = [
                    'conference call', 'earnings call', 'q&a', 'question and answer',
                    'prepared remarks', 'management discussion'
                ]

                text_lower = text.lower()
                start_idx = 0

                for marker in markers:
                    idx = text_lower.find(marker)
                    if idx > 0:
                        start_idx = idx
                        break

                if start_idx > 0:
                    # Take reasonable chunk after marker
                    return text[start_idx:start_idx + 50000]
                else:
                    # Return text but filter out metadata
                    return self._clean_filing_text(text)

            return None

        except Exception as e:
            logger.debug(f"Error extracting transcript from filing: {e}")
            return None

    def _clean_filing_text(self, text: str) -> str:
        """Remove SEC formatting and boilerplate from filing text."""
        # Remove common SEC header/footer noise
        lines = text.split('\n')

        # Filter out pure metadata lines
        content_lines = [
            line for line in lines
            if len(line.strip()) > 20 and not line.startswith('---') and
            '0000' not in line[:4]  # Skip lines starting with common CIK format
        ]

        return '\n'.join(content_lines[-20000:])  # Return last portion

    def _fetch_from_alternative_sources(self, ticker: str) -> Optional[str]:
        """
        Fallback: Try to fetch from alternative sources (free APIs if available).

        Args:
            ticker: Stock ticker

        Returns:
            Transcript text or None
        """
        try:
            # Try MarketWatch earnings transcripts (unofficial)
            mw_url = f"https://www.marketwatch.com/investing/stock/{ticker.lower()}/profile"

            # This is a fallback and may not always work
            # In production, might want to use a paid service like SeekingAlpha API
            logger.debug(f"Alternative sources lookup not fully implemented for {ticker}")

            return None

        except Exception as e:
            logger.debug(f"Error fetching from alternative sources: {e}")
            return None

    def analyze_transcript_sentiment(
        self, transcript: str, weighted: bool = True
    ) -> Tuple[float, Dict]:
        """
        Analyze earnings transcript for sentiment using keyword-based approach.

        Args:
            transcript: Full transcript text
            weighted: If True, use weighted keyword scoring; if False, use TextBlob

        Returns:
            Tuple of (sentiment_score -1.0 to 1.0, analysis_details)
        """
        try:
            if not transcript or len(transcript) < 100:
                return 0.0, {'method': 'insufficient_data', 'transcript_length': len(transcript) if transcript else 0}

            transcript_lower = transcript.lower()

            if weighted:
                # Weighted keyword-based approach (deterministic)
                return self._keyword_sentiment(transcript_lower)
            else:
                # TextBlob-based approach (if available)
                if HAS_TEXTBLOB:
                    return self._textblob_sentiment(transcript)
                else:
                    return self._keyword_sentiment(transcript_lower)

        except Exception as e:
            logger.debug(f"Error analyzing sentiment: {e}")
            return 0.0, {'error': str(e), 'method': 'error'}

    def _keyword_sentiment(self, text: str) -> Tuple[float, Dict]:
        """
        Analyze sentiment using weighted keyword matching.

        Args:
            text: Lowercase transcript text

        Returns:
            Tuple of (sentiment_score, details)
        """
        positive_score = 0.0
        negative_score = 0.0
        positive_hits = {}
        negative_hits = {}

        # Score positive keywords
        for keyword, weight in self.POSITIVE_KEYWORDS.items():
            count = len(re.findall(r'\b' + re.escape(keyword) + r'\b', text))
            if count > 0:
                positive_score += weight * count
                positive_hits[keyword] = count

        # Score negative keywords
        for keyword, weight in self.NEGATIVE_KEYWORDS.items():
            count = len(re.findall(r'\b' + re.escape(keyword) + r'\b', text))
            if count > 0:
                negative_score += abs(weight) * count
                negative_hits[keyword] = count

        # Calculate normalized sentiment
        total_score = positive_score + negative_score
        if total_score == 0:
            sentiment = 0.0
        else:
            sentiment = (positive_score - negative_score) / total_score

        # Clamp to -1.0 to 1.0
        sentiment = max(-1.0, min(1.0, sentiment))

        return sentiment, {
            'method': 'weighted_keywords',
            'positive_score': positive_score,
            'negative_score': negative_score,
            'total_score': total_score,
            'positive_hits': positive_hits,
            'negative_hits': negative_hits,
            'keywords_found': len(positive_hits) + len(negative_hits),
        }

    def _textblob_sentiment(self, text: str) -> Tuple[float, Dict]:
        """
        Analyze sentiment using TextBlob.

        Args:
            text: Transcript text

        Returns:
            Tuple of (sentiment_score, details)
        """
        try:
            blob = TextBlob(text)
            polarity = blob.sentiment.polarity  # -1 to 1
            subjectivity = blob.sentiment.subjectivity  # 0 to 1

            return polarity, {
                'method': 'textblob',
                'polarity': polarity,
                'subjectivity': subjectivity,
            }

        except Exception as e:
            logger.debug(f"Error using TextBlob: {e}")
            return 0.0, {'error': str(e), 'method': 'textblob_error'}

    def analyze_recent_earnings_for_ticker(
        self, ticker: str, filing_date: datetime
    ) -> Tuple[float, int, float]:
        """
        Analyze recent earnings call sentiment for a ticker.

        Args:
            ticker: Stock ticker
            filing_date: Date of insider filing

        Returns:
            Tuple of (sentiment_score -1.0 to 1.0, days_since_call, confidence)
        """
        try:
            # Get earnings date
            earnings_date = self._get_recent_earnings_date(ticker)
            if not earnings_date:
                return 0.0, 0, 0.0

            # Check if earnings was within meaningful window (5-30 days before filing)
            days_since = (filing_date - earnings_date).days

            if not (5 <= days_since <= 30):
                return 0.0, days_since, 0.3  # Low confidence outside window

            # Fetch transcript
            transcript = self.fetch_recent_earnings_transcripts(ticker)
            if not transcript:
                logger.debug(f"No transcript found for {ticker}")
                return 0.1, days_since, 0.3  # Default slightly positive

            # Analyze sentiment
            sentiment, analysis = self.analyze_transcript_sentiment(transcript)
            confidence = 0.8 if analysis.get('method') in ['weighted_keywords', 'textblob'] else 0.5

            logger.info(
                f"{ticker}: Earnings sentiment {sentiment:.2f} ({days_since}d before filing) "
                f"from {analysis.get('method', 'unknown')}"
            )

            return sentiment, days_since, confidence

        except Exception as e:
            logger.debug(f"Error analyzing recent earnings: {e}")
            return 0.0, 0, 0.0

    def _get_recent_earnings_date(self, ticker: str) -> Optional[datetime]:
        """Get recent earnings date for ticker."""
        try:
            stock = yf.Ticker(ticker)
            info = stock.info

            # Check earnings dates
            if 'earnings_dates' in info and info['earnings_dates']:
                earnings_dates = info['earnings_dates']
                if isinstance(earnings_dates, (list, tuple)) and len(earnings_dates) > 0:
                    date = earnings_dates[0]
                    if hasattr(date, 'to_pydatetime'):
                        return date.to_pydatetime()
                    elif isinstance(date, datetime):
                        return date

            # Check single earnings date
            earnings_date = info.get('earnings_date')
            if earnings_date:
                if hasattr(earnings_date, 'to_pydatetime'):
                    return earnings_date.to_pydatetime()
                elif isinstance(earnings_date, datetime):
                    return earnings_date

            return None

        except Exception as e:
            logger.debug(f"Error getting earnings date: {e}")
            return None


# Global instance
_analyzer_instance = None


def get_earnings_sentiment_analyzer() -> EarningsSentimentAnalyzer:
    """Get singleton instance of earnings sentiment analyzer."""
    global _analyzer_instance
    if _analyzer_instance is None:
        _analyzer_instance = EarningsSentimentAnalyzer()
    return _analyzer_instance


if __name__ == "__main__":
    analyzer = get_earnings_sentiment_analyzer()

    # Test with a ticker
    ticker = "AAPL"
    print(f"\n=== Testing Earnings Sentiment Analysis for {ticker} ===")

    # Fetch transcript
    print(f"\nFetching earnings transcript...")
    transcript = analyzer.fetch_recent_earnings_transcripts(ticker)
    if transcript:
        print(f"✓ Transcript found ({len(transcript)} characters)")

        # Analyze sentiment
        sentiment, details = analyzer.analyze_transcript_sentiment(transcript)
        print(f"\nSentiment Score: {sentiment:.3f}")
        print(f"Analysis Method: {details.get('method', 'unknown')}")
        print(f"Details: {json.dumps({k: v for k, v in details.items() if k != 'method'}, indent=2)}")
    else:
        print(f"✗ No transcript found for {ticker}")

    # Test recent earnings analysis
    print(f"\n\nAnalyzing recent earnings relative to filing...")
    sentiment, days_since, confidence = analyzer.analyze_recent_earnings_for_ticker(
        ticker, datetime.now()
    )
    print(f"Sentiment: {sentiment:.3f}")
    print(f"Days Since Earnings: {days_since}")
    print(f"Confidence: {confidence:.2f}")
