"""
Enhanced transaction analyzer with deduplication, grouping, and confidence scoring.
Handles duplicate filings, multi-insider patterns, and improved categorization.
"""
from typing import Dict, List, Optional, Tuple
from datetime import datetime, timedelta
from collections import defaultdict
import pandas as pd
from loguru import logger

import config


class TransactionAnalyzer:
    """Analyzes insider transactions with deduplication and confidence scoring."""

    def __init__(self):
        """Initialize transaction analyzer."""
        self.min_conviction_threshold = 0.60
        logger.info("Transaction analyzer initialized")

    def deduplicate_and_group_transactions(
        self, transactions: List[Dict]
    ) -> List[Dict]:
        """
        Remove duplicates and group identical transactions.

        Duplicates: Same ticker + insider + date + shares (within 5% tolerance)
        Groups multiple transactions into single signal with confidence boost.

        Args:
            transactions: List of transaction records

        Returns:
            List of deduplicated transactions with group metadata
        """
        if not transactions or len(transactions) == 0:
            return []

        # Convert to DataFrame for easier manipulation
        df = pd.DataFrame(transactions)
        df['ticker'] = df['ticker'].str.upper()

        # Create grouping key: ticker + insider + transaction_date
        df['group_key'] = (
            df['ticker'].astype(str) + '_' +
            df['insider_name'].astype(str) + '_' +
            pd.to_datetime(df['transaction_date']).dt.strftime('%Y-%m-%d')
        )

        grouped = []

        for group_key, group_df in df.groupby('group_key'):
            if len(group_df) == 0:
                continue

            # Take first record as representative
            primary = group_df.iloc[0].to_dict()

            # Count duplicates
            duplicate_count = len(group_df)
            total_shares = group_df['shares'].sum()
            total_value = group_df['total_value'].sum()

            # Add grouping metadata
            primary['duplicate_count'] = duplicate_count
            primary['grouped_shares'] = total_shares
            primary['grouped_value'] = total_value
            primary['is_grouped'] = duplicate_count > 1

            grouped.append(primary)

        logger.info(f"Deduplicated {len(transactions)} transactions → {len(grouped)} unique")
        return grouped

    def analyze_multi_insider_accumulation(
        self, ticker: str, transactions: List[Dict], window_days: int = 30
    ) -> Dict:
        """
        Detect if multiple insiders are buying same stock (strong signal).

        Args:
            ticker: Stock ticker
            transactions: List of recent transactions
            window_days: Days to look back

        Returns:
            Dict with accumulation analysis
        """
        ticker = ticker.upper()
        cutoff_date = datetime.now() - timedelta(days=window_days)

        # Filter to ticker and window
        ticker_txns = [
            t for t in transactions
            if t.get('ticker', '').upper() == ticker and
            isinstance(t.get('transaction_date'), (datetime, pd.Timestamp)) and
            (t.get('transaction_date') if isinstance(t['transaction_date'], datetime)
             else pd.to_datetime(t['transaction_date'])) >= cutoff_date
        ]

        if not ticker_txns:
            return {
                'multiple_insiders': False,
                'insider_count': 0,
                'total_transactions': 0,
                'confidence_multiplier': 1.0,
                'interpretation': 'No recent insider activity',
            }

        # Count unique insiders
        unique_insiders = len(set(t.get('insider_name', '') for t in ticker_txns))
        transaction_count = len(ticker_txns)

        # Confidence multiplier increases with insider count
        # Multiple insiders = coordinated signal = higher confidence
        confidence_multiplier = 1.0
        if unique_insiders >= 3:
            confidence_multiplier = 1.40  # 40% boost
        elif unique_insiders == 2:
            confidence_multiplier = 1.25  # 25% boost
        else:
            confidence_multiplier = 1.10  # 10% boost

        interpretation = ""
        if unique_insiders >= 3:
            interpretation = f"🔥 ACCUMULATION: {unique_insiders} insiders buying (very strong)"
        elif unique_insiders == 2:
            interpretation = f"👥 COORDINATED: {unique_insiders} insiders buying together"
        else:
            interpretation = f"Single insider activity"

        return {
            'multiple_insiders': unique_insiders >= 2,
            'insider_count': unique_insiders,
            'total_transactions': transaction_count,
            'confidence_multiplier': confidence_multiplier,
            'interpretation': interpretation,
            'insider_names': list(set(t.get('insider_name', '') for t in ticker_txns)),
        }

    def categorize_signal(
        self, conviction_score: float, confidence_multiplier: float = 1.0
    ) -> Tuple[str, str, str]:
        """
        Categorize signal into actionable categories.

        Args:
            conviction_score: Base conviction score (0-1.0)
            confidence_multiplier: Boost from multi-insider analysis

        Returns:
            Tuple of (category, action, emoji)
            category: "STRONG_BUY", "BUY", "ACCUMULATE", "HOLD", "WEAK", "SKIP"
            action: Description of recommended action
            emoji: Visual indicator
        """
        # Apply confidence multiplier
        adjusted_score = conviction_score * confidence_multiplier
        adjusted_score = min(adjusted_score, 1.0)

        # Categorization logic (optimized for profitability)
        if adjusted_score >= 0.85:
            return (
                'STRONG_BUY',
                '🔥 EXECUTE IMMEDIATELY - Multiple bullish signals aligned',
                '🔥',
            )
        elif adjusted_score >= 0.75:
            return (
                'BUY',
                '✅ HIGH CONFIDENCE - Strong insider signal with confirmation',
                '✅',
            )
        elif adjusted_score >= 0.65:
            return (
                'ACCUMULATE',
                '👍 GOOD SETUP - Consider building position over time',
                '👍',
            )
        elif adjusted_score >= 0.60:
            return (
                'WATCH',
                '👀 MONITOR - Weak signals but possible opportunity if they strengthen',
                '👀',
            )
        elif adjusted_score > 0.50:
            return (
                'WEAK_BUY',
                '❓ RISKY - Mixed signals, high false positive risk',
                '❓',
            )
        else:
            return (
                'SKIP',
                '❌ SKIP - Too many red flags, not worth capital',
                '❌',
            )

    def analyze_entry_timing(
        self, ticker: str, transaction_date: datetime, current_price: float,
        price_at_transaction: float
    ) -> Dict:
        """
        Analyze if current entry timing is early, optimal, or late.

        Args:
            ticker: Stock ticker
            transaction_date: When insider bought
            current_price: Current market price
            price_at_transaction: Price when insider bought

        Returns:
            Dict with timing analysis
        """
        try:
            days_since_transaction = (datetime.now() - transaction_date).days
            price_change_pct = ((current_price - price_at_transaction) / price_at_transaction * 100) if price_at_transaction > 0 else 0

            # Determine timing
            if days_since_transaction <= 7:
                timing = 'EARLY'
                timing_desc = '🌅 Early entry window (insider just bought)'
                timing_score = 1.0  # Best - momentum hasn't started
            elif days_since_transaction <= 30:
                timing = 'OPTIMAL'
                timing_desc = '📈 Optimal window (insider buying confirmed, momentum building)'
                timing_score = 0.9
            elif days_since_transaction <= 90:
                timing = 'LATE'
                timing_desc = '⚠️ Late entry (insider bought ~3 months ago, missing initial run)'
                timing_score = 0.7
            else:
                timing = 'STALE'
                timing_desc = '❌ Too late (insider signal becoming irrelevant)'
                timing_score = 0.4

            return {
                'timing_category': timing,
                'timing_description': timing_desc,
                'timing_score': timing_score,
                'days_since_transaction': days_since_transaction,
                'price_change_pct': price_change_pct,
                'price_change_since_insider_buy': price_change_pct,
                'interpretation': f"{timing_desc} - Stock {'+' if price_change_pct >= 0 else ''}{price_change_pct:.1f}% since insider buy",
            }

        except Exception as e:
            logger.debug(f"Error analyzing entry timing: {e}")
            return {
                'timing_category': 'UNKNOWN',
                'timing_description': 'Unable to calculate',
                'timing_score': 0.5,
                'days_since_transaction': 0,
                'price_change_pct': 0,
                'price_change_since_insider_buy': 0,
            }

    def generate_component_breakdown(
        self, conviction_components: Dict, ticker: str
    ) -> str:
        """
        Generate human-readable component breakdown explaining conviction score.

        Args:
            conviction_components: Dict with individual component scores

        Returns:
            Formatted string explaining each component
        """
        breakdown = f"\n{'='*60}\nWHY {ticker} IS A STRONG BUY\n{'='*60}\n"

        components = conviction_components.get('component_scores', {})
        details = conviction_components.get('components', {})
        multipliers = conviction_components.get('multipliers', {})

        # Define interpretations for each component
        interpretations = {
            'insider_cluster': {
                'name': 'Multi-Insider Activity',
                'emoji': '👥',
                'good': (0.7, 'Multiple high-ranking executives buying simultaneously'),
                'ok': (0.5, 'Single insider with significant position'),
                'bad': (0.3, 'Isolated insider activity'),
            },
            'filing_speed': {
                'name': 'Filing Speed',
                'emoji': '⚡',
                'good': (0.7, 'Filed same/next day - maximum conviction'),
                'ok': (0.5, 'Filed within deadline - normal confidence'),
                'bad': (0.3, 'Late filing - reduced confidence'),
            },
            'short_interest': {
                'name': 'Short Squeeze Potential',
                'emoji': '🔋',
                'good': (0.7, 'High short interest creates squeeze opportunity'),
                'ok': (0.5, 'Normal short interest levels'),
                'bad': (0.3, 'Low short interest - no squeeze catalyst'),
            },
            'accumulation': {
                'name': 'Sustained Buying Pattern',
                'emoji': '📈',
                'good': (0.7, 'Consistent insider accumulation over time'),
                'ok': (0.5, 'Recent insider activity'),
                'bad': (0.3, 'No sustained buying pattern'),
            },
            'options_precursor': {
                'name': 'Options Market Signal',
                'emoji': '📊',
                'good': (0.7, 'Unusual call volume before insider filing'),
                'ok': (0.5, 'Normal options activity'),
                'bad': (0.3, 'No options confirmation'),
            },
            'earnings_sentiment': {
                'name': 'Earnings Catalyst',
                'emoji': '💰',
                'good': (0.7, 'Recent positive earnings validate insider buying'),
                'ok': (0.5, 'No recent earnings impact'),
                'bad': (0.3, 'Insider buying despite negative earnings'),
            },
            'silence_score': {
                'name': 'Market Silence',
                'emoji': '🤫',
                'good': (0.7, 'Market hasn\'t priced in the opportunity yet'),
                'ok': (0.5, 'Normal market awareness'),
                'bad': (0.3, 'High market attention - less edge'),
            },
            'network_effects': {
                'name': 'Sector/Network Effects',
                'emoji': '🌐',
                'good': (0.7, 'Sector rotation and supply chain alignment'),
                'ok': (0.5, 'Neutral sector positioning'),
                'bad': (0.3, 'Sector headwinds or misalignment'),
            },
            'red_flags': {
                'name': 'Risk Factors',
                'emoji': '🚩',
                'good': (0.7, 'No red flags detected - clean opportunity'),
                'ok': (0.5, 'Minor risk factors present'),
                'bad': (0.3, 'Multiple red flags - high risk'),
            },
        }

        # Sort components by importance (weight * score)
        component_importance = []
        for component, score in components.items():
            if component not in interpretations:
                continue
            weight = details.get(component, {}).get('weight', 0)
            importance = weight * score
            component_importance.append((component, score, weight, importance))
        
        component_importance.sort(key=lambda x: x[3], reverse=True)

        breakdown += "KEY SIGNALS THAT MAKE THIS A STRONG BUY:\n\n"

        for component, actual_score, weight, importance in component_importance:
            info = interpretations[component]
            multiplier = multipliers.get(component, 1.0)

            # Determine status
            if actual_score >= info['good'][0]:
                status, description = '✅', info['good'][1]
            elif actual_score >= info['ok'][0]:
                status, description = '⚠️ ', info['ok'][1]
            else:
                status, description = '❌', info['bad'][1]

            # Show multiplier impact
            mult_text = f" (×{multiplier:.2f})" if multiplier != 1.0 else ""
            
            breakdown += f"{info['emoji']} {info['name']}{mult_text}\n"
            breakdown += f"   {status} {description}\n"
            breakdown += f"   Score: {actual_score:.2f} | Weight: {weight:.0%} | Impact: {importance:.3f}\n\n"

        # Add summary of why this is strong
        strong_signals = [c for c, s, w, i in component_importance if s >= 0.7]
        if strong_signals:
            breakdown += f"🎯 STRENGTH: {len(strong_signals)} strong signals align\n"
        
        breakdown += f"{'='*60}\n"
        return breakdown

    def generate_signal_explanation(
        self, conviction_components: Dict, ticker: str
    ) -> Dict:
        """
        Generate user-friendly signal explanation for dashboard display.
        
        Returns:
            Dict with formatted explanation sections
        """
        components = conviction_components.get('component_scores', {})
        details = conviction_components.get('components', {})
        multipliers = conviction_components.get('multipliers', {})
        
        # Find the strongest signals
        strong_signals = []
        moderate_signals = []
        weak_signals = []
        
        for component, score in components.items():
            if component in ['insider_cluster', 'filing_speed', 'short_interest', 'accumulation', 
                           'options_precursor', 'earnings_sentiment', 'silence_score', 'network_effects']:
                weight = details.get(component, {}).get('weight', 0)
                multiplier = multipliers.get(component, 1.0)
                impact = weight * score
                
                signal_info = {
                    'component': component,
                    'score': score,
                    'weight': weight,
                    'multiplier': multiplier,
                    'impact': impact
                }
                
                if score >= 0.7:
                    strong_signals.append(signal_info)
                elif score >= 0.5:
                    moderate_signals.append(signal_info)
                else:
                    weak_signals.append(signal_info)
        
        # Sort by impact
        strong_signals.sort(key=lambda x: x['impact'], reverse=True)
        moderate_signals.sort(key=lambda x: x['impact'], reverse=True)
        
        return {
            'ticker': ticker,
            'strong_signals': strong_signals,
            'moderate_signals': moderate_signals,
            'weak_signals': weak_signals,
            'total_strong': len(strong_signals),
            'total_moderate': len(moderate_signals),
            'total_weak': len(weak_signals)
        }

    def generate_action_summary(
        self,
        ticker: str,
        conviction_score: float,
        confidence_multiplier: float,
        category: str,
        action: str,
        timing_info: Dict,
        multi_insider_info: Dict,
        components_breakdown: Dict,
    ) -> str:
        """
        Generate executive summary with actionable recommendations.

        Args:
            ticker: Stock ticker
            conviction_score: Base conviction score
            confidence_multiplier: Confidence boost
            category: Signal category
            action: Recommended action
            timing_info: Entry timing analysis
            multi_insider_info: Multi-insider analysis
            components_breakdown: Component scores

        Returns:
            Formatted summary string
        """
        adjusted_score = min(conviction_score * confidence_multiplier, 1.0)

        summary = f"\n{'🎯'*30}\n"
        summary += f"SIGNAL SUMMARY: {ticker}\n"
        summary += f"{'🎯'*30}\n\n"

        summary += f"📊 BASE CONVICTION:    {conviction_score:.3f}\n"
        if confidence_multiplier > 1.0:
            summary += f"⭐ CONFIDENCE BOOST:   {confidence_multiplier:.2f}x ({multi_insider_info.get('interpretation', '')})\n"
        summary += f"🎯 ADJUSTED SCORE:     {adjusted_score:.3f}\n"
        summary += f"🏷️  CATEGORY:          {category}\n\n"

        summary += f"💡 RECOMMENDATION:\n"
        summary += f"   {action}\n\n"

        summary += f"⏰ ENTRY TIMING:\n"
        summary += f"   {timing_info.get('timing_description', 'Unknown')}\n"
        summary += f"   Price move since insider: {timing_info.get('price_change_since_insider_buy', 0):+.1f}%\n\n"

        summary += f"👥 INSIDER CONFIDENCE:\n"
        if multi_insider_info.get('multiple_insiders', False):
            summary += f"   ✅ {multi_insider_info.get('insider_count')} insiders buying\n"
            summary += f"   Names: {', '.join(multi_insider_info.get('insider_names', [])[:3])}\n"
        else:
            summary += f"   ⚠️  Single insider (standard)\n\n"

        summary += f"{'🎯'*30}\n"
        return summary


