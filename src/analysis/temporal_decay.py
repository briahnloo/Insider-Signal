"""
Temporal Decay Weighting - Time-based signal relevance decay.

Recent signals are more valuable than old signals. This module implements
exponential and linear decay functions to reduce weight of stale data.

Example:
  - Insider buy 1 day ago: 1.0x weight
  - Insider buy 7 days ago: 0.8x weight
  - Insider buy 30 days ago: 0.4x weight
  - Insider buy 90 days ago: 0.1x weight

This prevents the system from over-weighting old news while new signals
have more immediate impact.
"""

from typing import Optional
from datetime import datetime, timedelta
from dataclasses import dataclass
from enum import Enum
import math
from loguru import logger


class DecayFunction(Enum):
    """Available decay function types."""
    LINEAR = "linear"
    EXPONENTIAL = "exponential"
    SIGMOID = "sigmoid"
    STEP = "step"


@dataclass
class DecayConfig:
    """Configuration for temporal decay."""
    # Half-life: days until weight drops to 50%
    half_life_days: float = 30.0

    # Maximum age: days after which weight is ~0
    max_age_days: float = 180.0

    # Function type
    decay_function: DecayFunction = DecayFunction.EXPONENTIAL

    # Minimum weight floor (never go below this)
    min_weight: float = 0.05

    def __post_init__(self):
        """Validate configuration."""
        if self.half_life_days <= 0:
            raise ValueError("half_life_days must be positive")
        if self.max_age_days <= 0:
            raise ValueError("max_age_days must be positive")
        if not 0 <= self.min_weight <= 1:
            raise ValueError("min_weight must be in [0, 1]")


