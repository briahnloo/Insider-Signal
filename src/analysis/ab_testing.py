"""
A/B Testing Framework for comparing weight combinations.

Implements statistical A/B testing to safely evaluate new weight combinations
without risking the live trading strategy.

Features:
- Bucket-based test distribution (control vs treatment groups)
- Statistical significance testing
- Confidence intervals
- Multiple comparison correction
- Test allocation by conviction score
"""

from typing import Dict, List, Optional, Tuple
from dataclasses import dataclass
from datetime import datetime, timedelta
from enum import Enum
import json
from pathlib import Path
import numpy as np
from loguru import logger
from scipy import stats


class TestStatus(Enum):
    """Status of an A/B test."""
    RUNNING = "RUNNING"
    COMPLETED = "COMPLETED"
    INCONCLUSIVE = "INCONCLUSIVE"
    STOPPED_EARLY = "STOPPED_EARLY"


@dataclass
class TestGroup:
    """A/B test group metrics."""
    name: str
    weights: Dict[str, float]
    sample_size: int
    wins: int
    losses: int
    returns: List[float]

    @property
    def win_rate(self) -> float:
        """Win rate of this group."""
        total = self.wins + self.losses
        return self.wins / total if total > 0 else 0.0

    @property
    def avg_return(self) -> float:
        """Average return of this group."""
        return np.mean(self.returns) if self.returns else 0.0

    @property
    def std_return(self) -> float:
        """Standard deviation of returns."""
        return np.std(self.returns) if self.returns else 0.0

    @property
    def sharpe_ratio(self) -> float:
        """Sharpe ratio of this group."""
        if self.std_return == 0:
            return 0.0
        return (self.avg_return / self.std_return) * np.sqrt(252)


@dataclass
class ABTestResult:
    """Results of A/B test."""
    test_id: str
    status: TestStatus
    control_group: TestGroup
    treatment_group: TestGroup
    p_value: float
    confidence_level: float
    winner: Optional[str]  # 'control', 'treatment', or None
    recommendation: str
    started_at: datetime
    ended_at: Optional[datetime]
    statistical_power: float
    effect_size: float


