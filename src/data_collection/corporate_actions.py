"""Corporate actions scanning (buybacks, dividends, etc)."""
from typing import Dict, List, Optional, Tuple
from datetime import datetime, timedelta
import requests
import xml.etree.ElementTree as ET
from bs4 import BeautifulSoup
from loguru import logger
import time
import re

import config


class CorporateActionsScanner:
    """Scans 8-K filings for corporate actions."""

    BUYBACK_KEYWORDS = ['repurchase', 'buyback', 'share repurchase', 'buy back']
    DIVIDEND_KEYWORDS = ['dividend', 'special dividend', 'extraordinary dividend']
    ACQUISITION_KEYWORDS = ['acquisition', 'acquired', 'merger']

    def __init__(self):
        """Initialize scanner."""
        self.session = requests.Session()
        self.session.headers.update({'User-Agent': config.SEC_USER_AGENT})
        self.cache = {}
        self.cache_time = {}
        self.cache_ttl = 86400  # 24 hour cache

    def scan_for_buybacks(self, ticker: str, days_back: int = 90) -> Dict:
        """
        Scan 8-K filings for share buyback announcements.

        Args:
            ticker: Stock ticker
            days_back: Days to look back

        Returns:
            Dict with buyback info and multiplier (1.0-1.5x)
        """
        cache_key = f"buyback_{ticker}_{days_back}"
        if cache_key in self.cache:
            if time.time() - self.cache_time.get(cache_key, 0) < self.cache_ttl:
                return self.cache[cache_key]

        try:
            # Fetch 8-K filings from RSS
            filings = self._fetch_8k_filings(ticker, days_back)
            
            buyback_details = []
            total_amount = 0
            
            for filing_url in filings[:10]:  # Limit to 10 most recent
                try:
                    content = self._download_filing_text(filing_url)
                    if content:
                        # Check for buyback keywords
                        content_lower = content.lower()
                        has_buyback = any(kw in content_lower for kw in self.BUYBACK_KEYWORDS)
                        
                        if has_buyback:
                            # Try to extract dollar amount
                            amount = self._extract_dollar_amount(content)
                            buyback_details.append({
                                'filing_url': filing_url,
                                'amount': amount,
                            })
                            if amount:
                                total_amount += amount
                    
                    time.sleep(0.2)  # Rate limiting
                    
                except Exception as e:
                    logger.debug(f"Error processing 8-K for {ticker}: {e}")
                    continue
            
            result = {
                'ticker': ticker,
                'buyback_found': len(buyback_details) > 0,
                'multiplier': 1.0,
                'buyback_details': buyback_details,
                'total_buyback_amount': total_amount,
            }
            
            # Set multiplier based on amount
            if total_amount > 1_000_000_000:  # $1B+
                result['multiplier'] = 1.3
            elif total_amount > 500_000_000:  # $500M+
                result['multiplier'] = 1.2
            elif total_amount > 0:
                result['multiplier'] = 1.1
            
            self.cache[cache_key] = result
            self.cache_time[cache_key] = time.time()
            
            return result

        except Exception as e:
            logger.error(f"Error scanning buybacks for {ticker}: {e}")
            return {
                'ticker': ticker,
                'error': str(e),
                'multiplier': 1.0,
            }

    def scan_for_dividends(self, ticker: str, days_back: int = 90) -> Dict:
        """
        Scan 8-K filings for dividend announcements.

        Args:
            ticker: Stock ticker
            days_back: Days to look back

        Returns:
            Dict with dividend info
        """
        cache_key = f"dividend_{ticker}_{days_back}"
        if cache_key in self.cache:
            if time.time() - self.cache_time.get(cache_key, 0) < self.cache_ttl:
                return self.cache[cache_key]

        try:
            # Fetch 8-K filings from RSS
            filings = self._fetch_8k_filings(ticker, days_back)
            
            dividend_details = []
            
            for filing_url in filings[:10]:
                try:
                    content = self._download_filing_text(filing_url)
                    if content:
                        content_lower = content.lower()
                        has_dividend = any(kw in content_lower for kw in self.DIVIDEND_KEYWORDS)
                        
                        if has_dividend:
                            dividend_details.append({'filing_url': filing_url})
                    
                    time.sleep(0.2)
                    
                except Exception as e:
                    logger.debug(f"Error processing dividend 8-K: {e}")
                    continue
            
            result = {
                'ticker': ticker,
                'dividend_found': len(dividend_details) > 0,
                'multiplier': 1.1 if len(dividend_details) > 0 else 1.0,
                'dividend_details': dividend_details,
            }
            
            self.cache[cache_key] = result
            self.cache_time[cache_key] = time.time()
            
            return result

        except Exception as e:
            logger.error(f"Error scanning dividends for {ticker}: {e}")
            return {
                'ticker': ticker,
                'error': str(e),
                'multiplier': 1.0,
            }

    def calculate_corporate_action_multiplier(self, ticker: str) -> Tuple[float, Dict]:
        """
        Calculate multiplier based on corporate actions.

        Args:
            ticker: Stock ticker

        Returns:
            Tuple of (multiplier 1.0-1.5x, details_dict)
        """
        multiplier = 1.0
        factors = []

        try:
            # Scan for buybacks
            buyback_info = self.scan_for_buybacks(ticker)
            if buyback_info.get('buyback_found'):
                amount = buyback_info.get('total_buyback_amount', 0)
                if amount > 0:
                    multiplier *= 1.3
                    factors.append(f"Active buyback program (${amount/1e9:.1f}B)")

            # Scan for dividends
            div_info = self.scan_for_dividends(ticker)
            if div_info.get('dividend_found'):
                multiplier *= 1.1
                factors.append("Dividend announced")

            multiplier = min(multiplier, 1.5)  # Cap at 1.5x

            return multiplier, {
                'ticker': ticker,
                'multiplier': multiplier,
                'factors': factors,
                'buyback_info': buyback_info,
                'dividend_info': div_info,
            }

        except Exception as e:
            logger.error(f"Error calculating corporate action multiplier: {e}")
            return 1.0, {'ticker': ticker, 'error': str(e)}


    def _fetch_8k_filings(self, ticker: str, days_back: int) -> List[str]:
        """
        Fetch 8-K filing URLs for a ticker from RSS.

        Args:
            ticker: Stock ticker
            days_back: Days to look back

        Returns:
            List of filing URLs
        """
        try:
            rss_url = config.SEC_RSS_FEEDS['form8k']
            response = self.session.get(rss_url, timeout=30)
            response.raise_for_status()
            
            root = ET.fromstring(response.content)
            
            # Remove namespaces
            for elem in root.iter():
                if '}' in elem.tag:
                    elem.tag = elem.tag.split('}', 1)[1]
            
            filing_urls = []
            cutoff_date = datetime.now() - timedelta(days=days_back)
            
            for item in root.findall('.//item'):
                try:
                    title_elem = item.find('title')
                    link_elem = item.find('link')
                    
                    if title_elem is None or link_elem is None:
                        continue
                    
                    title = title_elem.text or ''
                    
                    # Check if ticker matches (roughly)
                    if ticker.upper() in title.upper():
                        filing_urls.append(link_elem.text)
                    
                except Exception as e:
                    continue
            
            logger.debug(f"Found {len(filing_urls)} 8-K filings for {ticker}")
            return filing_urls
            
        except Exception as e:
            logger.debug(f"Error fetching 8-K RSS for {ticker}: {e}")
            return []

    def _download_filing_text(self, filing_url: str) -> Optional[str]:
        """
        Download and extract text from a filing.

        Args:
            filing_url: URL to SEC filing

        Returns:
            Text content or None
        """
        try:
            response = self.session.get(filing_url, timeout=15)
            response.raise_for_status()
            
            soup = BeautifulSoup(response.text, 'html.parser')
            
            # Extract text from HTML
            text = soup.get_text(separator=' ', strip=True)
            return text
            
        except Exception as e:
            logger.debug(f"Error downloading filing: {e}")
            return None

    def _extract_dollar_amount(self, text: str) -> int:
        """
        Extract dollar amounts from text.

        Args:
            text: Text to search

        Returns:
            Dollar amount in dollars (0 if not found)
        """
        try:
            # Look for patterns like "$1.5 billion", "$500 million", "$100M"
            patterns = [
                r'\$\s*(\d+(?:\.\d+)?)\s*billion',
                r'\$\s*(\d+(?:\.\d+)?)\s*B\b',
                r'\$\s*(\d+(?:\.\d+)?)\s*million',
                r'\$\s*(\d+(?:\.\d+)?)\s*M\b',
            ]
            
            for pattern in patterns:
                matches = re.findall(pattern, text, re.IGNORECASE)
                if matches:
                    amount = float(matches[0])
                    if 'billion' in pattern.lower() or 'B' in pattern:
                        return int(amount * 1_000_000_000)
                    elif 'million' in pattern.lower() or 'M' in pattern:
                        return int(amount * 1_000_000)
            
            return 0
            
        except Exception as e:
            logger.debug(f"Error extracting dollar amount: {e}")
            return 0


if __name__ == "__main__":
    scanner = CorporateActionsScanner()
    mult, details = scanner.calculate_corporate_action_multiplier("AAPL")
    print(f"AAPL: {mult}x")
    print(f"Factors: {details['factors']}")
