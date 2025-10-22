"""
Real earnings quality scorer using yfinance and Alpha Vantage APIs.
Replaces placeholder earnings sentiment with actual earnings data.
"""

import yfinance as yf
import requests
import pandas as pd
from datetime import datetime, timedelta
from typing import Dict, Optional, Tuple
from loguru import logger
import os
import time


class EarningsQualityScorer:
    """Real earnings quality scorer using multiple data sources."""
    
    def __init__(self, alpha_vantage_key: Optional[str] = None):
        """
        Initialize earnings quality scorer.
        
        Args:
            alpha_vantage_key: Alpha Vantage API key (optional)
        """
        self.alpha_vantage_key = alpha_vantage_key or os.getenv('ALPHA_VANTAGE_API_KEY')
        self.cache = {}
        self.cache_ttl = 3600  # 1 hour cache
        
    def get_earnings_quality(self, ticker: str) -> Tuple[float, Dict]:
        """
        Get earnings quality score for a ticker.
        
        Args:
            ticker: Stock ticker symbol
            
        Returns:
            Tuple of (score 0.0-1.0, details_dict)
        """
        ticker = ticker.upper()
        
        # Check cache first
        cache_key = f"earnings_{ticker}"
        if cache_key in self.cache:
            cached_data, timestamp = self.cache[cache_key]
            if time.time() - timestamp < self.cache_ttl:
                return cached_data['score'], cached_data['details']
        
        try:
            # Try yfinance first
            score, details = self._get_earnings_from_yfinance(ticker)
            
            # If yfinance data is insufficient, try Alpha Vantage
            if score == 0.5 and details.get('source') == 'insufficient_data' and self.alpha_vantage_key:
                logger.debug(f"Trying Alpha Vantage for {ticker} earnings data")
                av_score, av_details = self._get_earnings_from_alpha_vantage(ticker)
                if av_score != 0.5:  # If we got better data
                    score, details = av_score, av_details
            
            # Apply staleness penalty
            score, details = self._apply_staleness_penalty(score, details)
            
            # Cache the result
            self.cache[cache_key] = ({
                'score': score,
                'details': details
            }, time.time())
            
            return score, details
            
        except Exception as e:
            logger.error(f"Error getting earnings quality for {ticker}: {e}")
            return 0.5, {
                'source': 'error',
                'error': str(e),
                'ticker': ticker,
                'score': 0.5,
                'quality': 'unknown'
            }
    
    def _get_earnings_from_yfinance(self, ticker: str) -> Tuple[float, Dict]:
        """Get earnings data from yfinance."""
        try:
            stock = yf.Ticker(ticker)
            
            # Get earnings dates
            earnings_dates = stock.earnings_dates
            if earnings_dates is None or earnings_dates.empty:
                return 0.5, {
                    'source': 'yfinance',
                    'ticker': ticker,
                    'score': 0.5,
                    'quality': 'no_data',
                    'message': 'No earnings dates available'
                }
            
            # Get most recent earnings with actual data
            for i in range(len(earnings_dates)):
                row = earnings_dates.iloc[i]
                earnings_date = row.name
                
                # Check if we have actual EPS data
                actual_eps = row.get('Reported EPS', None)
                estimate_eps = row.get('EPS Estimate', None)
                
                if not pd.isna(actual_eps) and not pd.isna(estimate_eps):
                    break
            else:
                # No earnings with actual data found
                return 0.5, {
                    'source': 'yfinance',
                    'ticker': ticker,
                    'score': 0.5,
                    'quality': 'no_actual_data',
                    'message': 'No earnings with actual data available'
                }
            
            if pd.isna(actual_eps) or pd.isna(estimate_eps):
                return 0.5, {
                    'source': 'yfinance',
                    'ticker': ticker,
                    'score': 0.5,
                    'quality': 'insufficient_data',
                    'message': 'Missing EPS data',
                    'earnings_date': earnings_date
                }
            
            # Calculate surprise percentage
            surprise_pct = ((actual_eps - estimate_eps) / abs(estimate_eps)) * 100 if estimate_eps != 0 else 0
            
            # Score based on surprise
            if surprise_pct > 10:
                score = 1.0
                quality = 'excellent_beat'
            elif surprise_pct > 5:
                score = 0.8
                quality = 'strong_beat'
            elif surprise_pct > 0:
                score = 0.7
                quality = 'small_beat'
            elif surprise_pct == 0:
                score = 0.5
                quality = 'met_expectations'
            elif surprise_pct > -5:
                score = 0.3
                quality = 'small_miss'
            else:
                score = 0.0
                quality = 'large_miss'
            
            return score, {
                'source': 'yfinance',
                'ticker': ticker,
                'score': score,
                'quality': quality,
                'earnings_date': earnings_date,
                'actual_eps': actual_eps,
                'estimate_eps': estimate_eps,
                'surprise_pct': surprise_pct,
                'days_since_earnings': (datetime.now() - earnings_date.replace(tzinfo=None)).days
            }
            
        except Exception as e:
            logger.debug(f"yfinance earnings error for {ticker}: {e}")
            return 0.5, {
                'source': 'yfinance',
                'ticker': ticker,
                'score': 0.5,
                'quality': 'error',
                'error': str(e)
            }
    
    def _get_earnings_from_alpha_vantage(self, ticker: str) -> Tuple[float, Dict]:
        """Get earnings data from Alpha Vantage."""
        if not self.alpha_vantage_key:
            return 0.5, {
                'source': 'alpha_vantage',
                'ticker': ticker,
                'score': 0.5,
                'quality': 'no_api_key',
                'message': 'Alpha Vantage API key not provided'
            }
        
        try:
            url = "https://www.alphavantage.co/query"
            params = {
                'function': 'EARNINGS',
                'symbol': ticker,
                'apikey': self.alpha_vantage_key
            }
            
            response = requests.get(url, params=params, timeout=10)
            data = response.json()
            
            if 'Error Message' in data:
                return 0.5, {
                    'source': 'alpha_vantage',
                    'ticker': ticker,
                    'score': 0.5,
                    'quality': 'api_error',
                    'error': data['Error Message']
                }
            
            if 'Note' in data:
                return 0.5, {
                    'source': 'alpha_vantage',
                    'ticker': ticker,
                    'score': 0.5,
                    'quality': 'rate_limited',
                    'message': 'API rate limit exceeded'
                }
            
            # Parse earnings data
            quarterly_earnings = data.get('quarterlyEarnings', [])
            if not quarterly_earnings:
                return 0.5, {
                    'source': 'alpha_vantage',
                    'ticker': ticker,
                    'score': 0.5,
                    'quality': 'no_data',
                    'message': 'No quarterly earnings data'
                }
            
            # Get most recent earnings
            most_recent = quarterly_earnings[0]
            reported_date = most_recent.get('reportedDate', '')
            surprise = most_recent.get('surprise', None)
            surprise_percentage = most_recent.get('surprisePercentage', None)
            
            if surprise_percentage is not None:
                surprise_pct = float(surprise_percentage)
            elif surprise is not None:
                surprise_pct = float(surprise)
            else:
                return 0.5, {
                    'source': 'alpha_vantage',
                    'ticker': ticker,
                    'score': 0.5,
                    'quality': 'insufficient_data',
                    'message': 'No surprise data available'
                }
            
            # Score based on surprise
            if surprise_pct > 10:
                score = 1.0
                quality = 'excellent_beat'
            elif surprise_pct > 5:
                score = 0.8
                quality = 'strong_beat'
            elif surprise_pct > 0:
                score = 0.7
                quality = 'small_beat'
            elif surprise_pct == 0:
                score = 0.5
                quality = 'met_expectations'
            elif surprise_pct > -5:
                score = 0.3
                quality = 'small_miss'
            else:
                score = 0.0
                quality = 'large_miss'
            
            # Calculate days since earnings
            try:
                earnings_date = datetime.strptime(reported_date, '%Y-%m-%d')
                days_since = (datetime.now() - earnings_date).days
            except:
                days_since = None
            
            return score, {
                'source': 'alpha_vantage',
                'ticker': ticker,
                'score': score,
                'quality': quality,
                'earnings_date': reported_date,
                'surprise_pct': surprise_pct,
                'days_since_earnings': days_since,
                'fiscal_date_ending': most_recent.get('fiscalDateEnding', ''),
                'estimated_eps': most_recent.get('estimatedEPS', ''),
                'reported_eps': most_recent.get('reportedEPS', '')
            }
            
        except Exception as e:
            logger.debug(f"Alpha Vantage earnings error for {ticker}: {e}")
            return 0.5, {
                'source': 'alpha_vantage',
                'ticker': ticker,
                'score': 0.5,
                'quality': 'error',
                'error': str(e)
            }
    
    def _apply_staleness_penalty(self, score: float, details: Dict) -> Tuple[float, Dict]:
        """Apply staleness penalty to earnings score."""
        days_since = details.get('days_since_earnings')
        
        if days_since is None:
            return score, details
        
        original_score = score
        
        # Apply staleness penalties
        if days_since > 180:
            score = 0.5  # Neutral for very old earnings
            penalty_reason = 'very_old_earnings'
        elif days_since > 90:
            score = score * 0.5  # 50% penalty for old earnings
            penalty_reason = 'old_earnings'
        else:
            penalty_reason = 'none'
        
        details['original_score'] = original_score
        details['staleness_penalty'] = penalty_reason
        details['final_score'] = score
        
        return score, details


