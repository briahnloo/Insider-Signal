# Live Data Integration - Usage Examples

Quick examples of how to use the new live data sources in your code.

## 1. Get Comprehensive Data for a Stock

```python
from src.data_collection.integration_hub import get_data_integration_hub
from datetime import datetime

hub = get_data_integration_hub()

# Get ALL available data for a ticker
data = hub.get_comprehensive_ticker_data("AAPL")

print(f"Ticker: {data['ticker']}")
print(f"Timestamp: {data['timestamp']}")

# Market data
market = data['data_sources'].get('market_data', {})
print(f"Price: ${market.get('current_price', 0):.2f}")
print(f"Market Cap: ${market.get('market_cap', 0)/1e9:.1f}B")

# Intraday momentum
momentum = data['data_sources'].get('intraday_momentum', {})
if momentum:
    print(f"5-min Change: {momentum.get('price_change_pct', 0):.2f}%")
    print(f"RSI: {momentum.get('rsi', 0):.1f}")

# Earnings sentiment
earnings = data['data_sources'].get('earnings_sentiment', {})
if earnings:
    print(f"Earnings Sentiment: {earnings.get('sentiment_score', 0):.3f}")

# News sentiment
news = data['data_sources'].get('news_sentiment', {})
if news:
    print(f"News Sentiment: {news.get('sentiment_score', 0):.3f}")
    print(f"Articles: {news.get('analysis', {}).get('articles_analyzed', 0)}")

# Options flow
options = data['data_sources'].get('options_flow', {})
if options:
    print(f"Options Flow: {options.get('flow_score', 0):.3f}")

# Analyst sentiment
analyst = data['data_sources'].get('analyst_sentiment', {})
if analyst:
    print(f"Analyst Sentiment: {analyst.get('sentiment_score', 0):.3f}")
```

---

## 2. Calculate Enhanced Conviction Score

```python
from src.analysis.enhanced_conviction_scorer import get_enhanced_conviction_scorer
from datetime import datetime

scorer = get_enhanced_conviction_scorer()

# Example: CEO purchased 100,000 shares with 0 days to file
result = scorer.calculate_enhanced_conviction_score(
    ticker='AAPL',
    filing_speed_days=0,  # Filed immediately (very bullish)
    insider_name='Tim Cook',
    transaction_date=datetime.now()
)

print(f"=== Enhanced Conviction Score ===")
print(f"Overall Score: {result['conviction_score']:.3f}")
print(f"Signal Strength: {result['signal_strength']}")

print(f"\nComponent Breakdown:")
for component, score in result['component_scores'].items():
    component_info = result['components'][component]
    weight = component_info['weight']
    print(f"  {component.replace('_', ' ').title():30s} {score:.3f} ({weight:.0%} weight)")

print(f"\nData Sources Used:")
for source, available in result['data_sources_used'].items():
    status = "✓" if available else "✗"
    print(f"  {status} {source.replace('_', ' ').title()}")
```

**Output Example:**
```
=== Enhanced Conviction Score ===
Overall Score: 0.847
Signal Strength: very_strong

Component Breakdown:
  Filing Speed                      0.857 (25% weight)
  Short Interest                    0.743 (20% weight)
  Accumulation                      0.821 (15% weight)
  Red Flags                         0.950 (10% weight)
  Earnings Sentiment                0.620 (10% weight)
  News Sentiment                    0.480 (10% weight)
  Options Flow                      0.712 (5% weight)
  Analyst Sentiment                 0.620 (5% weight)
  Intraday Momentum                 0.543 (3% weight)

Data Sources Used:
  ✓ Core
  ✓ Earnings Sentiment
  ✓ News Sentiment
  ✓ Options Flow
  ✓ Analyst Sentiment
  ✓ Intraday Momentum
```

---

## 3. Analyze Earnings Sentiment