# Global instance
_analyzer_instance = None


def get_transaction_analyzer() -> TransactionAnalyzer:
    """Get singleton instance of transaction analyzer."""
    global _analyzer_instance
    if _analyzer_instance is None:
        _analyzer_instance = TransactionAnalyzer()
    return _analyzer_instance


if __name__ == "__main__":
    analyzer = get_transaction_analyzer()

    # Test deduplication
    test_txns = [
        {
            'ticker': 'CMC',
            'insider_name': 'John Smith',
            'transaction_date': datetime.now(),
            'shares': 1000,
            'total_value': 99450,
        },
        {
            'ticker': 'CMC',
            'insider_name': 'John Smith',
            'transaction_date': datetime.now(),
            'shares': 1000,
            'total_value': 99450,
        },
        {
            'ticker': 'CMC',
            'insider_name': 'John Smith',
            'transaction_date': datetime.now(),
            'shares': 1000,
            'total_value': 99450,
        },
    ]

    deduplicated = analyzer.deduplicate_and_group_transactions(test_txns)
    print(f"Deduplicated {len(test_txns)} → {len(deduplicated)}")
    print(f"Grouped count: {deduplicated[0].get('duplicate_count')}")

    # Test categorization
    for score in [0.45, 0.55, 0.65, 0.75, 0.85]:
        category, action, emoji = analyzer.categorize_signal(score, confidence_multiplier=1.0)
        print(f"\nScore {score:.2f} → {emoji} {category}")
        print(f"  Action: {action}")

        # With multi-insider boost
        category_boosted, action_boosted, emoji_boosted = analyzer.categorize_signal(
            score, confidence_multiplier=1.3
        )
        print(f"  With 1.3x boost → {emoji_boosted} {category_boosted}")
