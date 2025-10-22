"""
Adaptive Learning System for Insider Trading Intelligence.

Implements machine learning capabilities to:
1. Optimize signal weights based on historical performance
2. Recognize successful signal combinations
3. Dynamically adjust conviction thresholds
4. Learn from win/loss patterns
5. A/B test new weight combinations

Uses scikit-learn models (RandomForest, GradientBoosting) for pattern recognition.
"""

from typing import Dict, List, Optional, Tuple
from datetime import datetime, timedelta
from dataclasses import dataclass, asdict
import json
import pickle
from pathlib import Path
from loguru import logger
import pandas as pd
import numpy as np
from functools import lru_cache

try:
    from sklearn.ensemble import RandomForestRegressor, GradientBoostingRegressor
    from sklearn.preprocessing import StandardScaler
    from sklearn.model_selection import train_test_split
    from sklearn.metrics import mean_squared_error, r2_score
    SKLEARN_AVAILABLE = True
except ImportError:
    SKLEARN_AVAILABLE = False
    logger.warning("scikit-learn not available - ML features disabled")


@dataclass
class LearningMetrics:
    """Metrics from a learning iteration."""
    timestamp: datetime
    version: int
    signal_weights: Dict[str, float]
    conviction_threshold: float
    win_rate: float
    avg_return: float
    sharpe_ratio: float
    max_drawdown: float
    sample_size: int
    model_r2: float
    model_mse: float
    test_r2: float
    improvement: float  # vs previous version


@dataclass
class WeightOptimization:
    """Weight optimization result."""
    original_weights: Dict[str, float]
    optimized_weights: Dict[str, float]
    confidence: float
    improvement_potential: float
    sample_size: int
    recommendation: str


@dataclass
class TradeOutcome:
    """Historical trade outcome for learning."""
    ticker: str
    entry_date: datetime
    entry_price: float
    exit_date: Optional[datetime]
    exit_price: Optional[float]
    signals_used: Dict[str, float]  # Signal scores at entry
    conviction_score: float
    win: bool
    profit_loss_pct: float
    holding_days: int
    insider_name: str


