"""
Intraday market data monitoring with real-time updates.
Fetches 5-minute and 1-minute interval data for active positions and watchlist items.
"""
from typing import Dict, List, Optional, Tuple
from datetime import datetime, timedelta
import yfinance as yf
import pandas as pd
from loguru import logger
import time
import threading
from queue import Queue

try:
    import polygon
    HAS_POLYGON = True
except ImportError:
    HAS_POLYGON = False


class IntradayMonitor:
    """Real-time intraday market data monitoring."""

    def __init__(self, interval: str = "5m", max_data_points: int = 288):
        """
        Initialize intraday monitor.

        Args:
            interval: Data interval ('1m', '5m', '15m', '60m')
            max_data_points: Maximum data points to retain per ticker
        """
        self.interval = interval
        self.max_data_points = max_data_points
        self.intraday_cache = {}
        self.cache_timestamps = {}
        self.lock = threading.Lock()
        self.last_refresh = {}

        # Minimum time between refreshes (seconds)
        self.min_refresh_interval = {
            '1m': 60,
            '5m': 300,
            '15m': 900,
            '60m': 3600,
        }.get(interval, 300)

        logger.info(f"Intraday monitor initialized with {interval} interval")

    def fetch_intraday_data(
        self, ticker: str, interval: Optional[str] = None
    ) -> Optional[pd.DataFrame]:
        """
        Fetch intraday data for a ticker.

        Args:
            ticker: Stock ticker
            interval: Time interval ('1m', '5m', '15m', '60m'). Uses default if None.

        Returns:
            DataFrame with intraday OHLCV data or None
        """
        ticker = ticker.upper()
        interval = interval or self.interval

        try:
            # Check if we need to refresh (respect rate limits)
            last_refresh = self.last_refresh.get(ticker, 0)
            if time.time() - last_refresh < self.min_refresh_interval:
                # Return cached data if still fresh
                with self.lock:
                    if ticker in self.intraday_cache:
                        return self.intraday_cache[ticker].copy()

            # Fetch from yfinance
            stock = yf.Ticker(ticker)

            # Determine period based on interval
            # Note: yfinance has restrictions on intraday periods
            # For 5m data, we need to use a longer period and then filter
            period_map = {
                '1m': '1d',     # Last day for 1-minute
                '5m': '5d',     # Last 5 days for 5-minute
                '15m': '5d',    # Last 5 days for 15-minute
                '60m': '60d',   # Last 60 days for hourly
            }
            period = period_map.get(interval, '5d')

            # yfinance has specific limitations with intraday data
            # If intraday fails, fall back to daily data
            try:
                hist = stock.history(period=period, interval=interval)
            except Exception as e:
                logger.debug(f"Intraday fetch failed with {interval}, using daily as fallback: {e}")
                hist = stock.history(period='60d', interval='1d')

            if hist is None or hist.empty:
                logger.debug(f"No intraday data for {ticker} at {interval}")
                return None

            # Cache the data
            with self.lock:
                # Keep only most recent data points
                if len(hist) > self.max_data_points:
                    hist = hist.tail(self.max_data_points)

                self.intraday_cache[ticker] = hist.copy()
                self.cache_timestamps[ticker] = time.time()
                self.last_refresh[ticker] = time.time()

            logger.debug(f"Fetched {len(hist)} intraday data points for {ticker}")
            return hist.copy()

        except Exception as e:
            logger.debug(f"Error fetching intraday data for {ticker}: {e}")
            return None

    def get_current_price_momentum(self, ticker: str) -> Optional[Dict]:
        """
        Calculate current price momentum and volatility.

        Args:
            ticker: Stock ticker

        Returns:
            Dict with momentum metrics or None
        """
        try:
            hist = self.fetch_intraday_data(ticker, '5m')
            if hist is None or len(hist) < 3:
                return None

            # Calculate metrics
            prices = hist['Close'].values
            current_price = prices[-1]
            previous_price = prices[-2] if len(prices) > 1 else prices[-1]

            # Intraday change
            price_change = current_price - previous_price
            price_change_pct = (price_change / previous_price * 100) if previous_price != 0 else 0

            # Short-term momentum (last 5 candles)
            short_term_trend = "bullish" if prices[-1] > prices[-5] else "bearish"

            # Volatility (standard deviation of recent prices)
            volatility = float(hist['Close'].std())
            volatility_pct = (volatility / current_price * 100) if current_price != 0 else 0

            # Volume analysis
            volume = float(hist['Volume'].iloc[-1]) if 'Volume' in hist else 0
            avg_volume = float(hist['Volume'].mean()) if 'Volume' in hist else 0
            volume_ratio = (volume / avg_volume) if avg_volume > 0 else 1.0

            # RSI-like calculation (simplified)
            rsi = self._calculate_simple_rsi(hist)

            return {
                'ticker': ticker,
                'current_price': float(current_price),
                'price_change': float(price_change),
                'price_change_pct': float(price_change_pct),
                'trend': short_term_trend,
                'volatility': float(volatility),
                'volatility_pct': float(volatility_pct),
                'volume': float(volume),
                'avg_volume': float(avg_volume),
                'volume_ratio': float(volume_ratio),
                'rsi': float(rsi),
                'timestamp': datetime.now().isoformat(),
            }

        except Exception as e:
            logger.debug(f"Error calculating momentum for {ticker}: {e}")
            return None

    def _calculate_simple_rsi(self, hist: pd.DataFrame, period: int = 14) -> float:
        """
        Calculate simplified RSI from OHLC data.

        Args:
            hist: DataFrame with price history
            period: RSI period

        Returns:
            RSI value (0-100)
        """
        try:
            if len(hist) < period:
                return 50.0  # Default if insufficient data

            prices = hist['Close'].values
            deltas = [prices[i] - prices[i-1] for i in range(1, len(prices))]

            seed = deltas[:period]
            up = sum(d for d in seed if d > 0) / period
            down = sum(abs(d) for d in seed if d < 0) / period

            # Calculate smoothed RS
            for d in deltas[period:]:
                up = (up * (period - 1) + (d if d > 0 else 0)) / period
                down = (down * (period - 1) + (abs(d) if d < 0 else 0)) / period

            rs = up / down if down != 0 else 100.0 if up != 0 else 50.0
            rsi = 100 - (100 / (1 + rs))

            return max(0, min(100, rsi))

        except Exception as e:
            logger.debug(f"Error calculating RSI: {e}")
            return 50.0

    def detect_price_action_signals(self, ticker: str) -> Optional[Dict]:
        """
        Detect significant price action signals (breakouts, reversals).

        Args:
            ticker: Stock ticker

        Returns:
            Dict with detected signals or None
        """
        try:
            hist = self.fetch_intraday_data(ticker, '5m')
            if hist is None or len(hist) < 10:
                return None

            data = hist.tail(10).copy()
            prices = data['Close'].values
            highs = data['High'].values
            lows = data['Low'].values

            signals = {
                'ticker': ticker,
                'breakout_high': False,
                'breakout_low': False,
                'reversal_pattern': None,
                'volume_spike': False,
                'trend_change': False,
            }

            # Detect breakouts
            recent_high = max(highs[-5:-1])
            recent_low = min(lows[-5:-1])
            current_price = prices[-1]

            if current_price > recent_high * 1.01:  # 1% above recent high
                signals['breakout_high'] = True
            elif current_price < recent_low * 0.99:  # 1% below recent low
                signals['breakout_low'] = True

            # Detect reversal patterns (simplified)
            if len(prices) >= 3:
                if prices[-3] > prices[-2] < prices[-1]:
                    signals['reversal_pattern'] = 'V-shape'
                elif prices[-3] < prices[-2] > prices[-1]:
                    signals['reversal_pattern'] = 'inverted-V'

            # Detect volume spike
            volumes = data['Volume'].values
            if len(volumes) > 5:
                avg_vol = sum(volumes[:-1]) / len(volumes[:-1])
                if volumes[-1] > avg_vol * 1.5:
                    signals['volume_spike'] = True

            # Detect trend changes
            if len(prices) >= 5:
                older_trend = "up" if prices[-5] < prices[-3] else "down"
                recent_trend = "up" if prices[-2] < prices[-1] else "down"
                if older_trend != recent_trend:
                    signals['trend_change'] = True

            return signals

        except Exception as e:
            logger.debug(f"Error detecting price signals for {ticker}: {e}")
            return None

    def bulk_fetch_intraday(self, tickers: List[str]) -> Dict[str, pd.DataFrame]:
        """
        Fetch intraday data for multiple tickers.

        Args:
            tickers: List of ticker symbols

        Returns:
            Dict mapping ticker to intraday DataFrame
        """
        results = {}

        for ticker in tickers:
            try:
                data = self.fetch_intraday_data(ticker)
                if data is not None:
                    results[ticker] = data
                    time.sleep(0.2)  # Rate limiting

            except Exception as e:
                logger.debug(f"Error fetching intraday for {ticker}: {e}")
                continue

        logger.info(f"Fetched intraday data for {len(results)}/{len(tickers)} tickers")
        return results

    def get_cache_stats(self) -> Dict:
        """Get statistics about cached intraday data."""
        with self.lock:
            return {
                'cached_tickers': len(self.intraday_cache),
                'cache_size_kb': sum(
                    len(df) * 8 / 1024
                    for df in self.intraday_cache.values()
                ),
                'oldest_data': min(
                    self.cache_timestamps.values()
                ) if self.cache_timestamps else None,
                'newest_data': max(
                    self.cache_timestamps.values()
                ) if self.cache_timestamps else None,
            }

    def clear_cache(self):
        """Clear all cached intraday data."""
        with self.lock:
            self.intraday_cache.clear()
            self.cache_timestamps.clear()
            self.last_refresh.clear()
            logger.info("Intraday cache cleared")


