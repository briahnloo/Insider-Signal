"""
Enhanced conviction scoring that incorporates all data sources.
Combines: Filing speed, Short interest, Accumulation, Red flags,
+ Earnings sentiment, News sentiment, Options flow, Analyst ratings, Intraday momentum
"""
from typing import Dict, Optional
from datetime import datetime
from loguru import logger

from src.analysis.filing_speed import calculate_filing_speed_multiplier
from src.analysis.short_interest import ShortInterestAnalyzer
from src.analysis.accumulation import AccumulationDetector
from src.analysis.red_flags import RedFlagDetector
from src.analysis.options_flow_analyzer import get_options_flow_analyzer
from src.analysis.insider_commitment import get_insider_commitment_analyzer
from src.analysis.signal_staleness import calculate_staleness_penalty, get_staleness_description
from src.analysis.insider_selling_analyzer import get_insider_selling_analyzer

# Import new data sources
try:
    from src.data_collection.earnings_sentiment import get_earnings_sentiment_analyzer
    HAS_EARNINGS_SENTIMENT = True
except ImportError:
    HAS_EARNINGS_SENTIMENT = False
    logger.debug("Earnings sentiment module not available")

try:
    from src.data_collection.earnings_quality_scorer import get_earnings_quality_scorer
    HAS_EARNINGS_QUALITY = True
except ImportError:
    HAS_EARNINGS_QUALITY = False
    logger.debug("Earnings quality scorer not available")

try:
    from src.data_collection.news_sentiment import get_news_sentiment_analyzer
    HAS_NEWS_SENTIMENT = True
except ImportError:
    HAS_NEWS_SENTIMENT = False
    logger.debug("News sentiment module not available")

try:
    from src.data_collection.polygon_options import get_polygon_options_analyzer
    HAS_POLYGON_OPTIONS = True
except ImportError:
    HAS_POLYGON_OPTIONS = False
    logger.debug("Polygon options module not available")

try:
    from src.data_collection.finnhub_integrator import get_finnhub_integrator
    HAS_FINNHUB = True
except ImportError:
    HAS_FINNHUB = False
    logger.debug("Finnhub integrator module not available")

try:
    from src.data_collection.intraday_monitor import get_intraday_monitor
    HAS_INTRADAY = True
except ImportError:
    HAS_INTRADAY = False
    logger.debug("Intraday monitor module not available")


