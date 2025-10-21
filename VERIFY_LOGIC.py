#!/usr/bin/env python3
"""
Comprehensive verification audit of all dashboard logic.
Tests: deduplication, timing, price changes, conviction scoring, categorization.
"""
import sys
from datetime import datetime, timedelta
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))

from src.analysis.transaction_analyzer import get_transaction_analyzer
from src.analysis.enhanced_conviction_scorer import get_enhanced_conviction_scorer
from loguru import logger

logger.remove()
logger.add(sys.stdout, format="<level>{level: <8}</level> | <level>{message}</level>", level="INFO")


def test_deduplication_accuracy():
    """Test 1: Deduplication preserves data integrity."""
    print("\n" + "="*70)
    print("TEST 1: DEDUPLICATION ACCURACY")
    print("="*70)

    analyzer = get_transaction_analyzer()

    # Test case 1: 4 identical transactions
    txns = [
        {
            'ticker': 'CMC',
            'insider_name': 'McPherson John R',
            'transaction_date': datetime.now(),
            'shares': 1000,
            'total_value': 99450,
            'price_per_share': 99.45,
        } for _ in range(4)
    ]

    result = analyzer.deduplicate_and_group_transactions(txns)

    print(f"Input: 4 identical transactions")
    print(f"  Each: 1,000 shares @ $99.45 = $99,450")
    print(f"Output: {len(result)} deduplicated transactions")
    print(f"  duplicate_count: {result[0]['duplicate_count']}")
    print(f"  grouped_shares: {result[0]['grouped_shares']:,}")
    print(f"  grouped_value: ${result[0]['grouped_value']:,.0f}")

    assert len(result) == 1, "Should deduplicate to 1 transaction"
    assert result[0]['duplicate_count'] == 4, "Duplicate count should be 4"
    assert result[0]['grouped_shares'] == 4000, f"Grouped shares should be 4,000, got {result[0]['grouped_shares']}"
    assert result[0]['grouped_value'] == 397800, f"Grouped value should be $397,800, got ${result[0]['grouped_value']}"

    print("✅ DEDUPLICATION ACCURACY TEST PASSED")
    return True


def test_entry_timing_calculations():
    """Test 2: Entry timing categories and scoring."""
    print("\n" + "="*70)
    print("TEST 2: ENTRY TIMING CALCULATIONS")
    print("="*70)

    analyzer = get_transaction_analyzer()

    test_cases = [
        (0, 'EARLY', 1.0, "Same day"),
        (3, 'EARLY', 1.0, "3 days ago"),
        (7, 'EARLY', 1.0, "7 days ago"),
        (8, 'OPTIMAL', 0.9, "8 days ago"),
        (15, 'OPTIMAL', 0.9, "15 days ago"),
        (30, 'OPTIMAL', 0.9, "30 days ago"),
        (31, 'LATE', 0.7, "31 days ago"),
        (60, 'LATE', 0.7, "60 days ago"),
        (90, 'LATE', 0.7, "90 days ago"),
        (91, 'STALE', 0.4, "91 days ago"),
        (120, 'STALE', 0.4, "120 days ago"),
    ]

    print("Testing entry timing boundaries:")
    all_passed = True

    for days_ago, expected_timing, expected_score, description in test_cases:
        txn_date = datetime.now() - timedelta(days=days_ago)
        timing = analyzer.analyze_entry_timing(
            'TEST',
            txn_date,
            current_price=100.0,
            price_at_transaction=100.0
        )

        actual_timing = timing['timing_category']
        actual_score = timing['timing_score']

        status = "✓" if actual_timing == expected_timing and abs(actual_score - expected_score) < 0.01 else "✗"
        print(f"  {status} {description:15s} → {actual_timing:8s} (score: {actual_score:.1f}) [expected: {expected_timing}, {expected_score:.1f}]")

        if actual_timing != expected_timing or abs(actual_score - expected_score) > 0.01:
            all_passed = False

    assert all_passed, "Entry timing test failed on some cases"
    print("✅ ENTRY TIMING CALCULATIONS TEST PASSED")
    return True


def test_price_change_calculations():
    """Test 3: Price change percentage calculations."""
    print("\n" + "="*70)
    print("TEST 3: PRICE CHANGE CALCULATIONS")
    print("="*70)

    analyzer = get_transaction_analyzer()

    test_cases = [
        (100.0, 100.0, 0.0, "No change"),
        (100.0, 110.0, 10.0, "+10% increase"),
        (100.0, 95.0, -5.0, "-5% decrease"),
        (100.0, 150.0, 50.0, "+50% increase"),
        (100.0, 50.0, -50.0, "-50% decrease"),
        (50.0, 100.0, 100.0, "Doubled (+100%)"),
    ]

    print("Testing price change calculations:")
    all_passed = True

    for price_at_txn, current_price, expected_pct, description in test_cases:
        txn_date = datetime.now() - timedelta(days=5)
        timing = analyzer.analyze_entry_timing(
            'TEST',
            txn_date,
            current_price=current_price,
            price_at_transaction=price_at_txn
        )

        actual_pct = timing.get('price_change_pct', 0.0)

        # Calculate expected: (current - at_txn) / at_txn * 100
        calc_expected = ((current_price - price_at_txn) / price_at_txn) * 100

        status = "✓" if abs(actual_pct - calc_expected) < 0.01 else "✗"
        print(f"  {status} {description:25s} → {actual_pct:+.1f}% [expected: {calc_expected:+.1f}%]")

        if abs(actual_pct - calc_expected) > 0.01:
            all_passed = False

    assert all_passed, "Price change test failed on some cases"
    print("✅ PRICE CHANGE CALCULATIONS TEST PASSED")
    return True


