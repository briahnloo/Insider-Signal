"""
Real backtesting system using actual historical price data.
Implements entry/exit logic with real P&L calculations.
"""

import yfinance as yf
import pandas as pd
import numpy as np
from datetime import datetime, timedelta
from typing import Dict, List, Tuple, Optional
from loguru import logger
import sys
import os

# Add project root to path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(__file__))))

from src.database import get_all_recent_transactions
from src.analysis.enhanced_conviction_scorer import EnhancedConvictionScorer


class RealBacktestEngine:
    """Real backtesting engine using historical price data."""
    
    def __init__(self, position_size: float = 10000, commission: float = 5.0, slippage: float = 0.0003):
        """
        Initialize backtest engine.
        
        Args:
            position_size: Dollar amount per trade
            commission: Commission per trade
            slippage: Slippage as decimal (0.0003 = 0.03%)
        """
        self.position_size = position_size
        self.commission = commission
        self.slippage = slippage
        self.scorer = EnhancedConvictionScorer()
        
    def fetch_historical_data(self, ticker: str, start_date: datetime, end_date: datetime) -> pd.DataFrame:
        """
        Fetch historical price data for a ticker.
        
        Args:
            ticker: Stock ticker symbol
            start_date: Start date for data
            end_date: End date for data
            
        Returns:
            DataFrame with OHLCV data
        """
        try:
            stock = yf.Ticker(ticker)
            hist = stock.history(start=start_date, end=end_date)
            
            if hist.empty:
                logger.warning(f"No historical data for {ticker}")
                return pd.DataFrame()
                
            # Ensure we have the required columns
            required_cols = ['Open', 'High', 'Low', 'Close', 'Volume']
            for col in required_cols:
                if col not in hist.columns:
                    logger.error(f"Missing column {col} for {ticker}")
                    return pd.DataFrame()
                    
            return hist
            
        except Exception as e:
            logger.error(f"Error fetching data for {ticker}: {e}")
            return pd.DataFrame()
    
    def calculate_entry_price(self, ticker: str, entry_date: datetime) -> Optional[float]:
        """
        Calculate entry price (next day's open with slippage).
        
        Args:
            ticker: Stock ticker symbol
            entry_date: Date to enter position
            
        Returns:
            Entry price or None if data unavailable
        """
        # Get data for entry date and a few days after
        start_date = entry_date
        end_date = entry_date + timedelta(days=5)
        
        hist = self.fetch_historical_data(ticker, start_date, end_date)
        
        if hist.empty:
            return None
            
        # Use next trading day's open price
        next_day = hist.index[0] if len(hist) > 0 else None
        if next_day is None:
            return None
            
        open_price = hist.loc[next_day, 'Open']
        
        # Apply slippage (buy at slightly higher price)
        entry_price = open_price * (1 + self.slippage)
        
        return entry_price
    
    def calculate_exit_price(self, ticker: str, entry_date: datetime, entry_price: float, 
                           stop_loss_pct: float = 0.15, max_days: int = 30) -> Tuple[Optional[float], str, datetime]:
        """
        Calculate exit price based on stop loss or time limit.
        
        Args:
            ticker: Stock ticker symbol
            entry_date: Date position was entered
            entry_price: Price position was entered at
            stop_loss_pct: Stop loss percentage (0.15 = 15%)
            max_days: Maximum days to hold position
            
        Returns:
            Tuple of (exit_price, exit_reason, exit_date)
        """
        # Get data for the holding period
        start_date = entry_date
        end_date = entry_date + timedelta(days=max_days + 5)  # Buffer for weekends
        
        hist = self.fetch_historical_data(ticker, start_date, end_date)
        
        if hist.empty:
            return None, "No data", entry_date
            
        stop_loss_price = entry_price * (1 - stop_loss_pct)
        
        # Check each day for stop loss or time limit
        for i, (date, row) in enumerate(hist.iterrows()):
            # Handle both datetime and date objects
            if hasattr(date, 'date'):
                date_obj = date.date()
            else:
                date_obj = date
            days_held = (date_obj - entry_date).days
            
            # Check stop loss
            if row['Low'] <= stop_loss_price:
                # Stop loss hit - exit at stop loss price
                exit_price = stop_loss_price * (1 - self.slippage)  # Sell at slightly lower price
                return exit_price, "Stop Loss", date_obj
            
            # Check time limit
            if days_held >= max_days:
                # Time limit reached - exit at close
                exit_price = row['Close'] * (1 - self.slippage)
                return exit_price, "Time Limit", date_obj
        
        # If we get here, use the last available price
        last_date = hist.index[-1]
        last_price = hist.loc[last_date, 'Close']
        exit_price = last_price * (1 - self.slippage)
        
        # Handle date conversion
        if hasattr(last_date, 'date'):
            last_date_obj = last_date.date()
        else:
            last_date_obj = last_date
            
        return exit_price, "End of Data", last_date_obj
    
    def calculate_trade_pnl(self, entry_price: float, exit_price: float, shares: int) -> Dict:
        """
        Calculate P&L for a single trade.
        
        Args:
            entry_price: Price shares were bought at
            exit_price: Price shares were sold at
            shares: Number of shares
            
        Returns:
            Dictionary with trade results
        """
        # Calculate gross P&L
        gross_pnl = (exit_price - entry_price) * shares
        
        # Calculate costs
        entry_cost = entry_price * shares * self.slippage
        exit_cost = exit_price * shares * self.slippage
        total_commission = self.commission * 2  # Entry and exit
        
        # Net P&L
        net_pnl = gross_pnl - entry_cost - exit_cost - total_commission
        
        # Calculate return percentage
        total_cost = entry_price * shares + entry_cost + self.commission
        return_pct = (net_pnl / total_cost) * 100
        
        return {
            'gross_pnl': gross_pnl,
            'net_pnl': net_pnl,
            'return_pct': return_pct,
            'entry_cost': entry_cost,
            'exit_cost': exit_cost,
            'commission': total_commission,
            'total_cost': total_cost
        }
    
    def run_backtest(self, min_conviction_score: float = 0.0) -> Dict:
        """
        Run complete backtest on all transactions.
        
        Args:
            min_conviction_score: Minimum conviction score to include trade
            
        Returns:
            Dictionary with backtest results
        """
        logger.info("Starting real backtest...")
        
        # Get all transactions
        df = get_all_recent_transactions(days=90, min_value=0)
        
        if df.empty:
            return {'error': 'No transactions found'}
        
        trades = []
        total_pnl = 0
        total_cost = 0
        winning_trades = 0
        losing_trades = 0
        
        logger.info(f"Processing {len(df)} transactions...")
        
        for idx, row in df.iterrows():
            ticker = row['ticker']
            transaction_date = row['transaction_date']
            filing_date = row['filing_date']
            total_value = row['total_value']
            
            # Calculate conviction score
            try:
                conviction_result = self.scorer.calculate_enhanced_conviction_score(
                    ticker=ticker,
                    filing_speed_days=(filing_date - transaction_date).days,
                    insider_name=row['insider_name'],
                    transaction_date=transaction_date
                )
                conviction_score = conviction_result['conviction_score']
            except Exception as e:
                logger.warning(f"Error calculating conviction for {ticker}: {e}")
                conviction_score = 0.0
            
            # Skip if below minimum conviction
            if conviction_score < min_conviction_score:
                continue
            
            # Entry date is day after filing
            entry_date = filing_date + timedelta(days=1)
            if hasattr(entry_date, 'date'):
                entry_date = entry_date.date()
            
            # Calculate entry price
            entry_price = self.calculate_entry_price(ticker, entry_date)
            if entry_price is None:
                logger.warning(f"No entry price data for {ticker} on {entry_date}")
                continue
            
            # Calculate position size
            shares = int(self.position_size / entry_price)
            if shares == 0:
                logger.warning(f"Position size too small for {ticker}")
                continue
            
            # Calculate exit price
            exit_price, exit_reason, exit_date = self.calculate_exit_price(
                ticker, entry_date, entry_price
            )
            
            if exit_price is None:
                logger.warning(f"No exit price data for {ticker}")
                continue
            
            # Calculate P&L
            trade_pnl = self.calculate_trade_pnl(entry_price, exit_price, shares)
            
            # Store trade results
            trade = {
                'ticker': ticker,
                'insider_name': row['insider_name'],
                'transaction_date': transaction_date,
                'entry_date': entry_date,
                'exit_date': exit_date,
                'entry_price': entry_price,
                'exit_price': exit_price,
                'shares': shares,
                'conviction_score': conviction_score,
                'exit_reason': exit_reason,
                'days_held': (exit_date - entry_date).days,
                'gross_pnl': trade_pnl['gross_pnl'],
                'net_pnl': trade_pnl['net_pnl'],
                'return_pct': trade_pnl['return_pct'],
                'total_cost': trade_pnl['total_cost']
            }
            
            trades.append(trade)
            total_pnl += trade_pnl['net_pnl']
            total_cost += trade_pnl['total_cost']
            
            if trade_pnl['net_pnl'] > 0:
                winning_trades += 1
            else:
                losing_trades += 0
        
        # Calculate performance metrics
        total_trades = len(trades)
        win_rate = (winning_trades / total_trades * 100) if total_trades > 0 else 0
        total_return_pct = (total_pnl / total_cost * 100) if total_cost > 0 else 0
        
        # Calculate average win/loss
        winning_trades_data = [t for t in trades if t['net_pnl'] > 0]
        losing_trades_data = [t for t in trades if t['net_pnl'] <= 0]
        
        avg_win = np.mean([t['net_pnl'] for t in winning_trades_data]) if winning_trades_data else 0
        avg_loss = np.mean([t['net_pnl'] for t in losing_trades_data]) if losing_trades_data else 0
        
        # Calculate Sharpe ratio (simplified)
        returns = [t['return_pct'] for t in trades]
        sharpe_ratio = np.mean(returns) / np.std(returns) if len(returns) > 1 and np.std(returns) > 0 else 0
        
        # Calculate maximum drawdown
        cumulative_pnl = np.cumsum([t['net_pnl'] for t in trades])
        running_max = np.maximum.accumulate(cumulative_pnl)
        drawdown = cumulative_pnl - running_max
        max_drawdown = np.min(drawdown) if len(drawdown) > 0 else 0
        
        results = {
            'total_trades': total_trades,
            'total_pnl': total_pnl,
            'total_return_pct': total_return_pct,
            'win_rate': win_rate,
            'winning_trades': winning_trades,
            'losing_trades': losing_trades,
            'avg_win': avg_win,
            'avg_loss': avg_loss,
            'sharpe_ratio': sharpe_ratio,
            'max_drawdown': max_drawdown,
            'trades': trades,
            'min_conviction_score': min_conviction_score
        }
        
        logger.info(f"Backtest complete: {total_trades} trades, {total_return_pct:.2f}% return")
        
        return results
    
    def compare_to_spy(self, start_date: datetime, end_date: datetime) -> Dict:
        """
        Compare strategy performance to SPY over the same period.
        
        Args:
            start_date: Start date for comparison
            end_date: End date for comparison
            
        Returns:
            Dictionary with SPY performance
        """
        try:
            spy = yf.Ticker("SPY")
            hist = spy.history(start=start_date, end=end_date)
            
            if hist.empty:
                return {'error': 'No SPY data available'}
            
            # Calculate SPY return
            start_price = hist.iloc[0]['Close']
            end_price = hist.iloc[-1]['Close']
            spy_return = ((end_price - start_price) / start_price) * 100
            
            return {
                'spy_return_pct': spy_return,
                'start_price': start_price,
                'end_price': end_price,
                'start_date': start_date,
                'end_date': end_date
            }
            
        except Exception as e:
            logger.error(f"Error fetching SPY data: {e}")
            return {'error': str(e)}