class EnhancedConvictionScorer:
    """Advanced conviction scoring with multi-source data fusion."""

    def __init__(self):
        """Initialize enhanced scorer with all available data sources."""
        # Core analyzers
        self.si_analyzer = ShortInterestAnalyzer()
        self.accumulation_detector = AccumulationDetector()
        self.red_flag_detector = RedFlagDetector()
        self.options_analyzer = get_options_flow_analyzer()  # New: Real options flow
        self.commitment_analyzer = get_insider_commitment_analyzer()  # New: Insider buy/sell analysis
        self.insider_selling_analyzer = get_insider_selling_analyzer()  # New: Insider selling red flags

        # Optional data sources
        self.earnings_analyzer = get_earnings_sentiment_analyzer() if HAS_EARNINGS_SENTIMENT else None
        self.earnings_quality_scorer = get_earnings_quality_scorer() if HAS_EARNINGS_QUALITY else None
        self.news_analyzer = get_news_sentiment_analyzer() if HAS_NEWS_SENTIMENT else None
        self.polygon_options = get_polygon_options_analyzer() if HAS_POLYGON_OPTIONS else None
        self.finnhub = get_finnhub_integrator() if HAS_FINNHUB else None
        self.intraday_monitor = get_intraday_monitor() if HAS_INTRADAY else None

        sources_available = sum([
            self.earnings_analyzer is not None,
            self.earnings_quality_scorer is not None,
            self.news_analyzer is not None,
            self.polygon_options is not None,
            self.finnhub is not None,
            self.intraday_monitor is not None,
        ])
        logger.info(
            f"Enhanced conviction scorer initialized with "
            f"{sources_available}/6 optional data sources enabled"
        )

    def calculate_enhanced_conviction_score(
        self,
        ticker: str,
        filing_speed_days: int,
        insider_name: str = None,
        transaction_date: datetime = None,
    ) -> Dict:
        """
        Calculate comprehensive conviction score using all available data.

        Weights (revised):
        - Filing speed: 25%
        - Short interest: 20%
        - Accumulation: 15%
        - Red flags: 10%
        - Earnings sentiment: 10%
        - News sentiment: 10%
        - Options flow: 5%
        - Analyst sentiment: 5%
        - Intraday momentum: 3%

        Args:
            ticker: Stock ticker
            filing_speed_days: Days from transaction to filing
            insider_name: Name of insider (optional)
            transaction_date: Date of transaction (optional)

        Returns:
            Dict with comprehensive conviction score and all signal breakdowns
        """
        scores = {}
        components = {}

        try:
            # ===== CORE SIGNALS (70% weight) =====

            # 1. Filing Speed (25% weight)
            fs_mult = calculate_filing_speed_multiplier(filing_speed_days)
            fs_signal = min(fs_mult / 1.4, 1.0)
            scores['filing_speed'] = fs_signal
            components['filing_speed'] = {
                'score': fs_signal,
                'multiplier': fs_mult,
                'weight': 0.25,
                'days': filing_speed_days,
            }

            # 2. Short Interest (18% weight)
            # NEW: Use real short interest data with updated scoring logic
            si_score, si_details = self.si_analyzer.calculate_short_interest_score(ticker)
            si_pct = si_details.get('short_interest_pct', 0)
            category = si_details.get('category', 'Unknown')

            scores['short_interest'] = si_score
            components['short_interest'] = {
                'score': si_score,
                'short_interest_pct': si_pct,
                'category': category,
                'weight': 0.18,
                'details': si_details,
            }
            
            # Calculate squeeze multiplier for final score adjustment
            squeeze_mult = 1.0
            if si_pct > 20:
                squeeze_mult = 1.5  # High squeeze potential
            elif si_pct > 10:
                squeeze_mult = 1.2  # Medium squeeze potential
            elif si_pct > 5:
                squeeze_mult = 1.1  # Low squeeze potential

            # 3. Accumulation (15% weight)
            accum = self.accumulation_detector.detect_multi_insider_accumulation(
                ticker, window_days=14
            )
            accum_mult = accum.get('multiplier', 1.0)
            accum_signal = min((accum_mult - 1.0) / 0.5, 1.0)
            scores['accumulation'] = accum_signal
            components['accumulation'] = {
                'score': accum_signal,
                'multiplier': accum_mult,
                'weight': 0.15,
                'details': accum,
            }

            # 4. Red Flags (10% weight)
            red_flags = {}
            if transaction_date:
                red_flags = self.red_flag_detector.detect_all_flags(ticker, transaction_date)
            penalty_mult = red_flags.get('penalty_multiplier', 1.0)
            scores['red_flags'] = penalty_mult
            components['red_flags'] = {
                'score': penalty_mult,
                'multiplier': penalty_mult,
                'weight': 0.10,
                'details': red_flags,
            }

            # ===== ALTERNATIVE DATA SOURCES (30% weight) =====

            # 5. Earnings Sentiment (10% weight)
            # NEW: Use real earnings quality scorer if available
            earnings_sentiment = 0.0
            earnings_confidence = 0.0
            earnings_details = {}
            
            if self.earnings_quality_scorer:
                try:
                    # Use the new earnings quality scorer (0.0-1.0 based on beat/miss)
                    earnings_score, quality_details = self.earnings_quality_scorer.get_earnings_quality(
                        ticker
                    )
                    earnings_sentiment = earnings_score
                    earnings_confidence = 1.0 if quality_details.get('surprise_pct') is not None else 0.5
                    earnings_details = quality_details
                    
                    logger.debug(
                        f"{ticker} earnings quality: {earnings_score:.2f} "
                        f"({quality_details.get('quality', 'unknown')}, "
                        f"{quality_details.get('surprise_pct', 0):+.1f}% surprise)"
                    )
                except Exception as e:
                    logger.debug(f"Earnings quality scorer error for {ticker}: {e}")
                    earnings_sentiment = 0.5  # Fallback
                    earnings_confidence = 0.0
            elif self.earnings_analyzer and transaction_date:
                # Fallback to old earnings sentiment analyzer
                try:
                    sentiment, days_since, confidence = (
                        self.earnings_analyzer.analyze_recent_earnings_for_ticker(
                            ticker, transaction_date
                        )
                    )
                    earnings_sentiment = (sentiment + 1.0) / 2.0  # Normalize -1..1 to 0..1
                    earnings_confidence = confidence
                except Exception as e:
                    logger.debug(f"Error analyzing earnings sentiment: {e}")

            scores['earnings_sentiment'] = earnings_sentiment
            components['earnings_sentiment'] = {
                'score': earnings_sentiment,
                'weight': 0.10,
                'confidence': earnings_confidence,
                'method': 'earnings_quality' if self.earnings_quality_scorer else ('earnings_transcripts' if self.earnings_analyzer else 'unavailable'),
                'details': earnings_details if earnings_details else {},
            }

            # 6. News Sentiment (10% weight)
            news_sentiment = 0.5  # Default neutral
            news_articles = 0
            if self.news_analyzer:
                try:
                    sentiment, analysis = self.news_analyzer.get_ticker_sentiment_trend(
                        ticker, days=7
                    )
                    news_sentiment = (sentiment + 1.0) / 2.0  # Normalize -1..1 to 0..1
                    news_articles = analysis.get('articles_analyzed', 0)
                except Exception as e:
                    logger.debug(f"Error analyzing news sentiment: {e}")

            scores['news_sentiment'] = news_sentiment
            components['news_sentiment'] = {
                'score': news_sentiment,
                'weight': 0.10,
                'articles_analyzed': news_articles,
                'method': 'gdelt_rss' if self.news_analyzer else 'unavailable',
            }

            # 7. Options Flow (5% weight)
            # NEW: Uses smart heuristics based on filing patterns
            # Get insider count for smart analysis
            insider_count = 1  # Default
            try:
                # Try to get insider count from accumulation analysis
                accum_data = self.accumulation_detector.detect_multi_insider_accumulation(ticker, window_days=14)
                insider_count = accum_data.get('insider_count', 1)
            except:
                insider_count = 1
            
            options_flow_signal = 0.5  # Default neutral
            flow_details = {'source': 'error', 'interpretation': 'unknown'}
            try:
                # Use smart heuristics instead of complex API calls
                options_flow_signal, flow_details = self.options_analyzer.analyze_options_flow_smart(
                    ticker, 
                    filing_speed_days=filing_speed_days,
                    insider_count=insider_count
                )
            except Exception as e:
                logger.debug(f"Error analyzing options flow: {e}")

            scores['options_flow'] = options_flow_signal
            components['options_flow'] = {
                'score': options_flow_signal,
                'weight': 0.05,
                'method': flow_details.get('source', 'unknown'),
                'interpretation': flow_details.get('interpretation', 'unknown'),
                'reasoning': flow_details.get('reasoning', 'unknown'),
                'disclaimer': flow_details.get('disclaimer', ''),
                'details': flow_details,
            }

            # 8. Insider Commitment (10% weight) - NEW!
            # Analyzes whether insiders are purely buying or also selling
            # Score: 1.0 = pure buying, 0.5 = mixed, 0.0 = net selling
            insider_commitment_score = 0.5  # Default neutral
            commitment_details = {'source': 'error', 'interpretation': 'Insufficient Data'}
            try:
                insider_commitment_score, commitment_details = (
                    self.commitment_analyzer.calculate_insider_commitment_score(ticker)
                )
            except Exception as e:
                logger.debug(f"Error analyzing insider commitment: {e}")

            scores['insider_commitment'] = insider_commitment_score
            components['insider_commitment'] = {
                'score': insider_commitment_score,
                'weight': 0.10,
                'method': commitment_details.get('source', 'unknown'),
                'interpretation': commitment_details.get('interpretation', 'unknown'),
                'buy_count': commitment_details.get('buy_count', 0),
                'sell_count': commitment_details.get('sell_count', 0),
                'conflicted_insiders': commitment_details.get('conflicted_count', 0),
                'details': commitment_details,
            }

            # 9. Analyst Sentiment (4% weight - reduced to fit insider commitment)
            analyst_sentiment = 0.5  # Default neutral
            if self.finnhub:
                try:
                    sentiment, analysis = self.finnhub.analyze_analyst_sentiment(ticker)
                    analyst_sentiment = (sentiment + 1.0) / 2.0  # Normalize
                except Exception as e:
                    logger.debug(f"Error analyzing analyst sentiment: {e}")

            scores['analyst_sentiment'] = analyst_sentiment
            components['analyst_sentiment'] = {
                'score': analyst_sentiment,
                'weight': 0.04,
                'method': 'finnhub' if self.finnhub else 'unavailable',
            }

            # 10. Intraday Momentum (2% weight - reduced to fit insider commitment)
            momentum_signal = 0.5  # Default neutral
            if self.intraday_monitor:
                try:
                    momentum = self.intraday_monitor.get_current_price_momentum(ticker)
                    if momentum:
                        # Convert RSI (0-100) to signal (0-1)
                        rsi = momentum.get('rsi', 50)
                        momentum_signal = rsi / 100.0
                except Exception as e:
                    logger.debug(f"Error analyzing intraday momentum: {e}")

            scores['intraday_momentum'] = momentum_signal
            components['intraday_momentum'] = {
                'score': momentum_signal,
                'weight': 0.02,
                'method': 'yfinance_intraday' if self.intraday_monitor else 'unavailable',
            }

            # ===== CALCULATE WEIGHTED CONVICTION SCORE =====

            # Weighted average with new insider commitment component
            # Total weights: 0.25 + 0.20 + 0.15 + 0.10 + 0.10 + 0.10 + 0.10 + 0.05 + 0.04 + 0.02 = 1.11 (needs normalization)
            # Adjusted weights sum to 1.0:
            conviction_score = (
                scores['filing_speed'] * 0.22         # Filing speed: 22%
                + scores['short_interest'] * 0.18     # Short interest: 18%
                + scores['accumulation'] * 0.14       # Accumulation: 14%
                + scores['red_flags'] * 0.09          # Red flags: 9%
                + scores['insider_commitment'] * 0.10  # Insider commitment: 10% (NEW)
                + scores['earnings_sentiment'] * 0.09 # Earnings: 9%
                + scores['news_sentiment'] * 0.09     # News: 9%
                + scores['options_flow'] * 0.05       # Options flow: 5%
                + scores['analyst_sentiment'] * 0.03  # Analyst: 3%
                + scores['intraday_momentum'] * 0.01  # Momentum: 1%
            )

            # Apply insider commitment as a multiplier (not just additive)
            # Pure buying (1.0) boosts the score
            # Mixed signals (0.5) is neutral
            # Net selling (0.0) dampens the score
            # FIXED: Changed range from 0.7-1.0 to 0.85-1.0 (don't penalize neutral signals)
            commitment_multiplier = 0.85 + (insider_commitment_score * 0.15)  # Range: 0.85-1.0

            # Calculate signal staleness penalty
            staleness_mult = 1.0
            staleness_category = "UNKNOWN"
            days_old = None
            
            if transaction_date:
                staleness_mult, staleness_category, days_old = calculate_staleness_penalty(
                    transaction_date, current_date=datetime.now()
                )
            
            components['staleness'] = {
                'multiplier': staleness_mult,
                'category': staleness_category,
                'days_old': days_old,
                'description': get_staleness_description(staleness_category, days_old) if days_old else "Unknown age"
            }
            
            # Apply multiplier adjustments (dampening factor)
            final_score = conviction_score * (
                fs_mult * 0.2
                + squeeze_mult * 0.2
                + accum_mult * 0.15
            # + penalty_mult * 0.15
                + commitment_multiplier * 0.15  # Insider commitment also as multiplier
                + (1.0 + earnings_sentiment) * 0.08
                + (1.0 + news_sentiment) * 0.08
                + (1.0 + options_flow_signal) * 0.04
                + (1.0 + analyst_sentiment) * 0.03
            )
            
            # Apply insider selling red flags penalty
            insider_selling_red_flags = self.insider_selling_analyzer.analyze_insider_selling_red_flags(
                ticker, insider_name, transaction_date
            )
            insider_selling_mult = insider_selling_red_flags['penalty_multiplier']
            # FIXED: Removed cascade application (final_score = final_score * insider_selling_mult)
            # This was causing double-penalty when combined with other multipliers
            # The red flags are already captured in the component analysis

            # Add insider selling red flags to components
            components['insider_selling_red_flags'] = {
                'penalty_multiplier': insider_selling_mult,
                'penalty_amount': insider_selling_red_flags['penalty_amount'],
                'red_flags': insider_selling_red_flags['red_flags'],
                'flag_count': insider_selling_red_flags['flag_count'],
                'same_insider_sell': insider_selling_red_flags['same_insider_sell'],
                'c_suite_sell': insider_selling_red_flags['c_suite_sell'],
                'net_selling': insider_selling_red_flags['net_selling']
            }

            # Apply staleness penalty to final score (ONLY external time-based multiplier)
            final_score = final_score * staleness_mult

            # Normalize final score to 0-1 range
            final_score = min(max(final_score, 0.0), 1.0)

            logger.info(
                f"{ticker}: Enhanced conviction {final_score:.3f} "
                f"(FS={scores['filing_speed']:.2f}, SI={scores['short_interest']:.2f}, "
                f"Commitment={scores['insider_commitment']:.2f}, "
                f"Options={scores['options_flow']:.2f})"
            )

            return {
                'ticker': ticker,
                'conviction_score': final_score,
                'component_scores': scores,
                'components': components,
                'signal_strength': self._signal_strength(final_score),
                'data_sources_used': self._count_data_sources(),
            }

        except Exception as e:
            logger.error(f"Error calculating enhanced conviction for {ticker}: {e}")
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

    def _count_data_sources(self) -> Dict[str, bool]:
        """Return availability of data sources."""
        return {
            'core': True,
            'earnings_sentiment': HAS_EARNINGS_SENTIMENT,
            'news_sentiment': HAS_NEWS_SENTIMENT,
            'options_flow': HAS_POLYGON_OPTIONS,
            'analyst_sentiment': HAS_FINNHUB,
            'intraday_momentum': HAS_INTRADAY,
        }

    def batch_score(self, transactions: list) -> list:
        """
        Score multiple transactions with enhanced scoring using parallel processing.

        Args:
            transactions: List of transaction dicts

        Returns:
            List of scored transactions
        """
        # OPTIMIZED: Use ThreadPoolExecutor for parallel scoring instead of sequential
        from concurrent.futures import ThreadPoolExecutor, as_completed
        import time

        scored = []

        # For small batches, use sequential (faster due to thread overhead)
        if len(transactions) < 5:
            for trans in transactions:
                score = self.calculate_enhanced_conviction_score(
                    ticker=trans.get('ticker'),
                    filing_speed_days=trans.get('filing_speed_days', 2),
                    insider_name=trans.get('insider_name'),
                    transaction_date=trans.get('transaction_date'),
                )
                scored.append({**trans, **score})
            return scored

        # For large batches, use parallel processing (max 5 workers to avoid overwhelming API)
        max_workers = min(5, len(transactions))

        def score_transaction(trans):
            """Helper function to score a single transaction."""
            try:
                score = self.calculate_enhanced_conviction_score(
                    ticker=trans.get('ticker'),
                    filing_speed_days=trans.get('filing_speed_days', 2),
                    insider_name=trans.get('insider_name'),
                    transaction_date=trans.get('transaction_date'),
                )
                return {**trans, **score}
            except Exception as e:
                logger.error(f"Error scoring {trans.get('ticker')}: {e}")
                return None

        with ThreadPoolExecutor(max_workers=max_workers) as executor:
            futures = {executor.submit(score_transaction, trans): trans for trans in transactions}

            for future in as_completed(futures):
                result = future.result()
                if result:
                    scored.append(result)

        return scored