```python
from src.data_collection.earnings_sentiment import get_earnings_sentiment_analyzer
from datetime import datetime

analyzer = get_earnings_sentiment_analyzer()

# Fetch and analyze recent earnings for a ticker
ticker = "AAPL"
print(f"Analyzing recent earnings for {ticker}...")

# Fetch the transcript
transcript = analyzer.fetch_recent_earnings_transcripts(ticker, max_days_back=90)

if transcript:
    # Analyze sentiment
    sentiment, analysis = analyzer.analyze_transcript_sentiment(transcript)

    print(f"\nEarnings Call Analysis:")
    print(f"  Sentiment Score: {sentiment:.3f}")
    print(f"  Method: {analysis.get('method', 'unknown')}")
    print(f"  Positive Keywords: {len(analysis.get('positive_hits', {}))}")
    print(f"  Negative Keywords: {len(analysis.get('negative_hits', {}))}")

    # Check if earnings timing aligns with insider buying
    sentiment_score, days_since, confidence = analyzer.analyze_recent_earnings_for_ticker(
        ticker, datetime.now()
    )

    print(f"\nEarnings Timing Relative to Insider Buy:")
    print(f"  Sentiment: {sentiment_score:.3f}")
    print(f"  Days Since Earnings: {days_since}")
    print(f"  Confidence: {confidence:.0%}")
else:
    print("  No recent earnings transcript found")
```

---

## 4. Get Real-Time Intraday Momentum

```python
from src.data_collection.intraday_monitor import get_intraday_monitor

monitor = get_intraday_monitor(interval='5m')

ticker = "AAPL"

# Get current momentum
momentum = monitor.get_current_price_momentum(ticker)

if momentum:
    print(f"=== {ticker} Intraday Momentum (5-min) ===")
    print(f"Current Price: ${momentum['current_price']:.2f}")
    print(f"5-min Change: {momentum['price_change_pct']:+.2f}%")
    print(f"Trend: {momentum['trend'].upper()}")
    print(f"RSI (14): {momentum['rsi']:.1f}")
    print(f"Volatility: {momentum['volatility_pct']:.2f}%")
    print(f"Volume Ratio: {momentum['volume_ratio']:.2f}x")

    # Check for price action signals
    signals = monitor.detect_price_action_signals(ticker)

    print(f"\nPrice Action Signals:")
    print(f"  Breakout High: {signals['breakout_high']}")
    print(f"  Breakout Low: {signals['breakout_low']}")
    print(f"  Reversal: {signals['reversal_pattern']}")
    print(f"  Volume Spike: {signals['volume_spike']}")
else:
    print("  No intraday data available")
```

---

## 5. Get News Sentiment Trend

```python
from src.data_collection.news_sentiment import get_news_sentiment_analyzer

analyzer = get_news_sentiment_analyzer()

ticker = "AAPL"

# Get 7-day news sentiment trend
sentiment, analysis = analyzer.get_ticker_sentiment_trend(ticker, days=7)

print(f"=== {ticker} News Sentiment (7-day) ===")
print(f"Average Sentiment: {sentiment:.3f}")
print(f"Interpretation: {analysis.get('interpretation', 'Unknown')}")
print(f"Articles Analyzed: {analysis.get('articles_analyzed', 0)}")
print(f"Trend: {analysis.get('trend', 'Unknown').upper()}")

if analysis.get('articles_analyzed', 0) > 0:
    print(f"  Positive Mentions: {analysis.get('positive_mentions', 0)}")
    print(f"  Negative Mentions: {analysis.get('negative_mentions', 0)}")

    # Detect events
    events = analyzer.detect_news_driven_events(ticker)
    if events:
        print(f"\nDetected Events:")
        for event in events[:5]:
            print(f"  - {event['event_type']}: {event['headline'][:60]}...")
```

---

## 6. Analyze Options Flow

