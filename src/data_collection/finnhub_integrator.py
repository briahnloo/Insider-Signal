"""
Finnhub API integration for enhanced market data and analytics.
Free tier includes company news, earnings data, and economic calendars.
"""
from typing import Dict, List, Optional, Tuple
from datetime import datetime, timedelta
import requests
from loguru import logger
import time
import os

# Finnhub endpoints (free tier available)
FINNHUB_BASE_URL = "https://finnhub.io/api/v1"


class FinnhubIntegrator:
    """Integration with Finnhub API for market insights."""

    def __init__(self, api_key: Optional[str] = None):
        """
        Initialize Finnhub integrator.

        Args:
            api_key: Finnhub API key (optional, for enhanced limits)
        """
        # Try to get API key from environment
        self.api_key = api_key or os.getenv("FINNHUB_API_KEY", "")
        self.base_url = FINNHUB_BASE_URL
        self.cache = {}
        self.cache_time = {}
        self.cache_ttl = 3600  # 1 hour
        self.rate_limit_remaining = 60
        self.rate_limit_reset = None

        if not self.api_key:
            logger.warning(
                "Finnhub API key not provided. Set FINNHUB_API_KEY environment variable "
                "for better rate limits. Free tier: 60 requests/minute"
            )

    def _get_cached(self, key: str) -> Optional[Dict]:
        """Get cached data if still valid."""
        if key in self.cache:
            if time.time() - self.cache_time.get(key, 0) < self.cache_ttl:
                return self.cache[key]
        return None

    def _set_cached(self, key: str, data):
        """Cache data with timestamp."""
        self.cache[key] = data
        self.cache_time[key] = time.time()

    def _make_request(self, endpoint: str, params: Dict) -> Optional[Dict]:
        """
        Make authenticated request to Finnhub API.

        Args:
            endpoint: API endpoint path
            params: Query parameters

        Returns:
            Response JSON or None
        """
        try:
            # Add API key to params
            if self.api_key:
                params['token'] = self.api_key

            url = f"{self.base_url}/{endpoint}"
            headers = {'User-Agent': 'Intelligent-Trader/1.0'}

            response = requests.get(url, params=params, headers=headers, timeout=10)

            # Check rate limiting
            if 'X-RateLimit-Remaining' in response.headers:
                self.rate_limit_remaining = int(response.headers['X-RateLimit-Remaining'])
                logger.debug(f"Finnhub rate limit: {self.rate_limit_remaining} remaining")

            if response.status_code == 200:
                return response.json()
            elif response.status_code == 429:
                logger.warning("Finnhub rate limit exceeded")
                return None
            else:
                logger.debug(f"Finnhub error {response.status_code}: {response.text}")
                return None

        except Exception as e:
            logger.debug(f"Error making Finnhub request: {e}")
            return None

    def get_company_profile(self, ticker: str) -> Optional[Dict]:
        """
        Get detailed company profile and information.

        Args:
            ticker: Stock ticker

        Returns:
            Company profile dict or None
        """
        ticker = ticker.upper()
        cache_key = f"profile_{ticker}"

        cached = self._get_cached(cache_key)
        if cached:
            return cached

        try:
            data = self._make_request('stock/profile2', {'symbol': ticker})

            if data:
                self._set_cached(cache_key, data)
                return data

            return None

        except Exception as e:
            logger.debug(f"Error fetching company profile for {ticker}: {e}")
            return None

    def get_company_news(
        self, ticker: str, days_back: int = 7, limit: int = 10
    ) -> List[Dict]:
        """
        Get recent company news and press releases.

        Args:
            ticker: Stock ticker
            days_back: Number of days to look back
            limit: Maximum number of news items

        Returns:
            List of news articles
        """
        ticker = ticker.upper()
        cache_key = f"news_{ticker}_{days_back}"

        cached = self._get_cached(cache_key)
        if cached:
            return cached

        try:
            from_date = (datetime.now() - timedelta(days=days_back)).strftime('%Y-%m-%d')
            to_date = datetime.now().strftime('%Y-%m-%d')

            data = self._make_request('company-news', {
                'symbol': ticker,
                'from': from_date,
                'to': to_date,
            })

            if data and isinstance(data, list):
                # Sort by date and limit
                news = sorted(data, key=lambda x: x.get('datetime', 0), reverse=True)[:limit]
                self._set_cached(cache_key, news)
                return news

            return []

        except Exception as e:
            logger.debug(f"Error fetching news for {ticker}: {e}")
            return []

    def analyze_news_sentiment(self, articles: List[Dict]) -> Tuple[float, Dict]:
        """
        Analyze sentiment from news articles.

        Args:
            articles: List of article dictionaries

        Returns:
            Tuple of (sentiment_score -1.0 to 1.0, analysis_details)
        """
        try:
            if not articles:
                return 0.0, {'articles_analyzed': 0}

            # Simple keyword-based sentiment for news headlines
            positive_keywords = {
                'gain', 'surge', 'rally', 'jump', 'beat', 'record', 'profit',
                'strong', 'upgrade', 'bullish', 'growth', 'expansion', 'strength',
                'outperform', 'succeed', 'positive', 'opportunity'
            }

            negative_keywords = {
                'lose', 'fall', 'crash', 'plunge', 'miss', 'decline', 'loss',
                'weak', 'downgrade', 'bearish', 'shrink', 'contraction', 'weakness',
                'underperform', 'fail', 'negative', 'risk', 'concern', 'warning'
            }

            positive_score = 0
            negative_score = 0
            total_analyzed = 0

            for article in articles:
                headline = (article.get('headline', '') + ' ' + article.get('summary', '')).lower()

                if not headline.strip():
                    continue

                total_analyzed += 1

                # Count keyword occurrences
                for keyword in positive_keywords:
                    if keyword in headline:
                        positive_score += 1

                for keyword in negative_keywords:
                    if keyword in headline:
                        negative_score += 1

            # Calculate normalized sentiment
            total_score = positive_score + negative_score
            if total_score == 0:
                sentiment = 0.0
            else:
                sentiment = (positive_score - negative_score) / total_score

            sentiment = max(-1.0, min(1.0, sentiment))

            return sentiment, {
                'articles_analyzed': total_analyzed,
                'positive_mentions': positive_score,
                'negative_mentions': negative_score,
                'net_sentiment': positive_score - negative_score,
            }

        except Exception as e:
            logger.debug(f"Error analyzing news sentiment: {e}")
            return 0.0, {'error': str(e)}

    def get_earnings_calendar(
        self, start_date: Optional[datetime] = None, end_date: Optional[datetime] = None
    ) -> List[Dict]:
        """
        Get earnings calendar for date range.

        Args:
            start_date: Start date (default: today)
            end_date: End date (default: 3 months from now)

        Returns:
            List of earnings events
        """
        try:
            if start_date is None:
                start_date = datetime.now()
            if end_date is None:
                end_date = datetime.now() + timedelta(days=90)

            from_date = start_date.strftime('%Y-%m-%d')
            to_date = end_date.strftime('%Y-%m-%d')

            cache_key = f"earnings_{from_date}_{to_date}"
            cached = self._get_cached(cache_key)
            if cached:
                return cached

            data = self._make_request('calendar/earnings', {
                'from': from_date,
                'to': to_date,
            })

            if data and isinstance(data, dict) and 'earningsCalendar' in data:
                earnings = data['earningsCalendar']
                self._set_cached(cache_key, earnings)
                return earnings

            return []

        except Exception as e:
            logger.debug(f"Error fetching earnings calendar: {e}")
            return []

    def get_insider_transactions(self, ticker: str) -> List[Dict]:
        """
        Get insider trading transactions for a company.

        Args:
            ticker: Stock ticker

        Returns:
            List of insider transaction records
        """
        ticker = ticker.upper()
        cache_key = f"insider_{ticker}"

        cached = self._get_cached(cache_key)
        if cached:
            return cached

        try:
            data = self._make_request('stock/insider-transactions', {'symbol': ticker})

            if data and isinstance(data, dict) and 'data' in data:
                transactions = data['data']
                # Cache for longer (24 hours) as this doesn't change frequently
                self.cache[cache_key] = transactions
                self.cache_time[cache_key] = time.time()
                return transactions

            return []

        except Exception as e:
            logger.debug(f"Error fetching insider transactions for {ticker}: {e}")
            return []

    def get_recommendation_trends(self, ticker: str) -> List[Dict]:
        """
        Get analyst recommendation trends.

        Args:
            ticker: Stock ticker

        Returns:
            List of recommendation data points
        """
        ticker = ticker.upper()
        cache_key = f"recommendations_{ticker}"

        cached = self._get_cached(cache_key)
        if cached:
            return cached

        try:
            data = self._make_request('stock/recommendation', {'symbol': ticker})

            if isinstance(data, list) and len(data) > 0:
                self._set_cached(cache_key, data)
                return data

            return []

        except Exception as e:
            logger.debug(f"Error fetching recommendations for {ticker}: {e}")
            return []

    def analyze_analyst_sentiment(self, ticker: str) -> Tuple[float, Dict]:
        """
        Analyze overall analyst sentiment and rating trends.

        Args:
            ticker: Stock ticker

        Returns:
            Tuple of (sentiment_score -1.0 to 1.0, analysis_details)
        """
        try:
            recommendations = self.get_recommendation_trends(ticker)

            if not recommendations:
                return 0.0, {'data_available': False}

            # Get most recent recommendation
            latest = recommendations[0]

            # Normalize recommendation scores
            strong_buy = latest.get('strongBuy', 0)
            buy = latest.get('buy', 0)
            hold = latest.get('hold', 0)
            sell = latest.get('sell', 0)
            strong_sell = latest.get('strongSell', 0)

            total = strong_buy + buy + hold + sell + strong_sell
            if total == 0:
                return 0.0, {'no_recommendations': True}

            # Calculate weighted sentiment
            # strong_buy = +1.0, buy = +0.5, hold = 0, sell = -0.5, strong_sell = -1.0
            positive_score = strong_buy * 1.0 + buy * 0.5
            negative_score = strong_sell * 1.0 + sell * 0.5

            sentiment = (positive_score - negative_score) / total
            sentiment = max(-1.0, min(1.0, sentiment))

            return sentiment, {
                'strong_buy': strong_buy,
                'buy': buy,
                'hold': hold,
                'sell': sell,
                'strong_sell': strong_sell,
                'total_analysts': total,
                'average_rating': (strong_buy * 5 + buy * 4 + hold * 3 + sell * 2 + strong_sell * 1) / total if total > 0 else 3.0,
            }

        except Exception as e:
            logger.debug(f"Error analyzing analyst sentiment for {ticker}: {e}")
            return 0.0, {'error': str(e)}

    def get_technical_indicators(self, ticker: str) -> Optional[Dict]:
        """
        Get technical analysis indicators.

        Args:
            ticker: Stock ticker

        Returns:
            Dict with technical indicators or None
        """
        ticker = ticker.upper()
        cache_key = f"technical_{ticker}"

        cached = self._get_cached(cache_key)
        if cached:
            return cached

        try:
            # Finnhub provides technical indicators for free tier
            data = self._make_request('technical-indicator', {
                'symbol': ticker,
                'resolution': 'D',
                'indicator': 'rsi',
            })

            if data:
                self._set_cached(cache_key, data)
                return data

            return None

        except Exception as e:
            logger.debug(f"Error fetching technical indicators for {ticker}: {e}")
            return None


