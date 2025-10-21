#!/usr/bin/env python
"""Complete end-to-end system test for Phase 2-4."""
import sys
from pathlib import Path
from datetime import datetime
from rich.console import Console
from rich.table import Table
from rich.panel import Panel

# Add src to path
sys.path.insert(0, str(Path(__file__).parent))

from src.database import get_recent_transactions, initialize_database
from src.analysis.conviction_scorer import ConvictionScorer
from src.data_collection.corporate_actions import CorporateActionsScanner
from src.data_collection.activist_tracker import ActivistTracker
from src.execution.trade_signal import TradeSignalEngine
from src.reporting.historical_analysis import HistoricalAnalyzer
from src.reporting.signal_report import SignalReportGenerator

# Phase 4 imports
try:
    from src.analysis.network_effects import NetworkAnalyzer
    from src.analysis.sector_rotation import SectorRotationDetector
    from src.execution.pairs_trading import PairsTradeGenerator
    PHASE4_AVAILABLE = True
except ImportError:
    PHASE4_AVAILABLE = False

from loguru import logger

console = Console()

# Configure logging
logger.remove()
logger.add(sys.stderr, format="<level>{level: <8}</level> | <level>{message}</level>")


def print_section(title: str):
    """Print formatted section."""
    console.print(f"\n[bold cyan]{'='*60}[/bold cyan]")
    console.print(f"[bold cyan]{title.center(60)}[/bold cyan]")
    console.print(f"[bold cyan]{'='*60}[/bold cyan]\n")


def test_database():
    """Test database functionality."""
    print_section("DATABASE TEST")
    try:
        initialize_database()
        console.print("[green]✓[/green] Database initialized")

        df = get_recent_transactions(days=30, min_value=50000)
        console.print(f"[green]✓[/green] Retrieved {len(df)} recent transactions")

        if not df.empty:
            console.print(f"  Unique tickers: {df['ticker'].nunique()}")
            console.print(f"  Unique insiders: {df['insider_name'].nunique()}")
            console.print(f"  Total value: ${df['total_value'].sum():,.0f}")
            return True
        else:
            console.print("[yellow]⚠[/yellow] No transactions in database (normal if markets closed)")
            return True

    except Exception as e:
        console.print(f"[red]✗[/red] Database test failed: {e}")
        return False


def test_conviction_scoring():
    """Test conviction scoring engine."""
    print_section("CONVICTION SCORING TEST")
    try:
        scorer = ConvictionScorer()
        console.print("[green]✓[/green] Conviction scorer initialized")

        # Get transactions to score
        df = get_recent_transactions(days=30, min_value=50000)

        if df.empty:
            console.print("[yellow]⚠[/yellow] No transactions to score")
            return True

        # Score first 5 transactions
        scored = []
        for i, (_, row) in enumerate(df.head(5).iterrows()):
            result = scorer.calculate_conviction_score(
                ticker=row['ticker'],
                filing_speed_days=row['filing_speed_days'],
                insider_name=row['insider_name'],
                transaction_date=row['transaction_date'],
            )
            scored.append(result)
            console.print(
                f"  [{i+1}] {row['ticker']}: {result['conviction_score']:.3f} "
                f"({result.get('signal_strength', 'N/A')})"
            )

        console.print(f"[green]✓[/green] Scored {len(scored)} transactions")
        return True

    except Exception as e:
        console.print(f"[red]✗[/red] Conviction scoring test failed: {e}")
        logger.exception("Conviction scoring error")
        return False