```python
from src.data_collection.polygon_options import get_polygon_options_analyzer

analyzer = get_polygon_options_analyzer()

ticker = "AAPL"

# Get options chain
chain = analyzer.get_options_chain_data(ticker)
print(f"=== {ticker} Options Chain ===")
print(f"Calls Available: {len(chain['calls'])}")
print(f"Puts Available: {len(chain['puts'])}")

# Analyze options flow (bullish/bearish sentiment)
flow_score, details = analyzer.analyze_options_flow(ticker)

print(f"\nOptions Flow Analysis:")
print(f"  Flow Score: {flow_score:.3f}")
print(f"  Interpretation: {details.get('flow_interpretation', 'Unknown')}")
print(f"  Call/Put Vol Ratio: {details.get('call_put_vol_ratio', 0):.2f}")
print(f"  Call/Put OI Ratio: {details.get('call_put_oi_ratio', 0):.2f}")

if details.get('call_put_vol_ratio', 1.0) > 1.2:
    print(f"  ► BULLISH SIGNAL: More call volume than puts")
elif details.get('call_put_vol_ratio', 1.0) < 0.8:
    print(f"  ► BEARISH SIGNAL: More put volume than calls")

# Detect unusual activity
unusual = analyzer.get_unusual_options_activity(ticker)
if unusual:
    print(f"\nUnusual Activity Detected ({len(unusual)} positions):")
    for activity in unusual[:3]:
        print(f"  - {activity['type'].upper()} ${activity['strike']} "
              f"  {activity['severity'].upper()} "
              f"  ({activity['oi_ratio_to_avg']:.1f}x avg OI)")
```

---

## 7. Get Analyst Ratings

```python
from src.data_collection.finnhub_integrator import get_finnhub_integrator

finnhub = get_finnhub_integrator()

ticker = "AAPL"

# Get analyst sentiment
sentiment, analysis = finnhub.analyze_analyst_sentiment(ticker)

print(f"=== {ticker} Analyst Consensus ===")
print(f"Sentiment Score: {sentiment:.3f}")

if 'average_rating' in analysis:
    print(f"Average Rating: {analysis['average_rating']:.1f}/5.0")
    print(f"Total Analysts: {analysis.get('total_analysts', 0)}")

    print(f"\nBreakdown:")
    print(f"  Strong Buy: {analysis.get('strong_buy', 0)}")
    print(f"  Buy: {analysis.get('buy', 0)}")
    print(f"  Hold: {analysis.get('hold', 0)}")
    print(f"  Sell: {analysis.get('sell', 0)}")
    print(f"  Strong Sell: {analysis.get('strong_sell', 0)}")

    if sentiment > 0.3:
        print(f"\n► BULLISH consensus from analysts")
    elif sentiment < -0.3:
        print(f"\n► BEARISH consensus from analysts")
    else:
        print(f"\n► NEUTRAL analyst outlook")

# Get company news from Finnhub
news = finnhub.get_company_news(ticker, days_back=7, limit=5)
if news:
    print(f"\nRecent Company News ({len(news)} articles):")
    for article in news[:3]:
        print(f"  - {article.get('headline', 'No headline')[:70]}...")
```

---

## 8. Validate Live Data Flow

```python
from src.data_collection.integration_hub import get_data_integration_hub

hub = get_data_integration_hub()

# Validate all data sources are responding
validation = hub.validate_live_data_flow(test_ticker="AAPL")

print("=== Data Source Status ===")
for source, result in validation['validations'].items():
    status_icon = "✓" if result['status'] == 'live' else "✗"
    print(f"{status_icon} {source.replace('_', ' ').title():25s} {result['status']}")

print(f"\nData Flow Health:")
print(f"  Live Sources: {validation['summary']['live_sources']}/7")
print(f"  Overall Status: {'✓ HEALTHY' if validation['summary']['data_flow_healthy'] else '✗ DEGRADED'}")

# Monitor cache freshness
status = hub.get_hub_status()
freshness = status['data_freshness']
print(f"\nCache Freshness:")
print(f"  Market Data Cached: {freshness['market_data_cached_tickers']} tickers")
print(f"  Intraday Data Cached: {freshness['intraday_data_cached_tickers']} tickers")
```

---

## 9. Batch Score Multiple Transactions

