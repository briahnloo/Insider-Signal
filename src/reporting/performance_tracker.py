"""
Performance Tracker - Ongoing validation of system performance in live trading.

Monitors:
1. Signal quality metrics (conviction trends, distribution)
2. Hypothetical P&L tracking (as if we traded every signal)
3. Model drift detection (score distribution changes, win rate)
4. Component performance (correlation with winning trades)
"""

from typing import Dict, List, Optional, Tuple
from datetime import datetime, timedelta
from dataclasses import dataclass, field
import pandas as pd
import numpy as np
from loguru import logger
from pathlib import Path
import json

from src.database import Session, InsiderTransaction, get_all_recent_transactions
import config


@dataclass
class SignalTrack:
    """Track a single signal for hypothetical P&L."""
    ticker: str
    signal_date: datetime
    conviction_score: float
    entry_price: float
    current_price: Optional[float] = None
    exit_price: Optional[float] = None
    exit_date: Optional[datetime] = None
    position_size: float = 0.025  # 2.5% default
    shares: int = 0
    entry_value: float = 0.0
    current_value: float = 0.0
    exit_value: float = 0.0
    unrealized_pnl: float = 0.0
    realized_pnl: float = 0.0
    pnl_pct: float = 0.0
    hold_days: int = 0
    status: str = "OPEN"  # OPEN, CLOSED, STOPPED
    components: Dict = field(default_factory=dict)


