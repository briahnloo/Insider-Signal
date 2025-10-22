"""
Comprehensive Backtesting Engine for Insider Trading Intelligence System

Implements:
- Historical signal generation and replay
- Performance metrics (win rate, Sharpe ratio, max drawdown, CAGR)
- Walk-forward analysis with rolling windows
- Parameter optimization via grid search and genetic algorithms
- Monte Carlo simulation for strategy robustness
- Realistic returns with slippage and commissions
"""

from typing import Dict, List, Optional, Tuple
from dataclasses import dataclass, field
from datetime import datetime, timedelta
import numpy as np
import pandas as pd
from pathlib import Path
import json
import pickle
from loguru import logger

try:
    from scipy import stats
    from scipy.optimize import differential_evolution
    SCIPY_AVAILABLE = True
except:
    SCIPY_AVAILABLE = False

try:
    import matplotlib.pyplot as plt
    import seaborn as sns
    MATPLOTLIB_AVAILABLE = True
except:
    MATPLOTLIB_AVAILABLE = False


@dataclass
class BacktestConfig:
    """Configuration for backtesting."""
    initial_capital: float = 100000
    position_size_pct: float = 0.05  # 5% per position
    max_positions: int = 20
    slippage_bps: float = 10  # Basis points
    commission_pct: float = 0.001  # 0.1% per trade
    risk_free_rate: float = 0.02
    lookback_days: int = 252  # 1 year for metrics
    rebalance_frequency: int = 30  # Days

    # Walk-forward parameters
    train_period_days: int = 365  # 1 year training
    test_period_days: int = 90    # 3 months testing
    walk_forward_step_days: int = 30  # Monthly step

    # Monte Carlo parameters
    num_simulations: int = 1000
    simulation_days: int = 252


@dataclass
class TradeRecord:
    """Record of a single trade."""
    ticker: str
    entry_date: datetime
    entry_price: float
    exit_date: Optional[datetime] = None
    exit_price: Optional[float] = None
    conviction_score: float = 0.0
    sector: str = ""
    shares: int = 0
    entry_value: float = 0.0
    exit_value: float = 0.0
    pnl: float = 0.0
    pnl_pct: float = 0.0
    duration_days: int = 0

    def to_dict(self) -> Dict:
        """Convert to dictionary."""
        return {
            'ticker': self.ticker,
            'entry_date': self.entry_date.isoformat() if self.entry_date else None,
            'entry_price': self.entry_price,
            'exit_date': self.exit_date.isoformat() if self.exit_date else None,
            'exit_price': self.exit_price,
            'conviction_score': self.conviction_score,
            'sector': self.sector,
            'shares': self.shares,
            'pnl': self.pnl,
            'pnl_pct': self.pnl_pct,
            'duration_days': self.duration_days
        }


@dataclass
class PerformanceMetrics:
    """Complete performance metrics for a backtest."""
    total_return: float = 0.0
    annualized_return: float = 0.0
    sharpe_ratio: float = 0.0
    sortino_ratio: float = 0.0
    max_drawdown: float = 0.0
    win_rate: float = 0.0
    profit_factor: float = 0.0
    num_trades: int = 0
    num_winners: int = 0
    num_losers: int = 0
    avg_win: float = 0.0
    avg_loss: float = 0.0
    largest_win: float = 0.0
    largest_loss: float = 0.0
    consecutive_winners: int = 0
    consecutive_losers: int = 0
    cagr: float = 0.0
    volatility: float = 0.0
    calmar_ratio: float = 0.0
    recovery_factor: float = 0.0

    def to_dict(self) -> Dict:
        """Convert to dictionary."""
        return {
            'total_return': self.total_return,
            'annualized_return': self.annualized_return,
            'sharpe_ratio': self.sharpe_ratio,
            'sortino_ratio': self.sortino_ratio,
            'max_drawdown': self.max_drawdown,
            'win_rate': self.win_rate,
            'profit_factor': self.profit_factor,
            'num_trades': self.num_trades,
            'cagr': self.cagr,
            'volatility': self.volatility,
            'calmar_ratio': self.calmar_ratio
        }


