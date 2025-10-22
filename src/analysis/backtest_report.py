"""
Generate comprehensive backtest reports for the Streamlit dashboard.
"""

import pandas as pd
import numpy as np
from datetime import datetime, timedelta
from typing import Dict, List
import sys
import os

# Add project root to path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(__file__))))

from src.analysis.real_backtest import RealBacktestEngine


class BacktestReporter:
    """Generate comprehensive backtest reports."""
    
    def __init__(self):
        self.engine = RealBacktestEngine()
    
    def generate_comprehensive_report(self) -> Dict:
        """Generate a comprehensive backtest report with multiple analyses."""
        
        print("Generating comprehensive backtest report...")
        
        # Run backtest with all trades
        all_trades_results = self.engine.run_backtest(min_conviction_score=0.0)
        
        # Run backtest with high conviction trades only
        high_conviction_results = self.engine.run_backtest(min_conviction_score=0.75)
        
        # Run backtest with very high conviction trades only
        very_high_conviction_results = self.engine.run_backtest(min_conviction_score=0.85)
        
        # Generate threshold analysis
        threshold_analysis = self._analyze_conviction_thresholds()
        
        # Generate monthly performance
        monthly_performance = self._analyze_monthly_performance(all_trades_results)
        
        # Generate ticker performance
        ticker_performance = self._analyze_ticker_performance(all_trades_results)
        
        # Generate risk metrics
        risk_metrics = self._calculate_risk_metrics(all_trades_results)
        
        return {
            'all_trades': all_trades_results,
            'high_conviction': high_conviction_results,
            'very_high_conviction': very_high_conviction_results,
            'threshold_analysis': threshold_analysis,
            'monthly_performance': monthly_performance,
            'ticker_performance': ticker_performance,
            'risk_metrics': risk_metrics,
            'generated_at': datetime.now()
        }
    
    def _analyze_conviction_thresholds(self) -> List[Dict]:
        """Analyze performance across different conviction thresholds."""
        
        thresholds = [0.0, 0.5, 0.6, 0.7, 0.75, 0.8, 0.85, 0.9]
        results = []
        
        for threshold in thresholds:
            try:
                result = self.engine.run_backtest(min_conviction_score=threshold)
                if result['total_trades'] > 0:
                    results.append({
                        'threshold': threshold,
                        'trades': result['total_trades'],
                        'return_pct': result['total_return_pct'],
                        'win_rate': result['win_rate'],
                        'avg_win': result['avg_win'],
                        'avg_loss': result['avg_loss'],
                        'sharpe_ratio': result['sharpe_ratio'],
                        'max_drawdown': result['max_drawdown']
                    })
                else:
                    results.append({
                        'threshold': threshold,
                        'trades': 0,
                        'return_pct': 0.0,
                        'win_rate': 0.0,
                        'avg_win': 0.0,
                        'avg_loss': 0.0,
                        'sharpe_ratio': 0.0,
                        'max_drawdown': 0.0
                    })
            except Exception as e:
                print(f"Error analyzing threshold {threshold}: {e}")
                results.append({
                    'threshold': threshold,
                    'trades': 0,
                    'return_pct': 0.0,
                    'win_rate': 0.0,
                    'avg_win': 0.0,
                    'avg_loss': 0.0,
                    'sharpe_ratio': 0.0,
                    'max_drawdown': 0.0
                })
        
        return results
    
    def _analyze_monthly_performance(self, results: Dict) -> List[Dict]:
        """Analyze performance by month."""
        
        if not results.get('trades'):
            return []
        
        # Group trades by month
        trades_df = pd.DataFrame(results['trades'])
        trades_df['entry_month'] = pd.to_datetime(trades_df['entry_date']).dt.to_period('M')
        
        monthly_stats = []
        for month, group in trades_df.groupby('entry_month'):
            monthly_pnl = group['net_pnl'].sum()
            monthly_return = (monthly_pnl / group['total_cost'].sum()) * 100 if group['total_cost'].sum() > 0 else 0
            win_rate = (group['net_pnl'] > 0).mean() * 100
            
            monthly_stats.append({
                'month': str(month),
                'trades': len(group),
                'pnl': monthly_pnl,
                'return_pct': monthly_return,
                'win_rate': win_rate,
                'avg_trade_pnl': group['net_pnl'].mean()
            })
        
        return sorted(monthly_stats, key=lambda x: x['month'])
    
    def _analyze_ticker_performance(self, results: Dict) -> List[Dict]:
        """Analyze performance by ticker."""
        
        if not results.get('trades'):
            return []
        
        # Group trades by ticker
        trades_df = pd.DataFrame(results['trades'])
        
        ticker_stats = []
        for ticker, group in trades_df.groupby('ticker'):
            ticker_pnl = group['net_pnl'].sum()
            ticker_return = (ticker_pnl / group['total_cost'].sum()) * 100 if group['total_cost'].sum() > 0 else 0
            win_rate = (group['net_pnl'] > 0).mean() * 100
            avg_conviction = group['conviction_score'].mean()
            
            ticker_stats.append({
                'ticker': ticker,
                'trades': len(group),
                'pnl': ticker_pnl,
                'return_pct': ticker_return,
                'win_rate': win_rate,
                'avg_conviction': avg_conviction,
                'avg_trade_pnl': group['net_pnl'].mean()
            })
        
        return sorted(ticker_stats, key=lambda x: x['return_pct'], reverse=True)
    
    def _calculate_risk_metrics(self, results: Dict) -> Dict:
        """Calculate advanced risk metrics."""
        
        if not results.get('trades'):
            return {
                'var_95': 0.0,
                'var_99': 0.0,
                'cvar_95': 0.0,
                'cvar_99': 0.0,
                'max_consecutive_losses': 0,
                'max_consecutive_wins': 0,
                'profit_factor': 0.0,
                'recovery_factor': 0.0
            }
        
        trades_df = pd.DataFrame(results['trades'])
        returns = trades_df['return_pct'].values
        
        # Value at Risk (VaR)
        var_95 = np.percentile(returns, 5)  # 5th percentile (95% VaR)
        var_99 = np.percentile(returns, 1)  # 1st percentile (99% VaR)
        
        # Conditional Value at Risk (CVaR)
        cvar_95 = returns[returns <= var_95].mean() if len(returns[returns <= var_95]) > 0 else 0
        cvar_99 = returns[returns <= var_99].mean() if len(returns[returns <= var_99]) > 0 else 0
        
        # Consecutive wins/losses
        consecutive_wins, consecutive_losses = self._calculate_consecutive_trades(trades_df)
        
        # Profit factor
        gross_profit = trades_df[trades_df['net_pnl'] > 0]['net_pnl'].sum()
        gross_loss = abs(trades_df[trades_df['net_pnl'] < 0]['net_pnl'].sum())
        profit_factor = gross_profit / gross_loss if gross_loss > 0 else float('inf')
        
        # Recovery factor
        max_dd = abs(results['max_drawdown'])
        recovery_factor = results['total_pnl'] / max_dd if max_dd > 0 else 0
        
        return {
            'var_95': var_95,
            'var_99': var_99,
            'cvar_95': cvar_95,
            'cvar_99': cvar_99,
            'max_consecutive_losses': consecutive_losses,
            'max_consecutive_wins': consecutive_wins,
            'profit_factor': profit_factor,
            'recovery_factor': recovery_factor
        }
    
    def _calculate_consecutive_trades(self, trades_df: pd.DataFrame) -> tuple:
        """Calculate maximum consecutive wins and losses."""
        
        trades_df = trades_df.sort_values('entry_date')
        is_win = trades_df['net_pnl'] > 0
        
        max_consecutive_wins = 0
        max_consecutive_losses = 0
        current_wins = 0
        current_losses = 0
        
        for win in is_win:
            if win:
                current_wins += 1
                current_losses = 0
                max_consecutive_wins = max(max_consecutive_wins, current_wins)
            else:
                current_losses += 1
                current_wins = 0
                max_consecutive_losses = max(max_consecutive_losses, current_losses)
        
        return max_consecutive_wins, max_consecutive_losses


