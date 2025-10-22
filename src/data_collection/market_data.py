"""Market data collection using yfinance."""
import yfinance as yf
from typing import Optional, Dict, Any
from loguru import logger
import time
from datetime import datetime, timedelta


def get_short_interest(ticker: str) -> Optional[float]:
    """
    Get real short interest data for a ticker using yfinance.
    
    Args:
        ticker: Stock ticker symbol
        
    Returns:
        Short interest as percentage of float, or None if unavailable
    """
    try:
        stock = yf.Ticker(ticker)
        info = stock.info
        
        # Try multiple fields for short interest data
        short_ratio = info.get('shortPercentOfFloat', 0)
        if short_ratio == 0:
            # Try alternative field names
            short_ratio = info.get('shortRatio', 0)
        if short_ratio == 0:
            # Try short interest as percentage
            short_ratio = info.get('shortInterest', 0)
            if short_ratio > 0 and short_ratio < 1:
                # Convert decimal to percentage
                short_ratio = short_ratio * 100
        
        # Ensure we have a percentage value
        if short_ratio > 0 and short_ratio < 1:
            short_ratio = short_ratio * 100
            
        logger.debug(f"{ticker} short interest: {short_ratio:.2f}%")
        return short_ratio if short_ratio > 0 else None
        
    except Exception as e:
        logger.warning(f"Failed to get short interest for {ticker}: {e}")
        return None


def get_market_cap(ticker: str) -> Optional[float]:
    """
    Get market capitalization for a ticker.
    
    Args:
        ticker: Stock ticker symbol
        
    Returns:
        Market cap in billions, or None if unavailable
    """
    try:
        stock = yf.Ticker(ticker)
        info = stock.info
        
        market_cap = info.get('marketCap', 0)
        if market_cap > 0:
            # Convert to billions
            market_cap_billions = market_cap / 1_000_000_000
            logger.debug(f"{ticker} market cap: ${market_cap_billions:.1f}B")
            return market_cap_billions
            
        return None
        
    except Exception as e:
        logger.warning(f"Failed to get market cap for {ticker}: {e}")
        return None


def get_volume_data(ticker: str, days: int = 30) -> Optional[Dict[str, float]]:
    """
    Get volume data for a ticker.
    
    Args:
        ticker: Stock ticker symbol
        days: Number of days to look back
        
    Returns:
        Dict with volume metrics, or None if unavailable
    """
    try:
        stock = yf.Ticker(ticker)
        
        # Get historical data
        end_date = datetime.now()
        start_date = end_date - timedelta(days=days)
        
        hist = stock.history(start=start_date, end=end_date)
        
        if hist.empty:
            return None
            
        # Calculate volume metrics
        avg_volume = hist['Volume'].mean()
        recent_volume = hist['Volume'].iloc[-1] if len(hist) > 0 else 0
        volume_ratio = recent_volume / avg_volume if avg_volume > 0 else 1.0
        
        return {
            'avg_volume': avg_volume,
            'recent_volume': recent_volume,
            'volume_ratio': volume_ratio
        }
        
    except Exception as e:
        logger.warning(f"Failed to get volume data for {ticker}: {e}")
        return None


def get_stock_info(ticker: str) -> Dict[str, Any]:
    """
    Get comprehensive stock information.
    
    Args:
        ticker: Stock ticker symbol
        
    Returns:
        Dict with stock information
    """
    try:
        stock = yf.Ticker(ticker)
        info = stock.info
        
        # Extract key metrics
        result = {
            'ticker': ticker,
            'name': info.get('longName', ticker),
            'sector': info.get('sector', 'Unknown'),
            'industry': info.get('industry', 'Unknown'),
            'market_cap': info.get('marketCap', 0),
            'price': info.get('currentPrice', info.get('regularMarketPrice', 0)),
            'pe_ratio': info.get('trailingPE', 0),
            'beta': info.get('beta', 0),
            'short_interest': get_short_interest(ticker),
            'volume_data': get_volume_data(ticker),
            'last_updated': datetime.now().isoformat()
        }
        
        logger.debug(f"Retrieved info for {ticker}: {result['name']}")
        return result
        
    except Exception as e:
        logger.error(f"Failed to get stock info for {ticker}: {e}")
        return {
            'ticker': ticker,
            'error': str(e),
            'last_updated': datetime.now().isoformat()
        }


def batch_get_short_interest(tickers: list, delay: float = 0.1) -> Dict[str, Optional[float]]:
    """
    Get short interest for multiple tickers with rate limiting.
    
    Args:
        tickers: List of ticker symbols
        delay: Delay between requests in seconds
        
    Returns:
        Dict mapping ticker to short interest percentage
    """
    results = {}
    
    for ticker in tickers:
        try:
            short_interest = get_short_interest(ticker)
            results[ticker] = short_interest
            
            # Rate limiting
            if delay > 0:
                time.sleep(delay)
                
        except Exception as e:
            logger.warning(f"Failed to get short interest for {ticker}: {e}")
            results[ticker] = None
    
    return results


if __name__ == "__main__":
    # Test the functions
    test_tickers = ['AAPL', 'MSFT', 'GOOGL']
    
    print("Testing short interest data:")
    for ticker in test_tickers:
        short_interest = get_short_interest(ticker)
        print(f"{ticker}: {short_interest:.2f}%" if short_interest else f"{ticker}: No data")
    
    print("\nTesting batch processing:")
    batch_results = batch_get_short_interest(test_tickers)
    for ticker, short_interest in batch_results.items():
        print(f"{ticker}: {short_interest:.2f}%" if short_interest else f"{ticker}: No data")

