"""
Enhanced insider selling analysis and red flag detection.
Tracks insider selling patterns and applies penalties to conviction scores.
"""

from typing import Dict, List, Tuple, Optional
from datetime import datetime, timedelta
import pandas as pd
from loguru import logger

import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(__file__))))

from src.database import get_transactions_by_ticker, Session, InsiderTransaction
from sqlalchemy import and_, or_


class InsiderSellingAnalyzer:
    """Analyzes insider selling patterns and applies red flag penalties."""
    
    def __init__(self):
        """Initialize insider selling analyzer."""
        self.session = Session()
    
    def analyze_insider_selling_red_flags(
        self, 
        ticker: str, 
        insider_name: str, 
        transaction_date: datetime
    ) -> Dict:
        """
        Analyze insider selling red flags for a specific transaction.
        
        Args:
            ticker: Stock ticker
            insider_name: Name of the insider
            transaction_date: Date of the insider purchase
            
        Returns:
            Dict with red flags and penalties
        """
        red_flags = []
        penalty_multiplier = 1.0
        
        # 1. Check if THIS insider sold within 90 days before buying
        same_insider_sell = self._check_same_insider_selling(
            ticker, insider_name, transaction_date, days_back=90
        )
        if same_insider_sell['found']:
            red_flags.append('same_insider_sold_recently')
            penalty_multiplier *= 0.8  # -0.20 penalty
            logger.debug(f"{ticker} {insider_name}: Same insider sold {same_insider_sell['days_ago']} days ago")
        
        # 2. Check if ANY C-suite executive sold within 30 days
        c_suite_sell = self._check_c_suite_selling(ticker, transaction_date, days_back=30)
        if c_suite_sell['found']:
            red_flags.append('c_suite_sold_recently')
            penalty_multiplier *= 0.85  # -0.15 penalty
            logger.debug(f"{ticker}: C-suite sold {c_suite_sell['days_ago']} days ago")
        
        # 3. Check net insider selling ratio over 90 days
        net_selling = self._check_net_insider_selling(ticker, transaction_date, days_back=90)
        if net_selling['net_selling']:
            red_flags.append('net_insider_selling')
            penalty_multiplier *= 0.75  # -0.25 penalty
            logger.debug(f"{ticker}: Net insider selling detected (${net_selling['sell_amount']:,.0f} sold vs ${net_selling['buy_amount']:,.0f} bought)")
        
        # Calculate final penalty
        penalty_amount = 1.0 - penalty_multiplier
        
        return {
            'ticker': ticker,
            'insider_name': insider_name,
            'transaction_date': transaction_date,
            'red_flags': red_flags,
            'penalty_multiplier': penalty_multiplier,
            'penalty_amount': penalty_amount,
            'flag_count': len(red_flags),
            'same_insider_sell': same_insider_sell,
            'c_suite_sell': c_suite_sell,
            'net_selling': net_selling
        }
    
    def _check_same_insider_selling(
        self, 
        ticker: str, 
        insider_name: str, 
        transaction_date: datetime, 
        days_back: int = 90
    ) -> Dict:
        """Check if the same insider sold within specified days."""
        try:
            cutoff_date = transaction_date - timedelta(days=days_back)
            
            # Query for sell transactions by the same insider
            sell_transactions = self.session.query(InsiderTransaction).filter(
                and_(
                    InsiderTransaction.ticker == ticker,
                    InsiderTransaction.insider_name == insider_name,
                    InsiderTransaction.transaction_date >= cutoff_date,
                    InsiderTransaction.transaction_date < transaction_date,
                    or_(
                        InsiderTransaction.transaction_type.like('%SALE%'),
                        InsiderTransaction.transaction_type.like('%SELL%'),
                        InsiderTransaction.transaction_type.like('%DISPOSE%'),
                        InsiderTransaction.transaction_type.like('%DISPOSITION%')
                    )
                )
            ).all()
            
            if sell_transactions:
                # Get the most recent sell transaction
                most_recent_sell = max(sell_transactions, key=lambda x: x.transaction_date)
                days_ago = (transaction_date - most_recent_sell.transaction_date).days
                
                return {
                    'found': True,
                    'days_ago': days_ago,
                    'sell_date': most_recent_sell.transaction_date,
                    'sell_amount': most_recent_sell.total_value,
                    'sell_type': most_recent_sell.transaction_type,
                    'transactions': len(sell_transactions)
                }
            else:
                return {'found': False}
                
        except Exception as e:
            logger.error(f"Error checking same insider selling for {ticker} {insider_name}: {e}")
            return {'found': False, 'error': str(e)}
    
    def _check_c_suite_selling(
        self, 
        ticker: str, 
        transaction_date: datetime, 
        days_back: int = 30
    ) -> Dict:
        """Check if any C-suite executive sold within specified days."""
        try:
            cutoff_date = transaction_date - timedelta(days=days_back)
            
            # C-suite titles to check
            c_suite_titles = [
                'CEO', 'Chief Executive Officer',
                'CFO', 'Chief Financial Officer', 
                'COO', 'Chief Operating Officer',
                'CTO', 'Chief Technology Officer',
                'President', 'Vice President', 'VP'
            ]
            
            # Query for sell transactions by C-suite executives
            sell_transactions = self.session.query(InsiderTransaction).filter(
                and_(
                    InsiderTransaction.ticker == ticker,
                    InsiderTransaction.transaction_date >= cutoff_date,
                    InsiderTransaction.transaction_date < transaction_date,
                    or_(
                        InsiderTransaction.transaction_type.like('%SALE%'),
                        InsiderTransaction.transaction_type.like('%SELL%'),
                        InsiderTransaction.transaction_type.like('%DISPOSE%'),
                        InsiderTransaction.transaction_type.like('%DISPOSITION%')
                    ),
                    or_(*[InsiderTransaction.insider_title.like(f'%{title}%') for title in c_suite_titles])
                )
            ).all()
            
            if sell_transactions:
                # Get the most recent sell transaction
                most_recent_sell = max(sell_transactions, key=lambda x: x.transaction_date)
                days_ago = (transaction_date - most_recent_sell.transaction_date).days
                
                return {
                    'found': True,
                    'days_ago': days_ago,
                    'sell_date': most_recent_sell.transaction_date,
                    'sell_amount': most_recent_sell.total_value,
                    'sell_type': most_recent_sell.transaction_type,
                    'insider_name': most_recent_sell.insider_name,
                    'insider_title': most_recent_sell.insider_title,
                    'transactions': len(sell_transactions)
                }
            else:
                return {'found': False}
                
        except Exception as e:
            logger.error(f"Error checking C-suite selling for {ticker}: {e}")
            return {'found': False, 'error': str(e)}
    
    def _check_net_insider_selling(
        self, 
        ticker: str, 
        transaction_date: datetime, 
        days_back: int = 90
    ) -> Dict:
        """Check net insider selling ratio over specified period."""
        try:
            cutoff_date = transaction_date - timedelta(days=days_back)
            
            # Get all transactions in the period
            transactions = self.session.query(InsiderTransaction).filter(
                and_(
                    InsiderTransaction.ticker == ticker,
                    InsiderTransaction.transaction_date >= cutoff_date,
                    InsiderTransaction.transaction_date < transaction_date
                )
            ).all()
            
            if not transactions:
                return {'net_selling': False, 'buy_amount': 0, 'sell_amount': 0, 'ratio': 0}
            
            # Separate buy and sell transactions
            buy_amount = 0
            sell_amount = 0
            
            for txn in transactions:
                if any(keyword in txn.transaction_type.upper() for keyword in ['BUY', 'PURCHASE', 'ACQUIRE', 'EXERCISE']):
                    buy_amount += txn.total_value or 0
                elif any(keyword in txn.transaction_type.upper() for keyword in ['SALE', 'SELL', 'DISPOSE', 'DISPOSITION']):
                    sell_amount += txn.total_value or 0
            
            # Calculate ratio
            if buy_amount > 0:
                ratio = sell_amount / buy_amount
                net_selling = ratio > 1.0  # More sold than bought
            else:
                ratio = float('inf') if sell_amount > 0 else 0
                net_selling = sell_amount > 0
            
            return {
                'net_selling': net_selling,
                'buy_amount': buy_amount,
                'sell_amount': sell_amount,
                'ratio': ratio,
                'total_transactions': len(transactions)
            }
            
        except Exception as e:
            logger.error(f"Error checking net insider selling for {ticker}: {e}")
            return {'net_selling': False, 'error': str(e)}
    
    def get_insider_activity_balance(self, ticker: str, days_back: int = 90) -> Dict:
        """Get comprehensive insider activity balance for a ticker."""
        try:
            cutoff_date = datetime.now() - timedelta(days=days_back)
            
            # Get all transactions in the period
            transactions = self.session.query(InsiderTransaction).filter(
                and_(
                    InsiderTransaction.ticker == ticker,
                    InsiderTransaction.transaction_date >= cutoff_date
                )
            ).all()
            
            if not transactions:
                return {
                    'ticker': ticker,
                    'total_transactions': 0,
                    'buy_amount': 0,
                    'sell_amount': 0,
                    'net_amount': 0,
                    'buy_transactions': 0,
                    'sell_transactions': 0,
                    'conflicted_insiders': []
                }
            
            # Analyze transactions
            buy_amount = 0
            sell_amount = 0
            buy_transactions = 0
            sell_transactions = 0
            insider_activity = {}
            
            for txn in transactions:
                insider = txn.insider_name
                if insider not in insider_activity:
                    insider_activity[insider] = {'buys': 0, 'sells': 0, 'buy_amount': 0, 'sell_amount': 0}
                
                if any(keyword in txn.transaction_type.upper() for keyword in ['BUY', 'PURCHASE', 'ACQUIRE', 'EXERCISE']):
                    buy_amount += txn.total_value or 0
                    buy_transactions += 1
                    insider_activity[insider]['buys'] += 1
                    insider_activity[insider]['buy_amount'] += txn.total_value or 0
                elif any(keyword in txn.transaction_type.upper() for keyword in ['SALE', 'SELL', 'DISPOSE', 'DISPOSITION']):
                    sell_amount += txn.total_value or 0
                    sell_transactions += 1
                    insider_activity[insider]['sells'] += 1
                    insider_activity[insider]['sell_amount'] += txn.total_value or 0
            
            # Find conflicted insiders (both bought and sold)
            conflicted_insiders = []
            for insider, activity in insider_activity.items():
                if activity['buys'] > 0 and activity['sells'] > 0:
                    conflicted_insiders.append({
                        'insider_name': insider,
                        'buys': activity['buys'],
                        'sells': activity['sells'],
                        'buy_amount': activity['buy_amount'],
                        'sell_amount': activity['sell_amount'],
                        'net_amount': activity['buy_amount'] - activity['sell_amount']
                    })
            
            return {
                'ticker': ticker,
                'total_transactions': len(transactions),
                'buy_amount': buy_amount,
                'sell_amount': sell_amount,
                'net_amount': buy_amount - sell_amount,
                'buy_transactions': buy_transactions,
                'sell_transactions': sell_transactions,
                'conflicted_insiders': conflicted_insiders,
                'insider_activity': insider_activity
            }
            
        except Exception as e:
            logger.error(f"Error getting insider activity balance for {ticker}: {e}")
            return {'error': str(e)}
    
    def __del__(self):
        """Close database session."""
        if hasattr(self, 'session'):
            self.session.close()


