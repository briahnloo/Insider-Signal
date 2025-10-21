"""Master trade signal orchestration."""
from typing import Dict, List
from datetime import datetime
from loguru import logger
from rich.console import Console
from rich.table import Table

from src.analysis.conviction_scorer import ConvictionScorer
from src.data_collection.corporate_actions import CorporateActionsScanner
from src.data_collection.activist_tracker import ActivistTracker
from src.execution.entry_timing import EntryTimer
from src.execution.position_sizing import PositionSizer

try:
    from src.execution.pairs_trading import PairsTradeGenerator
    PAIRS_AVAILABLE = True
except:
    PAIRS_AVAILABLE = False

console = Console()


class TradeSignalEngine:
    """Orchestrates all analysis into final trade signals."""

    def __init__(self, account_value: float = 100000):
        self.conviction_scorer = ConvictionScorer()
        self.corporate_actions = CorporateActionsScanner()
        self.activist_tracker = ActivistTracker()
        self.entry_timer = EntryTimer()
        self.position_sizer = PositionSizer(account_value=account_value)
        self.pairs_generator = PairsTradeGenerator() if PAIRS_AVAILABLE else None

    def generate_trade_signal(self, transaction: Dict) -> Dict:
        """
        Generate complete trade signal from insider transaction.

        Args:
            transaction: Dict with insider transaction data

        Returns:
            Dict with full trade recommendation
        """
        ticker = transaction.get('ticker')
        logger.info(f"Generating trade signal for {ticker}")

        try:
            # 1. Calculate conviction
            conviction_result = self.conviction_scorer.calculate_conviction_score(
                ticker=ticker,
                filing_speed_days=transaction.get('filing_speed_days', 2),
                insider_name=transaction.get('insider_name'),
                transaction_date=transaction.get('transaction_date'),
            )

            conviction_score = conviction_result.get('conviction_score', 0)

            # Check if conviction is high enough to proceed
            if conviction_score < 0.45:
                return {
                    'ticker': ticker,
                    'signal': 'SKIP',
                    'reason': f'Low conviction ({conviction_score:.2f})',
                    'conviction_score': conviction_score,
                }

            # 2. Check for corporate actions
            corp_mult, corp_details = self.corporate_actions.calculate_corporate_action_multiplier(
                ticker
            )

            # 3. Check for activist involvement
            activist_mult, activist_details = self.activist_tracker.calculate_activist_multiplier(
                ticker
            )

            # 4. Determine entry timing
            entry_strategy = self.entry_timer.determine_entry_strategy(
                ticker, conviction_score
            )

            current_price = entry_strategy.get('current_price', 0)

            # 5. Calculate position sizing
            position_sizing = self.position_sizer.calculate_position_size(
                conviction_score=conviction_score,
                price=current_price,
                catalyst_date=False,
            )

            # 6. Check for pairs trading opportunities (Phase 4)
            pairs_opportunities = []
            hedges = []
            if PAIRS_AVAILABLE and self.pairs_generator and conviction_score >= 0.60:
                pairs_data = self.pairs_generator.find_pairs_opportunities(ticker)
                pairs_opportunities = pairs_data.get('pairs_opportunities', [])
                hedges = self.pairs_generator.generate_hedge_trades(
                    ticker, long_conviction=conviction_score
                ).get('hedges', [])

            # Determine signal strength
            if conviction_score >= 0.85:
                signal = 'STRONG_BUY'
            elif conviction_score >= 0.75:
                signal = 'BUY'
            elif conviction_score >= 0.60:
                signal = 'WEAK_BUY'
            else:
                signal = 'NEUTRAL'

            final_signal = {
                'timestamp': datetime.now(),
                'ticker': ticker,
                'signal': signal,
                'conviction_score': conviction_score,
                'conviction_components': conviction_result.get('component_scores', {}),
                'insider_info': {
                    'name': transaction.get('insider_name'),
                    'title': transaction.get('insider_title'),
                    'shares': transaction.get('shares'),
                    'amount': transaction.get('total_value'),
                    'filing_speed_days': transaction.get('filing_speed_days'),
                },
                'entry': {
                    'strategy': entry_strategy.get('strategy'),
                    'reason': entry_strategy.get('reason'),
                    'current_price': current_price,
                    'wait_days': entry_strategy.get('wait_days', 0),
                },
                'position': {
                    'shares': position_sizing.get('shares'),
                    'size_pct': position_sizing.get('position_size_pct'),
                    'entry_price': position_sizing.get('entry_price'),
                    'stop_loss': position_sizing.get('stop_loss_price'),
                    'risk_amount': position_sizing.get('total_risk'),
                },
                'catalysts': {
                    'corporate_actions_multiplier': corp_mult,
                    'activist_involvement': activist_mult > 1.0,
                },
                'pairs_trading': {
                    'opportunities': pairs_opportunities,
                    'best_pair': pairs_opportunities[0] if pairs_opportunities else None,
                    'hedges': hedges,
                    'total_hedges': len(hedges),
                } if pairs_opportunities or hedges else None,
                'ready_for_entry': entry_strategy.get('ready', True),
            }

            logger.info(f"Signal for {ticker}: {signal} (Score: {conviction_score:.3f})")

            return final_signal

        except Exception as e:
            logger.error(f"Error generating signal for {ticker}: {e}")
            return {
                'ticker': ticker,
                'signal': 'ERROR',
                'error': str(e),
            }

    def batch_generate_signals(self, transactions: List[Dict]) -> List[Dict]:
        """
        Generate signals for multiple transactions.

        Args:
            transactions: List of insider transactions

        Returns:
            List of trade signals
        """
        signals = []
        for trans in transactions:
            signal = self.generate_trade_signal(trans)
            signals.append(signal)

        # Sort by conviction score
        signals.sort(
            key=lambda x: x.get('conviction_score', 0),
            reverse=True
        )

        return signals

    def display_signals(self, signals: List[Dict], top_n: int = 10):
        """Display trade signals in formatted table."""
        # Filter valid signals
        valid_signals = [s for s in signals if s.get('signal') != 'ERROR']

        if not valid_signals:
            console.print("[yellow]No valid signals generated[/yellow]")
            return

        # Create table
        table = Table(title=f"Trade Signals (Top {min(top_n, len(valid_signals))})")
        table.add_column("Ticker", style="cyan")
        table.add_column("Signal", style="green")
        table.add_column("Score", justify="right", style="magenta")
        table.add_column("Conviction", style="yellow")
        table.add_column("Entry", style="blue")
        table.add_column("Position", justify="right", style="white")
        table.add_column("Risk", justify="right", style="red")

        for sig in valid_signals[:top_n]:
            ticker = sig.get('ticker', 'N/A')
            signal = sig.get('signal', 'N/A')
            score = sig.get('conviction_score', 0)
            conviction_comp = sig.get('conviction_components', {})
            filing_speed = conviction_comp.get('filing_speed', 0)
            si = conviction_comp.get('short_interest', 0)
            accum = conviction_comp.get('accumulation', 0)

            conviction_str = (
                f"FS:{filing_speed:.2f} SI:{si:.2f} A:{accum:.2f}"
            )

            entry_strat = sig.get('entry', {}).get('strategy', 'N/A')
            position_info = sig.get('position', {})
            shares = position_info.get('shares', 0)
            size_pct = position_info.get('size_pct', 0)

            risk = position_info.get('risk_amount', 0)

            table.add_row(
                ticker,
                signal,
                f"{score:.3f}",
                conviction_str,
                entry_strat,
                f"{shares} @ {size_pct:.1f}%",
                f"${risk:,.0f}",
            )

        console.print(table)

    def get_top_signals(self, signals: List[Dict], n: int = 5) -> List[Dict]:
        """Get top N signals by conviction."""
        valid = [s for s in signals if s.get('signal') != 'ERROR']
        return sorted(
            valid,
            key=lambda x: x.get('conviction_score', 0),
            reverse=True
        )[:n]


if __name__ == "__main__":
    engine = TradeSignalEngine(account_value=100000)

    # Test transaction
    test_transaction = {
        'ticker': 'AAPL',
        'insider_name': 'Tim Cook',
        'insider_title': 'CEO',
        'shares': 10000,
        'total_value': 1500000,
        'filing_speed_days': 0,
        'transaction_date': datetime.now(),
    }

    signal = engine.generate_trade_signal(test_transaction)

    console.print(f"\n[bold]Trade Signal for {signal['ticker']}[/bold]")
    console.print(f"Signal: {signal['signal']}")
    console.print(f"Conviction Score: {signal['conviction_score']:.3f}")
    console.print(f"Entry Strategy: {signal['entry']['strategy']}")
    console.print(f"Position Size: {signal['position']['size_pct']:.2f}%")
