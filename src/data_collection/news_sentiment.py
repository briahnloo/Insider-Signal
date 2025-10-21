"""
News sentiment analysis for market-moving events.
Integrates with free news APIs (NewsAPI, GDELT, etc.) to track sentiment trends.
"""
from typing import Dict, List, Optional, Tuple
from datetime import datetime, timedelta
import requests
from loguru import logger
import time
import os
from urllib.parse import quote

try:
    import feedparser
    HAS_FEEDPARSER = True
except ImportError:
    HAS_FEEDPARSER = False


class NewsSentimentAnalyzer:
    """Analyzes news sentiment for trading signals."""

    def __init__(self):
        """Initialize news sentiment analyzer."""
        self.cache = {}
        self.cache_time = {}
        self.cache_ttl = 3600  # 1 hour
        self.user_agent = "Intelligent-Trader/1.0"

        # GDELT API (free, no key required)
        self.gdelt_base_url = "https://api.gdeltproject.org/api/v2"

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

    def fetch_gdelt_news(
        self, search_query: str, days_back: int = 7
    ) -> List[Dict]:
        """
        Fetch news using GDELT API (free, no authentication).

        Args:
            search_query: Search terms
            days_back: Number of days to look back

        Returns:
            List of news articles
        """
        cache_key = f"gdelt_{search_query}_{days_back}"

        cached = self._get_cached(cache_key)
        if cached:
            return cached

        try:
            # GDELT search API
            search_url = f"{self.gdelt_base_url}/news"

            params = {
                'query': search_query,
                'timespan': f'{days_back}d',
                'sort': 'dateDesc',
                'format': 'json',
            }

            response = requests.get(search_url, params=params, timeout=10)

            if response.status_code == 200:
                data = response.json()
                articles = data.get('articles', [])

                self._set_cached(cache_key, articles)
                return articles
            else:
                logger.debug(f"GDELT API error: {response.status_code}")
                return []

        except Exception as e:
            logger.debug(f"Error fetching GDELT news: {e}")
            return []

    def fetch_rss_news(
        self, ticker: str, source: str = "bloomberg"
    ) -> List[Dict]:
        """
        Fetch news from RSS feeds for a ticker.

        Args:
            ticker: Stock ticker
            source: News source ('bloomberg', 'cnbc', 'marketwatch')

        Returns:
            List of news articles
        """
        if not HAS_FEEDPARSER:
            logger.warning("feedparser not installed. Install with: pip install feedparser")
            return []

        cache_key = f"rss_{ticker}_{source}"

        cached = self._get_cached(cache_key)
        if cached:
            return cached

        # RSS feed URLs for different sources
        feed_urls = {
            'bloomberg': f"https://www.bloomberg.com/search/results?q={quote(ticker)}",
            'cnbc': f"https://feeds.cnbc.com/cnbc/financialnews/",
            'marketwatch': f"https://feeds.marketwatch.com/marketwatch/topstories/",
            'seeking_alpha': f"https://feeds.seekingalpha.com/feed.xml?symbol={ticker}",
        }

        url = feed_urls.get(source.lower(), feed_urls['bloomberg'])

        try:
            response = requests.get(url, timeout=10)
            feed = feedparser.parse(response.content)

            articles = []
            for entry in feed.entries[:20]:  # Get top 20
                article = {
                    'title': entry.get('title', ''),
                    'summary': entry.get('summary', ''),
                    'link': entry.get('link', ''),
                    'published': entry.get('published', ''),
                    'source': source,
                }
                articles.append(article)

            self._set_cached(cache_key, articles)
            return articles

        except Exception as e:
            logger.debug(f"Error fetching {source} RSS: {e}")
            return []

    def analyze_news_sentiment(
        self, articles: List[Dict]
    ) -> Tuple[float, Dict]:
        """
        Analyze sentiment from news articles.

        Args:
            articles: List of article dictionaries with 'title' and 'summary'

        Returns:
            Tuple of (sentiment_score -1.0 to 1.0, analysis_details)
        """
        try:
            if not articles:
                return 0.0, {'articles_analyzed': 0}

            # Keyword-based sentiment analysis
            positive_keywords = {
                'bullish': 3.0, 'buy': 2.5, 'surge': 2.5, 'rally': 2.5, 'gain': 2.0,
                'beat': 2.5, 'strong': 2.0, 'upgrade': 2.5, 'growth': 2.0, 'profit': 2.0,
                'record': 2.5, 'exceed': 2.5, 'expansion': 1.5, 'positive': 1.5,
                'outperform': 2.0, 'optimism': 2.0, 'upside': 1.5, 'opportunity': 1.5,
                'momentum': 2.0, 'strength': 1.5, 'recovery': 2.0, 'advance': 1.5,
            }

            negative_keywords = {
                'bearish': -3.0, 'sell': -2.5, 'plunge': -2.5, 'crash': -2.5, 'decline': -2.0,
                'miss': -2.5, 'weak': -2.0, 'downgrade': -2.5, 'loss': -2.0, 'negative': -1.5,
                'underperform': -2.0, 'concern': -1.5, 'risk': -1.0, 'challenge': -1.5,
                'warning': -2.0, 'recession': -2.5, 'crisis': -2.5, 'uncertain': -1.5,
                'pressure': -1.5, 'headwind': -2.0, 'shortage': -1.5, 'decline': -2.0,
            }

            total_score = 0
            total_hits = 0
            positive_mentions = 0
            negative_mentions = 0

            for article in articles:
                title = (article.get('title', '') + ' ' + article.get('summary', '')).lower()

                if not title.strip():
                    continue

                # Score positive keywords
                for keyword, weight in positive_keywords.items():
                    count = title.count(keyword)
                    if count > 0:
                        total_score += weight * count
                        positive_mentions += count
                        total_hits += count

                # Score negative keywords
                for keyword, weight in negative_keywords.items():
                    count = title.count(keyword)
                    if count > 0:
                        total_score += weight * count
                        negative_mentions += count
                        total_hits += count

            # Normalize sentiment
            if total_hits == 0:
                sentiment = 0.0
            else:
                sentiment = total_score / (total_hits * 3.0)  # Normalize by max weight

            sentiment = max(-1.0, min(1.0, sentiment))

            return sentiment, {
                'articles_analyzed': len(articles),
                'positive_mentions': positive_mentions,
                'negative_mentions': negative_mentions,
                'net_sentiment_words': positive_mentions - negative_mentions,
                'average_sentiment': sentiment,
                'interpretation': self._interpret_sentiment(sentiment),
            }

        except Exception as e:
            logger.debug(f"Error analyzing news sentiment: {e}")
            return 0.0, {'error': str(e)}

    def _interpret_sentiment(self, score: float) -> str:
        """Interpret sentiment score."""
        if score > 0.5:
            return "Very Positive"
        elif score > 0.2:
            return "Positive"
        elif score > -0.2:
            return "Neutral"
        elif score > -0.5:
            return "Negative"
        else:
            return "Very Negative"

    def get_ticker_sentiment_trend(
        self, ticker: str, days: int = 7
    ) -> Tuple[float, Dict]:
        """
        Get overall sentiment trend for a ticker over time.

        Args:
            ticker: Stock ticker
            days: Number of days to analyze

        Returns:
            Tuple of (trend_sentiment, trend_analysis)
        """
        try:
            # Get news for ticker
            news = self.fetch_gdelt_news(ticker, days_back=days)

            if not news:
                # Try RSS feeds as fallback
                news = self.fetch_rss_news(ticker)

            if not news:
                return 0.0, {'status': 'no_data'}

            # Analyze sentiment
            sentiment, analysis = self.analyze_news_sentiment(news)

            # Add trend information
            analysis['trend_period_days'] = days
            analysis['total_articles'] = len(news)

            # Determine trend direction
            if sentiment > 0.3:
                analysis['trend'] = 'positive'
            elif sentiment > -0.3:
                analysis['trend'] = 'neutral'
            else:
                analysis['trend'] = 'negative'

            return sentiment, analysis

        except Exception as e:
            logger.debug(f"Error getting sentiment trend for {ticker}: {e}")
            return 0.0, {'error': str(e)}

    def detect_news_driven_events(
        self, ticker: str
    ) -> List[Dict]:
        """
        Detect significant news-driven market events.

        Args:
            ticker: Stock ticker

        Returns:
            List of detected events
        """
        try:
            # Fetch recent news
            news = self.fetch_gdelt_news(ticker, days_back=3)

            events = []

            for article in news[:10]:
                title = article.get('title', '').lower()
                summary = article.get('summary', '').lower()
                full_text = title + ' ' + summary

                # Detect event keywords
                event_keywords = {
                    'earnings': 'earnings_report',
                    'ipo': 'ipo_event',
                    'merger': 'm&a_event',
                    'acquisition': 'm&a_event',
                    'bankruptcy': 'bankruptcy_event',
                    'lawsuit': 'legal_event',
                    'ceo': 'leadership_change',
                    'resignation': 'leadership_change',
                    'recall': 'product_event',
                    'regulatory': 'regulatory_event',
                    'sec': 'regulatory_event',
                }

                for keyword, event_type in event_keywords.items():
                    if keyword in full_text:
                        events.append({
                            'ticker': ticker,
                            'event_type': event_type,
                            'headline': article.get('title', ''),
                            'published': article.get('published', ''),
                            'source': article.get('source', 'gdelt'),
                        })
                        break  # One event per article

            return events

        except Exception as e:
            logger.debug(f"Error detecting news events for {ticker}: {e}")
            return []

    def get_sector_sentiment(
        self, sector: str, days: int = 7
    ) -> Tuple[float, Dict]:
        """
        Get overall sentiment for a sector.

        Args:
            sector: Sector name (e.g., 'technology', 'healthcare')
            days: Number of days to analyze

        Returns:
            Tuple of (sector_sentiment, analysis)
        """
        try:
            # Fetch news about sector
            news = self.fetch_gdelt_news(sector, days_back=days)

            if not news:
                return 0.0, {'status': 'no_data'}

            # Analyze sentiment
            sentiment, analysis = self.analyze_news_sentiment(news)
            analysis['sector'] = sector
            analysis['period_days'] = days

            return sentiment, analysis

        except Exception as e:
            logger.debug(f"Error getting sector sentiment: {e}")
            return 0.0, {'error': str(e)}


