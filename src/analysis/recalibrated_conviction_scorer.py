"""
RECALIBRATED Conviction Scorer - Aggressive filtering with proper discrimination.

Key changes:
1. Default optional sources to 0.0 (not available), not 0.5 (neutral)
2. Make filing speed much more aggressive (0.2x for slow, 1.0x for fast)
3. Require strong evidence for high scores (no default boosts)
4. Harsh red flag penalties (-30% to -50% reduction)
5. Remove the final multiplier boost that masks weak signals
6. Use absolute threshold - conviction MUST earn high scores
"""

from typing import Dict, Optional, Tuple
from datetime import datetime
from loguru import logger


class RecalibratedConvictionScorer:
    """Recalibrated scorer with harsh filtering and proper discrimination."""

    def __init__(self):
        """Initialize with data sources."""
        logger.info("Recalibrated Conviction Scorer initialized (aggressive mode)")

    def calculate_recalibrated_conviction(
        self,
        ticker: str,
        filing_speed_days: int = 2,
        has_multi_insider: bool = False,
        insider_count: int = 1,
        has_short_squeeze: bool = False,
        short_interest_pct: float = 0.0,
        has_red_flags: bool = False,
        red_flag_count: int = 0,
        earnings_positive: bool = False,
        news_sentiment_score: float = 0.0,
    ) -> Dict:
        """
        Calculate conviction with aggressive thresholds.

        Args:
            ticker: Stock ticker
            filing_speed_days: Days from transaction to filing (0-7+)
            has_multi_insider: Multiple insiders buying
            insider_count: Number of insiders
            has_short_squeeze: High short interest present
            short_interest_pct: Short interest percentage
            has_red_flags: Any red flags present
            red_flag_count: Number of red flags
            earnings_positive: Company has positive earnings
            news_sentiment_score: News sentiment (-1 to 1)

        Returns:
            Dict with recalibrated conviction and components
        """
        components = {}

        # ===== CORE COMPONENTS (much more strict) =====

        # 1. FILING SPEED (30% weight) - Much more aggressive
        #    0 days: 1.0x (same day filing = extremely bullish)
        #    1 day:  0.8x (next day)
        #    2 days: 0.6x (deadline)
        #    3+ days: 0.2x (late filing, suspicious)
        filing_mult_map = {0: 1.0, 1: 0.8, 2: 0.6, 3: 0.3, 4: 0.25, 5: 0.2, 6: 0.15, 7: 0.1}
        filing_mult = filing_mult_map.get(min(filing_speed_days, 7), 0.1)
        filing_score = filing_mult  # Direct use, no normalization
        components['filing_speed'] = {
            'score': filing_score,
            'multiplier': filing_mult,
            'weight': 0.30,
            'days': filing_speed_days,
        }

        # 2. ACCUMULATION PATTERN (20% weight)
        #    Single insider: 0.0 (no signal)
        #    2 insiders: 0.5 (some signal)
        #    3+ insiders: 1.0 (strong signal)
        if insider_count >= 3:
            accum_score = 1.0
            accum_detail = '3+ insiders'
        elif insider_count == 2:
            accum_score = 0.5
            accum_detail = '2 insiders'
        else:
            accum_score = 0.0
            accum_detail = 'single insider'

        components['accumulation'] = {
            'score': accum_score,
            'weight': 0.20,
            'insider_count': insider_count,
            'detail': accum_detail,
        }

        # 3. SHORT SQUEEZE POTENTIAL (15% weight)
        #    No short interest: 0.0
        #    <10% SI: 0.3
        #    10-20% SI: 0.7
        #    >20% SI: 1.0
        if short_interest_pct < 0.5:
            si_score = 0.0
            si_detail = 'minimal SI'
        elif short_interest_pct < 10:
            si_score = 0.3
            si_detail = f'{short_interest_pct:.1f}% SI'
        elif short_interest_pct < 20:
            si_score = 0.7
            si_detail = f'{short_interest_pct:.1f}% SI'
        else:
            si_score = 1.0
            si_detail = f'{short_interest_pct:.1f}% SI (high)'

        components['short_interest'] = {
            'score': si_score,
            'weight': 0.15,
            'short_interest_pct': short_interest_pct,
            'detail': si_detail,
        }

        # 4. RED FLAGS (15% weight) - HARSH PENALTY
        #    0 flags: 1.0 (no penalty)
        #    1 flag:  0.7 (-30% penalty)
        #    2 flags: 0.5 (-50% penalty)
        #    3+ flags: 0.2 (-80% penalty, nearly disqualifies)
        flag_penalty_map = {0: 1.0, 1: 0.7, 2: 0.5, 3: 0.2}
        flag_penalty = flag_penalty_map.get(min(red_flag_count, 3), 0.1)
        components['red_flags'] = {
            'penalty': flag_penalty,
            'weight': 0.15,
            'flag_count': red_flag_count,
            'detail': f'{red_flag_count} red flags' if red_flag_count > 0 else 'no flags',
        }

        # 5. FUNDAMENTALS (10% weight)
        #    Positive earnings: 1.0
        #    Negative earnings: 0.3 (much lower)
        fundamental_score = 1.0 if earnings_positive else 0.3
        components['fundamentals'] = {
            'score': fundamental_score,
            'weight': 0.10,
            'earnings_positive': earnings_positive,
        }

        # 6. NEWS SENTIMENT (10% weight)
        #    Only count if strong signal present
        #    Normalize to 0-1 range
        news_score = max(0, news_sentiment_score)  # Only positive sentiment counts
        components['news_sentiment'] = {
            'score': news_score,
            'weight': 0.10,
            'raw_sentiment': news_sentiment_score,
        }

        # ===== CALCULATE WEIGHTED CONVICTION =====

        conviction_score = (
            filing_score * 0.30
            + accum_score * 0.20
            + si_score * 0.15
            + fundamental_score * 0.10
            + news_score * 0.10
        )

        # ===== APPLY RED FLAG PENALTY (multiplicative) =====
        conviction_score = conviction_score * flag_penalty

        # Clamp to 0-1
        conviction_score = max(0.0, min(1.0, conviction_score))

        # ===== DETERMINE TIER =====
        if conviction_score >= 0.85:
            tier = 'STRONG_BUY'
        elif conviction_score >= 0.75:
            tier = 'BUY'
        elif conviction_score >= 0.65:
            tier = 'ACCUMULATE'
        elif conviction_score >= 0.50:
            tier = 'WATCH'
        else:
            tier = 'SKIP'

        return {
            'ticker': ticker,
            'conviction_score': conviction_score,
            'tier': tier,
            'components': components,
            'flag_penalty': flag_penalty,
        }


def get_recalibrated_scorer() -> RecalibratedConvictionScorer:
    """Get recalibrated scorer instance."""
    return RecalibratedConvictionScorer()