# Global instance
_enhanced_scorer_instance = None


def get_enhanced_conviction_scorer() -> EnhancedConvictionScorer:
    """Get singleton instance of enhanced conviction scorer."""
    global _enhanced_scorer_instance
    if _enhanced_scorer_instance is None:
        _enhanced_scorer_instance = EnhancedConvictionScorer()
    return _enhanced_scorer_instance


if __name__ == "__main__":
    scorer = get_enhanced_conviction_scorer()

    # Test with AAPL
    test_trans = {
        'ticker': 'AAPL',
        'filing_speed_days': 0,
        'insider_name': 'Tim Cook',
        'transaction_date': datetime.now(),
    }

    result = scorer.calculate_enhanced_conviction_score(
        test_trans['ticker'],
        test_trans['filing_speed_days'],
        test_trans['insider_name'],
        test_trans['transaction_date'],
    )

    print(f"\n=== Enhanced Conviction Score for {test_trans['ticker']} ===")
    print(f"Overall Score: {result['conviction_score']:.3f}")
    print(f"Signal Strength: {result['signal_strength']}")
    print(f"\nComponent Breakdown:")
    for component, data in result['component_scores'].items():
        weight = result['components'][component]['weight']
        print(f"  {component.replace('_', ' ').title():30s} {data:6.3f} (weight: {weight:.1%})")

    print(f"\nData Sources Used:")
    for source, available in result['data_sources_used'].items():
        status = "✓" if available else "✗"
        print(f"  {status} {source.replace('_', ' ').title()}")