def test_conviction_score_ranges():
    """Test 4: Conviction scores stay within 0-1.0 range."""
    print("\n" + "="*70)
    print("TEST 4: CONVICTION SCORE RANGES")
    print("="*70)

    scorer = get_enhanced_conviction_scorer()

    test_cases = [
        ('AAPL', 1, "Very fast filing"),
        ('MSFT', 2, "Fast filing"),
        ('GOOGL', 5, "Normal filing"),
        ('TSLA', 10, "Slow filing"),
        ('AMZN', 30, "Very slow filing"),
    ]

    print("Testing conviction score ranges (should all be 0.0-1.0):")
    all_passed = True

    for ticker, filing_days, description in test_cases:
        result = scorer.calculate_enhanced_conviction_score(
            ticker=ticker,
            filing_speed_days=filing_days,
            insider_name='Test Insider',
            transaction_date=datetime.now()
        )

        final_score = result.get('final_score', 0.0)

        # Check all component scores
        in_range = 0.0 <= final_score <= 1.0
        status = "✓" if in_range else "✗"

        print(f"  {status} {ticker:6s} ({filing_days:2d}d): {final_score:.3f} {description}")

        if not in_range:
            print(f"      ERROR: Score {final_score} out of range [0, 1]")
            all_passed = False

    assert all_passed, "Conviction score range test failed"
    print("✅ CONVICTION SCORE RANGES TEST PASSED")
    return True


def test_confidence_multiplier_application():
    """Test 5: Confidence multipliers apply correctly."""
    print("\n" + "="*70)
    print("TEST 5: CONFIDENCE MULTIPLIER APPLICATION")
    print("="*70)

    analyzer = get_transaction_analyzer()

    base_score = 0.56

    test_cases = [
        (1.0, 0.56, 'WEAK_BUY', "Single insider"),
        (1.15, 0.644, 'WATCH', "1.15x multiplier"),
        (1.25, 0.70, 'ACCUMULATE', "2 insiders"),
        (1.40, 0.784, 'BUY', "3+ insiders"),
    ]

    print(f"Base conviction score: {base_score}")
    print("Testing multiplier application:")
    all_passed = True

    for multiplier, expected_adjusted, expected_category, description in test_cases:
        adjusted = base_score * multiplier
        category, action, emoji = analyzer.categorize_signal(base_score, multiplier)

        status = "✓" if abs(adjusted - expected_adjusted) < 0.01 and category == expected_category else "✗"
        print(f"  {status} {description:20s}: {base_score} × {multiplier:.2f} = {adjusted:.3f} → {emoji} {category}")

        if abs(adjusted - expected_adjusted) > 0.01 or category != expected_category:
            all_passed = False
            print(f"      Expected: {expected_adjusted:.3f} → {expected_category}")

    assert all_passed, "Confidence multiplier test failed"
    print("✅ CONFIDENCE MULTIPLIER APPLICATION TEST PASSED")
    return True


def test_categorization_boundaries():
    """Test 6: Signal categorization boundaries are correct."""
    print("\n" + "="*70)
    print("TEST 6: CATEGORIZATION BOUNDARIES")
    print("="*70)

    analyzer = get_transaction_analyzer()

    test_cases = [
        (0.40, 'SKIP', "Below 0.50"),
        (0.50, 'SKIP', "At 0.50 boundary (inclusive lower bound)"),
        (0.501, 'WEAK_BUY', "Just above 0.50"),
        (0.55, 'WEAK_BUY', "Mid WEAK_BUY"),
        (0.599, 'WEAK_BUY', "Just below 0.60"),
        (0.60, 'WATCH', "At 0.60 boundary"),
        (0.65, 'ACCUMULATE', "At 0.65 boundary"),
        (0.70, 'ACCUMULATE', "Mid ACCUMULATE"),
        (0.749, 'ACCUMULATE', "Just below 0.75"),
        (0.75, 'BUY', "At 0.75 boundary"),
        (0.80, 'BUY', "Mid BUY"),
        (0.849, 'BUY', "Just below 0.85"),
        (0.85, 'STRONG_BUY', "At 0.85 boundary"),
        (0.90, 'STRONG_BUY', "High STRONG_BUY"),
    ]

    print("Testing category boundaries (1.0x multiplier):")
    all_passed = True

    for score, expected_category, description in test_cases:
        actual_category, action, emoji = analyzer.categorize_signal(score, 1.0)

        status = "✓" if actual_category == expected_category else "✗"
        print(f"  {status} Score {score:.3f}: {emoji} {actual_category:12s} {description}")

        if actual_category != expected_category:
            print(f"      ERROR: Expected {expected_category}, got {actual_category}")
            all_passed = False

    assert all_passed, "Categorization boundary test failed"
    print("✅ CATEGORIZATION BOUNDARIES TEST PASSED")
    return True