def get_earnings_quality_scorer() -> EarningsQualityScorer:
    """Get earnings quality scorer instance."""
    return EarningsQualityScorer()


def test_earnings_quality():
    """Test earnings quality for sample tickers."""
    
    print("=" * 80)
    print("EARNINGS QUALITY SCORER TEST")
    print("=" * 80)
    print()
    
    scorer = get_earnings_quality_scorer()
    test_tickers = ['AAPL', 'CMC', 'AMZN', 'META']
    
    for ticker in test_tickers:
        print(f"Testing {ticker}:")
        print("-" * 40)
        
        try:
            score, details = scorer.get_earnings_quality(ticker)
            
            print(f"  Score: {score:.3f}")
            print(f"  Quality: {details.get('quality', 'unknown')}")
            print(f"  Source: {details.get('source', 'unknown')}")
            
            if 'surprise_pct' in details:
                print(f"  Surprise: {details['surprise_pct']:+.1f}%")
            
            if 'earnings_date' in details:
                print(f"  Earnings Date: {details['earnings_date']}")
            
            if 'days_since_earnings' in details and details['days_since_earnings'] is not None:
                print(f"  Days Since: {details['days_since_earnings']}")
            
            if 'staleness_penalty' in details:
                print(f"  Staleness: {details['staleness_penalty']}")
            
            if 'error' in details:
                print(f"  Error: {details['error']}")
            
            print()
            
        except Exception as e:
            print(f"  Error: {e}")
            print()


if __name__ == "__main__":
    test_earnings_quality()