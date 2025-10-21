# Insider Trading Intelligence System

## Overview
A systematic trading strategy that combines SEC Form 4 insider buying data with multi-layered confirmation signals to identify high-conviction trade opportunities.

## Strategy Philosophy
- **Edge**: Execution timing + pattern recognition, not just raw insider data
- **Target Win Rate**: 55-58% (Phase 1), scaling to 60-65% with paid data
- **Position Sizing**: 1.5-4.5% based on conviction score
- **Expected Trades**: 3-8 per month

## Current Phase
**Phase 1: Foundation (Weeks 1-4)**
- Form 4 data collection
- Basic conviction scoring
- Mistake avoidance filters
- Manual entry logging

## Setup Instructions
See [Installation](#installation) section below

## Data Sources
- SEC EDGAR (Form 4 filings) - Free
- Yahoo Finance / Finviz (price, short interest) - Free
- [Future] Unusual Whales API ($50-100/mo)

## Key Features (Planned)
- [x] Project structure
- [ ] Form 4 scraper
- [ ] Filing speed analysis
- [ ] Short interest overlay
- [ ] Accumulation pattern detection
- [ ] Conviction scoring engine
- [ ] Entry timing logic

## Installation

1. Clone or set up the project directory
2. Install dependencies:
   ```bash
   pip install -r requirements.txt
   ```
3. Copy `.env.example` to `.env` and add your information:
   ```bash
   cp .env.example .env
   ```
4. Edit `.env` with your SEC user agent (email/name)

## Architecture

```
src/
├── data_collection/     # SEC and market data scrapers
├── analysis/            # Signal detection and scoring
└── execution/           # Trade logic and timing
```

## Usage

See individual component documentation as features are built.

## Development Status

This project is in active development. Each phase adds new capabilities:

- **Phase 1**: Foundation data collection and basic filtering
- **Phase 2**: Multi-signal confirmation and conviction scoring
- **Phase 3**: Automated entry timing and execution
- **Phase 4**: Portfolio optimization and risk management
