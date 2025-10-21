# Phase 2 Implementation Plan: Signal Confirmation

After Phase 1 foundation is complete, here's what Phase 2 will add:

## Phase 2 Goals
- Multi-layer signal confirmation
- Filing speed multiplier system
- Short interest overlay
- Accumulation pattern detection
- Initial conviction scoring

## Components to Build

### 1. Filing Speed Analysis (`src/analysis/filing_speed.py`)
**What it does**: Analyzes how quickly insiders file Form 4s after transactions
- Same day filing: 1.4x multiplier (strong signal - insider is very bullish)
- Next day filing: 1.2x multiplier (good signal)
- 2 days (deadline): 1.0x multiplier (standard)
- Late filing: 0.7x multiplier (potential issue)

**Database addition**:
```sql
ALTER TABLE insider_transactions ADD COLUMN filing_speed_multiplier REAL;
```

**Usage**:
```python
from src.analysis.filing_speed import calculate_filing_speed_multiplier
multiplier = calculate_filing_speed_multiplier(filing_speed_days=0)  # Returns 1.4
```

### 2. Market Data Collector (`src/data_collection/market_data.py`)
**What it does**: Collects supporting market metrics
- Current stock price
- Short interest percentage
- Days to cover (short squeeze potential)
- Recent price trends

**Database addition**:
```sql
CREATE TABLE stock_metrics (
    id INTEGER PRIMARY KEY,
    ticker TEXT,
    date DATE,
    current_price REAL,
    short_interest_pct REAL,
    days_to_cover REAL,
    price_change_5d REAL,
    volume_avg_30d REAL
);
```

**Implementation notes**:
- Use yfinance for price data (free)
- Use sec-edgar for short interest via alternative sources
- Cache data to reduce API calls

### 3. Conviction Scorer (`src/analysis/conviction_scorer.py`)
**What it does**: Combines signals into a 0-1 conviction score

**Scoring formula** (Phase 2):
```
conviction_score = (
    0.40 * filing_speed_multiplier +
    0.30 * short_interest_signal +
    0.20 * accumulation_signal +
    0.10 * price_trend_signal
)
```

**Signal components**:
- Filing speed multiplier: 0.7-1.4 (already calculated)
- Short interest signal: 0-1 (higher = more squeeze potential)
- Accumulation signal: 0-1 (multiple insiders buying)
- Price trend signal: 0-1 (technical confirmation)

**Database addition**:
```sql
CREATE TABLE transaction_scores (
    id INTEGER PRIMARY KEY,
    transaction_id INTEGER FOREIGN KEY,
    conviction_score REAL,
    filing_speed_multiplier REAL,
    short_interest_signal REAL,
    accumulation_signal REAL,
    price_trend_signal REAL,
    calculated_at TIMESTAMP
);
```

### 4. Accumulation Pattern Detection (`src/analysis/pattern_detection.py`)
**What it does**: Identifies accumulation patterns from multiple insiders

**Pattern types**:
1. **Multiple buyers**: 2+ insiders buying same company in 14 days
2. **Sustained accumulation**: Same insider buying multiple times
3. **Board-level buying**: Multiple executives (CEO, CFO, etc.) buying

**Scoring**:
- 2 insiders in 14 days: +0.3
- 3+ insiders in 14 days: +0.5 (strong signal)
- Officer-level buyers: +0.2 bonus

### 5. Entry Timing Logic (`src/execution/entry_timing.py`)
**What it does**: Determines best entry point after signal confirmed

**Strategy**:
- Market open dip entry (1st 15 min)
- On support level
- With volume confirmation
- Risk/reward ratio > 2:1

## How to Build Phase 2

### Step 1: Filing Speed Multiplier
```bash
claude-code "Create src/analysis/filing_speed.py that calculates filing speed multipliers:
- Same day: 1.4x
- Next day: 1.2x
- 2 days: 1.0x
- Late: 0.7x

Add function: calculate_filing_speed_multiplier(days: int) -> float
Include logging and error handling."
```

### Step 2: Market Data Collection
```bash
claude-code "Create src/data_collection/market_data.py that:
- Uses yfinance to fetch: current price, short interest, volume
- Add table: stock_metrics (ticker, date, price, short_interest_pct, days_to_cover)
- Include function: fetch_stock_metrics(ticker: str) -> dict
- Cache results to minimize API calls
- Add to main database"
```

### Step 3: Conviction Scorer
```bash
claude-code "Create src/analysis/conviction_scorer.py that:
- Combines filing_speed_multiplier + short_interest + accumulation + price_trend
- Calculates final conviction_score (0-1)
- Weights: filing_speed=40%, short_interest=30%, accumulation=20%, trend=10%
- Add transaction_scores table
- Include function: calculate_conviction_score(transaction_id: int) -> float"
```

### Step 4: Accumulation Patterns
```bash
claude-code "Create src/analysis/pattern_detection.py that:
- Detects 2+ insiders buying same company in 14 days
- Tracks sustained accumulation by same insider
- Flags officer-level buyers (CEO, CFO, etc.)
- Returns accumulation_signal (0-1) for conviction score
- Include function: detect_accumulation_patterns(ticker: str, days: int) -> float"
```

### Step 5: Testing
```bash
claude-code "Update test_scraper.py to:
- Test each Phase 2 component
- Show example trades with full conviction scores
- Display top signals by conviction score
- Show filing speed, short interest, accumulation patterns"
```

## Database Schema - Phase 2 Summary

After Phase 2, you'll have:
```
insider_transactions (Phase 1)
├── Basic transaction data
├── filing_speed_days
└── total_value

stock_metrics (Phase 2 NEW)
├── ticker, date
├── current_price
├── short_interest_pct
└── days_to_cover

transaction_scores (Phase 2 NEW)
├── conviction_score
├── filing_speed_multiplier
├── short_interest_signal
├── accumulation_signal
└── price_trend_signal

accumulation_patterns (Phase 2 NEW)
├── ticker
├── insider_count
├── pattern_type
└── confidence_score
```

## Estimated Timeline
- Filing speed multiplier: 1 hour
- Market data collector: 1.5 hours
- Conviction scorer: 1.5 hours
- Pattern detection: 2 hours
- Testing & debugging: 1.5 hours

**Total Phase 2: ~8 hours of implementation**

## Success Metrics for Phase 2
- [x] All transactions scored 0-1 conviction scale
- [x] Filing speed multiplier integrated
- [x] Short interest data available
- [x] Accumulation patterns detected
- [x] Test suite validates scores
- [x] Top 10 signals displayed with full breakdown

Then Phase 3 will add execution logic and entry timing!