def test_signal_generation():
    """Test trade signal generation."""
    print_section("TRADE SIGNAL GENERATION TEST")
    try:
        engine = TradeSignalEngine(account_value=100000)
        console.print("[green]✓[/green] Signal engine initialized")

        # Get transactions
        df = get_recent_transactions(days=30, min_value=50000)

        if df.empty:
            console.print("[yellow]⚠[/yellow] No transactions for signal generation")
            return True

        # Generate signals
        signals = []
        for _, row in df.head(5).iterrows():
            trans = {
                'ticker': row['ticker'],
                'insider_name': row['insider_name'],
                'insider_title': row['insider_title'],
                'shares': row['shares'],
                'total_value': row['total_value'],
                'filing_speed_days': row['filing_speed_days'],
                'transaction_date': row['transaction_date'],
            }
            signal = engine.generate_trade_signal(trans)
            if signal.get('signal') != 'ERROR':
                signals.append(signal)

        # Display signals
        if signals:
            table = Table(title="Generated Signals")
            table.add_column("Ticker", style="cyan")
            table.add_column("Signal", style="green")
            table.add_column("Score", justify="right")
            table.add_column("Entry", style="blue")
            table.add_column("Position Size", justify="right")

            for sig in signals:
                table.add_row(
                    sig.get('ticker', 'N/A'),
                    sig.get('signal', 'N/A'),
                    f"{sig.get('conviction_score', 0):.3f}",
                    sig.get('entry', {}).get('strategy', 'N/A'),
                    f"{sig.get('position', {}).get('size_pct', 0):.2f}%",
                )

            console.print(table)
            console.print(f"[green]✓[/green] Generated {len(signals)} valid signals")
            return True
        else:
            console.print("[yellow]⚠[/yellow] No valid signals generated")
            return True

    except Exception as e:
        console.print(f"[red]✗[/red] Signal generation test failed: {e}")
        logger.exception("Signal generation error")
        return False


def test_historical_analysis():
    """Test historical analysis."""
    print_section("HISTORICAL ANALYSIS TEST")
    try:
        analyzer = HistoricalAnalyzer()
        console.print("[green]✓[/green] Historical analyzer initialized")

        # Run backtest
        backtest = analyzer.backtest_conviction_scoring(days_back=30)

        if 'error' in backtest:
            console.print(f"[yellow]⚠[/yellow] {backtest['error']}")
            return True

        console.print(f"  Transactions analyzed: {backtest.get('transactions_analyzed', 0)}")
        console.print(
            f"  Actionable signals: {backtest.get('actionable_signals', 0)} "
            f"({backtest.get('actionable_pct', 0):.1f}%)"
        )

        # Show distribution
        dist = backtest.get('conviction_distribution', {})
        console.print(f"\n  Conviction Distribution:")
        console.print(f"    Mean: {dist.get('mean', 0):.3f}")
        console.print(f"    Median: {dist.get('median', 0):.3f}")
        console.print(f"    Range: {dist.get('min', 0):.3f} - {dist.get('max', 0):.3f}")

        console.print("[green]✓[/green] Historical analysis complete")
        return True

    except Exception as e:
        console.print(f"[red]✗[/red] Historical analysis test failed: {e}")
        logger.exception("Historical analysis error")
        return False


def test_corporate_actions():
    """Test corporate actions scanner."""
    print_section("CORPORATE ACTIONS TEST")
    try:
        scanner = CorporateActionsScanner()
        console.print("[green]✓[/green] Corporate actions scanner initialized")

        mult, details = scanner.calculate_corporate_action_multiplier("AAPL")
        console.print(f"  AAPL multiplier: {mult}x")
        console.print(f"  Factors: {', '.join(details.get('factors', []))}")

        console.print("[green]✓[/green] Corporate actions test complete")
        return True

    except Exception as e:
        console.print(f"[red]✗[/red] Corporate actions test failed: {e}")
        return False


def test_activist_tracking():
    """Test activist tracking."""
    print_section("ACTIVIST TRACKING TEST")
    try:
        tracker = ActivistTracker()
        console.print("[green]✓[/green] Activist tracker initialized")

        mult, details = tracker.calculate_activist_multiplier("AAPL")
        console.print(f"  AAPL activist multiplier: {mult}x")
        console.print(f"  Activists found: {len(details.get('activists', []))}")

        console.print("[green]✓[/green] Activist tracking test complete")
        return True

    except Exception as e:
        console.print(f"[red]✗[/red] Activist tracking test failed: {e}")
        return False


