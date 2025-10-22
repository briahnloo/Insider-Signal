"""
Exit timing and strategy logic for managing trade exits.

This module implements a sophisticated multi-signal exit strategy that considers:
- Profit taking at optimal levels (risk-reward targets)
- Stop losses on technical breaks
- Time-based exits after insider selling or catalysts
- Technical exit signals (support breaks, pattern completions)
- Insider selling activity (negative signals)

Exit Strategy Philosophy:
- Maximize profits by exiting winners near resistance or targets
- Minimize losses by exiting broken trades with defined risk
- Protect gains with trailing stops
- Harvest profits from insider momentum plays (typically 1-6 months)
"""

from typing import Dict, List, Optional, Tuple
from datetime import datetime, timedelta
from dataclasses import dataclass
from enum import Enum
from loguru import logger
import yfinance as yf
import pandas as pd
from functools import lru_cache


class ExitSignal(Enum):
    """Exit signal categories."""
    STOP_LOSS = "STOP_LOSS"  # Hard stop on technical break
    PROFIT_TAKE = "PROFIT_TAKE"  # Take profits at target
    TECHNICAL_EXIT = "TECHNICAL_EXIT"  # Technical breakdown signal
    TIME_EXIT = "TIME_EXIT"  # Exit after time target reached
    INSIDER_SELL = "INSIDER_SELL"  # Insider selling activity detected
    CATALYST_COMPLETE = "CATALYST_COMPLETE"  # Catalyst event completed
    CONVICTION_DROP = "CONVICTION_DROP"  # Conviction score deteriorated


@dataclass
class ExitRecommendation:
    """Exit recommendation with reasoning."""
    ticker: str
    signal_type: ExitSignal
    urgency: str  # IMMEDIATE, HIGH, MEDIUM, LOW
    exit_price: float  # Recommended exit price
    current_price: float  # Current price
    profit_target: Optional[float]  # If profit-taking
    stop_loss: Optional[float]  # If using stop
    reason: str  # Human-readable explanation
    confidence: float  # Confidence 0-1
    days_held: int  # Days since entry (if known)
    suggested_action: str  # "EXIT_NOW", "EXIT_SOON", "EXIT_ON_STRENGTH", "HOLD"


