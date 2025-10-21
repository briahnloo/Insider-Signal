"""Filing speed multiplier calculation."""
from datetime import datetime
from typing import Dict
from loguru import logger


def calculate_filing_speed_multiplier(filing_speed_days: int) -> float:
    """
    Calculate multiplier based on filing speed.

    Args:
        filing_speed_days: Days from transaction to filing

    Returns:
        Multiplier 0.7x to 1.4x
    """
    if filing_speed_days == 0:
        return 1.4  # Same day - very bullish
    elif filing_speed_days == 1:
        return 1.2  # Next day - bullish
    elif filing_speed_days == 2:
        return 1.0  # Meets deadline
    else:
        return 0.7  # Late filing - weak signal


def analyze_filing_speed_distribution(filing_speeds: list) -> Dict:
    """Analyze distribution of filing speeds."""
    if not filing_speeds:
        return {}

    distribution = {
        'same_day': sum(1 for x in filing_speeds if x == 0),
        'next_day': sum(1 for x in filing_speeds if x == 1),
        'deadline': sum(1 for x in filing_speeds if x == 2),
        'late': sum(1 for x in filing_speeds if x > 2),
    }

    total = len(filing_speeds)
    distribution['same_day_pct'] = distribution['same_day'] / total * 100
    distribution['next_day_pct'] = distribution['next_day'] / total * 100

    return distribution


if __name__ == "__main__":
    print(f"0 days: {calculate_filing_speed_multiplier(0)}x")
    print(f"1 day: {calculate_filing_speed_multiplier(1)}x")
    print(f"2 days: {calculate_filing_speed_multiplier(2)}x")
    print(f"3+ days: {calculate_filing_speed_multiplier(3)}x")
