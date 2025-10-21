#!/usr/bin/env python3
"""
Database migration script to clean duplicate transactions.
Removes duplicate entries, keeping the first occurrence of each unique transaction.
"""
import sys
from pathlib import Path
from datetime import datetime
from rich.console import Console
from rich.table import Table
from loguru import logger

# Add parent directory to path
sys.path.insert(0, str(Path(__file__).parent.parent))

from src.database import Session, InsiderTransaction, initialize_database
from sqlalchemy import func

console = Console()


def print_banner():
    """Print migration banner."""
    console.print("\n[bold cyan]" + "=" * 70 + "[/bold cyan]")
    console.print("[bold cyan]" + "DATABASE MIGRATION - DUPLICATE CLEANUP".center(70) + "[/bold cyan]")
    console.print("[bold cyan]" + "=" * 70 + "[/bold cyan]\n")


def analyze_duplicates():
    """Analyze current database for duplicates."""
    session = Session()
    try:
        # Get all transactions
        all_transactions = session.query(InsiderTransaction).all()
        
        if not all_transactions:
            console.print("[yellow]⚠[/yellow] Database is empty")
            return 0, 0
        
        # Group by unique transaction key
        groups = {}
        for t in all_transactions:
            key = (
                t.ticker,
                t.insider_name,
                t.transaction_date,
                t.shares,
                t.price_per_share
            )
            
            if key not in groups:
                groups[key] = []
            groups[key].append(t)
        
        # Count duplicates
        duplicates = 0
        unique_groups = 0
        
        for key, transactions in groups.items():
            unique_groups += 1
            if len(transactions) > 1:
                duplicates += len(transactions) - 1
        
        console.print(f"[bold]Database Analysis:[/bold]")
        console.print(f"  • Total transactions: {len(all_transactions)}")
        console.print(f"  • Unique transactions: {unique_groups}")
        console.print(f"  • Duplicates found: {duplicates}")
        
        return len(all_transactions), duplicates
        
    except Exception as e:
        console.print(f"[red]✗[/red] Failed to analyze database: {e}")
        return 0, 0
    finally:
        session.close()


def clean_duplicates():
    """Remove duplicate transactions, keeping the first occurrence."""
    session = Session()
    try:
        # Get all transactions ordered by ID (first inserted = first kept)
        all_transactions = session.query(InsiderTransaction).order_by(InsiderTransaction.id).all()
        
        if not all_transactions:
            console.print("[yellow]⚠[/yellow] No transactions to clean")
            return 0
        
        # Group by unique transaction key
        groups = {}
        for t in all_transactions:
            key = (
                t.ticker,
                t.insider_name,
                t.transaction_date,
                t.shares,
                t.price_per_share
            )
            
            if key not in groups:
                groups[key] = []
            groups[key].append(t)
        
        # Remove duplicates (keep first, delete rest)
        removed_count = 0
        duplicate_details = []
        
        for key, transactions in groups.items():
            if len(transactions) > 1:
                # Keep the first transaction (lowest ID)
                keep_transaction = transactions[0]
                duplicates = transactions[1:]
                
                for dup in duplicates:
                    session.delete(dup)
                    removed_count += 1
                    duplicate_details.append({
                        'ticker': dup.ticker,
                        'insider': dup.insider_name,
                        'date': dup.transaction_date,
                        'shares': dup.shares,
                        'id': dup.id
                    })
        
        session.commit()
        
        # Show what was removed
        if duplicate_details:
            console.print(f"\n[bold]Removed {removed_count} duplicate transactions:[/bold]")
            table = Table(show_header=True, header_style="bold magenta")
            table.add_column("Ticker", style="cyan")
            table.add_column("Insider", style="green")
            table.add_column("Date", style="yellow")
            table.add_column("Shares", style="blue")
            table.add_column("ID", style="red")
            
            for detail in duplicate_details[:10]:  # Show first 10
                table.add_row(
                    detail['ticker'],
                    detail['insider'],
                    str(detail['date']),
                    str(detail['shares']),
                    str(detail['id'])
                )
            
            console.print(table)
            
            if len(duplicate_details) > 10:
                console.print(f"... and {len(duplicate_details) - 10} more")
        
        return removed_count
        
    except Exception as e:
        session.rollback()
        console.print(f"[red]✗[/red] Failed to clean duplicates: {e}")
        logger.exception("Migration error")
        return 0
    finally:
        session.close()


def verify_cleanup():
    """Verify that duplicates have been removed."""
    session = Session()
    try:
        # Check for remaining duplicates
        result = session.query(
            InsiderTransaction.ticker,
            InsiderTransaction.insider_name,
            InsiderTransaction.transaction_date,
            InsiderTransaction.shares,
            InsiderTransaction.price_per_share,
            func.count(InsiderTransaction.id).label('count')
        ).group_by(
            InsiderTransaction.ticker,
            InsiderTransaction.insider_name,
            InsiderTransaction.transaction_date,
            InsiderTransaction.shares,
            InsiderTransaction.price_per_share
        ).having(func.count(InsiderTransaction.id) > 1).all()
        
        if result:
            console.print(f"[red]✗[/red] Still found {len(result)} duplicate groups")
            return False
        else:
            console.print("[green]✓[/green] No duplicates found - cleanup successful")
            return True
            
    except Exception as e:
        console.print(f"[red]✗[/red] Failed to verify cleanup: {e}")
        return False
    finally:
        session.close()


def main():
    """Main migration workflow."""
    # Configure logging
    logger.remove()
    logger.add(
        sys.stderr,
        format="<level>{level: <8}</level> | <level>{message}</level>",
        level="WARNING"
    )
    
    print_banner()
    
    # Step 1: Analyze current state
    console.print("[bold]Step 1:[/bold] Analyzing database for duplicates...")
    total_transactions, duplicate_count = analyze_duplicates()
    
    if duplicate_count == 0:
        console.print("[green]✓[/green] No duplicates found - database is clean")
        return 0
    
    # Step 2: Clean duplicates
    console.print(f"\n[bold]Step 2:[/bold] Removing {duplicate_count} duplicate transactions...")
    removed_count = clean_duplicates()
    
    if removed_count == 0:
        console.print("[red]✗[/red] Failed to remove duplicates")
        return 1
    
    # Step 3: Verify cleanup
    console.print(f"\n[bold]Step 3:[/bold] Verifying cleanup...")
    if not verify_cleanup():
        console.print("[red]✗[/red] Cleanup verification failed")
        return 1
    
    # Step 4: Show final stats
    console.print(f"\n[bold]Step 4:[/bold] Final database state...")
    final_total, final_duplicates = analyze_duplicates()
    
    console.print(f"\n[bold green]✓ MIGRATION COMPLETE[/bold green]")
    console.print(f"  • Removed: {removed_count} duplicate transactions")
    console.print(f"  • Final count: {final_total} transactions")
    console.print(f"  • Duplicates: {final_duplicates}")
    
    return 0


if __name__ == "__main__":
    sys.exit(main())