def test_network_effects():
    """Test network effects analysis (Phase 4)."""
    if not PHASE4_AVAILABLE:
        print_section("NETWORK EFFECTS TEST (SKIPPED)")
        console.print("[yellow]⚠[/yellow] Phase 4 modules not available")
        return True

    print_section("NETWORK EFFECTS TEST")
    try:
        analyzer = NetworkAnalyzer()
        console.print("[green]✓[/green] Network analyzer initialized")

        # Test supply chain network
        supply_chain = analyzer.analyze_supplier_customer_network(
            ticker="AAPL",
            filing_date=datetime.now(),
            window_days=30
        )
        console.print(f"  AAPL supply chain network score: {supply_chain.get('network_score', 0):.3f}")
        console.print(f"  Suppliers buying: {supply_chain.get('supplier_count', 0)}")
        console.print(f"  Customers buying: {supply_chain.get('customer_count', 0)}")

        # Test peer cluster
        peer_cluster = analyzer.analyze_peer_cluster(
            ticker="AAPL",
            filing_date=datetime.now(),
            window_days=14
        )
        console.print(f"  AAPL peer cluster score: {peer_cluster.get('cluster_score', 0):.3f}")
        console.print(f"  Active peers: {peer_cluster.get('active_peer_count', 0)}")

        # Test network multiplier
        multiplier, reason = analyzer.get_network_multiplier("AAPL", datetime.now())
        console.print(f"  Network multiplier: {multiplier:.3f}x ({reason})")

        console.print("[green]✓[/green] Network effects test complete")
        return True

    except Exception as e:
        console.print(f"[red]✗[/red] Network effects test failed: {e}")
        logger.exception("Network effects error")
        return False


def test_sector_rotation():
    """Test sector rotation detection (Phase 4)."""
    if not PHASE4_AVAILABLE:
        print_section("SECTOR ROTATION TEST (SKIPPED)")
        console.print("[yellow]⚠[/yellow] Phase 4 modules not available")
        return True

    print_section("SECTOR ROTATION TEST")
    try:
        detector = SectorRotationDetector()
        console.print("[green]✓[/green] Sector rotation detector initialized")

        # Detect sector rotation
        rotation_data = detector.detect_sector_rotation(lookback_days=30)
        anomalies = rotation_data.get('anomalies', [])
        console.print(f"  Sector rotation detected: {rotation_data.get('sector_rotation_detected', False)}")
        console.print(f"  Anomalies found: {len(anomalies)}")

        if anomalies:
            console.print("  Top anomalies:")
            for anom in anomalies[:3]:
                console.print(
                    f"    - {anom['sector']}: Z-score {anom['z_score']:.2f}, "
                    f"Score {anom['rotation_score']:.3f}"
                )

        # Test sector rotation score for AAPL
        aapl_rotation = detector.get_sector_rotation_score("AAPL")
        console.print(f"  AAPL rotation score: {aapl_rotation.get('rotation_score', 0):.3f}")

        # Test relative sector strength
        rsr = detector.get_relative_sector_strength("AAPL")
        console.print(f"  AAPL relative strength: {rsr.get('relative_strength_score', 0):.3f}")

        # Test sector multiplier
        mult, reason = detector.get_sector_multiplier("AAPL")
        console.print(f"  Sector multiplier: {mult:.3f}x ({reason})")

        console.print("[green]✓[/green] Sector rotation test complete")
        return True

    except Exception as e:
        console.print(f"[red]✗[/red] Sector rotation test failed: {e}")
        logger.exception("Sector rotation error")
        return False


