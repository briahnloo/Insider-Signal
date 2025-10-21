#!/usr/bin/env python
"""Clear all data from the database."""
import sys
from pathlib import Path
from rich.console import Console
from rich.prompt import Confirm

# Add parent directory to path
sys.path.insert(0, str(Path(__file__).parent.parent))

from src.database import Session, InsiderTransaction, get_database_stats

console = Console()


def clear_database():
    """Clear all transactions from the database."""
    console.print("\n[bold red]⚠ WARNING: This will delete ALL data from the database![/bold red]\n")
    
    # Show current stats
    stats = get_database_stats()
    console.print(f"Current database contains:")
    console.print(f"  • Total transactions: {stats.get('total_transactions', 0)}")
    console.print(f"  • Unique tickers: {stats.get('unique_tickers', 0)}")
    console.print()
    
    # Confirm deletion
    if not Confirm.ask("Are you sure you want to delete all data?", default=False):
        console.print("[yellow]Cancelled.[/yellow]")
        return
    
    # Delete all records
    session = Session()
    try:
        count = session.query(InsiderTransaction).count()
        session.query(InsiderTransaction).delete()
        session.commit()
        
        console.print(f"\n[green]✓[/green] Successfully deleted {count} transactions")
        console.print("[green]✓[/green] Database cleared\n")
        
        # Verify
        new_stats = get_database_stats()
        console.print("Database is now empty:")
        console.print(f"  • Total transactions: {new_stats.get('total_transactions', 0)}")
        console.print()
        
    except Exception as e:
        session.rollback()
        console.print(f"[red]✗[/red] Error clearing database: {e}")
    finally:
        session.close()
    
    console.print("[cyan]To repopulate with fresh data, run:[/cyan]")
    console.print("[cyan]  python scripts/initialize_data.py[/cyan]\n")


if __name__ == "__main__":
    clear_database()