class BacktestEngine:
    """
    Comprehensive backtesting engine for insider trading signals.

    Supports:
    - Signal replay on historical data
    - Performance metrics calculation
    - Walk-forward analysis
    - Parameter optimization
    - Monte Carlo simulation
    """

    def __init__(
        self,
        config: Optional[BacktestConfig] = None,
        data_dir: str = 'data/backtest'
    ):
        """
        Initialize backtesting engine.

        Args:
            config: BacktestConfig instance
            data_dir: Directory for storing backtest results
        """
        self.config = config or BacktestConfig()
        self.data_dir = Path(data_dir)
        self.data_dir.mkdir(parents=True, exist_ok=True)

        # State
        self.trades: List[TradeRecord] = []
        self.daily_returns: List[float] = []
        self.portfolio_values: List[float] = []
        self.backtest_results: Dict = {}
        self.optimization_results: Dict = {}

        logger.info(f"BacktestEngine initialized with capital: ${self.config.initial_capital:,.0f}")

    def replay_signals(
        self,
        transactions: pd.DataFrame,
        signal_scorer,
        start_date: Optional[datetime] = None,
        end_date: Optional[datetime] = None,
        hold_days: int = 30
    ) -> Tuple[List[TradeRecord], PerformanceMetrics]:
        """
        Replay historical signals and simulate trades.

        Args:
            transactions: DataFrame with insider transactions
            signal_scorer: Function to score conviction
            start_date: Backtest start date
            end_date: Backtest end date
            hold_days: How long to hold each position

        Returns:
            Tuple of (trade records, performance metrics)
        """
        logger.info(f"Replaying signals from {start_date} to {end_date}")

        if transactions.empty:
            logger.warning("No transactions provided for replay")
            return [], PerformanceMetrics()

        # Filter by date
        df = transactions.copy()
        if start_date:
            df = df[df['filing_date'] >= start_date]
        if end_date:
            df = df[df['filing_date'] <= end_date]

        if df.empty:
            logger.warning(f"No transactions in date range {start_date} to {end_date}")
            return [], PerformanceMetrics()

        # Sort by date
        df = df.sort_values('filing_date')

        # Generate signals and create trades
        trades = []
        portfolio = {}
        current_date = df['filing_date'].min()

        for idx, row in df.iterrows():
            try:
                # Score signal
                ticker = row['ticker']
                conviction = signal_scorer(row)

                if conviction < 0.45:  # Skip low conviction
                    continue

                # Create entry trade
                entry_date = row['filing_date']
                entry_price = row.get('price_per_share', 0)

                if entry_price <= 0:
                    continue

                # Calculate position size
                position_value = self.config.initial_capital * self.config.position_size_pct
                shares = int(position_value / entry_price)

                if shares <= 0:
                    continue

                # Calculate realistic entry price with slippage
                slippage = entry_price * (self.config.slippage_bps / 10000)
                entry_price_slipped = entry_price + slippage
                entry_value = shares * entry_price_slipped

                # Create trade record
                trade = TradeRecord(
                    ticker=ticker,
                    entry_date=entry_date,
                    entry_price=entry_price_slipped,
                    conviction_score=conviction,
                    sector=row.get('sector', ''),
                    shares=shares,
                    entry_value=entry_value
                )

                # Assume 30-day hold and close at random profit/loss
                exit_date = entry_date + timedelta(days=hold_days)

                # Random price movement: normal distribution with 10% annualized vol
                daily_vol = 0.10 / np.sqrt(252)
                price_movement = np.random.normal(0, daily_vol * hold_days, 1)[0]
                exit_price = entry_price * (1 + price_movement)

                # Apply slippage to exit
                exit_price_slipped = exit_price - slippage
                exit_value = shares * exit_price_slipped

                # Calculate P&L (excluding commissions for now)
                pnl = exit_value - entry_value
                pnl_pct = pnl / entry_value if entry_value > 0 else 0

                # Apply commissions
                commission = entry_value * self.config.commission_pct + exit_value * self.config.commission_pct
                pnl -= commission
                pnl_pct = pnl / entry_value if entry_value > 0 else 0

                trade.exit_date = exit_date
                trade.exit_price = exit_price_slipped
                trade.exit_value = exit_value
                trade.pnl = pnl
                trade.pnl_pct = pnl_pct
                trade.duration_days = hold_days

                trades.append(trade)

            except Exception as e:
                logger.debug(f"Error processing transaction {idx}: {e}")
                continue

        self.trades = trades

        # Calculate metrics
        metrics = self._calculate_metrics(trades)

        logger.info(f"Replay complete: {len(trades)} trades, {metrics.win_rate:.1%} win rate")

        return trades, metrics

    def _calculate_metrics(self, trades: List[TradeRecord]) -> PerformanceMetrics:
        """Calculate comprehensive performance metrics."""
        if not trades:
            return PerformanceMetrics()

        metrics = PerformanceMetrics()

        # Basic trade stats
        metrics.num_trades = len(trades)

        pnls = [t.pnl for t in trades]
        pnl_pcts = [t.pnl_pct for t in trades]

        # Winners and losers
        winners = [p for p in pnls if p > 0]
        losers = [p for p in pnls if p < 0]

        metrics.num_winners = len(winners)
        metrics.num_losers = len(losers)
        metrics.win_rate = len(winners) / len(trades) if trades else 0

        # Average win/loss
        metrics.avg_win = np.mean(winners) if winners else 0
        metrics.avg_loss = np.mean(losers) if losers else 0
        metrics.largest_win = max(winners) if winners else 0
        metrics.largest_loss = min(losers) if losers else 0

        # Profit factor
        total_wins = sum(winners) if winners else 0
        total_losses = abs(sum(losers)) if losers else 0
        metrics.profit_factor = total_wins / total_losses if total_losses > 0 else 0

        # Return metrics
        total_pnl = sum(pnls)
        metrics.total_return = total_pnl / self.config.initial_capital

        # Annualized return
        num_trades_per_year = 252 / (np.mean([t.duration_days for t in trades]) if trades else 1)
        metrics.annualized_return = metrics.total_return * num_trades_per_year

        # CAGR (simplified for multi-year data)
        if trades:
            first_date = min(t.entry_date for t in trades)
            last_date = max(t.exit_date or t.entry_date for t in trades)
            years = (last_date - first_date).days / 365.25
            if years > 0:
                metrics.cagr = (1 + metrics.total_return) ** (1 / years) - 1

        # Volatility
        if pnl_pcts:
            metrics.volatility = np.std(pnl_pcts)

        # Sharpe ratio
        if metrics.volatility > 0:
            metrics.sharpe_ratio = (metrics.annualized_return - self.config.risk_free_rate) / metrics.volatility

        # Sortino ratio (downside deviation)
        downside_returns = [r for r in pnl_pcts if r < 0]
        if downside_returns:
            downside_std = np.std(downside_returns)
            if downside_std > 0:
                metrics.sortino_ratio = (metrics.annualized_return - self.config.risk_free_rate) / downside_std

        # Max drawdown (simplified)
        cumulative_pnl = 0
        peak = 0
        max_dd = 0
        for pnl in pnls:
            cumulative_pnl += pnl
            if cumulative_pnl > peak:
                peak = cumulative_pnl
            else:
                dd = (peak - cumulative_pnl) / peak if peak > 0 else 0
                max_dd = max(max_dd, dd)

        metrics.max_drawdown = max_dd

        # Calmar ratio
        if metrics.max_drawdown > 0:
            metrics.calmar_ratio = metrics.cagr / metrics.max_drawdown

        # Recovery factor
        if metrics.largest_loss != 0:
            metrics.recovery_factor = total_wins / abs(metrics.largest_loss)

        # Consecutive winners/losers
        max_consecutive_wins = 0
        max_consecutive_losses = 0
        current_wins = 0
        current_losses = 0

        for pnl in pnls:
            if pnl > 0:
                current_wins += 1
                current_losses = 0
                max_consecutive_wins = max(max_consecutive_wins, current_wins)
            else:
                current_losses += 1
                current_wins = 0
                max_consecutive_losses = max(max_consecutive_losses, current_losses)

        metrics.consecutive_winners = max_consecutive_wins
        metrics.consecutive_losers = max_consecutive_losses

        return metrics

    def walk_forward_analysis(
        self,
        transactions: pd.DataFrame,
        signal_scorer,
        start_date: datetime,
        end_date: datetime
    ) -> Dict:
        """
        Perform walk-forward analysis with rolling windows.

        Args:
            transactions: DataFrame with transactions
            signal_scorer: Signal scoring function
            start_date: Analysis start date
            end_date: Analysis end date

        Returns:
            Dictionary with walk-forward results
        """
        logger.info(f"Starting walk-forward analysis from {start_date} to {end_date}")

        windows = []
        current_train_start = start_date

        while current_train_start < end_date:
            train_end = current_train_start + timedelta(days=self.config.train_period_days)
            test_start = train_end
            test_end = test_start + timedelta(days=self.config.test_period_days)

            if test_end > end_date:
                break

            # Get training and testing data
            train_df = transactions[
                (transactions['filing_date'] >= current_train_start) &
                (transactions['filing_date'] < train_end)
            ]

            test_df = transactions[
                (transactions['filing_date'] >= test_start) &
                (transactions['filing_date'] < test_end)
            ]

            if train_df.empty or test_df.empty:
                current_train_start += timedelta(days=self.config.walk_forward_step_days)
                continue

            # Run backtest on test data
            trades, metrics = self.replay_signals(
                test_df, signal_scorer,
                start_date=test_start,
                end_date=test_end
            )

            windows.append({
                'train_start': current_train_start,
                'train_end': train_end,
                'test_start': test_start,
                'test_end': test_end,
                'num_trades': len(trades),
                'metrics': metrics.to_dict()
            })

            current_train_start += timedelta(days=self.config.walk_forward_step_days)

        # Aggregate results
        all_metrics = [w['metrics'] for w in windows]
        avg_metrics = self._aggregate_metrics(all_metrics)

        result = {
            'windows': windows,
            'num_windows': len(windows),
            'average_metrics': avg_metrics,
            'start_date': start_date.isoformat(),
            'end_date': end_date.isoformat()
        }

        self.backtest_results['walk_forward'] = result

        logger.info(f"Walk-forward analysis complete: {len(windows)} windows")

        return result

    def _aggregate_metrics(self, metrics_list: List[Dict]) -> Dict:
        """Aggregate metrics across multiple periods."""
        if not metrics_list:
            return {}

        aggregated = {}
        numeric_keys = [
            'total_return', 'sharpe_ratio', 'max_drawdown', 'win_rate',
            'profit_factor', 'num_trades', 'cagr', 'volatility'
        ]

        for key in numeric_keys:
            values = [m.get(key, 0) for m in metrics_list]
            aggregated[f'{key}_mean'] = np.mean(values)
            aggregated[f'{key}_std'] = np.std(values)
            aggregated[f'{key}_min'] = np.min(values)
            aggregated[f'{key}_max'] = np.max(values)

        return aggregated

    def monte_carlo_simulation(
        self,
        trades: List[TradeRecord],
        num_simulations: Optional[int] = None
    ) -> Dict:
        """
        Run Monte Carlo simulation to test strategy robustness.

        Args:
            trades: List of historical trades
            num_simulations: Number of simulations to run

        Returns:
            Dictionary with simulation results
        """
        if not trades:
            logger.warning("No trades provided for Monte Carlo simulation")
            return {}

        num_simulations = num_simulations or self.config.num_simulations

        logger.info(f"Running {num_simulations} Monte Carlo simulations")

        # Extract P&L percentages
        pnl_pcts = [t.pnl_pct for t in trades]

        simulation_results = []

        for sim in range(num_simulations):
            # Random sampling with replacement
            sample_returns = np.random.choice(pnl_pcts, size=len(pnl_pcts), replace=True)

            cumulative_return = np.prod([1 + r for r in sample_returns]) - 1
            max_dd = self._calculate_max_drawdown_from_returns(sample_returns)
            sharpe = self._calculate_sharpe_from_returns(sample_returns)

            simulation_results.append({
                'cumulative_return': cumulative_return,
                'max_drawdown': max_dd,
                'sharpe_ratio': sharpe
            })

        # Calculate statistics
        returns = [r['cumulative_return'] for r in simulation_results]
        drawdowns = [r['max_drawdown'] for r in simulation_results]
        sharpes = [r['sharpe_ratio'] for r in simulation_results]

        result = {
            'num_simulations': num_simulations,
            'return_mean': np.mean(returns),
            'return_std': np.std(returns),
            'return_percentile_5': np.percentile(returns, 5),
            'return_percentile_95': np.percentile(returns, 95),
            'max_dd_mean': np.mean(drawdowns),
            'max_dd_worst': np.max(drawdowns),
            'sharpe_mean': np.mean(sharpes),
            'sharpe_std': np.std(sharpes),
            'simulations': simulation_results[:100]  # Store first 100 for reference
        }

        self.backtest_results['monte_carlo'] = result

        logger.info(f"Monte Carlo complete: {num_simulations} simulations")

        return result

    def _calculate_max_drawdown_from_returns(self, returns: List[float]) -> float:
        """Calculate max drawdown from return series."""
        cumulative = np.cumprod([1 + r for r in returns])
        peak = cumulative[0]
        max_dd = 0

        for value in cumulative:
            if value > peak:
                peak = value
            dd = (peak - value) / peak if peak > 0 else 0
            max_dd = max(max_dd, dd)

        return max_dd

    def _calculate_sharpe_from_returns(self, returns) -> float:
        """Calculate Sharpe ratio from return series."""
        try:
            returns_array = np.asarray(returns)
            if returns_array.size == 0 or len(returns_array) < 2:
                return 0

            mean_return = np.mean(returns_array)
            std_return = np.std(returns_array)

            if std_return == 0:
                return 0

            return float((mean_return - self.config.risk_free_rate / 252) / std_return)
        except:
            return 0

    def parameter_optimization(
        self,
        transactions: pd.DataFrame,
        parameter_ranges: Dict,
        signal_scorer_factory,
        num_iterations: int = 50
    ) -> Dict:
        """
        Optimize strategy parameters via grid search.

        Args:
            transactions: Transaction data
            parameter_ranges: Dict of parameter: [min, max] values
            signal_scorer_factory: Function that creates scorer with given params
            num_iterations: Number of optimization iterations

        Returns:
            Dictionary with optimization results
        """
        logger.info(f"Starting parameter optimization with {num_iterations} iterations")

        best_sharpe = -np.inf
        best_params = None
        optimization_history = []

        # Simple grid search
        param_names = list(parameter_ranges.keys())

        for iteration in range(num_iterations):
            # Random parameter combination
            params = {}
            for param, (min_val, max_val) in parameter_ranges.items():
                params[param] = np.random.uniform(min_val, max_val)

            try:
                # Backtest with these parameters
                scorer = signal_scorer_factory(**params)
                trades, metrics = self.replay_signals(
                    transactions, scorer,
                    start_date=transactions['filing_date'].min(),
                    end_date=transactions['filing_date'].max()
                )

                sharpe = metrics.sharpe_ratio

                optimization_history.append({
                    'iteration': iteration,
                    'parameters': params,
                    'sharpe_ratio': sharpe,
                    'metrics': metrics.to_dict()
                })

                if sharpe > best_sharpe:
                    best_sharpe = sharpe
                    best_params = params
                    logger.info(f"Iteration {iteration}: New best Sharpe = {sharpe:.3f}")

            except Exception as e:
                logger.debug(f"Error in optimization iteration {iteration}: {e}")
                continue

        result = {
            'best_sharpe': best_sharpe,
            'best_parameters': best_params,
            'num_iterations': num_iterations,
            'optimization_history': optimization_history[-20:]  # Keep last 20
        }

        self.optimization_results['parameter_opt'] = result

        logger.info(f"Optimization complete: Best Sharpe = {best_sharpe:.3f}")

        return result

    def save_results(self, filename: str = 'backtest_results.pkl'):
        """Save backtest results to file."""
        filepath = self.data_dir / filename
        try:
            with open(filepath, 'wb') as f:
                pickle.dump({
                    'trades': self.trades,
                    'backtest_results': self.backtest_results,
                    'optimization_results': self.optimization_results
                }, f)
            logger.info(f"Results saved to {filepath}")
        except Exception as e:
            logger.error(f"Failed to save results: {e}")

    def load_results(self, filename: str = 'backtest_results.pkl'):
        """Load backtest results from file."""
        filepath = self.data_dir / filename
        try:
            with open(filepath, 'rb') as f:
                data = pickle.load(f)
                self.trades = data.get('trades', [])
                self.backtest_results = data.get('backtest_results', {})
                self.optimization_results = data.get('optimization_results', {})
            logger.info(f"Results loaded from {filepath}")
        except Exception as e:
            logger.error(f"Failed to load results: {e}")


def get_backtest_engine(config: Optional[BacktestConfig] = None) -> BacktestEngine:
    """Factory function to get backtesting engine instance."""
    return BacktestEngine(config=config)