def get_insider_selling_analyzer() -> InsiderSellingAnalyzer:
    """Get insider selling analyzer instance."""
    return InsiderSellingAnalyzer()


def test_insider_selling_analysis():
    """Test insider selling analysis for current signals."""
    
    print("=" * 80)
    print("INSIDER SELLING RED FLAGS ANALYSIS")
    print("=" * 80)
    print()
    
    analyzer = get_insider_selling_analyzer()
    
    # Test tickers from our dataset
    test_tickers = ['AAPL', 'META', 'AMZN', 'MSFT', 'CMC']
    
    for ticker in test_tickers:
        print(f"🔍 Analyzing {ticker}:")
        print("-" * 40)
        
        # Get insider activity balance
        balance = analyzer.get_insider_activity_balance(ticker, days_back=90)
        
        if 'error' in balance:
            print(f"  Error: {balance['error']}")
            continue
        
        print(f"  Total Transactions: {balance['total_transactions']}")
        print(f"  Buy Amount: ${balance['buy_amount']:,.0f}")
        print(f"  Sell Amount: ${balance['sell_amount']:,.0f}")
        print(f"  Net Amount: ${balance['net_amount']:,.0f}")
        print(f"  Buy/Sell Ratio: {balance['buy_transactions']}/{balance['sell_transactions']}")
        
        if balance['conflicted_insiders']:
            print(f"  Conflicted Insiders: {len(balance['conflicted_insiders'])}")
            for insider in balance['conflicted_insiders'][:3]:  # Show top 3
                print(f"    • {insider['insider_name']}: ${insider['buy_amount']:,.0f} bought, ${insider['sell_amount']:,.0f} sold")
        else:
            print(f"  Conflicted Insiders: 0")
        
        print()
    
    print("=" * 80)
    print("✅ INSIDER SELLING ANALYSIS COMPLETE")
    print("=" * 80)


if __name__ == "__main__":
    test_insider_selling_analysis()
