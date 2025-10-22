"""
Signal Staleness Analyzer

Calculates time-decay penalties for insider trading signals to ensure
only fresh, actionable signals receive high conviction scores.

Older signals are penalized because:
- Market conditions change over time
- Information gets priced in
- Insider knowledge becomes less relevant
"""

from typing import Tuple
from datetime import datetime
from loguru import logger

import config


def calculate_staleness_penalty(
    transaction_date: datetime,
    current_date: datetime = None
) -> Tuple[float, str, int]:
    """
    Calculate staleness penalty for signals based on transaction age.
    
    Time-decay logic:
    - 0-14 days old: 1.0x (no penalty) - FRESH
    - 15-30 days old: 0.9x (10% penalty) - RECENT  
    - 31-45 days old: 0.7x (30% penalty) - AGING
    - 46-60 days old: 0.5x (50% penalty) - STALE
    - 61+ days old: 0.3x (70% penalty) - VERY STALE
    
    Rationale:
    - Insider information loses relevance as market absorbs it
    - Market conditions change significantly over weeks/months
    - Fresh signals are more actionable than old ones
    
    Args:
        transaction_date: Date when insider made the purchase
        current_date: Reference date for staleness calculation (default: now)
        
    Returns:
        Tuple of (penalty_multiplier, staleness_category, days_old)
    """
    if current_date is None:
        current_date = datetime.now()
    
    # Handle date vs datetime
    if hasattr(transaction_date, 'date'):
        transaction_date = transaction_date.date()
    if hasattr(current_date, 'date'):
        current_date = current_date.date()
    
    # Calculate days since transaction
    days_old = (current_date - transaction_date).days
    
    # Apply time-decay penalty (updated logic)
    if days_old <= 14:
        penalty = 1.0
        category = "FRESH"
    elif days_old <= 30:
        penalty = 0.95  # -5% penalty
        category = "RECENT"
    elif days_old <= 45:
        penalty = 0.85  # -15% penalty
        category = "AGING"
    elif days_old <= 60:
        penalty = 0.70  # -30% penalty
        category = "STALE"
    else:
        penalty = 0.50  # -50% penalty
        category = "VERY STALE"
    
    logger.debug(
        f"Signal staleness: {days_old} days old → "
        f"{penalty:.1f}x penalty ({category})"
    )
    
    return penalty, category, days_old


def get_staleness_description(category: str, days_old: int) -> str:
    """
    Get human-readable description of staleness.
    
    Args:
        category: Staleness category (FRESH, RECENT, etc.)
        days_old: Age in days
        
    Returns:
        Formatted description string
    """
    descriptions = {
        "FRESH": f"Fresh signal ({days_old}d old) - highly actionable",
        "RECENT": f"Recent signal ({days_old}d old) - still relevant with slight decay",
        "AGING": f"Aging signal ({days_old}d old) - relevance declining",
        "STALE": f"Stale signal ({days_old}d old) - information likely priced in",
        "VERY STALE": f"Very stale signal ({days_old}d old) - outdated information"
    }
    
    return descriptions.get(category, f"Unknown ({days_old}d old)")


def should_filter_signal(days_old: int, max_age: int = None) -> bool:
    """
    Determine if signal should be filtered due to age.
    
    Args:
        days_old: Age of signal in days
        max_age: Maximum acceptable age (default: from config)
        
    Returns:
        True if signal should be filtered out
    """
    if max_age is None:
        max_age = config.MAX_SIGNAL_AGE_DEFAULT
    
    return days_old > max_age