class IntradayAlertSystem:
    """Real-time alert system for intraday price movements and signals."""

    def __init__(self, monitor: IntradayMonitor):
        """
        Initialize alert system.

        Args:
            monitor: IntradayMonitor instance
        """
        self.monitor = monitor
        self.alerts = []
        self.alert_threshold_pct = 2.0  # Alert on 2%+ moves
        self.watched_tickers = set()

    def add_watched_ticker(self, ticker: str, alert_threshold_pct: float = 2.0):
        """
        Add ticker to watchlist with alert threshold.

        Args:
            ticker: Stock ticker
            alert_threshold_pct: Percentage move to trigger alert
        """
        self.watched_tickers.add(ticker.upper())

    def check_for_alerts(self) -> List[Dict]:
        """
        Check all watched tickers for alert conditions.

        Returns:
            List of active alerts
        """
        new_alerts = []

        for ticker in self.watched_tickers:
            momentum = self.monitor.get_current_price_momentum(ticker)
            if momentum and abs(momentum['price_change_pct']) > self.alert_threshold_pct:
                alert = {
                    'ticker': ticker,
                    'type': 'price_move',
                    'severity': 'high' if abs(momentum['price_change_pct']) > 5 else 'medium',
                    'price_change_pct': momentum['price_change_pct'],
                    'current_price': momentum['current_price'],
                    'timestamp': datetime.now().isoformat(),
                }
                new_alerts.append(alert)

            # Check for technical signals
            signals = self.monitor.detect_price_action_signals(ticker)
            if signals and (signals['breakout_high'] or signals['breakout_low']):
                alert = {
                    'ticker': ticker,
                    'type': 'breakout',
                    'direction': 'up' if signals['breakout_high'] else 'down',
                    'current_price': momentum['current_price'] if momentum else None,
                    'timestamp': datetime.now().isoformat(),
                }
                new_alerts.append(alert)

        self.alerts = new_alerts
        return new_alerts