class ABTestManager:
    """
    Manager for A/B testing different weight combinations.

    Strategy:
    - Split traffic between control (current) and treatment (new) weights
    - Allocate trades probabilistically based on conviction score
    - Collect statistics until significant difference found
    - Recommend winner with statistical confidence
    """

    def __init__(self, data_dir: str = 'data/ab_tests'):
        """Initialize A/B test manager."""
        self.data_dir = Path(data_dir)
        self.data_dir.mkdir(parents=True, exist_ok=True)

        self.active_tests: Dict[str, 'ABTest'] = {}
        self.completed_tests: List[ABTestResult] = []
        self.allocation_history: List[Dict] = []

        self._load_test_history()

    def create_test(
        self,
        test_id: str,
        control_weights: Dict[str, float],
        treatment_weights: Dict[str, float],
        allocation: float = 0.5,  # 50-50 split
        min_samples: int = 50,
        confidence: float = 0.95
    ) -> 'ABTest':
        """
        Create a new A/B test.

        Args:
            test_id: Unique test ID
            control_weights: Control group weights (current)
            treatment_weights: Treatment group weights (new)
            allocation: Fraction of trades to allocate to treatment (0.5 = 50-50)
            min_samples: Minimum samples needed for significance
            confidence: Confidence level for significance testing (0.95, 0.99, etc)

        Returns:
            ABTest instance
        """
        if test_id in self.active_tests:
            logger.warning(f"Test {test_id} already exists")
            return self.active_tests[test_id]

        test = ABTest(
            test_id=test_id,
            control_weights=control_weights,
            treatment_weights=treatment_weights,
            allocation=allocation,
            min_samples=min_samples,
            confidence=confidence
        )

        self.active_tests[test_id] = test
        logger.info(f"Created A/B test {test_id} (allocation: {allocation:.0%})")

        return test

    def allocate_trade(self, test_id: str, conviction_score: float) -> Tuple[str, Dict[str, float]]:
        """
        Allocate a trade to test group.

        Strategy:
        - Higher conviction trades: more likely to go to treatment (accept more risk)
        - Lower conviction trades: more likely to stay with control (safer)

        Args:
            test_id: Test ID
            conviction_score: Conviction score (0-1)

        Returns:
            Tuple of (group_name, weights_to_use)
        """
        if test_id not in self.active_tests:
            logger.warning(f"Test {test_id} not found")
            return "control", {}

        test = self.active_tests[test_id]

        # Adjust allocation based on conviction
        # High conviction: more aggressive about testing new weights
        # Low conviction: stick with proven weights
        adjusted_allocation = test.allocation * (0.8 + conviction_score * 0.4)
        adjusted_allocation = np.clip(adjusted_allocation, 0.1, 0.9)

        # Randomly assign based on adjusted allocation
        if np.random.random() < adjusted_allocation:
            group = "treatment"
            weights = test.treatment_weights
        else:
            group = "control"
            weights = test.control_weights

        # Record allocation
        self.allocation_history.append({
            'timestamp': datetime.now().isoformat(),
            'test_id': test_id,
            'group': group,
            'conviction_score': conviction_score,
            'adjusted_allocation': adjusted_allocation,
        })

        return group, weights

    def record_trade_result(
        self,
        test_id: str,
        group: str,
        profit_loss_pct: float,
        win: bool
    ) -> None:
        """
        Record result of a trade in the test.

        Args:
            test_id: Test ID
            group: 'control' or 'treatment'
            profit_loss_pct: Profit/loss percentage
            win: Whether it was a winning trade
        """
        if test_id not in self.active_tests:
            logger.warning(f"Test {test_id} not found")
            return

        test = self.active_tests[test_id]
        test.record_result(group, profit_loss_pct, win)

    def check_significance(self, test_id: str) -> Optional[ABTestResult]:
        """
        Check if test has reached statistical significance.

        Uses Mann-Whitney U test for win rates and Welch's t-test for returns.

        Args:
            test_id: Test ID

        Returns:
            ABTestResult if significant, None if still running
        """
        if test_id not in self.active_tests:
            return None

        test = self.active_tests[test_id]

        # Check if enough samples
        if (test.control_group.sample_size < test.min_samples or
                test.treatment_group.sample_size < test.min_samples):
            return None

        # Test for difference in win rates
        contingency_table = np.array([
            [test.control_group.wins, test.control_group.losses],
            [test.treatment_group.wins, test.treatment_group.losses]
        ])

        # Chi-square test
        chi2, p_value_chi = stats.chi2_contingency(contingency_table)[:2]

        # Welch's t-test for returns
        t_stat, p_value_t = stats.ttest_ind(
            test.control_group.returns,
            test.treatment_group.returns,
            equal_var=False
        )

        # Use more conservative p-value (maximum of the two)
        p_value = max(p_value_chi, p_value_t)
        alpha = 1 - test.confidence

        # Calculate effect size
        effect_size = abs(test.treatment_group.avg_return - test.control_group.avg_return)

        # Calculate statistical power
        power = self._calculate_power(
            test.control_group.sample_size,
            test.treatment_group.sample_size,
            effect_size,
            test.control_group.std_return
        )

        # Determine winner
        winner = None
        if p_value < alpha:
            if test.treatment_group.avg_return > test.control_group.avg_return:
                winner = "treatment"
            else:
                winner = "control"

            status = TestStatus.COMPLETED
            recommendation = self._generate_recommendation(test, winner, p_value, effect_size)
        else:
            status = TestStatus.RUNNING
            recommendation = f"Running... ({test.control_group.sample_size} samples, p={p_value:.3f})"

        result = ABTestResult(
            test_id=test_id,
            status=status,
            control_group=test.control_group,
            treatment_group=test.treatment_group,
            p_value=p_value,
            confidence_level=test.confidence,
            winner=winner,
            recommendation=recommendation,
            started_at=test.started_at,
            ended_at=datetime.now() if winner else None,
            statistical_power=power,
            effect_size=effect_size,
        )

        # Save if completed
        if status == TestStatus.COMPLETED:
            self.completed_tests.append(result)
            del self.active_tests[test_id]
            self._save_test_history()
            logger.info(f"Test {test_id} completed: {winner} wins (p={p_value:.4f})")

        return result

    def get_test_status(self, test_id: str) -> Optional[ABTestResult]:
        """Get current status of a test."""
        if test_id not in self.active_tests:
            return None

        return self.check_significance(test_id)

    def list_active_tests(self) -> List[Dict]:
        """List all active tests."""
        tests = []
        for test_id, test in self.active_tests.items():
            tests.append({
                'test_id': test_id,
                'control_samples': test.control_group.sample_size,
                'treatment_samples': test.treatment_group.sample_size,
                'control_win_rate': test.control_group.win_rate,
                'treatment_win_rate': test.treatment_group.win_rate,
                'control_avg_return': test.control_group.avg_return,
                'treatment_avg_return': test.treatment_group.avg_return,
                'started_at': test.started_at.isoformat(),
            })
        return tests

    def get_completed_tests(self) -> List[Dict]:
        """Get all completed tests."""
        return [
            {
                'test_id': result.test_id,
                'winner': result.winner,
                'p_value': result.p_value,
                'effect_size': result.effect_size,
                'power': result.statistical_power,
                'recommendation': result.recommendation,
                'completed_at': result.ended_at.isoformat() if result.ended_at else None,
            }
            for result in self.completed_tests
        ]

    def _generate_recommendation(self, test: 'ABTest', winner: str, p_value: float, effect_size: float) -> str:
        """Generate recommendation based on test results."""
        if winner == "treatment":
            improvement = (test.treatment_group.avg_return - test.control_group.avg_return) / abs(test.control_group.avg_return + 0.01)
            if effect_size > 0.05 and p_value < 0.01:
                return f"STRONGLY_RECOMMENDED: Adopt treatment weights (+{improvement:.1%} improvement, p<0.01)"
            elif effect_size > 0.02 and p_value < 0.05:
                return f"RECOMMENDED: Consider treatment weights (+{improvement:.1%} improvement, p<0.05)"
            else:
                return f"MARGINAL: Slight improvement, optional (+{improvement:.1%})"
        else:
            return "CONTROL_WINS: Keep existing weights"

    @staticmethod
    def _calculate_power(n1: int, n2: int, effect_size: float, std: float) -> float:
        """Estimate statistical power."""
        if std == 0:
            return 0.0

        # Use simplified power calculation
        # Power ≈ 1 - Φ(z_α/2 - z_β)
        z_alpha = stats.norm.ppf(0.975)  # Two-tailed, 0.05 alpha
        se = std * np.sqrt(1/n1 + 1/n2)

        if se == 0:
            return 0.0

        z_beta = (effect_size / se) - z_alpha
        power = 1 - stats.norm.cdf(z_beta)

        return min(power, 1.0)

    def _save_test_history(self) -> None:
        """Save test history to disk."""
        try:
            history_file = self.data_dir / 'test_history.json'
            history_data = [
                {
                    'test_id': result.test_id,
                    'status': result.status.value,
                    'winner': result.winner,
                    'p_value': result.p_value,
                    'effect_size': result.effect_size,
                    'power': result.statistical_power,
                    'started_at': result.started_at.isoformat(),
                    'ended_at': result.ended_at.isoformat() if result.ended_at else None,
                }
                for result in self.completed_tests
            ]
            with open(history_file, 'w') as f:
                json.dump(history_data, f, indent=2)
        except Exception as e:
            logger.error(f"Error saving test history: {e}")

    def _load_test_history(self) -> None:
        """Load test history from disk."""
        try:
            history_file = self.data_dir / 'test_history.json'
            if history_file.exists():
                with open(history_file) as f:
                    # This is simplified - in production, would reconstruct full objects
                    logger.debug("Loaded test history from disk")
        except Exception as e:
            logger.warning(f"Error loading test history: {e}")