def run_complete_backtest():
    """Run complete backtest and display results."""
    
    print("=" * 80)
    print("REAL BACKTESTING RESULTS - HISTORICAL P&L ANALYSIS")
    print("=" * 80)
    print()
    
    # Initialize backtest engine
    engine = RealBacktestEngine(
        position_size=10000,  # $10,000 per trade
        commission=5.0,       # $5 per trade
        slippage=0.0003      # 0.03% slippage
    )
    
    # Run backtest with all trades
    print("Running backtest on all transactions...")
    results = engine.run_backtest(min_conviction_score=0.0)
    
    if 'error' in results:
        print(f"Error: {results['error']}")
        return
    
    # Display results
    print(f"📊 BACKTEST RESULTS:")
    print(f"   Total Trades: {results['total_trades']}")
    print(f"   Total P&L: ${results['total_pnl']:,.2f}")
    print(f"   Total Return: {results['total_return_pct']:.2f}%")
    print(f"   Win Rate: {results['win_rate']:.1f}%")
    print(f"   Winning Trades: {results['winning_trades']}")
    print(f"   Losing Trades: {results['losing_trades']}")
    print(f"   Average Win: ${results['avg_win']:,.2f}")
    print(f"   Average Loss: ${results['avg_loss']:,.2f}")
    print(f"   Sharpe Ratio: {results['sharpe_ratio']:.2f}")
    print(f"   Max Drawdown: ${results['max_drawdown']:,.2f}")
    
    # Show individual trades
    print(f"\n📋 INDIVIDUAL TRADE RESULTS:")
    print("-" * 100)
    print(f"{'Ticker':<6} {'Insider':<20} {'Entry':<10} {'Exit':<10} {'Days':<4} {'Entry$':<8} {'Exit$':<8} {'P&L':<10} {'Return%':<8} {'Reason':<12}")
    print("-" * 100)
    
    for trade in results['trades']:
        print(f"{trade['ticker']:<6} {trade['insider_name'][:19]:<20} "
              f"{trade['entry_date'].strftime('%Y-%m-%d'):<10} "
              f"{trade['exit_date'].strftime('%Y-%m-%d'):<10} "
              f"{trade['days_held']:<4} "
              f"${trade['entry_price']:<7.2f} "
              f"${trade['exit_price']:<7.2f} "
              f"${trade['net_pnl']:<9.2f} "
              f"{trade['return_pct']:<7.1f}% "
              f"{trade['exit_reason']:<12}")
    
    # Run comparison with different conviction thresholds
    print(f"\n🎯 CONVICTION THRESHOLD ANALYSIS:")
    print("-" * 60)
    
    thresholds = [0.0, 0.5, 0.6, 0.7, 0.8, 0.85]
    for threshold in thresholds:
        threshold_results = engine.run_backtest(min_conviction_score=threshold)
        if threshold_results['total_trades'] > 0:
            print(f"   Score ≥{threshold:.2f}: {threshold_results['total_trades']:2d} trades, "
                  f"{threshold_results['total_return_pct']:6.2f}% return, "
                  f"{threshold_results['win_rate']:5.1f}% win rate")
        else:
            print(f"   Score ≥{threshold:.2f}: No trades")
    
    # Compare to SPY
    print(f"\n📈 BENCHMARK COMPARISON:")
    print("-" * 40)
    
    if results['trades']:
        start_date = min(trade['entry_date'] for trade in results['trades'])
        end_date = max(trade['exit_date'] for trade in results['trades'])
        
        spy_results = engine.compare_to_spy(start_date, end_date)
        
        if 'error' not in spy_results:
            print(f"   Strategy Return: {results['total_return_pct']:.2f}%")
            print(f"   SPY Return:      {spy_results['spy_return_pct']:.2f}%")
            print(f"   Outperformance: {results['total_return_pct'] - spy_results['spy_return_pct']:.2f}%")
        else:
            print(f"   SPY comparison unavailable: {spy_results['error']}")
    
    print("\n" + "=" * 80)
    print("✅ REAL BACKTEST COMPLETE")
    print("=" * 80)


if __name__ == "__main__":
    run_complete_backtest()