class ExitManager:
    """
    Sophisticated exit management system.

    Implements a risk-managed exit strategy that:
    1. Takes profits at calculated targets (R:R based)
    2. Protects against losses with tight stops
    3. Exits on insider selling activity
    4. Recognizes technical failures
    5. Harvests gains from temporary momentum
    """

    def __init__(self):
        """Initialize exit manager."""
        self.exit_strategies = {
            'aggressive': 'Take profits quickly, tight stops (for momentum plays)',
            'balanced': 'Balanced profit-taking and stop losses',
            'conservative': 'Wait for targets, wider stops (for conviction plays)',
            'trailing': 'Use trailing stops to capture full moves',
            'time_based': 'Exit after catalyst window closes',
        }

        # Historical exit performance tracking
        self.exit_history: List[Dict] = []
        self.win_rate_by_exit = {}
        self.avg_profit_by_exit = {}

    def determine_exit_strategy(
        self,
        ticker: str,
        entry_price: float,
        conviction_score: float,
        entry_date: datetime,
        insider_name: str = "Unknown",
        current_price: Optional[float] = None,
        risk_tolerance: str = "balanced"  # aggressive, balanced, conservative
    ) -> Dict:
        """
        Determine comprehensive exit strategy for a position.

        Args:
            ticker: Stock ticker
            entry_price: Entry price when purchased
            conviction_score: Initial conviction score (0-1)
            entry_date: When position was entered
            insider_name: Name of insider for context
            current_price: Current price (fetched if None)
            risk_tolerance: Risk tolerance level

        Returns:
            Dict with exit strategy, targets, and signals
        """
        if current_price is None:
            try:
                stock = yf.Ticker(ticker)
                current_price = stock.info.get('currentPrice', stock.history(period='1d')['Close'].iloc[-1])
            except:
                current_price = entry_price

        logger.info(f"Determining exit strategy for {ticker} (Entry: ${entry_price:.2f}, Current: ${current_price:.2f})")

        current_return = (current_price - entry_price) / entry_price
        days_held = (datetime.now() - entry_date).days

        try:
            # Get technical data for analysis
            technical_data = self._analyze_technicals(ticker)
            insider_sells = self._check_insider_selling(ticker)

            # Calculate exit targets and stops
            profit_targets = self._calculate_profit_targets(
                entry_price, conviction_score, risk_tolerance
            )
            stop_levels = self._calculate_stop_losses(
                entry_price, conviction_score, risk_tolerance, technical_data
            )

            # Generate exit signals
            exit_signals = self._generate_exit_signals(
                ticker=ticker,
                entry_price=entry_price,
                current_price=current_price,
                current_return=current_return,
                conviction_score=conviction_score,
                days_held=days_held,
                technical_data=technical_data,
                insider_sells=insider_sells,
                profit_targets=profit_targets,
                stop_levels=stop_levels,
                risk_tolerance=risk_tolerance
            )

            # Determine primary exit signal (highest urgency)
            primary_signal = max(exit_signals, key=lambda x: self._urgency_value(x['urgency'])) if exit_signals else None

            return {
                'ticker': ticker,
                'entry_price': entry_price,
                'current_price': current_price,
                'current_return': current_return,
                'current_return_pct': f"{current_return * 100:+.2f}%",
                'days_held': days_held,
                'conviction_score': conviction_score,
                'profit_targets': profit_targets,
                'stop_levels': stop_levels,
                'exit_signals': exit_signals,
                'primary_signal': primary_signal,
                'suggested_action': self._determine_action(primary_signal, exit_signals, current_return),
                'strategy': self._select_strategy(conviction_score, days_held, current_return, insider_sells),
            }

        except Exception as e:
            logger.error(f"Error determining exit strategy: {e}")
            return {
                'ticker': ticker,
                'entry_price': entry_price,
                'current_price': current_price,
                'error': str(e),
                'suggested_action': 'HOLD',
            }

    def _analyze_technicals(self, ticker: str) -> Dict:
        """Analyze technical indicators for exit signals."""
        try:
            stock = yf.Ticker(ticker)
            hist = stock.history(period='90d')

            if len(hist) < 20:
                return {'insufficient_data': True}

            # Calculate key technical indicators
            close = hist['Close']
            volume = hist['Volume']

            # Moving averages
            ma20 = close.rolling(20).mean().iloc[-1]
            ma50 = close.rolling(50).mean().iloc[-1]
            current_price = close.iloc[-1]

            # Support and resistance
            high_90d = close.max()
            low_90d = close.min()
            support = low_90d
            resistance = high_90d

            # Volume analysis
            avg_volume_20d = volume.tail(20).mean()
            current_volume = volume.iloc[-1]
            volume_surge = current_volume > (avg_volume_20d * 1.5)

            # Momentum
            rsi_14 = self._calculate_rsi(close, 14)
            macd_line, signal_line, macd_histogram = self._calculate_macd(close)

            # Trend
            price_vs_ma20 = (current_price - ma20) / ma20
            price_vs_ma50 = (current_price - ma50) / ma50

            return {
                'current_price': current_price,
                'ma20': ma20,
                'ma50': ma50,
                'support': support,
                'resistance': resistance,
                'price_vs_ma20': price_vs_ma20,
                'price_vs_ma50': price_vs_ma50,
                'rsi': rsi_14,
                'macd_histogram': macd_histogram,
                'volume_surge': volume_surge,
                'avg_volume': avg_volume_20d,
                'current_volume': current_volume,
            }

        except Exception as e:
            logger.warning(f"Error analyzing technicals for {ticker}: {e}")
            return {'error': str(e)}

    def _calculate_profit_targets(
        self, entry_price: float, conviction_score: float, risk_tolerance: str
    ) -> Dict[str, float]:
        """
        Calculate profit-taking targets based on risk-reward analysis.

        Strategy:
        - High conviction: 2:1 risk-reward (20% target for 10% stop)
        - Medium conviction: 1.5:1 risk-reward (15% target)
        - Low conviction: 1:1 risk-reward (10% target)

        Insider trading historical patterns show:
        - 30-50% of trades show +10-15% in first month
        - 40-60% show +5-10% within 2 weeks
        - Volatility highest in first 1-3 months
        """
        if conviction_score >= 0.75:
            # High conviction: shoot for larger gains
            targets = {
                'aggressive': entry_price * 1.08,  # 8% quick take
                'standard': entry_price * 1.15,  # 15% target
                'extended': entry_price * 1.25,  # 25% extended hold
            }
        elif conviction_score >= 0.60:
            # Moderate conviction: balanced targets
            targets = {
                'aggressive': entry_price * 1.05,  # 5% quick take
                'standard': entry_price * 1.10,  # 10% target
                'extended': entry_price * 1.18,  # 18% extended
            }
        else:
            # Low conviction: conservative targets
            targets = {
                'aggressive': entry_price * 1.03,  # 3% quick take
                'standard': entry_price * 1.07,  # 7% target
                'extended': entry_price * 1.12,  # 12% extended
            }

        # Adjust for risk tolerance
        if risk_tolerance == 'aggressive':
            # Push targets higher, take bigger risks
            targets = {k: v * 1.1 for k, v in targets.items()}
        elif risk_tolerance == 'conservative':
            # Lower targets, tighter risk
            targets = {k: v * 0.95 for k, v in targets.items()}

        return targets

    def _calculate_stop_losses(
        self, entry_price: float, conviction_score: float, risk_tolerance: str, technical_data: Dict
    ) -> Dict[str, float]:
        """
        Calculate intelligent stop-loss levels.

        Strategy:
        - High conviction: wider stops (10% below entry) - allows volatility
        - Medium conviction: medium stops (7% below entry)
        - Low conviction: tight stops (4% below entry) - quick exit on failure
        - Technical stops: Use MA20 or recent support
        """
        # Base stop levels by conviction
        if conviction_score >= 0.75:
            # High conviction: can tolerate more volatility
            base_stop = entry_price * 0.90
            tech_stop = entry_price * 0.88
        elif conviction_score >= 0.60:
            # Moderate conviction
            base_stop = entry_price * 0.93
            tech_stop = entry_price * 0.91
        else:
            # Low conviction: tight stops
            base_stop = entry_price * 0.96
            tech_stop = entry_price * 0.94

        # Use technical levels if available
        if 'support' in technical_data and not technical_data.get('insufficient_data'):
            support = technical_data['support']
            ma20 = technical_data.get('ma20', entry_price)
            # Use support or MA20 whichever is higher (less likely to trigger falsely)
            tech_stop = max(support, ma20) * 0.99

        stops = {
            'hard_stop': base_stop,  # Hard exit if hit
            'technical_stop': tech_stop,  # Exit if key level breaks
            'trailing_10': entry_price * 0.97,  # Trailing stop (tighter)
        }

        # Adjust for risk tolerance
        if risk_tolerance == 'aggressive':
            # Tighter stops to preserve capital
            stops = {k: v * 1.02 for k, v in stops.items()}
        elif risk_tolerance == 'conservative':
            # Wider stops for conviction
            stops = {k: v * 0.98 for k, v in stops.items()}

        return stops

    def _generate_exit_signals(
        self,
        ticker: str,
        entry_price: float,
        current_price: float,
        current_return: float,
        conviction_score: float,
        days_held: int,
        technical_data: Dict,
        insider_sells: Dict,
        profit_targets: Dict,
        stop_levels: Dict,
        risk_tolerance: str
    ) -> List[Dict]:
        """Generate all applicable exit signals for the position."""
        signals = []

        # Signal 1: PROFIT TAKING
        if current_return >= (profit_targets['aggressive'] - entry_price) / entry_price:
            signals.append({
                'signal_type': ExitSignal.PROFIT_TAKE,
                'urgency': 'HIGH',
                'exit_price': current_price,
                'profit_target': profit_targets['standard'],
                'stop_loss': None,
                'reason': 'Aggressive target hit (+5-8%)',
                'confidence': 0.9,
                'suggested_action': 'CONSIDER_TAKING_PROFITS',
            })

        if current_return >= (profit_targets['standard'] - entry_price) / entry_price:
            signals.append({
                'signal_type': ExitSignal.PROFIT_TAKE,
                'urgency': 'MEDIUM',
                'exit_price': current_price,
                'profit_target': profit_targets['standard'],
                'stop_loss': stop_levels['hard_stop'],
                'reason': f'Standard profit target hit ({(profit_targets["standard"] - entry_price) / entry_price * 100:.1f}%)',
                'confidence': 0.95,
                'suggested_action': 'TAKE_PROFITS_OR_TIGHTEN_STOP',
            })

        # Signal 2: STOP LOSS
        if current_price <= stop_levels['hard_stop']:
            signals.append({
                'signal_type': ExitSignal.STOP_LOSS,
                'urgency': 'IMMEDIATE',
                'exit_price': stop_levels['hard_stop'],
                'profit_target': None,
                'stop_loss': stop_levels['hard_stop'],
                'reason': f'Hard stop loss hit (-{(1 - current_price / entry_price) * 100:.1f}%)',
                'confidence': 0.99,
                'suggested_action': 'EXIT_IMMEDIATELY',
            })

        # Signal 3: TECHNICAL EXIT
        if 'support' in technical_data and current_price < technical_data['support'] * 0.99:
            signals.append({
                'signal_type': ExitSignal.TECHNICAL_EXIT,
                'urgency': 'HIGH',
                'exit_price': current_price,
                'profit_target': None,
                'stop_loss': technical_data['support'],
                'reason': 'Key support level broken - downside momentum',
                'confidence': 0.85,
                'suggested_action': 'EXIT_ON_WEAKNESS',
            })

        if 'rsi' in technical_data and technical_data['rsi'] > 85:
            signals.append({
                'signal_type': ExitSignal.TECHNICAL_EXIT,
                'urgency': 'MEDIUM',
                'exit_price': current_price,
                'profit_target': profit_targets['standard'],
                'stop_loss': None,
                'reason': 'RSI overbought (>85) - potential reversal',
                'confidence': 0.7,
                'suggested_action': 'CONSIDER_TAKING_PROFITS',
            })

        # Signal 4: TIME-BASED EXIT
        # Insider trading catalysts typically play out over 1-6 months
        catalyst_window_days = 90
        if days_held > catalyst_window_days:
            signals.append({
                'signal_type': ExitSignal.TIME_EXIT,
                'urgency': 'LOW',
                'exit_price': current_price,
                'profit_target': profit_targets['standard'],
                'stop_loss': None,
                'reason': f'Catalyst window closing ({days_held} days held, typical 60-90 day window)',
                'confidence': 0.6,
                'suggested_action': 'EXIT_ON_STRENGTH',
            })

        # Signal 5: INSIDER SELLING
        if insider_sells.get('recent_sells', 0) > 0:
            sell_intensity = insider_sells.get('sell_intensity', 0)
            if sell_intensity >= 'HIGH':
                signals.append({
                    'signal_type': ExitSignal.INSIDER_SELL,
                    'urgency': 'HIGH',
                    'exit_price': current_price,
                    'profit_target': None,
                    'stop_loss': stop_levels['hard_stop'],
                    'reason': f'Insider selling detected - possible profit taking by insiders',
                    'confidence': 0.85,
                    'suggested_action': 'EXIT_SOON',
                })

        # Signal 6: CONVICTION DROP
        if conviction_score < 0.50:
            signals.append({
                'signal_type': ExitSignal.CONVICTION_DROP,
                'urgency': 'MEDIUM',
                'exit_price': current_price,
                'profit_target': None,
                'stop_loss': None,
                'reason': f'Conviction score declined to {conviction_score:.2f}',
                'confidence': 0.75,
                'suggested_action': 'EXIT_SOON',
            })

        return signals

    def _check_insider_selling(self, ticker: str) -> Dict:
        """Check for insider selling activity (negative signal)."""
        try:
            # This would integrate with real insider data
            # For now, return placeholder
            return {
                'recent_sells': 0,
                'sell_intensity': 'LOW',
                'last_sell_days_ago': None,
            }
        except:
            return {}

    @staticmethod
    def _calculate_rsi(prices, period=14):
        """Calculate RSI indicator."""
        try:
            deltas = prices.diff()
            seed = deltas[:period+1]
            up = seed[seed >= 0].sum() / period
            down = -seed[seed < 0].sum() / period
            rs = up / down
            rsi = 100. - 100. / (1. + rs)

            # Smooth with EMA
            rsi_values = [100. - 100. / (1. + up / down)]
            for i in range(period + 1, len(prices)):
                delta = deltas.iloc[i]
                if delta > 0:
                    up = (up * (period - 1) + delta) / period
                    down = (down * (period - 1)) / period
                else:
                    up = (up * (period - 1)) / period
                    down = (down * (period - 1) + -delta) / period
                rs = up / down
                rsi_values.append(100. - 100. / (1. + rs))

            return rsi_values[-1]
        except:
            return 50.0

    @staticmethod
    def _calculate_macd(prices, fast=12, slow=26, signal=9):
        """Calculate MACD indicator."""
        try:
            exp1 = prices.ewm(span=fast).mean()
            exp2 = prices.ewm(span=slow).mean()
            macd_line = exp1 - exp2
            signal_line = macd_line.ewm(span=signal).mean()
            macd_histogram = macd_line - signal_line

            return macd_line.iloc[-1], signal_line.iloc[-1], macd_histogram.iloc[-1]
        except:
            return 0, 0, 0

    @staticmethod
    def _urgency_value(urgency: str) -> int:
        """Convert urgency string to numeric value for sorting."""
        urgency_map = {'IMMEDIATE': 4, 'HIGH': 3, 'MEDIUM': 2, 'LOW': 1}
        return urgency_map.get(urgency, 0)

    def _determine_action(self, primary_signal: Optional[Dict], all_signals: List[Dict], current_return: float) -> str:
        """Determine primary recommended action."""
        if not primary_signal:
            return 'HOLD'

        urgency = primary_signal['urgency']
        signal_type = primary_signal['signal_type']

        if urgency == 'IMMEDIATE':
            return 'EXIT_IMMEDIATELY'
        elif urgency == 'HIGH':
            if signal_type == ExitSignal.PROFIT_TAKE and current_return > 0.05:
                return 'TAKE_PROFITS'
            else:
                return 'EXIT_SOON'
        elif urgency == 'MEDIUM':
            return 'MONITOR_CLOSELY'
        else:
            return 'HOLD'

    def _select_strategy(self, conviction_score: float, days_held: int, current_return: float, insider_sells: Dict) -> str:
        """Select exit strategy based on position characteristics."""
        if conviction_score >= 0.75:
            if days_held > 60:
                return 'trailing'  # Trail profits on conviction plays
            else:
                return 'balanced'
        elif conviction_score >= 0.60:
            return 'balanced'
        else:
            return 'conservative'


def get_exit_manager() -> ExitManager:
    """Factory function to get ExitManager instance."""
    return ExitManager()
