#!/usr/bin/env python
"""Initialize database with historical Form 4 data and populate cache."""
import sys
from pathlib import Path
from datetime import datetime
from rich.console import Console
from rich.progress import Progress, SpinnerColumn, TextColumn
from loguru import logger

# Add parent directory to path
sys.path.insert(0, str(Path(__file__).parent.parent))

from src.database import initialize_database, get_database_stats
from src.data_collection.form4_scraper import Form4Scraper
from src.data_collection.market_data_cache import get_market_cache
import config

console = Console()


def print_banner():
    """Print welcome banner."""
    console.print("\n[bold cyan]" + "=" * 70 + "[/bold cyan]")
    console.print("[bold cyan]" + "INSIDER TRADING SYSTEM - DATA INITIALIZATION".center(70) + "[/bold cyan]")
    console.print("[bold cyan]" + "=" * 70 + "[/bold cyan]\n")


def initialize_db():
    """Initialize database schema."""
    console.print("[bold]Step 1:[/bold] Initializing database...")
    try:
        initialize_database()
        console.print("[green]✓[/green] Database initialized successfully\n")
        return True
    except Exception as e:
        console.print(f"[red]✗[/red] Database initialization failed: {e}\n")
        return False


def scrape_historical_data(days_back: int = 30):
    """
    Scrape historical Form 4 data.

    Args:
        days_back: Number of days to look back (default: 30)

    Returns:
        Number of transactions scraped
    """
    console.print(f"[bold]Step 2:[/bold] Scraping Form 4 filings (last {days_back} days)...")
    console.print("This may take several minutes...\n")
    
    try:
        scraper = Form4Scraper()
        
        with Progress(
            SpinnerColumn(),
            TextColumn("[progress.description]{task.description}"),
            console=console,
        ) as progress:
            task = progress.add_task("Scraping SEC filings...", total=None)
            df = scraper.scrape_recent_filings(days_back=days_back)
            progress.update(task, completed=True)
        
        if len(df) > 0:
            console.print(f"[green]✓[/green] Successfully scraped {len(df)} transactions")
            
            # Show summary
            console.print(f"  • Unique tickers: {df['ticker'].nunique()}")
            console.print(f"  • Unique insiders: {df['insider_name'].nunique()}")
            console.print(f"  • Total value: ${df['total_value'].sum():,.0f}\n")
            
            # Show top 5 tickers
            top_tickers = df.groupby('ticker')['total_value'].sum().sort_values(ascending=False).head(5)
            console.print("  Top 5 tickers by transaction value:")
            for ticker, value in top_tickers.items():
                console.print(f"    • {ticker}: ${value:,.0f}")
            console.print()
            
            return len(df)
        else:
            console.print("[yellow]⚠[/yellow] No transactions found")
            console.print("This might be normal if markets are closed or no recent insider purchases\n")
            return 0
            
    except Exception as e:
        console.print(f"[red]✗[/red] Scraping failed: {e}\n")
        logger.exception("Scraping error")
        return 0


def populate_market_cache():
    """Populate market data cache for all tickers in database."""
    console.print("[bold]Step 3:[/bold] Populating market data cache...")
    
    try:
        from src.database import get_recent_transactions
        
        # Get all tickers from database
        df = get_recent_transactions(days=90, min_value=0)
        
        if df.empty:
            console.print("[yellow]⚠[/yellow] No tickers in database to cache\n")
            return 0
        
        tickers = df['ticker'].unique().tolist()
        console.print(f"Caching data for {len(tickers)} tickers...\n")
        
        # Bulk fetch market data
        cache = get_market_cache()
        
        with Progress(
            SpinnerColumn(),
            TextColumn("[progress.description]{task.description}"),
            console=console,
        ) as progress:
            task = progress.add_task("Fetching market data...", total=None)
            results = cache.bulk_fetch_ticker_data(tickers)
            progress.update(task, completed=True)
        
        console.print(f"[green]✓[/green] Successfully cached data for {len(results)}/{len(tickers)} tickers")
        
        # Show cache stats
        stats = cache.get_cache_stats()
        console.print(f"  • Price cache entries: {stats['price_cache_size']}")
        console.print(f"  • Short interest entries: {stats['si_cache_size']}")
        console.print(f"  • Info entries: {stats['info_cache_size']}\n")
        
        return len(results)
        
    except Exception as e:
        console.print(f"[red]✗[/red] Cache population failed: {e}\n")
        logger.exception("Cache error")
        return 0


def validate_setup():
    """Validate that system is ready to use."""
    console.print("[bold]Step 4:[/bold] Validating setup...")
    
    try:
        # Check database has data
        stats = get_database_stats()
        
        if stats.get('total_transactions', 0) == 0:
            console.print("[yellow]⚠[/yellow] Database is empty")
            console.print("You may want to run this script again or check SEC website\n")
            return False
        
        console.print("[green]✓[/green] Validation complete")
        console.print(f"  • Total transactions: {stats['total_transactions']}")
        console.print(f"  • Unique tickers: {stats['unique_tickers']}")
        console.print(f"  • Average transaction: ${stats['average_transaction_value']:,.0f}\n")
        
        return True
        
    except Exception as e:
        console.print(f"[red]✗[/red] Validation failed: {e}\n")
        return False


def print_next_steps():
    """Print instructions for next steps."""
    console.print("[bold cyan]" + "=" * 70 + "[/bold cyan]")
    console.print("[bold green]✓ INITIALIZATION COMPLETE[/bold green]\n")
    console.print("[bold]Next Steps:[/bold]")
    console.print("1. Launch the Streamlit dashboard:")
    console.print("   [cyan]streamlit run streamlit_app.py[/cyan]\n")
    console.print("2. Set up hourly data refresh (optional):")
    console.print("   [cyan]python -m src.jobs.data_refresh[/cyan]\n")
    console.print("3. View the full system test:")
    console.print("   [cyan]python full_system_test.py[/cyan]\n")
    console.print("[bold cyan]" + "=" * 70 + "[/bold cyan]\n")


def main():
    """Main initialization workflow."""
    # Configure logging
    logger.remove()
    logger.add(
        sys.stderr,
        format="<level>{level: <8}</level> | <level>{message}</level>",
        level="WARNING"
    )
    
    print_banner()
    
    # Step 1: Initialize database
    if not initialize_db():
        console.print("[red]✗ Initialization failed - cannot continue[/red]")
        return 1
    
    # Step 2: Scrape historical data
    transaction_count = scrape_historical_data(days_back=config.MAX_FORM4_DAYS_BACK)
    
    # Step 3: Populate cache (only if we have data)
    if transaction_count > 0:
        cache_count = populate_market_cache()
    else:
        console.print("[yellow]Skipping cache population (no transactions)[/yellow]\n")
        cache_count = 0
    
    # Step 4: Validate
    validate_setup()
    
    # Print next steps
    print_next_steps()
    
    return 0


if __name__ == "__main__":
    sys.exit(main())