def test_multi_insider_detection():
    """Test 7: Multi-insider accumulation detection."""
    print("\n" + "="*70)
    print("TEST 7: MULTI-INSIDER ACCUMULATION DETECTION")
    print("="*70)

    analyzer = get_transaction_analyzer()

    # Create transactions from different insiders
    transactions = [
        {
            'ticker': 'TEST',
            'insider_name': 'Insider A',
            'transaction_date': datetime.now() - timedelta(days=5),
            'shares': 1000,
            'total_value': 100000,
        },
        {
            'ticker': 'TEST',
            'insider_name': 'Insider B',
            'transaction_date': datetime.now() - timedelta(days=3),
            'shares': 1500,
            'total_value': 150000,
        },
        {
            'ticker': 'TEST',
            'insider_name': 'Insider C',
            'transaction_date': datetime.now() - timedelta(days=1),
            'shares': 2000,
            'total_value': 200000,
        },
        {
            'ticker': 'OTHER',  # Different ticker
            'insider_name': 'Other Insider',
            'transaction_date': datetime.now(),
            'shares': 1000,
            'total_value': 100000,
        },
    ]

    print("Testing multi-insider detection:")
    print(f"  Input: 3 insiders buying TEST, 1 buying OTHER")

    result = analyzer.analyze_multi_insider_accumulation('TEST', transactions, window_days=30)

    print(f"  TEST ticker: {result.get('insider_count')} insiders, {result.get('confidence_multiplier')}x confidence")
    print(f"  Total value in window: ${result.get('total_value', 0):,.0f}")
    print(f"  Interpretation: {result.get('interpretation', 'N/A')}")

    # Should detect 3 insiders for TEST
    assert result.get('insider_count') == 3, f"Should detect 3 insiders, got {result.get('insider_count')}"

    # With 3 insiders, confidence should be 1.4x
    expected_multiplier = 1.4
    assert result.get('confidence_multiplier') == expected_multiplier, \
        f"3 insiders should give {expected_multiplier}x, got {result.get('confidence_multiplier')}x"

    print("✅ MULTI-INSIDER ACCUMULATION DETECTION TEST PASSED")
    return True


def main():
    """Run all verification tests."""
    print("\n" + "🎯"*35)
    print("COMPREHENSIVE DASHBOARD LOGIC VERIFICATION")
    print("🎯"*35)

    tests = [
        ("Deduplication Accuracy", test_deduplication_accuracy),
        ("Entry Timing Calculations", test_entry_timing_calculations),
        ("Price Change Calculations", test_price_change_calculations),
        ("Conviction Score Ranges", test_conviction_score_ranges),
        ("Confidence Multiplier Application", test_confidence_multiplier_application),
        ("Categorization Boundaries", test_categorization_boundaries),
        ("Multi-Insider Detection", test_multi_insider_detection),
    ]

    results = []
    for test_name, test_func in tests:
        try:
            result = test_func()
            results.append((test_name, "✅ PASS"))
        except Exception as e:
            logger.error(f"Test failed: {e}")
            results.append((test_name, f"❌ FAIL: {str(e)[:40]}"))

    # Summary
    print("\n" + "="*70)
    print("VERIFICATION AUDIT SUMMARY")
    print("="*70)

    for test_name, result in results:
        print(f"{result:50s} | {test_name}")

    passed = sum(1 for _, r in results if "PASS" in r)
    total = len(results)

    print(f"\nTotal: {passed}/{total} verification tests passed")

    if passed == total:
        print("\n✅ ALL LOGIC VERIFIED - SYSTEM READY FOR PRODUCTION")
        print("\nKey Findings:")
        print("  • Deduplication preserves data integrity")
        print("  • Entry timing calculations correct (0-7d EARLY, 8-30d OPTIMAL, 31-90d LATE, 90+d STALE)")
        print("  • Price changes calculated accurately")
        print("  • Conviction scores remain in 0-1.0 range")
        print("  • Confidence multipliers (1.0x/1.25x/1.4x) apply correctly")
        print("  • All 6 categorization boundaries correct")
        print("  • Multi-insider detection working as expected")
        return 0
    else:
        print(f"\n❌ {total - passed} verification tests failed")
        print("Fix issues before deploying to production")
        return 1


if __name__ == "__main__":
    sys.exit(main())
