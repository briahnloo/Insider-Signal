"""Entry timing logic based on technical analysis."""
from typing import Dict, Literal
from datetime import datetime
from loguru import logger
import yfinance as yf


class EntryTimer:
    """Determines optimal entry points based on volume and price action."""

    def __init__(self):
        self.entry_strategies = {
            'immediate': 'Buy on news immediately',
            'pullback': 'Wait for 3-5% pullback for better entry',
            'support': 'Enter on key support level',
            'breakout': 'Enter on breakout above resistance',
            'delay': 'Wait for confirmation before entering',
        }

    def determine_entry_strategy(
        self, ticker: str, conviction_score: float
    ) -> Dict:
        """
        Determine entry strategy based on conviction and technicals.

        Args:
            ticker: Stock ticker
            conviction_score: Conviction score (0-1)

        Returns:
            Dict with entry strategy and timing
        """
        try:
            stock = yf.Ticker(ticker)
            hist = stock.history(period='60d')

            if len(hist) < 10:
                return {
                    'ticker': ticker,
                    'strategy': 'insufficient_data',
                    'reason': 'Not enough historical data',
                    'wait_days': 0,
                }

            # Calculate technical indicators
            avg_volume_30d = hist['Volume'].tail(30).mean()
            current_price = hist['Close'].iloc[-1]
            high_52w = hist['Close'].max()
            low_52w = hist['Close'].min()
            price_position = (current_price - low_52w) / (high_52w - low_52w)

            # Determine strategy based on conviction and price position
            if conviction_score >= 0.80:
                # High conviction - buy on any pullback
                if price_position > 0.80:
                    strategy = 'pullback'
                    reason = 'High conviction, stock near highs - wait for pullback'
                    wait_days = 2
                else:
                    strategy = 'immediate'
                    reason = 'High conviction, good entry point'
                    wait_days = 0

            elif conviction_score >= 0.65:
                # Moderate-High - wait for support
                if price_position > 0.75:
                    strategy = 'support'
                    reason = 'Moderate conviction, identify key support'
                    wait_days = 3
                else:
                    strategy = 'immediate'
                    reason = 'Moderate conviction, reasonable entry'
                    wait_days = 1

            elif conviction_score >= 0.50:
                # Moderate - wait for confirmation
                strategy = 'delay'
                reason = 'Moderate conviction, wait for confirmation'
                wait_days = 5

            else:
                strategy = 'delay'
                reason = 'Low conviction, high risk'
                wait_days = 7

            return {
                'ticker': ticker,
                'strategy': strategy,
                'reason': reason,
                'wait_days': wait_days,
                'current_price': current_price,
                'price_position': price_position,
                'avg_volume_30d': avg_volume_30d,
                'conviction_score': conviction_score,
            }

        except Exception as e:
            logger.error(f"Error determining entry strategy for {ticker}: {e}")
            return {
                'ticker': ticker,
                'strategy': 'error',
                'reason': str(e),
                'wait_days': 0,
            }

    def calculate_entry_price(
        self, ticker: str, strategy: str, current_price: float
    ) -> Dict:
        """
        Calculate target entry price based on strategy.

        Args:
            ticker: Stock ticker
            strategy: Entry strategy
            current_price: Current stock price

        Returns:
            Dict with entry price targets
        """
        targets = {
            'ticker': ticker,
            'strategy': strategy,
            'current_price': current_price,
        }

        if strategy == 'immediate':
            targets['primary_entry'] = current_price
            targets['limit_order'] = current_price * 1.01  # 1% above

        elif strategy == 'pullback':
            targets['primary_entry'] = current_price * 0.95  # 5% pullback
            targets['secondary_entry'] = current_price * 0.90  # 10% pullback
            targets['limit_order'] = current_price * 0.95

        elif strategy == 'support':
            targets['primary_entry'] = current_price * 0.93  # 7% pullback
            targets['limit_order'] = current_price * 0.93

        elif strategy == 'breakout':
            targets['primary_entry'] = current_price * 1.05  # 5% above
            targets['limit_order'] = current_price * 1.05

        elif strategy == 'delay':
            targets['primary_entry'] = current_price * 0.98
            targets['limit_order'] = current_price * 0.98

        else:
            targets['primary_entry'] = current_price
            targets['limit_order'] = current_price

        return targets

    def check_entry_conditions(self, ticker: str) -> Dict:
        """
        Check if all conditions are met for entry.

        Args:
            ticker: Stock ticker

        Returns:
            Dict with entry readiness and any blockers
        """
        try:
            stock = yf.Ticker(ticker)
            hist = stock.history(period='5d')

            if len(hist) < 3:
                return {
                    'ticker': ticker,
                    'ready': False,
                    'blockers': ['Insufficient recent data'],
                }

            blockers = []

            # Check for gap down (avoid buying into weak opening)
            if len(hist) >= 2:
                today_open = hist['Open'].iloc[-1]
                yesterday_close = hist['Close'].iloc[-2]
                gap_pct = ((today_open - yesterday_close) / yesterday_close) * 100

                if gap_pct < -3:
                    blockers.append(
                        f'Large gap down ({gap_pct:.1f}%) - wait for stabilization'
                    )

            # Check volume
            avg_vol = hist['Volume'].mean()
            current_vol = hist['Volume'].iloc[-1]

            if current_vol < (avg_vol * 0.5):
                blockers.append('Low volume - wait for confirmation')

            ready = len(blockers) == 0

            return {
                'ticker': ticker,
                'ready': ready,
                'blockers': blockers,
                'current_volume': current_vol,
                'avg_volume': avg_vol,
            }

        except Exception as e:
            logger.error(f"Error checking entry conditions: {e}")
            return {
                'ticker': ticker,
                'ready': False,
                'blockers': [str(e)],
            }


if __name__ == "__main__":
    timer = EntryTimer()

    # Test entry strategy
    strategy = timer.determine_entry_strategy("AAPL", conviction_score=0.75)
    print(f"Entry Strategy: {strategy['strategy']}")
    print(f"Reason: {strategy['reason']}")
    print(f"Wait Days: {strategy['wait_days']}")

    # Test entry price
    entry = timer.calculate_entry_price(
        "AAPL", strategy['strategy'], strategy.get('current_price', 150)
    )
    print(f"\nEntry Price Targets: {entry}")