```python
from src.analysis.enhanced_conviction_scorer import get_enhanced_conviction_scorer
from datetime import datetime, timedelta

scorer = get_enhanced_conviction_scorer()

# Example: Multiple insider purchases to score
transactions = [
    {
        'ticker': 'AAPL',
        'insider_name': 'Tim Cook',
        'filing_speed_days': 0,
        'transaction_date': datetime.now(),
    },
    {
        'ticker': 'MSFT',
        'insider_name': 'Satya Nadella',
        'filing_speed_days': 1,
        'transaction_date': datetime.now() - timedelta(days=1),
    },
    {
        'ticker': 'GOOGL',
        'insider_name': 'Larry Page',
        'filing_speed_days': 2,
        'transaction_date': datetime.now() - timedelta(days=2),
    },
]

# Batch score all transactions
scored = scorer.batch_score(transactions)

# Sort by conviction score
scored_sorted = sorted(scored, key=lambda x: x['conviction_score'], reverse=True)

print("=== Batch Scoring Results ===")
for tx in scored_sorted:
    score = tx['conviction_score']
    strength = tx['signal_strength']
    ticker = tx['ticker']

    emoji = "🔴" if strength == 'very_weak' else \
            "🟠" if strength == 'weak' else \
            "🟡" if strength == 'moderate' else \
            "🟢" if strength == 'strong' else "🟣"

    print(f"{emoji} {ticker:6s} {score:.3f} - {strength.upper()}")
```

---

## 10. Real Production Example: Execute Based on Conviction

```python
from src.analysis.enhanced_conviction_scorer import get_enhanced_conviction_scorer
from src.data_collection.market_data_cache import get_market_cache
from datetime import datetime
import config

scorer = get_enhanced_conviction_scorer()
market_cache = get_market_cache()

def execute_trade_if_high_conviction(ticker, filing_speed_days, insider_name):
    """Execute trade only if conviction is high enough."""

    # Calculate conviction score
    result = scorer.calculate_enhanced_conviction_score(
        ticker=ticker,
        filing_speed_days=filing_speed_days,
        insider_name=insider_name,
        transaction_date=datetime.now()
    )

    conviction_score = result['conviction_score']

    # Get market data
    market_cache.bulk_fetch_ticker_data([ticker])
    market_data = market_cache.get_cached_info(ticker)

    if not market_data:
        print(f"  ✗ Market data unavailable for {ticker}")
        return False

    current_price = market_data.get('current_price', 0)

    print(f"\n{'='*60}")
    print(f"TRADE SIGNAL: {ticker} ({insider_name})")
    print(f"{'='*60}")
    print(f"Price: ${current_price:.2f}")
    print(f"Conviction Score: {conviction_score:.3f}")
    print(f"Signal Strength: {result['signal_strength'].upper()}")

    # Trading logic
    if conviction_score >= config.MIN_CONVICTION_SCORE:
        print(f"\n✓ BUY SIGNAL - Score meets threshold ({conviction_score:.3f} >= {config.MIN_CONVICTION_SCORE})")

        # Calculate position size
        portfolio_value = 100000  # Example: $100k portfolio
        position_size_pct = config.BASE_POSITION_SIZE
        position_value = portfolio_value * position_size_pct
        shares = position_value / current_price

        print(f"\nPosition Sizing:")
        print(f"  Portfolio: ${portfolio_value:,.0f}")
        print(f"  Allocation: {position_size_pct:.1%}")
        print(f"  Position Value: ${position_value:,.0f}")
        print(f"  Shares to Buy: {shares:,.0f}")

        # Print conviction breakdown
        print(f"\nConviction Breakdown:")
        for component, score in result['component_scores'].items():
            weight = result['components'][component]['weight']
            bar = "█" * int(score * 10) + "░" * (10 - int(score * 10))
            print(f"  {component:20s} [{bar}] {score:.3f}")

        return True
    else:
        print(f"\n✗ SKIP - Score below threshold ({conviction_score:.3f} < {config.MIN_CONVICTION_SCORE})")
        return False

# Example usage
execute_trade_if_high_conviction(
    ticker="AAPL",
    filing_speed_days=0,
    insider_name="Tim Cook"
)
```

---

## Notes

- All examples use the **free tier** of APIs where available
- Most APIs work without authentication keys, but provide better rate limits with keys
- All data sources have **graceful fallbacks** - if one fails, others continue working
- Conviction scores are **deterministic** - same inputs always produce same outputs
- All caching is **thread-safe** for concurrent access

---

## See Also

- `LIVE_DATA_INTEGRATION.md` - Complete setup and configuration guide
- `IMPLEMENTATION_SUMMARY.md` - Technical overview and statistics
- `TEST_LIVE_DATA.py` - Automated test suite
- `src/analysis/enhanced_conviction_scorer.py` - Scorer implementation
- `src/data_collection/integration_hub.py` - Hub implementation
