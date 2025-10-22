"""
Form 4 scraper for collecting insider trading data from SEC EDGAR.
"""
import xml.etree.ElementTree as ET
from datetime import datetime, timedelta
from pathlib import Path
from typing import List, Dict, Optional, Tuple
import tempfile
import os

import requests
from sec_edgar_downloader import Downloader
from loguru import logger
import pandas as pd

import config
from src.database import insert_transaction, initialize_database

# SEC EDGAR namespace
SEC_NAMESPACE = {
    'doc': 'http://www.sec.gov/cgi-bin/browse-edgar',
    'xbrli': 'http://www.xbrl.org/2003/instance',
}


class Form4Scraper:
    """Scrapes SEC Form 4 filings for insider trading activity."""

    def __init__(self):
        """Initialize the Form 4 scraper."""
        self.user_agent = config.SEC_USER_AGENT
        self.session = requests.Session()
        # Set comprehensive headers for SEC compliance
        self.session.headers.update({
            'User-Agent': self.user_agent,
            'Accept': 'application/rss+xml,application/xml,text/xml,*/*',
            'Accept-Encoding': 'gzip, deflate',
            'Accept-Language': 'en-US,en;q=0.9',
            'Connection': 'keep-alive',
            'Referer': 'https://www.sec.gov/cgi-bin/browse-edgar'
        })
        initialize_database()

    def download_form4_filings(self, days_back: int = 30) -> Path:
        """
        Download Form 4 filings from SEC EDGAR.

        Args:
            days_back: Number of days to look back (default: 30)

        Returns:
            Path to the directory containing downloaded filings
        """
        try:
            # Create temporary directory for downloads
            temp_dir = tempfile.mkdtemp()
            logger.info(f"Downloading Form 4 filings from last {days_back} days to {temp_dir}")

            # Use sec-edgar-downloader to fetch Form 4s
            downloader = Downloader(
                company='',
                cik='',
                amount=None,
                after=None,
                before=None,
                filing_type='4',
                user_agent=self.user_agent
            )

            # Download filings to temp directory
            downloader.download(temp_dir, skip_existing=False)
            logger.info(f"Successfully downloaded Form 4 filings")
            return Path(temp_dir)

        except Exception as e:
            logger.error(f"Failed to download Form 4 filings: {e}")
            return None

    def parse_form4_xml(self, xml_path: Path) -> Optional[Dict]:
        """
        Parse a single Form 4 XML file.

        Args:
            xml_path: Path to the Form 4 XML file

        Returns:
            Dictionary with parsed transaction data, or None if parsing fails
        """
        try:
            tree = ET.parse(xml_path)
            root = tree.getroot()

            # Remove namespaces for easier parsing
            for elem in root.iter():
                if '}' in elem.tag:
                    elem.tag = elem.tag.split('}', 1)[1]

            # Extract filing information
            filing_date_elem = root.find('.//periodOfReport')
            if filing_date_elem is None:
                filing_date_elem = root.find('.//fileNumber')

            filings = []

            # Extract ticker from issuer section
            ticker_elem = root.find('.//issuerTradingSymbol')
            if ticker_elem is None or not ticker_elem.text:
                logger.debug("No trading symbol found in Form 4")
                return None
            
            ticker = ticker_elem.text.upper().strip()
            
            # Extract insider info
            insider_elem = root.find('.//rptOwnerName')
            insider_name = insider_elem.text if insider_elem is not None else 'Unknown'
            
            # Extract insider title/relationship
            insider_title = ''
            if root.find('.//isDirector') is not None and root.find('.//isDirector').text == '1':
                insider_title = 'Director'
            elif root.find('.//isOfficer') is not None and root.find('.//isOfficer').text == '1':
                officer_title_elem = root.find('.//officerTitle')
                insider_title = officer_title_elem.text if officer_title_elem is not None else 'Officer'
            elif root.find('.//isTenPercentOwner') is not None and root.find('.//isTenPercentOwner').text == '1':
                insider_title = '10% Owner'

            # Extract transactions (both buys and sells)
            transactions = root.findall('.//nonDerivativeTransaction')
            for transaction in transactions:
                try:
                    # Include purchase, sale, and exercise transactions
                    trans_code_elem = transaction.find('.//transactionCode')
                    if trans_code_elem is None:
                        continue

                    trans_code = trans_code_elem.text
                    # P = Purchase, M = Exercise of derivative, S = Sale, G = Gift
                    if trans_code not in ['P', 'M', 'S', 'G']:
                        continue

                    # Skip gifts and non-monetary transactions
                    if trans_code == 'G':
                        continue

                    # Extract transaction date
                    trans_date_elem = transaction.find('.//transactionDate/value')
                    if trans_date_elem is None or trans_date_elem.text is None:
                        continue
                    transaction_date = datetime.strptime(trans_date_elem.text, '%Y-%m-%d').date()

                    # Extract shares
                    shares_elem = transaction.find('.//transactionShares/value')
                    if shares_elem is None or shares_elem.text is None:
                        continue
                    try:
                        shares = int(float(shares_elem.text))
                    except (ValueError, TypeError):
                        continue

                    # Extract price
                    price_elem = transaction.find('.//transactionPricePerShare/value')
                    price = float(price_elem.text) if price_elem is not None and price_elem.text else 0.0

                    # Calculate total value
                    total_value = shares * price if price > 0 else shares * 50  # Estimate if no price

                    # For purchases, filter by minimum amount
                    # For sales, include all (they're indicators of insider confidence declining)
                    if trans_code in ['P', 'M'] and total_value < config.MIN_PURCHASE_AMOUNT:
                        continue

                    # Extract filing date
                    filing_date_str = self._extract_filing_date_from_xml(root)
                    if filing_date_str:
                        filing_date = datetime.strptime(filing_date_str, '%Y-%m-%d').date()
                    else:
                        filing_date = transaction_date

                    # Determine transaction type for analysis
                    if trans_code == 'P':
                        transaction_type = 'BUY'
                    elif trans_code == 'M':
                        transaction_type = 'EXERCISE'
                    elif trans_code == 'S':
                        transaction_type = 'SALE'
                    else:
                        transaction_type = 'OTHER'

                    filings.append({
                        'ticker': ticker,
                        'insider_name': insider_name,
                        'insider_title': insider_title,
                        'transaction_date': transaction_date,
                        'filing_date': filing_date,
                        'shares': shares,
                        'price_per_share': price,
                        'total_value': total_value,
                        'transaction_type': transaction_type,  # Now tracks BUY, SALE, EXERCISE, etc.
                        'transaction_code': trans_code,  # Keep raw SEC code for reference
                        'form_4_url': str(xml_path)
                    })

                except Exception as e:
                    logger.debug(f"Error parsing individual transaction: {e}")
                    continue

            return filings if filings else None

        except Exception as e:
            logger.error(f"Failed to parse Form 4 XML {xml_path}: {e}")
            return None

    def _extract_filing_date_from_xml(self, root: ET.Element) -> Optional[str]:
        """Extract filing date from Form 4 XML."""
        period_elem = root.find('.//periodOfReport')
        if period_elem is not None and period_elem.text:
            return period_elem.text
        return None

    def scrape_recent_filings(self, days_back: int = 30) -> pd.DataFrame:
        """
        Scrape recent Form 4 filings and return as DataFrame.

        Args:
            days_back: Number of days to look back (default: 30)

        Returns:
            DataFrame with parsed insider transaction data
        """
        logger.info(f"Starting Form 4 scraping for last {days_back} days")

        all_transactions = []

        # For longer periods, use batch scraping strategy
        if days_back > 30:
            all_transactions = self._scrape_historical_batch(days_back)
        else:
            # Try direct SEC query for recent data
            try:
                all_transactions = self._query_sec_directly(days_back)
            except Exception as e:
                logger.warning(f"Direct SEC query failed, trying alternative method: {e}")

        logger.info(f"Found {len(all_transactions)} insider purchase transactions")

        # Insert into database
        inserted_count = 0
        for transaction in all_transactions:
            if insert_transaction(transaction):
                inserted_count += 1

        logger.info(f"Inserted {inserted_count} transactions into database")

        return pd.DataFrame(all_transactions)

    def _query_sec_directly(self, days_back: int = 30) -> List[Dict]:
        """
        Query SEC EDGAR API directly for Form 4 filings using RSS feed.

        Args:
            days_back: Number of days to look back

        Returns:
            List of parsed transaction dictionaries
        """
        transactions = []
        cutoff_date = datetime.now() - timedelta(days=days_back)

        try:
            # Use SEC EDGAR RSS feed for Form 4 filings (from config)
            rss_url = config.SEC_RSS_FEEDS.get('form4', 'https://www.sec.gov/cgi-bin/browse-edgar?action=getcurrent&type=4&output=atom')

            logger.info(f"Fetching Form 4 filings from SEC RSS feed: {rss_url}")

            # Retry mechanism for SEC rate limiting
            max_retries = 3
            for attempt in range(max_retries):
                try:
                    response = self.session.get(rss_url, timeout=30)

                    # SEC might return 403 on first request - retry with delay
                    if response.status_code == 403 and attempt < max_retries - 1:
                        import time
                        logger.debug(f"Got 403, retrying in 5 seconds (attempt {attempt + 1}/{max_retries})")
                        time.sleep(5)
                        continue

                    response.raise_for_status()
                    break  # Success
                except Exception as e:
                    if attempt == max_retries - 1:
                        raise
                    import time
                    time.sleep(2)

            # Parse Atom feed
            root = ET.fromstring(response.content)

            # Remove namespaces
            for elem in root.iter():
                if '}' in elem.tag:
                    elem.tag = elem.tag.split('}', 1)[1]

            # Extract filing links from Atom entries
            entries = root.findall('.//entry')
            logger.debug(f"Found {len(entries)} Atom entries")

            for item in entries:
                try:
                    # Check if this is a Form 4 filing
                    category_elem = item.find('category')
                    if category_elem is None:
                        continue
                    
                    form_type = category_elem.get('term', '').upper()
                    if form_type != '4':
                        continue

                    # Get filing title and link
                    title_elem = item.find('title')
                    link_elem = item.find('link')
                    updated_elem = item.find('updated')

                    if title_elem is None or link_elem is None:
                        continue

                    title = title_elem.text or ''
                    # Atom feeds use attributes for links
                    link = link_elem.get('href', '') or link_elem.text or ''

                    # Parse publication date from Atom feed
                    if updated_elem is not None and updated_elem.text:
                        try:
                            # Parse ISO 8601 date format: "2025-10-21T13:24:43-04:00"
                            from dateutil import parser as date_parser
                            pub_date = date_parser.parse(updated_elem.text).date()

                            # Skip if older than cutoff
                            if pub_date < cutoff_date.date():
                                continue
                        except Exception as e:
                            logger.debug(f"Failed to parse date: {e}")
                            continue

                    # Download and parse the actual Form 4 document
                    # The ticker will be extracted from the Form 4 XML itself
                    try:
                        filing_data = self._fetch_and_parse_form4(link, ticker=None)
                        if filing_data:
                            transactions.extend(filing_data)
                            logger.debug(f"Parsed {len(filing_data)} transactions from {title}")
                        
                        # Rate limiting: be respectful to SEC servers
                        import time
                        time.sleep(0.15)  # 150ms between requests
                    except Exception as e:
                        logger.debug(f"Failed to parse Form 4 at {link}: {e}")
                        continue

                except Exception as e:
                    logger.debug(f"Error processing RSS item: {e}")
                    continue

            logger.info(f"Successfully queried SEC RSS feed and found {len(transactions)} transactions")

        except Exception as e:
            logger.error(f"Failed to query SEC EDGAR RSS feed: {e}")

        return transactions

    def _scrape_historical_batch(self, days_back: int) -> List[Dict]:
        """
        Scrape historical data using SEC's company search API for major companies.
        
        Args:
            days_back: Number of days to look back
            
        Returns:
            List of parsed transaction dictionaries
        """
        logger.info(f"Starting historical scraping for {days_back} days using company search")
        
        all_transactions = []
        
        # List of major companies with regular insider activity (S&P 500 subset)
        major_companies = [
            {'cik': '0000320193', 'ticker': 'AAPL', 'name': 'Apple Inc.'},
            {'cik': '0000789019', 'ticker': 'MSFT', 'name': 'Microsoft Corp.'},
            {'cik': '0001018724', 'ticker': 'AMZN', 'name': 'Amazon.com Inc.'},
            {'cik': '0000789019', 'ticker': 'GOOGL', 'name': 'Alphabet Inc.'},
            {'cik': '0001326801', 'ticker': 'TSLA', 'name': 'Tesla Inc.'},
            {'cik': '0000789019', 'ticker': 'META', 'name': 'Meta Platforms Inc.'},
            {'cik': '0000789019', 'ticker': 'NVDA', 'name': 'NVIDIA Corp.'},
            {'cik': '0000789019', 'ticker': 'JPM', 'name': 'JPMorgan Chase & Co.'},
            {'cik': '0000789019', 'ticker': 'JNJ', 'name': 'Johnson & Johnson'},
            {'cik': '0000789019', 'ticker': 'V', 'name': 'Visa Inc.'},
            {'cik': '0000789019', 'ticker': 'PG', 'name': 'Procter & Gamble Co.'},
            {'cik': '0000789019', 'ticker': 'UNH', 'name': 'UnitedHealth Group Inc.'},
            {'cik': '0000789019', 'ticker': 'HD', 'name': 'Home Depot Inc.'},
            {'cik': '0000789019', 'ticker': 'MA', 'name': 'Mastercard Inc.'},
            {'cik': '0000789019', 'ticker': 'DIS', 'name': 'Walt Disney Co.'},
        ]
        
        logger.info(f"Scraping {len(major_companies)} major companies for Form 4 filings")
        
        for i, company in enumerate(major_companies, 1):
            try:
                logger.info(f"Processing company {i}/{len(major_companies)}: {company['ticker']} ({company['name']})")
                
                # Query SEC for this company's Form 4 filings
                company_transactions = self._query_company_form4s(company['cik'], company['ticker'], days_back)
                all_transactions.extend(company_transactions)
                
                logger.info(f"  Found {len(company_transactions)} transactions for {company['ticker']}")
                
                # Rate limiting between companies
                import time
                time.sleep(1.0)  # 1 second between companies
                
            except Exception as e:
                logger.warning(f"Failed to scrape {company['ticker']}: {e}")
        
        logger.info(f"Historical scraping complete: {len(all_transactions)} total transactions")
        return all_transactions

    def _query_sec_by_date_range(self, start_date: datetime, end_date: datetime) -> List[Dict]:
        """
        Query SEC for Form 4 filings within a specific date range.
        
        Args:
            start_date: Start date for the range
            end_date: End date for the range
            
        Returns:
            List of parsed transaction dictionaries
        """
        transactions = []
        
        try:
            # Use SEC's company search with date filters
            # This is a simplified approach - in practice, you'd need to iterate through
            # different company CIKs or use SEC's full-text search API
            
            # For now, fall back to the RSS approach but with date filtering
            rss_url = config.SEC_RSS_FEEDS.get('form4', 'https://www.sec.gov/cgi-bin/browse-edgar?action=getcurrent&type=4&output=atom')
            
            response = self.session.get(rss_url, timeout=30)
            response.raise_for_status()
            
            # Parse Atom feed
            root = ET.fromstring(response.content)
            
            # Remove namespaces
            for elem in root.iter():
                if '}' in elem.tag:
                    elem.tag = elem.tag.split('}', 1)[1]
            
            # Extract filing links from Atom entries
            entries = root.findall('.//entry')
            
            for item in entries:
                try:
                    # Check if this is a Form 4 filing
                    category_elem = item.find('category')
                    if category_elem is None:
                        continue
                    
                    form_type = category_elem.get('term', '').upper()
                    if form_type != '4':
                        continue

                    # Get filing title and link
                    title_elem = item.find('title')
                    link_elem = item.find('link')
                    updated_elem = item.find('updated')

                    if title_elem is None or link_elem is None:
                        continue

                    title = title_elem.text or ''
                    link = link_elem.get('href', '') or link_elem.text or ''

                    # Parse publication date from Atom feed
                    if updated_elem is not None and updated_elem.text:
                        try:
                            from dateutil import parser as date_parser
                            pub_date = date_parser.parse(updated_elem.text).date()
                            
                            # Check if within date range
                            if pub_date < start_date.date() or pub_date > end_date.date():
                                continue
                                
                        except Exception as e:
                            logger.debug(f"Failed to parse date: {e}")
                            continue

                    # Download and parse the actual Form 4 document
                    try:
                        filing_data = self._fetch_and_parse_form4(link, ticker=None)
                        if filing_data:
                            transactions.extend(filing_data)
                            logger.debug(f"Parsed {len(filing_data)} transactions from {title}")
                        
                        # Rate limiting: be respectful to SEC servers
                        import time
                        time.sleep(0.15)  # 150ms between requests
                    except Exception as e:
                        logger.debug(f"Failed to parse Form 4 at {link}: {e}")
                        continue

                except Exception as e:
                    logger.debug(f"Error processing RSS item: {e}")
                    continue

        except Exception as e:
            logger.error(f"Failed to query SEC for date range: {e}")

        return transactions

    def _query_company_form4s(self, cik: str, ticker: str, days_back: int) -> List[Dict]:
        """
        Query SEC for Form 4 filings for a specific company.
        
        Args:
            cik: Company's Central Index Key
            ticker: Stock ticker symbol
            days_back: Number of days to look back
            
        Returns:
            List of parsed transaction dictionaries
        """
        transactions = []
        
        try:
            # Use SEC's company search API
            # URL format: https://www.sec.gov/cgi-bin/browse-edgar?action=getcompany&CIK={cik}&type=4&dateb=&count=100&output=atom
            search_url = f"https://www.sec.gov/cgi-bin/browse-edgar?action=getcompany&CIK={cik}&type=4&dateb=&count=100&output=atom"
            
            logger.debug(f"Querying SEC for {ticker} (CIK: {cik})")
            
            response = self.session.get(search_url, timeout=30)
            response.raise_for_status()
            
            # Parse Atom feed
            root = ET.fromstring(response.content)
            
            # Remove namespaces
            for elem in root.iter():
                if '}' in elem.tag:
                    elem.tag = elem.tag.split('}', 1)[1]
            
            # Extract filing links from Atom entries
            entries = root.findall('.//entry')
            logger.debug(f"Found {len(entries)} entries for {ticker}")
            
            cutoff_date = datetime.now() - timedelta(days=days_back)
            
            for item in entries:
                try:
                    # Check if this is a Form 4 filing
                    category_elem = item.find('category')
                    if category_elem is None:
                        continue
                    
                    form_type = category_elem.get('term', '').upper()
                    if form_type != '4':
                        continue

                    # Get filing title and link
                    title_elem = item.find('title')
                    link_elem = item.find('link')
                    updated_elem = item.find('updated')

                    if title_elem is None or link_elem is None:
                        continue

                    title = title_elem.text or ''
                    link = link_elem.get('href', '') or link_elem.text or ''

                    # Parse publication date from Atom feed
                    if updated_elem is not None and updated_elem.text:
                        try:
                            from dateutil import parser as date_parser
                            pub_date = date_parser.parse(updated_elem.text).date()
                            
                            # Check if within date range
                            if pub_date < cutoff_date.date():
                                continue
                                
                        except Exception as e:
                            logger.debug(f"Failed to parse date: {e}")
                            continue

                    # Download and parse the actual Form 4 document
                    try:
                        filing_data = self._fetch_and_parse_form4(link, ticker=ticker)
                        if filing_data:
                            transactions.extend(filing_data)
                            logger.debug(f"Parsed {len(filing_data)} transactions from {title}")
                        
                        # Rate limiting: be respectful to SEC servers
                        import time
                        time.sleep(0.2)  # 200ms between filings
                    except Exception as e:
                        logger.debug(f"Failed to parse Form 4 at {link}: {e}")
                        continue

                except Exception as e:
                    logger.debug(f"Error processing RSS item: {e}")
                    continue

        except Exception as e:
            logger.error(f"Failed to query SEC for {ticker}: {e}")

        return transactions

    def _fetch_and_parse_form4(self, filing_link: str, ticker: Optional[str] = None) -> Optional[List[Dict]]:
        """
        Fetch and parse a specific Form 4 filing from SEC.

        Args:
            filing_link: URL to the SEC filing
            ticker: Stock ticker symbol (optional, will be extracted from XML if not provided)

        Returns:
            List of parsed transaction dictionaries, or None if parsing fails
        """
        try:
            # Get the filing details page
            response = self.session.get(filing_link, timeout=30)
            response.raise_for_status()

            # Extract XML URL from the filing page
            # Form 4 XML files are typically named like: form4.xml
            from bs4 import BeautifulSoup
            soup = BeautifulSoup(response.text, 'html.parser')

            # Look for XML document link in the document table
            xml_link = None
            
            # Parse the document table for Form 4 XML files
            for table in soup.find_all('table', {'class': 'tableFile'}):
                for row in table.find_all('tr'):
                    cells = row.find_all('td')
                    if len(cells) >= 4:
                        doc_type = cells[3].text.strip()
                        if doc_type == '4':  # This is a Form 4 document
                            link_elem = cells[2].find('a')
                            if link_elem:
                                href = link_elem.get('href', '')
                                # Only get XML files, not HTML
                                if href.endswith('.xml') and not href.endswith('.html'):
                                    xml_link = href
                                    break
                if xml_link:
                    break
            
            # Fallback: look for any XML link with form4 in the name
            if not xml_link:
                for link in soup.find_all('a'):
                    href = link.get('href', '')
                    if 'form4' in href.lower() and href.endswith('.xml'):
                        xml_link = href
                        break

            if not xml_link:
                logger.debug(f"Could not find XML link for {filing_link}")
                return None

            # Ensure absolute URL and remove XSLT transformation path
            if not xml_link.startswith('http'):
                xml_link = 'https://www.sec.gov' + (xml_link if xml_link.startswith('/') else '/' + xml_link)
            
            # Remove XSLT transformation directories (xslF345X0*, etc.) to get raw XML
            # Example: /Archives/.../xslF345X05/file.xml -> /Archives/.../file.xml
            import re
            xml_link = re.sub(r'/xsl[^/]+/', '/', xml_link)

            # Fetch and parse the XML
            xml_response = self.session.get(xml_link, timeout=30)
            xml_response.raise_for_status()

            # Write to temp file and parse
            temp_file = tempfile.NamedTemporaryFile(suffix='.xml', delete=False)
            temp_file.write(xml_response.content)
            temp_file.close()

            try:
                parsed_data = self.parse_form4_xml(Path(temp_file.name))
                if parsed_data:
                    # Ensure ticker is set (if provided as parameter)
                    if ticker:
                        for transaction in parsed_data:
                            if not transaction.get('ticker'):
                                transaction['ticker'] = ticker
                    return parsed_data
            finally:
                # Clean up temp file
                Path(temp_file.name).unlink(missing_ok=True)

            return None

        except Exception as e:
            logger.debug(f"Failed to fetch Form 4 from {filing_link}: {e}")
            return None

    def get_filing_speed_stats(self) -> Dict:
        """Get statistics on filing speed (transaction_date to filing_date)."""
        from src.database import get_recent_transactions

        df = get_recent_transactions(days=90, min_value=config.MIN_PURCHASE_AMOUNT)

        if df.empty:
            return {}

        stats = {
            'mean_days': df['filing_speed_days'].mean(),
            'median_days': df['filing_speed_days'].median(),
            'std_dev': df['filing_speed_days'].std(),
            'same_day_filings': len(df[df['filing_speed_days'] == 0]),
            'next_day_filings': len(df[df['filing_speed_days'] == 1]),
        }

        return stats


if __name__ == "__main__":
    scraper = Form4Scraper()
    results = scraper.scrape_recent_filings(days_back=7)
    print(f"\nScraped {len(results)} transactions")
    if len(results) > 0:
        print("\nTop 10 largest purchases:")
        print(results.nlargest(10, 'total_value')[['ticker', 'insider_name', 'shares', 'total_value', 'filing_speed_days']])