# Global instance
_finnhub_instance = None


def get_finnhub_integrator(api_key: Optional[str] = None) -> FinnhubIntegrator:
    """Get singleton instance of Finnhub integrator."""
    global _finnhub_instance
    if _finnhub_instance is None:
        _finnhub_instance = FinnhubIntegrator(api_key=api_key)
    return _finnhub_instance


if __name__ == "__main__":
    integrator = get_finnhub_integrator()

    ticker = "AAPL"
    print(f"\n=== Testing Finnhub Integration for {ticker} ===")

    # Test company profile
    print(f"\n1. Company Profile:")
    profile = integrator.get_company_profile(ticker)
    if profile:
        print(f"   Company: {profile.get('name', 'N/A')}")
        print(f"   Exchange: {profile.get('exchange', 'N/A')}")
        print(f"   Industry: {profile.get('finnhubIndustry', 'N/A')}")
    else:
        print("   Not available")

    # Test company news
    print(f"\n2. Recent News ({ticker}):")
    news = integrator.get_company_news(ticker, days_back=7, limit=5)
    if news:
        for article in news[:3]:
            print(f"   - {article.get('headline', 'No headline')[:60]}...")
        sentiment, details = integrator.analyze_news_sentiment(news)
        print(f"   News Sentiment: {sentiment:.3f}")
    else:
        print("   No news available")

    # Test analyst sentiment
    print(f"\n3. Analyst Sentiment:")
    sentiment, details = integrator.analyze_analyst_sentiment(ticker)
    print(f"   Sentiment Score: {sentiment:.3f}")
    if 'average_rating' in details:
        print(f"   Average Rating: {details['average_rating']:.1f}/5.0")
    if 'total_analysts' in details:
        print(f"   Analysts: {details['total_analysts']}")

    # Test insider transactions
    print(f"\n4. Insider Transactions:")
    insider_txns = integrator.get_insider_transactions(ticker)
    if insider_txns:
        print(f"   Found {len(insider_txns)} transactions")
        if len(insider_txns) > 0:
            latest = insider_txns[0]
            print(f"   Latest: {latest.get('name', 'N/A')} - {latest.get('transactionType', 'N/A')}")
    else:
        print("   No transactions available")

    # Test earnings calendar
    print(f"\n5. Upcoming Earnings:")
    earnings = integrator.get_earnings_calendar(
        start_date=datetime.now(),
        end_date=datetime.now() + timedelta(days=30)
    )
    if earnings:
        print(f"   Found {len(earnings)} earnings events in next 30 days")
        # Filter to ticker if available
        ticker_earnings = [e for e in earnings if e.get('symbol') == ticker]
        if ticker_earnings:
            for e in ticker_earnings[:2]:
                print(f"   - {e.get('symbol')}: {e.get('epsEstimate', 'N/A')} EPS (est.)")
    else:
        print("   No earnings data available")