class AdaptiveLearner:
    """
    Adaptive learning system that continuously improves signal weights.

    Learns from historical performance to:
    - Optimize individual signal weights
    - Identify best signal combinations
    - Adjust conviction thresholds dynamically
    - Detect market regime changes
    """

    def __init__(self, data_dir: str = 'data/learning'):
        """Initialize adaptive learner."""
        self.data_dir = Path(data_dir)
        self.data_dir.mkdir(parents=True, exist_ok=True)

        # Default weights (fallback if ML not available or insufficient data)
        self.default_weights = {
            'insider_cluster': 0.20,
            'filing_speed': 0.12,
            'short_interest': 0.12,
            'accumulation': 0.12,
            'options_precursor': 0.12,
            'earnings_sentiment': 0.08,
            'silence_score': 0.04,
            'network_effects': 0.10,
            'red_flags': 0.10,
        }

        # Current weights (start with defaults)
        self.current_weights = self.default_weights.copy()
        self.conviction_threshold = 0.60

        # Learning history
        self.learning_history: List[LearningMetrics] = []
        self.trade_outcomes: List[TradeOutcome] = []
        self.version = 0

        # ML Models
        self.weight_optimizer: Optional[GradientBoostingRegressor] = None
        self.scaler: Optional[StandardScaler] = None
        self.signal_patterns: Dict[str, float] = {}

        # Load existing learning data
        self._load_learning_data()

        logger.info(f"AdaptiveLearner initialized (version {self.version})")

    def record_trade_outcome(
        self,
        ticker: str,
        entry_date: datetime,
        entry_price: float,
        signals_used: Dict[str, float],
        conviction_score: float,
        insider_name: str,
        exit_price: Optional[float] = None,
        exit_date: Optional[datetime] = None,
        holding_days: int = 0
    ) -> None:
        """
        Record a completed trade for learning.

        Args:
            ticker: Stock ticker
            entry_date: Entry date
            entry_price: Entry price
            signals_used: Signal scores at entry
            conviction_score: Conviction score at entry
            insider_name: Insider name
            exit_price: Exit price (if known)
            exit_date: Exit date (if known)
            holding_days: Days held
        """
        if exit_price is None:
            exit_price = entry_price
            win = False
            profit_loss_pct = 0.0
        else:
            profit_loss_pct = (exit_price - entry_price) / entry_price
            win = profit_loss_pct > 0

        outcome = TradeOutcome(
            ticker=ticker,
            entry_date=entry_date,
            entry_price=entry_price,
            exit_date=exit_date,
            exit_price=exit_price,
            signals_used=signals_used,
            conviction_score=conviction_score,
            win=win,
            profit_loss_pct=profit_loss_pct,
            holding_days=holding_days,
            insider_name=insider_name,
        )

        self.trade_outcomes.append(outcome)
        logger.debug(f"Recorded trade outcome for {ticker}: {'WIN' if win else 'LOSS'} ({profit_loss_pct:+.2%})")

    def optimize_weights(self, min_samples: int = 30) -> Optional[WeightOptimization]:
        """
        Optimize signal weights based on historical performance.

        Uses GradientBoosting to learn which signals correlate with winning trades.

        Args:
            min_samples: Minimum trades needed to optimize

        Returns:
            WeightOptimization with new weights and metrics, or None if insufficient data
        """
        if len(self.trade_outcomes) < min_samples:
            logger.info(f"Insufficient data for weight optimization ({len(self.trade_outcomes)}/{min_samples})")
            return None

        if not SKLEARN_AVAILABLE:
            logger.warning("scikit-learn not available - cannot optimize weights")
            return None

        logger.info(f"Optimizing weights with {len(self.trade_outcomes)} trade outcomes...")

        try:
            # Prepare data
            df = self._prepare_learning_data()

            if df.shape[0] < min_samples:
                logger.warning(f"Not enough valid trades for optimization")
                return None

            # Separate features and target
            feature_cols = [col for col in df.columns if col.startswith('signal_')]
            X = df[feature_cols].values
            y = df['profit_loss_pct'].values

            # Scale features
            if self.scaler is None:
                self.scaler = StandardScaler()
            X_scaled = self.scaler.fit_transform(X)

            # Train-test split
            X_train, X_test, y_train, y_test = train_test_split(X_scaled, y, test_size=0.2, random_state=42)

            # Train GradientBoosting model
            model = GradientBoostingRegressor(
                n_estimators=100,
                learning_rate=0.1,
                max_depth=5,
                random_state=42
            )
            model.fit(X_train, y_train)

            # Evaluate
            train_r2 = model.score(X_train, y_train)
            test_r2 = model.score(X_test, y_test)
            train_mse = mean_squared_error(y_train, model.predict(X_train))
            test_mse = mean_squared_error(y_test, model.predict(X_test))

            # Extract feature importances as optimized weights
            importances = model.feature_importances_
            normalized_importances = importances / importances.sum()

            optimized_weights = {}
            for i, col in enumerate(feature_cols):
                signal_name = col.replace('signal_', '')
                optimized_weights[signal_name] = float(normalized_importances[i])

            # Calculate improvement
            current_r2 = self._evaluate_current_weights()
            improvement = test_r2 - current_r2

            # Calculate win rate
            wins = sum(1 for o in self.trade_outcomes if o.win)
            win_rate = wins / len(self.trade_outcomes)

            self.weight_optimizer = model
            self.current_weights = optimized_weights

            optimization = WeightOptimization(
                original_weights=self.default_weights.copy(),
                optimized_weights=optimized_weights,
                confidence=test_r2,
                improvement_potential=improvement,
                sample_size=len(self.trade_outcomes),
                recommendation=self._generate_recommendation(improvement, win_rate)
            )

            logger.info(f"Weight optimization complete: {improvement:+.2%} improvement potential")
            logger.info(f"New weights: {optimized_weights}")

            # Record metrics
            self._record_learning_metrics(
                win_rate=win_rate,
                model_r2=train_r2,
                test_r2=test_r2,
                model_mse=train_mse,
                improvement=improvement
            )

            self._save_learning_data()
            return optimization

        except Exception as e:
            logger.error(f"Error optimizing weights: {e}")
            return None

    def detect_pattern_combinations(self) -> Dict[str, Dict]:
        """
        Identify which signal combinations correlate with winning trades.

        Returns:
            Dict of signal combinations and their performance metrics
        """
        if len(self.trade_outcomes) < 20:
            logger.warning("Insufficient data for pattern detection")
            return {}

        patterns = {}

        # Group trades by signal combinations
        for outcome in self.trade_outcomes:
            # Create pattern signature
            pattern_key = self._create_pattern_signature(outcome.signals_used)

            if pattern_key not in patterns:
                patterns[pattern_key] = {
                    'wins': 0,
                    'losses': 0,
                    'avg_return': 0.0,
                    'signals': outcome.signals_used.copy(),
                }

            if outcome.win:
                patterns[pattern_key]['wins'] += 1
            else:
                patterns[pattern_key]['losses'] += 1

            patterns[pattern_key]['avg_return'] += outcome.profit_loss_pct

        # Calculate metrics
        for pattern_key, pattern_data in patterns.items():
            total = pattern_data['wins'] + pattern_data['losses']
            if total > 0:
                pattern_data['win_rate'] = pattern_data['wins'] / total
                pattern_data['avg_return'] /= total
            pattern_data['sample_size'] = total

        # Sort by win rate
        sorted_patterns = sorted(
            patterns.items(),
            key=lambda x: x[1]['win_rate'],
            reverse=True
        )

        # Store top patterns
        self.signal_patterns = {k: v for k, v in sorted_patterns[:10]}

        logger.info(f"Detected {len(patterns)} signal patterns, top 10 recorded")
        return dict(sorted_patterns[:20])  # Return top 20

    def adjust_conviction_threshold(self) -> float:
        """
        Dynamically adjust conviction threshold based on performance.

        Strategy:
        - If win rate > 60% at current threshold: can lower threshold (more aggressive)
        - If win rate < 50% at current threshold: should raise threshold (more conservative)
        - Target: 55-60% win rate

        Returns:
            Recommended conviction threshold
        """
        if len(self.trade_outcomes) < 20:
            return self.conviction_threshold

        # Calculate win rate in different conviction ranges
        ranges = [
            (0.50, 0.60, "low"),
            (0.60, 0.70, "medium"),
            (0.70, 0.80, "high"),
            (0.80, 1.00, "very_high"),
        ]

        range_metrics = {}
        for low, high, name in ranges:
            trades_in_range = [
                o for o in self.trade_outcomes
                if low <= o.conviction_score < high
            ]
            if trades_in_range:
                wins = sum(1 for o in trades_in_range if o.win)
                win_rate = wins / len(trades_in_range)
                range_metrics[name] = {
                    'win_rate': win_rate,
                    'sample_size': len(trades_in_range)
                }

        # Find optimal threshold
        best_threshold = self.conviction_threshold
        best_win_rate = 0.0

        for name, metrics in range_metrics.items():
            if metrics['sample_size'] >= 5 and 0.55 <= metrics['win_rate'] <= 0.65:
                # Prefer win rates in 55-65% range
                if metrics['win_rate'] > best_win_rate:
                    best_win_rate = metrics['win_rate']
                    # Map name to threshold
                    threshold_map = {
                        "low": 0.55,
                        "medium": 0.60,
                        "high": 0.70,
                        "very_high": 0.80,
                    }
                    best_threshold = threshold_map.get(name, self.conviction_threshold)

        self.conviction_threshold = best_threshold
        logger.info(f"Adjusted conviction threshold to {best_threshold:.2f} (optimal win rate: {best_win_rate:.1%})")

        return best_threshold

    def get_adaptive_weights(self) -> Dict[str, float]:
        """Get current adaptive weights (or defaults if insufficient data)."""
        # Use optimized weights if confidence is high, otherwise defaults
        if self.weight_optimizer is not None and len(self.trade_outcomes) >= 30:
            return self.current_weights
        else:
            return self.default_weights

    def get_learning_report(self) -> Dict:
        """Generate comprehensive learning report."""
        wins = sum(1 for o in self.trade_outcomes if o.win)
        total = len(self.trade_outcomes)
        win_rate = wins / total if total > 0 else 0.0

        avg_return = np.mean([o.profit_loss_pct for o in self.trade_outcomes]) if self.trade_outcomes else 0.0
        median_return = np.median([o.profit_loss_pct for o in self.trade_outcomes]) if self.trade_outcomes else 0.0

        best_trade = max(
            (o.profit_loss_pct for o in self.trade_outcomes),
            default=0.0
        )
        worst_trade = min(
            (o.profit_loss_pct for o in self.trade_outcomes),
            default=0.0
        )

        # Calculate Sharpe ratio
        if self.trade_outcomes:
            returns = [o.profit_loss_pct for o in self.trade_outcomes]
            std_dev = np.std(returns)
            sharpe = (avg_return / std_dev * np.sqrt(252)) if std_dev > 0 else 0.0
        else:
            sharpe = 0.0

        return {
            'version': self.version,
            'total_trades': total,
            'wins': wins,
            'losses': total - wins,
            'win_rate': win_rate,
            'avg_return': avg_return,
            'median_return': median_return,
            'best_trade': best_trade,
            'worst_trade': worst_trade,
            'sharpe_ratio': sharpe,
            'conviction_threshold': self.conviction_threshold,
            'current_weights': self.current_weights,
            'learning_history': [asdict(m) for m in self.learning_history[-10:]],  # Last 10
            'top_patterns': list(self.signal_patterns.keys())[:5],
        }

    def _prepare_learning_data(self) -> pd.DataFrame:
        """Prepare data for ML training."""
        data = []

        for outcome in self.trade_outcomes:
            row = {
                'profit_loss_pct': outcome.profit_loss_pct,
                'win': outcome.win,
                'holding_days': outcome.holding_days,
                'conviction_score': outcome.conviction_score,
            }

            # Add signals
            for signal_name, signal_value in outcome.signals_used.items():
                row[f'signal_{signal_name}'] = signal_value

            data.append(row)

        df = pd.DataFrame(data)
        return df

    def _evaluate_current_weights(self) -> float:
        """Evaluate R² of current weights."""
        if not self.trade_outcomes or len(self.trade_outcomes) < 10:
            return 0.0

        try:
            df = self._prepare_learning_data()
            feature_cols = [col for col in df.columns if col.startswith('signal_')]

            # Create predicted returns using current weights
            weighted_signals = np.zeros(len(df))
            for col in feature_cols:
                signal_name = col.replace('signal_', '')
                weight = self.current_weights.get(signal_name, 0.0)
                weighted_signals += df[col].values * weight

            # Calculate R²
            actual = df['profit_loss_pct'].values
            ss_res = np.sum((actual - weighted_signals) ** 2)
            ss_tot = np.sum((actual - np.mean(actual)) ** 2)
            r2 = 1 - (ss_res / ss_tot)

            return r2
        except:
            return 0.0

    def _create_pattern_signature(self, signals: Dict[str, float]) -> str:
        """Create a signature for a signal combination."""
        # Round signals to 1 decimal for pattern matching
        rounded = {k: round(v, 1) for k, v in signals.items()}
        # Sort for consistency
        sorted_items = sorted(rounded.items())
        return "_".join([f"{k}:{v}" for k, v in sorted_items])

    def _generate_recommendation(self, improvement: float, win_rate: float) -> str:
        """Generate recommendation based on improvement and win rate."""
        if improvement > 0.05 and win_rate > 0.55:
            return "STRONGLY_RECOMMENDED: Adopt new weights immediately"
        elif improvement > 0.02 and win_rate > 0.50:
            return "RECOMMENDED: Consider adopting new weights"
        elif improvement > 0:
            return "NEUTRAL: Marginal improvement, optional"
        else:
            return "NOT_RECOMMENDED: Keep existing weights"

    def _record_learning_metrics(
        self,
        win_rate: float,
        model_r2: float,
        test_r2: float,
        model_mse: float,
        improvement: float
    ) -> None:
        """Record learning metrics for history."""
        prev_improvement = 0.0
        if self.learning_history:
            prev_improvement = self.learning_history[-1].improvement

        metrics = LearningMetrics(
            timestamp=datetime.now(),
            version=self.version,
            signal_weights=self.current_weights.copy(),
            conviction_threshold=self.conviction_threshold,
            win_rate=win_rate,
            avg_return=np.mean([o.profit_loss_pct for o in self.trade_outcomes]),
            sharpe_ratio=self._calculate_sharpe(),
            max_drawdown=self._calculate_max_drawdown(),
            sample_size=len(self.trade_outcomes),
            model_r2=model_r2,
            model_mse=model_mse,
            test_r2=test_r2,
            improvement=improvement - prev_improvement,
        )

        self.learning_history.append(metrics)
        self.version += 1

    def _calculate_sharpe(self) -> float:
        """Calculate Sharpe ratio."""
        if not self.trade_outcomes:
            return 0.0

        returns = [o.profit_loss_pct for o in self.trade_outcomes]
        avg_return = np.mean(returns)
        std_dev = np.std(returns)

        if std_dev == 0:
            return 0.0

        return (avg_return / std_dev) * np.sqrt(252)

    def _calculate_max_drawdown(self) -> float:
        """Calculate maximum drawdown."""
        if not self.trade_outcomes:
            return 0.0

        cumulative = 1.0
        peak = 1.0
        max_dd = 0.0

        for outcome in sorted(self.trade_outcomes, key=lambda x: x.entry_date):
            cumulative *= (1 + outcome.profit_loss_pct)
            if cumulative > peak:
                peak = cumulative
            dd = (peak - cumulative) / peak
            max_dd = max(max_dd, dd)

        return max_dd

    def _save_learning_data(self) -> None:
        """Save learning data to disk."""
        try:
            # Save weights
            weights_file = self.data_dir / 'current_weights.json'
            with open(weights_file, 'w') as f:
                json.dump(self.current_weights, f, indent=2)

            # Save trade outcomes
            outcomes_file = self.data_dir / 'trade_outcomes.json'
            outcomes_data = [
                {
                    **asdict(o),
                    'entry_date': o.entry_date.isoformat(),
                    'exit_date': o.exit_date.isoformat() if o.exit_date else None,
                }
                for o in self.trade_outcomes
            ]
            with open(outcomes_file, 'w') as f:
                json.dump(outcomes_data, f, indent=2)

            # Save model
            if self.weight_optimizer:
                model_file = self.data_dir / 'weight_optimizer.pkl'
                with open(model_file, 'wb') as f:
                    pickle.dump(self.weight_optimizer, f)

            logger.debug("Learning data saved to disk")
        except Exception as e:
            logger.error(f"Error saving learning data: {e}")

    def _load_learning_data(self) -> None:
        """Load learning data from disk."""
        try:
            # Load weights
            weights_file = self.data_dir / 'current_weights.json'
            if weights_file.exists():
                with open(weights_file) as f:
                    self.current_weights = json.load(f)
                logger.debug("Loaded weights from disk")

            # Load model
            model_file = self.data_dir / 'weight_optimizer.pkl'
            if model_file.exists():
                with open(model_file, 'rb') as f:
                    self.weight_optimizer = pickle.load(f)
                logger.debug("Loaded model from disk")

        except Exception as e:
            logger.warning(f"Error loading learning data: {e}")


def get_adaptive_learner() -> AdaptiveLearner:
    """Factory function to get AdaptiveLearner instance."""
    return AdaptiveLearner()