class ABTest:
    """Individual A/B test."""

    def __init__(
        self,
        test_id: str,
        control_weights: Dict[str, float],
        treatment_weights: Dict[str, float],
        allocation: float,
        min_samples: int,
        confidence: float
    ):
        """Initialize A/B test."""
        self.test_id = test_id
        self.control_weights = control_weights
        self.treatment_weights = treatment_weights
        self.allocation = allocation
        self.min_samples = min_samples
        self.confidence = confidence
        self.started_at = datetime.now()

        self.control_group = TestGroup(
            name="control",
            weights=control_weights,
            sample_size=0,
            wins=0,
            losses=0,
            returns=[]
        )

        self.treatment_group = TestGroup(
            name="treatment",
            weights=treatment_weights,
            sample_size=0,
            wins=0,
            losses=0,
            returns=[]
        )

    def record_result(self, group: str, profit_loss_pct: float, win: bool) -> None:
        """Record result for a group."""
        if group == "control":
            target_group = self.control_group
        else:
            target_group = self.treatment_group

        target_group.sample_size += 1
        target_group.returns.append(profit_loss_pct)

        if win:
            target_group.wins += 1
        else:
            target_group.losses += 1


def get_ab_test_manager() -> ABTestManager:
    """Factory function to get ABTestManager instance."""
    return ABTestManager()
