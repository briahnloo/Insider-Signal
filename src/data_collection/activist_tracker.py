"""Activist investor tracking via 13D/G filings."""
from typing import Dict, List, Tuple
from datetime import datetime, timedelta
import requests
import xml.etree.ElementTree as ET
from bs4 import BeautifulSoup
from loguru import logger
import time
import re

import config


class ActivistTracker:
    """Tracks known activist investors from 13D/G filings."""

    KNOWN_ACTIVISTS = {
        'ELLIOTT MANAGEMENT': 1.5,
        'BERKSHIRE HATHAWAY': 1.4,
        'STARBOARD VALUE': 1.5,
        'ICAHN ENTERPRISES': 1.6,
        'ICAHN': 1.6,
        'PERSHING SQUARE': 1.5,
        'BAUPOST GROUP': 1.3,
        'TIGER GLOBAL': 1.4,
        'THIRD POINT': 1.5,
        'SOROS FUND': 1.4,
        'SILVERLAKE': 1.3,
        'JANA PARTNERS': 1.5,
        'VALUEACT': 1.4,
        'GREENLIGHT CAPITAL': 1.4,
    }

    def __init__(self):
        """Initialize activist tracker."""
        self.session = requests.Session()
        self.session.headers.update({'User-Agent': config.SEC_USER_AGENT})
        self.cache = {}
        self.cache_time = {}
        self.cache_ttl = 86400  # 24 hour cache

    def detect_activist_filing(self, ticker: str, days_back: int = 90) -> Dict:
        """
        Detect 13D/G filings from known activists.

        Args:
            ticker: Stock ticker
            days_back: Days to look back

        Returns:
            Dict with activist info and multiplier (1.0-1.6x)
        """
        cache_key = f"activist_{ticker}_{days_back}"
        if cache_key in self.cache:
            if time.time() - self.cache_time.get(cache_key, 0) < self.cache_ttl:
                return self.cache[cache_key]

        try:
            # Fetch 13D and 13G filings
            filings_13d = self._fetch_13d_filings(ticker, days_back)
            filings_13g = self._fetch_13g_filings(ticker, days_back)
            all_filings = filings_13d + filings_13g
            
            activist_details = []
            
            for filing_url in all_filings[:10]:  # Limit to 10 most recent
                try:
                    content = self._download_filing_text(filing_url)
                    if content:
                        # Check for known activists
                        content_upper = content.upper()
                        for activist_name, mult in self.KNOWN_ACTIVISTS.items():
                            if activist_name in content_upper:
                                # Try to extract ownership percentage
                                pct = self._extract_ownership_pct(content)
                                activist_details.append({
                                    'name': activist_name,
                                    'filing_url': filing_url,
                                    'ownership_pct': pct,
                                    'multiplier': mult,
                                })
                                break
                    
                    time.sleep(0.2)  # Rate limiting
                    
                except Exception as e:
                    logger.debug(f"Error processing 13D/G for {ticker}: {e}")
                    continue
            
            result = {
                'ticker': ticker,
                'activist_found': len(activist_details) > 0,
                'multiplier': 1.0,
                'activist_details': activist_details,
            }
            
            # Set highest multiplier if activists found
            if activist_details:
                result['multiplier'] = max(a['multiplier'] for a in activist_details)
            
            self.cache[cache_key] = result
            self.cache_time[cache_key] = time.time()
            
            return result

        except Exception as e:
            logger.error(f"Error detecting activist filings for {ticker}: {e}")
            return {
                'ticker': ticker,
                'error': str(e),
                'multiplier': 1.0,
            }

    def calculate_activist_multiplier(self, ticker: str) -> Tuple[float, Dict]:
        """
        Calculate multiplier for activist involvement.

        Args:
            ticker: Stock ticker

        Returns:
            Tuple of (multiplier 1.0-1.6x, details_dict)
        """
        multiplier = 1.0
        activist_info = []

        try:
            filing = self.detect_activist_filing(ticker)

            if filing.get('activist_found'):
                details = filing.get('activist_details', [])
                for activist_name, filing_pct in details:
                    activist_name_upper = activist_name.upper()

                    # Check against known activists
                    for known in self.KNOWN_ACTIVISTS:
                        if known in activist_name_upper:
                            mult = self.KNOWN_ACTIVISTS[known]
                            multiplier = max(multiplier, mult)
                            activist_info.append({
                                'name': activist_name,
                                'percentage': filing_pct,
                                'multiplier': mult,
                            })
                            logger.info(
                                f"Detected activist {activist_name} in {ticker}"
                            )
                            break

            return min(multiplier, 1.6), {
                'ticker': ticker,
                'activist_multiplier': min(multiplier, 1.6),
                'activists': activist_info,
            }

        except Exception as e:
            logger.error(f"Error calculating activist multiplier: {e}")
            return 1.0, {'ticker': ticker, 'error': str(e)}

    def is_activist_target(
        self, ticker: str, ownership_threshold: float = 5.0
    ) -> bool:
        """
        Check if stock is an activist target.

        Args:
            ticker: Stock ticker
            ownership_threshold: Minimum ownership % to flag

        Returns:
            True if activist with >5% stake
        """
        try:
            mult, details = self.calculate_activist_multiplier(ticker)
            if mult > 1.0:
                for activist in details.get('activists', []):
                    if activist['percentage'] >= ownership_threshold:
                        return True
            return False

        except Exception as e:
            logger.error(f"Error checking activist target: {e}")
            return False


    def _fetch_13d_filings(self, ticker: str, days_back: int) -> List[str]:
        """Fetch 13D filing URLs from RSS."""
        return self._fetch_filings_from_rss(config.SEC_RSS_FEEDS['form13d'], ticker, days_back)

    def _fetch_13g_filings(self, ticker: str, days_back: int) -> List[str]:
        """Fetch 13G filing URLs from RSS."""
        return self._fetch_filings_from_rss(config.SEC_RSS_FEEDS['form13g'], ticker, days_back)

    def _fetch_filings_from_rss(self, rss_url: str, ticker: str, days_back: int) -> List[str]:
        """
        Fetch filing URLs from SEC RSS feed.

        Args:
            rss_url: RSS feed URL
            ticker: Stock ticker
            days_back: Days to look back

        Returns:
            List of filing URLs
        """
        try:
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
                    
                    # Check if ticker matches
                    if ticker.upper() in title.upper():
                        filing_urls.append(link_elem.text)
                    
                except Exception as e:
                    continue
            
            logger.debug(f"Found {len(filing_urls)} 13D/G filings for {ticker}")
            return filing_urls
            
        except Exception as e:
            logger.debug(f"Error fetching RSS: {e}")
            return []

    def _download_filing_text(self, filing_url: str) -> str:
        """
        Download and extract text from filing.

        Args:
            filing_url: URL to SEC filing

        Returns:
            Text content
        """
        try:
            response = self.session.get(filing_url, timeout=15)
            response.raise_for_status()
            
            soup = BeautifulSoup(response.text, 'html.parser')
            text = soup.get_text(separator=' ', strip=True)
            return text
            
        except Exception as e:
            logger.debug(f"Error downloading filing: {e}")
            return ""

    def _extract_ownership_pct(self, text: str) -> float:
        """
        Extract ownership percentage from filing text.

        Args:
            text: Filing text

        Returns:
            Ownership percentage (0-100)
        """
        try:
            # Look for patterns like "5.1%", "10.5 percent"
            patterns = [
                r'(\d+\.\d+)\s*%',
                r'(\d+)\s*%',
                r'(\d+\.\d+)\s*percent',
            ]
            
            for pattern in patterns:
                matches = re.findall(pattern, text, re.IGNORECASE)
                if matches:
                    # Return first match that seems reasonable (0-50%)
                    for match in matches:
                        pct = float(match)
                        if 0 < pct < 50:
                            return pct
            
            return 0.0
            
        except Exception as e:
            logger.debug(f"Error extracting ownership: {e}")
            return 0.0


if __name__ == "__main__":
    tracker = ActivistTracker()
    mult, details = tracker.calculate_activist_multiplier("AAPL")
    print(f"AAPL: {mult}x")
    print(f"Activists: {details['activists']}")