def generate_backtest_report():
    """Generate and display comprehensive backtest report."""
    
    print("=" * 80)
    print("COMPREHENSIVE BACKTEST REPORT")
    print("=" * 80)
    print()
    
    reporter = BacktestReporter()
    report = reporter.generate_comprehensive_report()
    
    # Display main results
    all_trades = report['all_trades']
    high_conviction = report['high_conviction']
    very_high_conviction = report['very_high_conviction']
    
    print("📊 MAIN RESULTS:")
    print("-" * 50)
    print(f"All Trades ({all_trades['total_trades']}): {all_trades['total_return_pct']:.2f}% return, {all_trades['win_rate']:.1f}% win rate")
    print(f"High Conviction ≥0.75 ({high_conviction['total_trades']}): {high_conviction['total_return_pct']:.2f}% return, {high_conviction['win_rate']:.1f}% win rate")
    print(f"Very High Conviction ≥0.85 ({very_high_conviction['total_trades']}): {very_high_conviction['total_return_pct']:.2f}% return, {very_high_conviction['win_rate']:.1f}% win rate")
    
    # Display threshold analysis
    print(f"\n🎯 CONVICTION THRESHOLD ANALYSIS:")
    print("-" * 60)
    print(f"{'Threshold':<10} {'Trades':<6} {'Return%':<8} {'Win%':<6} {'Sharpe':<7} {'MaxDD':<8}")
    print("-" * 60)
    
    for analysis in report['threshold_analysis']:
        print(f"{analysis['threshold']:<10.2f} {analysis['trades']:<6} "
              f"{analysis['return_pct']:<7.2f}% {analysis['win_rate']:<5.1f}% "
              f"{analysis['sharpe_ratio']:<6.2f} ${analysis['max_drawdown']:<7.0f}")
    
    # Display monthly performance
    print(f"\n📅 MONTHLY PERFORMANCE:")
    print("-" * 50)
    print(f"{'Month':<12} {'Trades':<6} {'P&L':<10} {'Return%':<8} {'Win%':<6}")
    print("-" * 50)
    
    for month_data in report['monthly_performance']:
        print(f"{month_data['month']:<12} {month_data['trades']:<6} "
              f"${month_data['pnl']:<9.0f} {month_data['return_pct']:<7.2f}% "
              f"{month_data['win_rate']:<5.1f}%")
    
    # Display ticker performance
    print(f"\n🏢 TICKER PERFORMANCE:")
    print("-" * 60)
    print(f"{'Ticker':<6} {'Trades':<6} {'P&L':<10} {'Return%':<8} {'Win%':<6} {'Avg Conviction':<12}")
    print("-" * 60)
    
    for ticker_data in report['ticker_performance']:
        print(f"{ticker_data['ticker']:<6} {ticker_data['trades']:<6} "
              f"${ticker_data['pnl']:<9.0f} {ticker_data['return_pct']:<7.2f}% "
              f"{ticker_data['win_rate']:<5.1f}% {ticker_data['avg_conviction']:<11.3f}")
    
    # Display risk metrics
    risk = report['risk_metrics']
    print(f"\n⚠️ RISK METRICS:")
    print("-" * 40)
    print(f"VaR 95%: {risk['var_95']:.2f}%")
    print(f"VaR 99%: {risk['var_99']:.2f}%")
    print(f"CVaR 95%: {risk['cvar_95']:.2f}%")
    print(f"CVaR 99%: {risk['cvar_99']:.2f}%")
    print(f"Max Consecutive Wins: {risk['max_consecutive_wins']}")
    print(f"Max Consecutive Losses: {risk['max_consecutive_losses']}")
    print(f"Profit Factor: {risk['profit_factor']:.2f}")
    print(f"Recovery Factor: {risk['recovery_factor']:.2f}")
    
    print("\n" + "=" * 80)
    print("✅ COMPREHENSIVE BACKTEST REPORT COMPLETE")
    print("=" * 80)
    
    return report


if __name__ == "__main__":
    generate_backtest_report()