# Global instance
_monitor_instance = None


def get_intraday_monitor(interval: str = "5m") -> IntradayMonitor:
    """Get singleton instance of intraday monitor."""
    global _monitor_instance
    if _monitor_instance is None:
        _monitor_instance = IntradayMonitor(interval=interval)
    return _monitor_instance


if __name__ == "__main__":
    monitor = get_intraday_monitor('5m')

    # Test with AAPL
    ticker = "AAPL"
    print(f"\n=== Testing Intraday Monitoring for {ticker} ===")

    print(f"\nFetching 5-minute data...")
    data = monitor.fetch_intraday_data(ticker, '5m')
    if data is not None:
        print(f"✓ Got {len(data)} data points")
        print(f"Latest price: ${data['Close'].iloc[-1]:.2f}")
    else:
        print(f"✗ No data available")

    print(f"\nPrice momentum:")
    momentum = monitor.get_current_price_momentum(ticker)
    if momentum:
        print(f"  Current: ${momentum['current_price']:.2f}")
        print(f"  Change: {momentum['price_change_pct']:.2f}%")
        print(f"  Trend: {momentum['trend']}")
        print(f"  RSI: {momentum['rsi']:.1f}")
    else:
        print("  No momentum data")

    print(f"\nPrice action signals:")
    signals = monitor.detect_price_action_signals(ticker)
    if signals:
        print(f"  Breakout High: {signals['breakout_high']}")
        print(f"  Breakout Low: {signals['breakout_low']}")
        print(f"  Reversal: {signals['reversal_pattern']}")
        print(f"  Volume Spike: {signals['volume_spike']}")
    else:
        print("  No signals detected")

    # Test alert system
    print(f"\n\nTesting Alert System:")
    alert_system = IntradayAlertSystem(monitor)
    alert_system.add_watched_ticker(ticker, alert_threshold_pct=0.5)
    alerts = alert_system.check_for_alerts()
    print(f"Active alerts: {len(alerts)}")
    for alert in alerts:
        print(f"  - {alert}")
