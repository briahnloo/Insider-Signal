# Getting Started

## Quick Start (3 steps)

```bash
# 1. Install dependencies
pip install -r requirements.txt

# 2. Run test suite
python test_scraper.py

# 3. Review results
# Shows insider transactions, filing speeds, database stats
```

## Setup

1. Edit `.env` file (already pre-configured with your email)
2. Run `pip install -r requirements.txt`
3. Run `python test_scraper.py`

## Project Structure

```
src/
├── database.py           # Database models & utilities
├── data_collection/      # Scrapers
│   └── form4_scraper.py
├── analysis/             # Phase 2: signal detection
└── execution/            # Phase 3: trade logic

config.py               # Configuration
test_scraper.py         # Test suite
```

## Next Steps

1. Review data after first run
2. Read `PHASE_2_PLAN.md` for next features
3. Use Claude Code with provided prompts to build Phase 2

## Troubleshooting

- **Import errors**: `pip install -r requirements.txt`
- **No transactions found**: Normal if markets closed. Try again later.
- **SEC error**: Check `.env` has valid `SEC_USER_AGENT`

See `SETUP.md` for detailed help.
