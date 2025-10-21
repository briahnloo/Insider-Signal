# Phase 2 - Quick Start Guide

## Get Started in 3 Steps

### 1. Install Dependencies
```bash
pip install -r requirements.txt
```

### 2. Run the System Test
```bash
python full_system_test.py
```

This validates all Phase 2 components:
- Conviction scoring ✅
- Trade signals ✅
- Historical analysis ✅
- Corporate actions ✅
- Activist tracking ✅

### 3. Launch the Dashboard
```bash
streamlit run streamlit_app.py
```

Then visit `http://localhost:8501` in your browser.

## Dashboard Tabs

1. **Current Signals** - Real-time insider trade analysis
2. **Historical Analysis** - Backtest and top candidates
3. **Component Breakdown** - Deep dive into signal components
4. **Database Stats** - Transaction statistics

## Key Files

| File | Purpose |
|------|---------|
| `src/analysis/conviction_scorer.py` | Master scoring engine |
| `src/execution/trade_signal.py` | Signal generation |
| `streamlit_app.py` | Interactive dashboard |
| `full_system_test.py` | End-to-end testing |
| `PHASE_2_COMPLETE.md` | Full documentation |

## Signal Quality

Typical 30-day analysis:
- 20-30 insider transactions
- 40-50% actionable (conviction ≥ 0.65)
- 10-15% STRONG_BUY signals
- Average conviction: 0.55

## Conviction Score Breakdown

- **Filing Speed** (40%): Most important - 0.7x to 1.4x
- **Short Interest** (30%): Squeeze potential - 1.0x to 1.5x
- **Accumulation** (20%): Multiple insider buying - 1.0x to 1.5x
- **Red Flags** (10%): Penalties for risk factors - 0.5x to 1.0x

## Position Sizing

Conviction Score → Position Size:
- 0.85+: 4.5% of account
- 0.75-0.85: 4.05%
- 0.65-0.75: 3.75%
- 0.55-0.65: 2.5%
- <0.55: 0.83%-1.66%

## Next: Phase 3

Phase 3 will add:
- Live paper trading
- Real-time execution
- Portfolio tracking
- ML optimization

## Questions?

See `PHASE_2_COMPLETE.md` for full documentation.

---

**Status**: Phase 2 Complete ✅

**Version**: 2.0.0

**Last Updated**: 2025-10-20