# Global instance
_news_analyzer_instance = None


def get_news_sentiment_analyzer() -> NewsSentimentAnalyzer:
    """Get singleton instance of news sentiment analyzer."""
    global _news_analyzer_instance
    if _news_analyzer_instance is None:
        _news_analyzer_instance = NewsSentimentAnalyzer()
    return _news_analyzer_instance


if __name__ == "__main__":
    analyzer = get_news_sentiment_analyzer()

    ticker = "AAPL"
    print(f"\n=== Testing News Sentiment Analysis for {ticker} ===")

    # Test ticker sentiment
    print(f"\n1. Getting ticker sentiment trend (7 days)...")
    sentiment, trend = analyzer.get_ticker_sentiment_trend(ticker, days=7)
    print(f"   Sentiment Score: {sentiment:.3f}")
    print(f"   Interpretation: {trend.get('interpretation', 'Unknown')}")
    print(f"   Articles Analyzed: {trend.get('articles_analyzed', 0)}")
    if 'trend' in trend:
        print(f"   Trend: {trend['trend'].upper()}")

    # Test event detection
    print(f"\n2. Detecting news-driven events...")
    events = analyzer.detect_news_driven_events(ticker)
    if events:
        print(f"   Found {len(events)} events:")
        for event in events[:5]:
            print(f"   - {event['event_type']}: {event['headline'][:60]}...")
    else:
        print("   No major events detected")

    # Test sector sentiment
    print(f"\n3. Getting sector sentiment (Technology)...")
    sector_sentiment, sector_analysis = analyzer.get_sector_sentiment('technology', days=7)
    print(f"   Sector Sentiment: {sector_sentiment:.3f}")
    print(f"   Articles: {sector_analysis.get('articles_analyzed', 0)}")
    print(f"   Interpretation: {sector_analysis.get('interpretation', 'Unknown')}")