class PerformanceTracker:
    """Tracks and validates system performance over time."""
    
    def __init__(self, data_dir: str = "data/performance"):
        """Initialize performance tracker."""
        self.data_dir = Path(data_dir)
        self.data_dir.mkdir(parents=True, exist_ok=True)
        
        self.signals_file = self.data_dir / "tracked_signals.json"
        self.metrics_file = self.data_dir / "daily_metrics.json"
        
        # Load existing tracked signals
        self.tracked_signals = self._load_tracked_signals()
        
        # Performance thresholds for alerts
        self.thresholds = {
            'min_win_rate': 0.55,
            'max_avg_conviction': 0.80,
            'min_sharpe_ratio': 0.5,
            'max_score_std_change': 0.15,
        }
        
        logger.info(f"Performance tracker initialized with {len(self.tracked_signals)} tracked signals")
    
    def _load_tracked_signals(self) -> List[SignalTrack]:
        """Load previously tracked signals from disk."""
        if not self.signals_file.exists():
            return []
        
        try:
            with open(self.signals_file, 'r') as f:
                data = json.load(f)
                signals = []
                for item in data:
                    # Convert date strings back to datetime
                    item['signal_date'] = datetime.fromisoformat(item['signal_date'])
                    if item.get('exit_date'):
                        item['exit_date'] = datetime.fromisoformat(item['exit_date'])
                    signals.append(SignalTrack(**item))
                return signals
        except Exception as e:
            logger.error(f"Error loading tracked signals: {e}")
            return []
    
    def _save_tracked_signals(self):
        """Save tracked signals to disk."""
        try:
            data = []
            for signal in self.tracked_signals:
                item = signal.__dict__.copy()
                # Convert datetime to ISO format
                item['signal_date'] = item['signal_date'].isoformat()
                if item.get('exit_date'):
                    item['exit_date'] = item['exit_date'].isoformat()
                data.append(item)
            
            with open(self.signals_file, 'w') as f:
                json.dump(data, f, indent=2)
        except Exception as e:
            logger.error(f"Error saving tracked signals: {e}")
    
    def track_new_signal(
        self,
        ticker: str,
        conviction_score: float,
        entry_price: float,
        components: Dict,
        signal_date: Optional[datetime] = None
    ) -> SignalTrack:
        """
        Start tracking a new signal for hypothetical P&L.
        
        Args:
            ticker: Stock ticker
            conviction_score: Conviction score at signal generation
            entry_price: Entry price when signal generated
            components: Component scores that made up the conviction
            signal_date: Date of signal (default: now)
            
        Returns:
            SignalTrack object
        """
        if signal_date is None:
            signal_date = datetime.now()
        
        # Calculate position size based on conviction
        position_size = self._calculate_position_size(conviction_score)
        
        # Assume $100k account
        account_value = 100000
        entry_value = account_value * position_size
        shares = int(entry_value / entry_price)
        entry_value = shares * entry_price
        
        signal = SignalTrack(
            ticker=ticker,
            signal_date=signal_date,
            conviction_score=conviction_score,
            entry_price=entry_price,
            current_price=entry_price,
            position_size=position_size,
            shares=shares,
            entry_value=entry_value,
            current_value=entry_value,
            components=components
        )
        
        self.tracked_signals.append(signal)
        self._save_tracked_signals()
        
        logger.info(f"Tracking new signal: {ticker} @ ${entry_price:.2f}, {shares} shares, conviction {conviction_score:.3f}")
        
        return signal
    
    def _calculate_position_size(self, conviction_score: float) -> float:
        """Calculate position size based on conviction score."""
        # Scale from 1.5% to 4.5% based on conviction (0.60 to 1.0)
        if conviction_score >= 0.85:
            return 0.045  # 4.5% for highest conviction
        elif conviction_score >= 0.75:
            return 0.035  # 3.5%
        elif conviction_score >= 0.65:
            return 0.025  # 2.5%
        else:
            return 0.015  # 1.5% for lower conviction
    
    def update_signal_prices(self, price_data: Dict[str, float]):
        """
        Update current prices for all open signals.
        
        Args:
            price_data: Dict of {ticker: current_price}
        """
        for signal in self.tracked_signals:
            if signal.status == "OPEN" and signal.ticker in price_data:
                signal.current_price = price_data[signal.ticker]
                signal.current_value = signal.shares * signal.current_price
                signal.unrealized_pnl = signal.current_value - signal.entry_value
                signal.pnl_pct = (signal.unrealized_pnl / signal.entry_value) * 100
                signal.hold_days = (datetime.now() - signal.signal_date).days
                
                # Close position after 30 days (our rule)
                if signal.hold_days >= 30:
                    signal.exit_price = signal.current_price
                    signal.exit_date = datetime.now()
                    signal.exit_value = signal.current_value
                    signal.realized_pnl = signal.unrealized_pnl
                    signal.unrealized_pnl = 0.0
                    signal.status = "CLOSED"
                    
                    logger.info(
                        f"Closed {signal.ticker}: {signal.realized_pnl:+.2f} "
                        f"({signal.pnl_pct:+.1f}%) after {signal.hold_days} days"
                    )
        
        self._save_tracked_signals()
    
    def get_signal_quality_metrics(
        self,
        days_back: int = 30
    ) -> Dict:
        """
        Calculate signal quality metrics for recent period.
        
        Args:
            days_back: Number of days to analyze
            
        Returns:
            Dict with signal quality metrics
        """
        cutoff_date = datetime.now() - timedelta(days=days_back)
        recent_signals = [s for s in self.tracked_signals if s.signal_date.date() >= cutoff_date.date()]
        
        if not recent_signals:
            return {
                'signals_generated': 0,
                'avg_conviction': 0.0,
                'conviction_std': 0.0,
                'conviction_min': 0.0,
                'conviction_max': 0.0,
                'conviction_distribution': {},
                'signals_by_day': [],
                'tickers': [],
            }
        
        conviction_scores = [s.conviction_score for s in recent_signals]
        
        # Score distribution
        bins = [0.0, 0.5, 0.6, 0.7, 0.8, 0.9, 1.0]
        distribution = {}
        for i in range(len(bins) - 1):
            count = sum(1 for score in conviction_scores if bins[i] <= score < bins[i+1])
            distribution[f"{bins[i]:.1f}-{bins[i+1]:.1f}"] = count
        
        # Signals by day
        signals_by_day = pd.DataFrame([{
            'date': s.signal_date.date(),
            'ticker': s.ticker,
            'conviction': s.conviction_score
        } for s in recent_signals])
        
        daily_counts = signals_by_day.groupby('date').size().to_dict()
        
        return {
            'signals_generated': len(recent_signals),
            'avg_conviction': np.mean(conviction_scores),
            'conviction_std': np.std(conviction_scores),
            'conviction_min': np.min(conviction_scores),
            'conviction_max': np.max(conviction_scores),
            'conviction_distribution': distribution,
            'signals_by_day': daily_counts,
            'tickers': list(set(s.ticker for s in recent_signals)),
        }
    
    def get_hypothetical_pnl(self) -> Dict:
        """
        Calculate hypothetical P&L from tracked signals.
        
        Returns:
            Dict with P&L metrics
        """
        open_signals = [s for s in self.tracked_signals if s.status == "OPEN"]
        closed_signals = [s for s in self.tracked_signals if s.status == "CLOSED"]
        
        # Unrealized P&L (open positions)
        total_unrealized_pnl = sum(s.unrealized_pnl for s in open_signals)
        total_entry_value = sum(s.entry_value for s in open_signals)
        unrealized_pnl_pct = (total_unrealized_pnl / total_entry_value * 100) if total_entry_value > 0 else 0
        
        # Realized P&L (closed positions)
        total_realized_pnl = sum(s.realized_pnl for s in closed_signals)
        closed_entry_value = sum(s.entry_value for s in closed_signals)
        realized_pnl_pct = (total_realized_pnl / closed_entry_value * 100) if closed_entry_value > 0 else 0
        
        # Win rate
        winners = [s for s in closed_signals if s.realized_pnl > 0]
        losers = [s for s in closed_signals if s.realized_pnl <= 0]
        win_rate = (len(winners) / len(closed_signals)) if closed_signals else 0
        
        # Sharpe ratio (simplified)
        if closed_signals:
            returns = [s.pnl_pct for s in closed_signals]
            avg_return = np.mean(returns)
            std_return = np.std(returns)
            sharpe_ratio = (avg_return / std_return) if std_return > 0 else 0
        else:
            sharpe_ratio = 0
        
        # Total P&L
        total_pnl = total_unrealized_pnl + total_realized_pnl
        
        return {
            'total_pnl': total_pnl,
            'unrealized_pnl': total_unrealized_pnl,
            'unrealized_pnl_pct': unrealized_pnl_pct,
            'realized_pnl': total_realized_pnl,
            'realized_pnl_pct': realized_pnl_pct,
            'open_positions': len(open_signals),
            'closed_positions': len(closed_signals),
            'win_rate': win_rate,
            'num_winners': len(winners),
            'num_losers': len(losers),
            'sharpe_ratio': sharpe_ratio,
            'avg_winner': np.mean([s.realized_pnl for s in winners]) if winners else 0,
            'avg_loser': np.mean([s.realized_pnl for s in losers]) if losers else 0,
            'best_trade': max([s.realized_pnl for s in closed_signals]) if closed_signals else 0,
            'worst_trade': min([s.realized_pnl for s in closed_signals]) if closed_signals else 0,
        }
    
    def detect_model_drift(
        self,
        lookback_days: int = 30,
        baseline_days: int = 90
    ) -> Dict:
        """
        Detect if model behavior has changed significantly.
        
        Args:
            lookback_days: Recent period to analyze
            baseline_days: Historical baseline period
            
        Returns:
            Dict with drift detection results and alerts
        """
        alerts = []
        
        # Get metrics for recent and baseline periods
        recent_cutoff = datetime.now() - timedelta(days=lookback_days)
        baseline_cutoff = datetime.now() - timedelta(days=baseline_days)
        
        recent_signals = [s for s in self.tracked_signals if s.signal_date >= recent_cutoff]
        baseline_signals = [
            s for s in self.tracked_signals 
            if baseline_cutoff <= s.signal_date < recent_cutoff
        ]
        
        if not recent_signals or not baseline_signals:
            return {
                'drift_detected': False,
                'alerts': ['Insufficient data for drift detection'],
                'metrics': {}
            }
        
        # 1. Check score distribution change
        recent_avg = np.mean([s.conviction_score for s in recent_signals])
        baseline_avg = np.mean([s.conviction_score for s in baseline_signals])
        recent_std = np.std([s.conviction_score for s in recent_signals])
        baseline_std = np.std([s.conviction_score for s in baseline_signals])
        
        avg_change = abs(recent_avg - baseline_avg)
        std_change = abs(recent_std - baseline_std)
        
        if avg_change > 0.10:
            alerts.append(
                f"⚠️ Conviction score mean shifted {avg_change:.3f} "
                f"({recent_avg:.3f} vs {baseline_avg:.3f} baseline)"
            )
        
        if std_change > self.thresholds['max_score_std_change']:
            alerts.append(
                f"⚠️ Score distribution changed significantly (std: {recent_std:.3f} vs {baseline_std:.3f})"
            )
        
        # 2. Check if scoring too bullish
        if recent_avg > self.thresholds['max_avg_conviction']:
            alerts.append(
                f"🚨 Average conviction too high: {recent_avg:.3f} "
                f"(threshold: {self.thresholds['max_avg_conviction']:.2f})"
            )
        
        # 3. Check win rate
        recent_closed = [s for s in recent_signals if s.status == "CLOSED"]
        if recent_closed:
            recent_win_rate = sum(1 for s in recent_closed if s.realized_pnl > 0) / len(recent_closed)
            
            if recent_win_rate < self.thresholds['min_win_rate']:
                alerts.append(
                    f"🚨 Win rate below threshold: {recent_win_rate:.1%} "
                    f"(threshold: {self.thresholds['min_win_rate']:.0%})"
                )
        
        # 4. Check Sharpe ratio
        if recent_closed and len(recent_closed) >= 5:
            returns = [s.pnl_pct for s in recent_closed]
            sharpe = (np.mean(returns) / np.std(returns)) if np.std(returns) > 0 else 0
            
            if sharpe < self.thresholds['min_sharpe_ratio']:
                alerts.append(
                    f"⚠️ Sharpe ratio below threshold: {sharpe:.2f} "
                    f"(threshold: {self.thresholds['min_sharpe_ratio']:.1f})"
                )
        
        drift_detected = len(alerts) > 0
        
        return {
            'drift_detected': drift_detected,
            'alerts': alerts,
            'metrics': {
                'recent_avg_conviction': recent_avg,
                'baseline_avg_conviction': baseline_avg,
                'avg_change': avg_change,
                'recent_std': recent_std,
                'baseline_std': baseline_std,
                'std_change': std_change,
            }
        }
    
    def analyze_component_performance(self) -> Dict:
        """
        Analyze which components correlate with winning trades.
        
        Returns:
            Dict with component performance analysis
        """
        closed_signals = [s for s in self.tracked_signals if s.status == "CLOSED"]
        
        if len(closed_signals) < 10:
            return {
                'status': 'insufficient_data',
                'message': f'Need at least 10 closed trades (have {len(closed_signals)})'
            }
        
        # Extract component scores and outcomes
        component_names = []
        if closed_signals[0].components:
            component_names = list(closed_signals[0].components.keys())
        
        if not component_names:
            return {
                'status': 'no_component_data',
                'message': 'No component data available in tracked signals'
            }
        
        correlations = {}
        recommendations = []
        
        for component in component_names:
            # Get component scores and outcomes
            scores = []
            outcomes = []
            
            for signal in closed_signals:
                if component in signal.components:
                    comp_data = signal.components[component]
                    score = comp_data.get('score', 0.5)
                    scores.append(score)
                    outcomes.append(1 if signal.realized_pnl > 0 else 0)
            
            if len(scores) >= 5:
                # Calculate correlation
                correlation = np.corrcoef(scores, outcomes)[0, 1] if len(scores) > 1 else 0
                
                correlations[component] = {
                    'correlation': correlation,
                    'avg_score_winners': np.mean([s for s, o in zip(scores, outcomes) if o == 1]) if sum(outcomes) > 0 else 0,
                    'avg_score_losers': np.mean([s for s, o in zip(scores, outcomes) if o == 0]) if sum(outcomes) < len(outcomes) else 0,
                    'sample_size': len(scores)
                }
                
                # Generate recommendations
                if correlation > 0.3:
                    recommendations.append(
                        f"✅ {component}: Strong positive correlation ({correlation:.2f}) - consider increasing weight"
                    )
                elif correlation < -0.2:
                    recommendations.append(
                        f"❌ {component}: Negative correlation ({correlation:.2f}) - consider decreasing weight or removing"
                    )
                elif abs(correlation) < 0.1:
                    recommendations.append(
                        f"⚠️ {component}: No correlation ({correlation:.2f}) - may not be predictive"
                    )
        
        return {
            'status': 'success',
            'correlations': correlations,
            'recommendations': recommendations,
            'total_closed_trades': len(closed_signals),
        }


def get_performance_tracker() -> PerformanceTracker:
    """Get singleton performance tracker instance."""
    if not hasattr(get_performance_tracker, '_instance'):
        get_performance_tracker._instance = PerformanceTracker()
    return get_performance_tracker._instance