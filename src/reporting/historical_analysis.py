"""Historical backtest analysis on conviction scoring."""
from typing import Dict, List
from datetime import datetime, timedelta
import pandas as pd
from loguru import logger

from src.database import get_recent_transactions
from src.analysis.conviction_scorer import ConvictionScorer


class HistoricalAnalyzer:
    """Analyzes historical transactions for conviction scoring validation."""

    def __init__(self):
        self.scorer = ConvictionScorer()

    def backtest_conviction_scoring(self, days_back: int = 180) -> Dict:
        """
        Backtest conviction scoring on historical data.

        Args:
            days_back: Days of historical data to analyze

        Returns:
            Dict with backtest results
        """
        try:
            # Get historical transactions
            df = get_recent_transactions(days=days_back, min_value=50000)

            if df.empty:
                logger.warning("No historical data for backtest")
                return {
                    'transactions_analyzed': 0,
                    'error': 'No data available',
                }

            logger.info(f"Backtesting on {len(df)} transactions")

            # Score each transaction
            scores = []
            for _, row in df.iterrows():
                score_result = self.scorer.calculate_conviction_score(
                    ticker=row['ticker'],
                    filing_speed_days=row['filing_speed_days'],
                    insider_name=row['insider_name'],
                    transaction_date=row['transaction_date'],
                )

                score_result['transaction'] = {
                    'ticker': row['ticker'],
                    'total_value': row['total_value'],
                    'filing_date': row['filing_date'],
                }

                scores.append(score_result)

            # Analyze distribution
            conviction_scores = [s['conviction_score'] for s in scores]

            distribution = {
                'mean': sum(conviction_scores) / len(conviction_scores),
                'median': sorted(conviction_scores)[len(conviction_scores) // 2],
                'min': min(conviction_scores),
                'max': max(conviction_scores),
                'std_dev': self._std_dev(conviction_scores),
            }

            # Categorize signals
            very_strong = sum(1 for s in conviction_scores if s >= 0.80)
            strong = sum(1 for s in conviction_scores if 0.65 <= s < 0.80)
            moderate = sum(1 for s in conviction_scores if 0.50 <= s < 0.65)
            weak = sum(1 for s in conviction_scores if 0.35 <= s < 0.50)
            very_weak = sum(1 for s in conviction_scores if s < 0.35)

            results = {
                'backtest_period_days': days_back,
                'transactions_analyzed': len(df),
                'conviction_distribution': distribution,
                'signal_breakdown': {
                    'very_strong (0.80+)': very_strong,
                    'strong (0.65-0.80)': strong,
                    'moderate (0.50-0.65)': moderate,
                    'weak (0.35-0.50)': weak,
                    'very_weak (<0.35)': very_weak,
                },
                'high_conviction_threshold': 0.65,
                'actionable_signals': very_strong + strong,
                'actionable_pct': (very_strong + strong) / len(df) * 100,
            }

            logger.info(
                f"Backtest: {very_strong + strong} high-conviction signals "
                f"({results['actionable_pct']:.1f}%)"
            )

            return results

        except Exception as e:
            logger.error(f"Error in backtest: {e}")
            return {'error': str(e)}

    def _std_dev(self, values: List[float]) -> float:
        """Calculate standard deviation."""
        if len(values) < 2:
            return 0
        mean = sum(values) / len(values)
        variance = sum((x - mean) ** 2 for x in values) / len(values)
        return variance ** 0.5

    def analyze_by_ticker(self, ticker: str, days_back: int = 180) -> Dict:
        """
        Analyze conviction scoring for a specific ticker.

        Args:
            ticker: Stock ticker
            days_back: Historical period

        Returns:
            Dict with ticker analysis
        """
        try:
            df = get_recent_transactions(days=days_back, min_value=50000)

            if df.empty:
                return {'ticker': ticker, 'transactions': 0}

            ticker_df = df[df['ticker'] == ticker.upper()]

            if ticker_df.empty:
                return {'ticker': ticker, 'transactions': 0}

            # Score each transaction
            scores = []
            for _, row in ticker_df.iterrows():
                score = self.scorer.calculate_conviction_score(
                    ticker=row['ticker'],
                    filing_speed_days=row['filing_speed_days'],
                )
                scores.append(score['conviction_score'])

            avg_score = sum(scores) / len(scores) if scores else 0

            return {
                'ticker': ticker,
                'transactions': len(ticker_df),
                'avg_conviction_score': avg_score,
                'insider_count': ticker_df['insider_name'].nunique(),
                'total_investment': ticker_df['total_value'].sum(),
                'avg_transaction': ticker_df['total_value'].mean(),
                'conviction_scores': scores,
            }

        except Exception as e:
            logger.error(f"Error analyzing {ticker}: {e}")
            return {'ticker': ticker, 'error': str(e)}

    def find_top_scoring_candidates(
        self, days_back: int = 30, min_conviction: float = 0.75
    ) -> List[Dict]:
        """
        Find top conviction scoring opportunities.

        Args:
            days_back: Recent period to analyze
            min_conviction: Minimum conviction threshold

        Returns:
            List of high-conviction transactions
        """
        try:
            df = get_recent_transactions(days=days_back, min_value=50000)

            if df.empty:
                return []

            candidates = []

            for _, row in df.iterrows():
                score_result = self.scorer.calculate_conviction_score(
                    ticker=row['ticker'],
                    filing_speed_days=row['filing_speed_days'],
                    insider_name=row['insider_name'],
                    transaction_date=row['transaction_date'],
                )

                conviction = score_result.get('conviction_score', 0)

                if conviction >= min_conviction:
                    candidates.append({
                        'ticker': row['ticker'],
                        'insider': row['insider_name'],
                        'conviction_score': conviction,
                        'amount': row['total_value'],
                        'filing_speed_days': row['filing_speed_days'],
                        'filing_date': row['filing_date'],
                    })

            # Sort by conviction
            candidates.sort(
                key=lambda x: x['conviction_score'],
                reverse=True
            )

            logger.info(
                f"Found {len(candidates)} candidates with "
                f"conviction >= {min_conviction}"
            )

            return candidates

        except Exception as e:
            logger.error(f"Error finding candidates: {e}")
            return []


if __name__ == "__main__":
    analyzer = HistoricalAnalyzer()

    # Run backtest
    backtest = analyzer.backtest_conviction_scoring(days_back=30)
    print(f"\nBacktest Results:")
    print(f"  Transactions: {backtest['transactions_analyzed']}")
    print(f"  Actionable: {backtest['actionable_signals']} "
          f"({backtest['actionable_pct']:.1f}%)")

    # Find top candidates
    candidates = analyzer.find_top_scoring_candidates(
        days_back=30, min_conviction=0.65
    )
    print(f"\nTop Candidates ({len(candidates)}):")
    for cand in candidates[:5]:
        print(f"  {cand['ticker']}: {cand['conviction_score']:.3f}")