class TemporalDecay:
    """
    Calculates decay multipliers based on time elapsed.

    Provides multiple decay strategies:
    - Exponential: Smooth, continuous decay
    - Linear: Simple proportional decay
    - Sigmoid: S-curve decay (slow at start, faster in middle, slow at end)
    - Step: Discrete decay (1.0x until threshold, then drops)
    """

    def __init__(self, config: Optional[DecayConfig] = None):
        """Initialize with optional configuration."""
        self.config = config or DecayConfig()

    def days_since(self, date: datetime) -> float:
        """Calculate days elapsed since given date."""
        return (datetime.now() - date).total_seconds() / (24 * 3600)

    def decay_multiplier(self, date: datetime) -> float:
        """
        Calculate decay multiplier for a date.

        Returns value in [min_weight, 1.0] where:
        - 1.0 = fresh (today)
        - min_weight = very old (beyond max_age_days)
        """
        days_old = self.days_since(date)

        if self.config.decay_function == DecayFunction.EXPONENTIAL:
            return self._exponential_decay(days_old)
        elif self.config.decay_function == DecayFunction.LINEAR:
            return self._linear_decay(days_old)
        elif self.config.decay_function == DecayFunction.SIGMOID:
            return self._sigmoid_decay(days_old)
        elif self.config.decay_function == DecayFunction.STEP:
            return self._step_decay(days_old)
        else:
            return 1.0

    def _exponential_decay(self, days_old: float) -> float:
        """
        Exponential decay: weight = e^(-ln(2) * days / half_life)

        This is the standard exponential decay with configurable half-life.
        """
        if days_old <= 0:
            return 1.0

        # Exponential decay formula
        decay_rate = math.log(2) / self.config.half_life_days
        weight = math.exp(-decay_rate * days_old)

        # Apply floor
        return max(self.config.min_weight, weight)

    def _linear_decay(self, days_old: float) -> float:
        """
        Linear decay: weight drops proportionally from 1.0 to min_weight.

        After max_age_days, weight stays at min_weight.
        """
        if days_old <= 0:
            return 1.0

        if days_old >= self.config.max_age_days:
            return self.config.min_weight

        # Linear interpolation
        weight_range = 1.0 - self.config.min_weight
        weight = 1.0 - (days_old / self.config.max_age_days) * weight_range

        return max(self.config.min_weight, weight)

    def _sigmoid_decay(self, days_old: float) -> float:
        """
        Sigmoid decay: S-curve decay.

        Slow decay at start (recent signals stay strong), faster in middle,
        then levels off at min_weight.
        """
        if days_old <= 0:
            return 1.0

        if days_old >= self.config.max_age_days:
            return self.config.min_weight

        # Normalize to [-5, 5] range for sigmoid
        # This gives an S-curve centered at half_life_days
        x = 10 * (days_old - self.config.half_life_days) / self.config.max_age_days
        sigmoid = 1.0 / (1.0 + math.exp(x))

        # Scale to [min_weight, 1.0]
        weight_range = 1.0 - self.config.min_weight
        weight = self.config.min_weight + sigmoid * weight_range

        return max(self.config.min_weight, weight)

    def _step_decay(self, days_old: float) -> float:
        """
        Step decay: Discrete levels.

        1.0x up to 7 days
        0.8x up to 14 days
        0.6x up to 30 days
        0.4x up to 60 days
        0.2x up to 90 days
        min_weight beyond
        """
        if days_old <= 7:
            return 1.0
        elif days_old <= 14:
            return 0.8
        elif days_old <= 30:
            return 0.6
        elif days_old <= 60:
            return 0.4
        elif days_old <= 90:
            return 0.2
        else:
            return self.config.min_weight

    def weight_score(
        self,
        score: float,
        signal_date: datetime,
        decay_function: Optional[DecayFunction] = None
    ) -> float:
        """
        Apply temporal decay to a signal score.

        Args:
            score: Original signal score [0, 1]
            signal_date: When the signal was generated
            decay_function: Override decay function (uses config default if None)

        Returns:
            Decayed score
        """
        if decay_function:
            original_config = self.config
            self.config = DecayConfig(
                half_life_days=original_config.half_life_days,
                max_age_days=original_config.max_age_days,
                decay_function=decay_function,
                min_weight=original_config.min_weight,
            )
            result = score * self.decay_multiplier(signal_date)
            self.config = original_config
            return result

        return score * self.decay_multiplier(signal_date)

    def get_decay_schedule(self, days: int = 180) -> str:
        """Generate readable decay schedule."""
        lines = []
        lines.append(f"\n{'='*70}")
        lines.append(f"TEMPORAL DECAY SCHEDULE - {self.config.decay_function.value.upper()}")
        lines.append(f"{'='*70}")
        lines.append(f"Half-life: {self.config.half_life_days} days")
        lines.append(f"Max age: {self.config.max_age_days} days")
        lines.append(f"Min weight floor: {self.config.min_weight * 100:.0f}%\n")

        lines.append(f"{'Days Ago':<15} {'Weight':<15} {'Effect':<50}")
        lines.append("-" * 70)

        # Show decay at key intervals
        intervals = [0, 1, 7, 14, 30, 60, 90, 180, 365]
        for days in intervals:
            if days > self.config.max_age_days + 30:
                break

            test_date = datetime.now() - timedelta(days=days)
            weight = self.decay_multiplier(test_date)
            weight_pct = weight * 100

            # Visual bar
            bar_length = int(weight_pct / 5)
            bar = "█" * bar_length + "░" * (20 - bar_length)

            lines.append(f"{days:<15} {weight_pct:>6.1f}% {bar:<50}")

        lines.append("=" * 70)
        return "\n".join(lines)

    def compare_decay_functions(self, signal_date: datetime) -> str:
        """Compare all decay functions for a given signal date."""
        days_old = self.days_since(signal_date)

        lines = []
        lines.append(f"\n{'='*70}")
        lines.append(f"DECAY COMPARISON - Signal from {days_old:.1f} days ago")
        lines.append(f"{'='*70}\n")

        lines.append(f"{'Function':<20} {'Weight':<15} {'Effect':<55}")
        lines.append("-" * 70)

        for func in DecayFunction:
            weight = self.decay_multiplier(signal_date) if func == self.config.decay_function else None

            if func == DecayFunction.EXPONENTIAL:
                config = DecayConfig(decay_function=DecayFunction.EXPONENTIAL)
                decay = TemporalDecay(config)
                weight = decay.decay_multiplier(signal_date)
            elif func == DecayFunction.LINEAR:
                config = DecayConfig(decay_function=DecayFunction.LINEAR)
                decay = TemporalDecay(config)
                weight = decay.decay_multiplier(signal_date)
            elif func == DecayFunction.SIGMOID:
                config = DecayConfig(decay_function=DecayFunction.SIGMOID)
                decay = TemporalDecay(config)
                weight = decay.decay_multiplier(signal_date)
            else:  # STEP
                config = DecayConfig(decay_function=DecayFunction.STEP)
                decay = TemporalDecay(config)
                weight = decay.decay_multiplier(signal_date)

            weight_pct = weight * 100
            bar_length = int(weight_pct / 5)
            bar = "█" * bar_length + "░" * (20 - bar_length)

            lines.append(f"{func.value:<20} {weight_pct:>6.1f}% {bar:<55}")

        lines.append("=" * 70)
        return "\n".join(lines)


def get_temporal_decay(
    half_life_days: float = 30.0,
    decay_function: DecayFunction = DecayFunction.EXPONENTIAL
) -> TemporalDecay:
    """Factory function to create temporal decay instance."""
    config = DecayConfig(
        half_life_days=half_life_days,
        decay_function=decay_function
    )
    return TemporalDecay(config)


# Example usage and testing
if __name__ == "__main__":
    # Create temporal decay with exponential function
    decay = get_temporal_decay(half_life_days=30, decay_function=DecayFunction.EXPONENTIAL)

    # Show decay schedule
    print(decay.get_decay_schedule())

    # Test with specific dates
    today = datetime.now()
    one_week_ago = today - timedelta(days=7)
    one_month_ago = today - timedelta(days=30)
    three_months_ago = today - timedelta(days=90)

    print(f"\nSignal from TODAY: {decay.decay_multiplier(today):.2f}x")
    print(f"Signal from 7 days ago: {decay.decay_multiplier(one_week_ago):.2f}x")
    print(f"Signal from 30 days ago: {decay.decay_multiplier(one_month_ago):.2f}x")
    print(f"Signal from 90 days ago: {decay.decay_multiplier(three_months_ago):.2f}x")

    # Apply decay to score
    original_score = 0.75
    decayed_score = decay.weight_score(original_score, one_month_ago)
    print(f"\nOriginal score: {original_score:.2f}")
    print(f"Decayed score (30 days old): {decayed_score:.2f}")

    # Compare decay functions
    print(decay.compare_decay_functions(one_month_ago))
