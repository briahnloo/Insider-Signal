"""Master conviction scoring engine."""
from typing import Dict
from datetime import datetime
from loguru import logger

from src.analysis.filing_speed import calculate_filing_speed_multiplier
from src.analysis.short_interest import ShortInterestAnalyzer
from src.analysis.accumulation import AccumulationDetector
from src.analysis.red_flags import RedFlagDetector


class ConvictionScorer:
    """Combines all signals into final conviction score (0-1.0)."""

    def __init__(self):
        self.si_analyzer = ShortInterestAnalyzer()
        self.accumulation_detector = AccumulationDetector()
        self.red_flag_detector = RedFlagDetector()

    def calculate_conviction_score(
        self,
        ticker: str,
        filing_speed_days: int,
        insider_name: str = None,
        transaction_date: datetime = None,
    ) -> Dict:
        """
        Calculate comprehensive conviction score.

        Weights:
        - Filing speed: 40%
        - Short interest: 30%
        - Accumulation: 20%
        - Red flags: 10%

        Args:
            ticker: Stock ticker
            filing_speed_days: Days from transaction to filing
            insider_name: Name of insider (optional)
            transaction_date: Date of transaction (optional)

        Returns:
            Dict with conviction score and component breakdown
        """
        scores = {}
        components = {}

        try:
            # 1. Filing Speed (40% weight)
            fs_mult = calculate_filing_speed_multiplier(filing_speed_days)
            fs_signal = min(fs_mult / 1.4, 1.0)  # Normalize to 0-1
            scores['filing_speed'] = fs_signal
            components['filing_speed'] = {
                'multiplier': fs_mult,
                'normalized_score': fs_signal,
                'weight': 0.40,
            }

            # 2. Short Interest (30% weight)
            squeeze_mult, si_details = self.si_analyzer.calculate_squeeze_potential(
                ticker
            )
            si_signal = min((squeeze_mult - 1.0) / 0.5, 1.0)  # Normalize 1.0-1.5 to 0-1
            scores['short_interest'] = si_signal
            components['short_interest'] = {
                'multiplier': squeeze_mult,
                'normalized_score': si_signal,
                'weight': 0.30,
                'details': si_details,
            }

            # 3. Accumulation (20% weight)
            accum = self.accumulation_detector.detect_multi_insider_accumulation(
                ticker, window_days=14
            )
            accum_mult = accum.get('multiplier', 1.0)
            accum_signal = min((accum_mult - 1.0) / 0.5, 1.0)  # Normalize to 0-1
            scores['accumulation'] = accum_signal
            components['accumulation'] = {
                'multiplier': accum_mult,
                'normalized_score': accum_signal,
                'weight': 0.20,
                'details': accum,
            }

            # 4. Red Flags (10% weight - acts as penalty)
            red_flags = {}
            if transaction_date:
                red_flags = self.red_flag_detector.detect_all_flags(
                    ticker, transaction_date
                )
            penalty_mult = red_flags.get('penalty_multiplier', 1.0)
            red_flag_signal = penalty_mult  # Direct penalty
            scores['red_flags'] = red_flag_signal
            components['red_flags'] = {
                'multiplier': penalty_mult,
                'normalized_score': red_flag_signal,
                'weight': 0.10,
                'details': red_flags,
            }

            # Calculate weighted conviction score
            conviction_score = (
                scores['filing_speed'] * 0.40
                + scores['short_interest'] * 0.30
                + scores['accumulation'] * 0.20
                + scores['red_flags'] * 0.10
            )

            # Apply multipliers as final adjustment
            final_score = conviction_score * (
                fs_mult * 0.3 + squeeze_mult * 0.3 + accum_mult * 0.2 + penalty_mult * 0.2
            )
            final_score = min(max(final_score, 0.0), 1.0)  # Clamp 0-1

            logger.info(
                f"{ticker}: Conviction score {final_score:.3f} "
                f"(FS={fs_signal:.2f}, SI={si_signal:.2f}, "
                f"Accum={accum_signal:.2f}, Flags={red_flag_signal:.2f})"
            )

            return {
                'ticker': ticker,
                'conviction_score': final_score,
                'component_scores': scores,
                'components': components,
                'signal_strength': self._signal_strength(final_score),
            }

        except Exception as e:
            logger.error(f"Error calculating conviction for {ticker}: {e}")
            return {
                'ticker': ticker,
                'conviction_score': 0.0,
                'error': str(e),
                'signal_strength': 'error',
            }

    def _signal_strength(self, score: float) -> str:
        """Categorize signal strength."""
        if score >= 0.80:
            return 'very_strong'
        elif score >= 0.65:
            return 'strong'
        elif score >= 0.50:
            return 'moderate'
        elif score >= 0.35:
            return 'weak'
        else:
            return 'very_weak'

    def batch_score(self, transactions: list) -> list:
        """
        Score multiple transactions.

        Args:
            transactions: List of transaction dicts

        Returns:
            List of scored transactions
        """
        scored = []
        for trans in transactions:
            score = self.calculate_conviction_score(
                ticker=trans.get('ticker'),
                filing_speed_days=trans.get('filing_speed_days', 2),
                insider_name=trans.get('insider_name'),
                transaction_date=trans.get('transaction_date'),
            )
            scored.append({**trans, **score})

        return scored


if __name__ == "__main__":
    scorer = ConvictionScorer()

    # Test transaction
    test_trans = {
        'ticker': 'AAPL',
        'filing_speed_days': 0,
        'insider_name': 'Tim Cook',
        'transaction_date': datetime.now(),
    }

    result = scorer.calculate_conviction_score(
        test_trans['ticker'],
        test_trans['filing_speed_days'],
        test_trans['insider_name'],
        test_trans['transaction_date'],
    )

    print(f"\nConviction Score: {result['conviction_score']:.3f}")
    print(f"Signal Strength: {result['signal_strength']}")
    print(f"\nComponents:")
    for component, data in result['component_scores'].items():
        print(f"  {component}: {data:.2f}")
