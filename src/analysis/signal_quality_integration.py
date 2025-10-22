"""
Signal Quality Integration - Hooks signal quality enhancer into trade signal workflow.

This module provides the integration layer between the signal quality enhancer
and the existing conviction scoring system, allowing for gradual rollout of improvements.
"""

from typing import Dict, List, Optional
from datetime import datetime
from loguru import logger

from src.analysis.signal_quality_enhancer import get_signal_quality_enhancer, SignalQualityScore


class SignalQualityIntegrator:
    """Integrates signal quality enhancer into existing signal flow."""

    def __init__(self, enable_by_default: bool = True):
        """
        Initialize integrator.

        Args:
            enable_by_default: Whether to apply quality enhancements by default
        """
        self.enhancer = get_signal_quality_enhancer()
        self.enabled = enable_by_default
        logger.info(f"Signal Quality Integrator initialized (enabled={enable_by_default})")

    def enhance_conviction_signal(
        self,
        ticker: str,
        original_conviction: float,
        conviction_details: Dict,
        transaction: Dict,
        apply_enhancements: Optional[bool] = None
    ) -> Dict:
        """
        Apply signal quality enhancements to a conviction score.

        Args:
            ticker: Stock ticker
            original_conviction: Original conviction score (0-1)
            conviction_details: Details from conviction scorer
            transaction: Original transaction data
            apply_enhancements: Override enable flag (None = use self.enabled)

        Returns:
            Dict with enhanced conviction and analysis
        """
        if apply_enhancements is None:
            apply_enhancements = self.enabled

        if not apply_enhancements:
            # Return original without enhancements
            return {
                'ticker': ticker,
                'conviction_score': original_conviction,
                'original_conviction': original_conviction,
                'quality_enhanced': False,
                'conviction_details': conviction_details,
            }

        try:
            # Extract transaction details
            insider_name = transaction.get('insider_name', 'Unknown')
            insider_title = transaction.get('insider_title', 'Unknown')
            transaction_value = transaction.get('total_value', 0)
            transaction_date = transaction.get('transaction_date', datetime.now())
            insider_names = transaction.get('insider_names', [insider_name])

            # Apply signal quality enhancements
            quality_score = self.enhancer.enhance_signal_quality(
                ticker=ticker,
                original_conviction=original_conviction,
                insider_name=insider_name,
                insider_title=insider_title,
                transaction_value=transaction_value,
                transaction_date=transaction_date,
                insider_names=insider_names,
            )

            # Build enhanced result
            enhanced_signal = {
                'ticker': ticker,
                'conviction_score': quality_score.enhanced_conviction,
                'original_conviction': original_conviction,
                'quality_enhanced': True,
                'signal_tier': quality_score.signal_tier,
                'quality_analysis': quality_score.to_dict(),
                'issues_detected': quality_score.issues_detected,
                'recommendations': quality_score.recommendations,
                'conviction_details': conviction_details,
            }

            logger.info(
                f"{ticker}: Signal enhanced {original_conviction:.3f} -> "
                f"{quality_score.enhanced_conviction:.3f} ({quality_score.signal_tier})"
            )

            return enhanced_signal

        except Exception as e:
            logger.error(f"Error enhancing conviction for {ticker}: {e}")
            # Return original on error
            return {
                'ticker': ticker,
                'conviction_score': original_conviction,
                'original_conviction': original_conviction,
                'quality_enhanced': False,
                'error': str(e),
                'conviction_details': conviction_details,
            }

    def filter_low_quality_signals(
        self,
        signals: List[Dict],
        min_tier_threshold: str = "MODERATE"
    ) -> List[Dict]:
        """
        Filter out low-quality signals based on tier classification.

        Args:
            signals: List of trade signals
            min_tier_threshold: Minimum tier to keep (ULTRA_HIGH, HIGH, MODERATE, LOW)

        Returns:
            Filtered list of signals
        """
        tier_rankings = {
            'ULTRA_HIGH': 4,
            'HIGH': 3,
            'MODERATE': 2,
            'LOW': 1,
        }

        min_ranking = tier_rankings.get(min_tier_threshold, 2)
        filtered = []

        for signal in signals:
            tier = signal.get('signal_tier', 'LOW')
            tier_ranking = tier_rankings.get(tier, 0)

            if tier_ranking >= min_ranking:
                filtered.append(signal)
            else:
                logger.debug(
                    f"Filtered {signal.get('ticker', 'unknown')}: "
                    f"Tier {tier} below threshold {min_tier_threshold}"
                )

        return filtered

    def generate_quality_report(
        self,
        signals: List[Dict]
    ) -> str:
        """
        Generate readable report of signal quality analysis.

        Args:
            signals: List of signals with quality analysis

        Returns:
            Formatted report string
        """
        lines = []
        lines.append("\n" + "=" * 100)
        lines.append("SIGNAL QUALITY ANALYSIS REPORT")
        lines.append("=" * 100)

        # Group by tier
        by_tier = {}
        for signal in signals:
            tier = signal.get('signal_tier', 'UNKNOWN')
            if tier not in by_tier:
                by_tier[tier] = []
            by_tier[tier].append(signal)

        # Report each tier
        for tier in ['ULTRA_HIGH', 'HIGH', 'MODERATE', 'LOW']:
            if tier in by_tier:
                tier_signals = by_tier[tier]
                lines.append(f"\n{tier} ({len(tier_signals)} signals):")
                lines.append("-" * 100)

                for sig in tier_signals[:5]:  # Show top 5
                    ticker = sig.get('ticker', '?')
                    original = sig.get('original_conviction', 0)
                    enhanced = sig.get('conviction_score', 0)
                    improvement = enhanced / max(original, 0.01)

                    lines.append(
                        f"  {ticker:<6} "
                        f"Original: {original:.3f} → Enhanced: {enhanced:.3f} "
                        f"({improvement:.1%} improvement)"
                    )

                    # Show key issues
                    issues = sig.get('issues_detected', [])
                    if issues:
                        for issue in issues[:2]:
                            lines.append(f"           ⚠️  {issue}")

        lines.append("\n" + "=" * 100)
        return "\n".join(lines)


def get_signal_quality_integrator(enable_by_default: bool = True) -> SignalQualityIntegrator:
    """Get signal quality integrator instance."""
    return SignalQualityIntegrator(enable_by_default=enable_by_default)


if __name__ == "__main__":
    integrator = get_signal_quality_integrator()

    # Example: Enhance a signal
    result = integrator.enhance_conviction_signal(
        ticker="AAPL",
        original_conviction=0.72,
        conviction_details={'source': 'insider_accumulation'},
        transaction={
            'ticker': 'AAPL',
            'insider_name': 'Tim Cook',
            'insider_title': 'CEO',
            'total_value': 5_000_000,
            'transaction_date': datetime.now(),
        }
    )

    print(f"Enhanced Signal: {result['conviction_score']:.3f}")
    print(f"Tier: {result.get('signal_tier', 'N/A')}")
    print(f"Recommendations: {result.get('recommendations', [])}")