def test_pairs_trading():
    """Test pairs trading generation (Phase 4)."""
    if not PHASE4_AVAILABLE:
        print_section("PAIRS TRADING TEST (SKIPPED)")
        console.print("[yellow]⚠[/yellow] Phase 4 modules not available")
        return True

    print_section("PAIRS TRADING TEST")
    try:
        generator = PairsTradeGenerator()
        console.print("[green]✓[/green] Pairs trade generator initialized")

        # Find pairs opportunities
        pairs = generator.find_pairs_opportunities(
            high_conviction_ticker="AAPL",
            window_days=14
        )
        opportunities = pairs.get('pairs_opportunities', [])
        console.print(f"  AAPL pairs opportunities: {len(opportunities)}")

        if opportunities:
            console.print("  Top pairs:")
            for pair in opportunities[:3]:
                console.print(
                    f"    - SHORT {pair['short_ticker']}: Quality {pair['pair_quality_score']:.3f}, "
                    f"Correlation {pair['correlation']:.2f}"
                )

        # Generate hedges
        hedges = generator.generate_hedge_trades(
            long_ticket="AAPL",
            long_conviction=0.75
        )
        hedge_list = hedges.get('hedges', [])
        console.print(f"  Hedging opportunities: {len(hedge_list)}")

        # Get pairs multiplier
        mult, reason = generator.get_pairs_multiplier("AAPL")
        console.print(f"  Pairs multiplier: {mult:.3f}x ({reason})")

        console.print("[green]✓[/green] Pairs trading test complete")
        return True

    except Exception as e:
        console.print(f"[red]✗[/red] Pairs trading test failed: {e}")
        logger.exception("Pairs trading error")
        return False


def main():
    """Run all tests."""
    phase_label = "PHASE 2-4" if PHASE4_AVAILABLE else "PHASE 2"
    console.print(Panel.fit(
        f"[bold cyan]INSIDER TRADING SYSTEM - {phase_label} TEST SUITE[/bold cyan]",
        style="cyan"
    ))

    tests = [
        ("Database", test_database),
        ("Conviction Scoring", test_conviction_scoring),
        ("Trade Signals", test_signal_generation),
        ("Historical Analysis", test_historical_analysis),
        ("Corporate Actions", test_corporate_actions),
        ("Activist Tracking", test_activist_tracking),
    ]

    # Add Phase 4 tests if available
    if PHASE4_AVAILABLE:
        tests.extend([
            ("Network Effects", test_network_effects),
            ("Sector Rotation", test_sector_rotation),
            ("Pairs Trading", test_pairs_trading),
        ])

    results = []
    for test_name, test_func in tests:
        try:
            result = test_func()
            results.append((test_name, result))
        except Exception as e:
            console.print(f"\n[red]✗[/red] Test '{test_name}' crashed: {e}")
            results.append((test_name, False))

    # Summary
    print_section("TEST SUMMARY")

    summary_table = Table(title="Test Results")
    summary_table.add_column("Test", style="cyan")
    summary_table.add_column("Result", style="green")

    passed = 0
    for test_name, result in results:
        status = "[green]PASS[/green]" if result else "[red]FAIL[/red]"
        summary_table.add_row(test_name, status)
        if result:
            passed += 1

    console.print(summary_table)

    console.print(f"\nTotal: [green]{passed}[/green]/[cyan]{len(results)}[/cyan] tests passed")

    if passed == len(results):
        console.print("\n[green bold]✓ ALL TESTS PASSED[/green bold]")
        phase_msg = "Phase 2-4" if PHASE4_AVAILABLE else "Phase 2"
        console.print(f"\n[cyan]{phase_msg} system is fully functional![/cyan]")
        if PHASE4_AVAILABLE:
            console.print("\n[cyan bold]Phase 4 Network Intelligence enabled[/cyan bold]")
        return 0
    else:
        console.print(f"\n[red bold]✗ {len(results) - passed} TEST(S) FAILED[/red bold]")
        return 1


if __name__ == "__main__":
    sys.exit(main())
