"""
Comprehensive Portfolio Management System

Implements:
- Dynamic position sizing based on conviction and volatility
- Risk management with sector limits
- Correlation analysis to avoid over-concentration
- Portfolio rebalancing logic
- Drawdown protection and stress testing
- Risk metrics: Sharpe ratio, max drawdown, VaR
"""

from typing import Dict, List, Optional, Tuple
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from pathlib import Path
import json
import pickle
import numpy as np
import pandas as pd
from loguru import logger

try:
    from sklearn.preprocessing import StandardScaler
    from sklearn.covariance import LedoitWolf
    SKLEARN_AVAILABLE = True
except:
    SKLEARN_AVAILABLE = False


@dataclass
class Position:
    """Represents a single position in the portfolio."""
    ticker: str
    entry_price: float
    entry_date: datetime
    shares: int
    conviction_score: float
    sector: str = ""
    conviction_multiplier: float = 1.0  # Multi-insider, etc.
    entry_signal_type: str = ""  # BUY, ACCUMULATE, etc.

    @property
    def position_value(self) -> float:
        """Current position value (at entry price)."""
        return self.entry_price * self.shares

    @property
    def weight_pct(self) -> float:
        """Weight will be calculated by portfolio."""
        return 0.0


@dataclass
class PortfolioMetrics:
    """Portfolio-level risk and performance metrics."""
    total_value: float
    cash: float
    num_positions: int
    sector_concentrations: Dict[str, float] = field(default_factory=dict)

    # Risk metrics
    portfolio_volatility: float = 0.0
    sharpe_ratio: float = 0.0
    max_drawdown: float = 0.0
    var_95: float = 0.0  # Value at Risk at 95% confidence
    var_99: float = 0.0  # Value at Risk at 99% confidence

    # Correlation metrics
    avg_correlation: float = 0.0
    max_correlation: float = 0.0
    concentration_risk: float = 0.0

    # Rebalancing info
    needs_rebalancing: bool = False
    last_rebalance_date: Optional[datetime] = None
    days_since_rebalance: int = 0


@dataclass
class RiskConstraints:
    """Portfolio-level risk constraints."""
    max_position_pct: float = 0.05  # Max 5% per position
    max_sector_pct: float = 0.20    # Max 20% per sector
    max_correlation_threshold: float = 0.75  # Warn if correlation > 75%
    min_diversification: int = 5     # Minimum 5 positions for diversification
    max_drawdown_limit: float = 0.15 # Stop adding if > 15% drawdown
    rebalance_frequency_days: int = 30  # Rebalance monthly
    target_cash_pct: float = 0.10   # Keep 10% in cash


class PortfolioManager:
    """
    Comprehensive portfolio management system.

    Manages:
    - Position sizing with conviction-based weighting
    - Risk metrics and monitoring
    - Sector allocation limits
    - Correlation analysis
    - Portfolio rebalancing
    - Drawdown protection
    """

    def __init__(
        self,
        account_value: float = 100000,
        data_dir: str = 'data/portfolio',
        risk_constraints: Optional[RiskConstraints] = None
    ):
        """
        Initialize portfolio manager.

        Args:
            account_value: Initial portfolio value
            data_dir: Directory for persistence
            risk_constraints: Custom risk constraints
        """
        self.account_value = account_value
        self.initial_value = account_value
        self.data_dir = Path(data_dir)
        self.data_dir.mkdir(parents=True, exist_ok=True)

        self.risk_constraints = risk_constraints or RiskConstraints()

        # Portfolio state
        self.positions: Dict[str, Position] = {}
        self.cash = account_value
        self.trade_history: List[Dict] = []
        self.metrics_history: List[PortfolioMetrics] = []
        self.last_rebalance_date = datetime.now()

        # Market data cache (price history)
        self.price_history: Dict[str, List[float]] = {}
        self.returns_history: Dict[str, List[float]] = {}

        self._load_state()

    def add_position(
        self,
        ticker: str,
        entry_price: float,
        shares: int,
        conviction_score: float,
        sector: str = "",
        signal_type: str = "BUY",
        conviction_multiplier: float = 1.0,
        allow_existing: bool = False
    ) -> Tuple[bool, str]:
        """
        Add or update a position with constraint checking.

        Args:
            ticker: Stock ticker
            entry_price: Entry price
            shares: Number of shares
            conviction_score: Conviction score (0-1)
            sector: Sector name
            signal_type: Signal type (BUY, ACCUMULATE, etc.)
            conviction_multiplier: Multiplier for multi-insider signals
            allow_existing: If True, replace existing position

        Returns:
            (success, message)
        """
        try:
            # Skip if ticker already exists and not allowing update
            if ticker in self.positions and not allow_existing:
                return False, f"{ticker} already in portfolio"

            # If replacing, return cash from old position
            if ticker in self.positions and allow_existing:
                old_position = self.positions[ticker]
                self.cash += old_position.position_value

            position_value = entry_price * shares

            # Check 1: Position size constraint
            max_position_value = self.account_value * self.risk_constraints.max_position_pct
            if position_value > max_position_value:
                shares = int(max_position_value / entry_price)
                position_value = entry_price * shares
                logger.warning(
                    f"Reduced {ticker} to max position size: "
                    f"{shares} shares (${position_value:,.0f})"
                )

            # Check 2: Cash availability
            if position_value > self.cash:
                return False, f"Insufficient cash: need ${position_value:,.0f}, have ${self.cash:,.0f}"

            # Check 3: Sector concentration (skip if already in position)
            if ticker not in self.positions:
                new_sector_pct = self._calculate_sector_pct(sector, position_value)
                if new_sector_pct > self.risk_constraints.max_sector_pct:
                    return False, (
                        f"Sector limit exceeded: {sector} would be {new_sector_pct:.1%} "
                        f"(max {self.risk_constraints.max_sector_pct:.1%})"
                    )

            # Check 4: Correlation analysis
            correlation_warning = self._check_correlation(ticker)
            if correlation_warning:
                logger.warning(f"High correlation warning for {ticker}: {correlation_warning}")

            # Check 5: Drawdown protection
            if self.get_current_drawdown() > self.risk_constraints.max_drawdown_limit:
                return False, (
                    f"Drawdown limit exceeded: {self.get_current_drawdown():.1%} "
                    f"(max {self.risk_constraints.max_drawdown_limit:.1%})"
                )

            # All checks passed - add position
            self.positions[ticker] = Position(
                ticker=ticker,
                entry_price=entry_price,
                entry_date=datetime.now(),
                shares=shares,
                conviction_score=conviction_score,
                sector=sector,
                conviction_multiplier=conviction_multiplier,
                entry_signal_type=signal_type
            )

            self.cash -= position_value

            self.trade_history.append({
                'timestamp': datetime.now().isoformat(),
                'action': 'BUY',
                'ticker': ticker,
                'shares': shares,
                'price': entry_price,
                'value': position_value,
                'conviction': conviction_score,
            })

            logger.info(
                f"Added {ticker}: {shares} shares @ ${entry_price:.2f} "
                f"(${position_value:,.0f}), conviction: {conviction_score:.2f}"
            )

            return True, f"Position added: {shares} shares of {ticker}"

        except Exception as e:
            logger.error(f"Error adding position: {e}")
            return False, f"Error: {str(e)}"

    def close_position(
        self,
        ticker: str,
        exit_price: float,
        exit_reason: str = ""
    ) -> Tuple[bool, Dict]:
        """
        Close a position and record P&L.

        Args:
            ticker: Stock ticker
            exit_price: Exit price
            exit_reason: Reason for exit

        Returns:
            (success, trade_result)
        """
        try:
            if ticker not in self.positions:
                return False, {"error": f"{ticker} not found in portfolio"}

            position = self.positions[ticker]
            entry_value = position.entry_price * position.shares
            exit_value = exit_price * position.shares
            pnl = exit_value - entry_value
            pnl_pct = pnl / entry_value if entry_value > 0 else 0

            self.cash += exit_value
            del self.positions[ticker]

            result = {
                'ticker': ticker,
                'shares': position.shares,
                'entry_price': position.entry_price,
                'exit_price': exit_price,
                'entry_value': entry_value,
                'exit_value': exit_value,
                'pnl': pnl,
                'pnl_pct': pnl_pct,
                'exit_reason': exit_reason,
                'holding_days': (datetime.now() - position.entry_date).days
            }

            self.trade_history.append({
                'timestamp': datetime.now().isoformat(),
                'action': 'SELL',
                'ticker': ticker,
                'shares': position.shares,
                'price': exit_price,
                'value': exit_value,
                'pnl': pnl,
                'pnl_pct': pnl_pct,
            })

            logger.info(
                f"Closed {ticker}: {pnl_pct:+.2%} P&L "
                f"(${pnl:+,.0f}) - {exit_reason}"
            )

            return True, result

        except Exception as e:
            logger.error(f"Error closing position: {e}")
            return False, {"error": str(e)}

    def calculate_portfolio_metrics(
        self,
        market_data: Optional[Dict[str, float]] = None
    ) -> PortfolioMetrics:
        """
        Calculate comprehensive portfolio metrics.

        Args:
            market_data: Optional dict of ticker -> current_price

        Returns:
            PortfolioMetrics object
        """
        try:
            # Calculate positions value
            positions_value = sum(p.position_value for p in self.positions.values())
            total_value = positions_value + self.cash

            # Sector concentrations
            sector_concentrations = {}
            for position in self.positions.values():
                if position.sector:
                    sector_concentrations[position.sector] = \
                        sector_concentrations.get(position.sector, 0.0) + \
                        (position.position_value / total_value if total_value > 0 else 0)

            # Calculate risk metrics
            metrics = PortfolioMetrics(
                total_value=total_value,
                cash=self.cash,
                num_positions=len(self.positions),
                sector_concentrations=sector_concentrations,
            )

            # Calculate volatility and Sharpe ratio
            if len(self.returns_history) > 1:
                returns_array = np.array(list(self.returns_history.values()))
                if returns_array.size > 0:
                    metrics.portfolio_volatility = float(np.std(returns_array, axis=0).mean())

                    # Sharpe ratio (assuming 2% risk-free rate)
                    annual_return = (total_value - self.initial_value) / self.initial_value * 252 / \
                                    max((datetime.now() - datetime.now().replace(hour=0, minute=0)).days, 1)
                    annual_volatility = metrics.portfolio_volatility * np.sqrt(252)
                    risk_free_rate = 0.02
                    metrics.sharpe_ratio = (annual_return - risk_free_rate) / annual_volatility \
                        if annual_volatility > 0 else 0

            # Max drawdown
            metrics.max_drawdown = self._calculate_max_drawdown()

            # Value at Risk
            if len(self.returns_history) > 0:
                returns_array = np.array(list(self.returns_history.values()))
                if returns_array.size > 0:
                    metrics.var_95 = float(np.percentile(returns_array, 5))
                    metrics.var_99 = float(np.percentile(returns_array, 1))

            # Correlation metrics
            if len(self.positions) > 1:
                correlations = self._calculate_correlations()
                if correlations:
                    metrics.avg_correlation = float(np.mean(correlations))
                    metrics.max_correlation = float(np.max(correlations))

            # Concentration risk (Herfindahl index)
            weights = [p.position_value / total_value for p in self.positions.values()]
            metrics.concentration_risk = float(np.sum(np.array(weights) ** 2))

            # Rebalancing check
            days_since = (datetime.now() - self.last_rebalance_date).days
            metrics.days_since_rebalance = days_since
            metrics.last_rebalance_date = self.last_rebalance_date
            metrics.needs_rebalancing = days_since > self.risk_constraints.rebalance_frequency_days

            self.metrics_history.append(metrics)
            self._save_state()

            return metrics

        except Exception as e:
            logger.error(f"Error calculating portfolio metrics: {e}")
            return PortfolioMetrics(
                total_value=self.account_value,
                cash=self.cash,
                num_positions=len(self.positions)
            )

    def rebalance_portfolio(self) -> Dict:
        """
        Rebalance portfolio to target allocations.

        Uses Modern Portfolio Theory to optimize weights.

        Returns:
            Rebalancing action plan
        """
        try:
            if len(self.positions) < 2:
                return {"action": "SKIP", "reason": "Insufficient positions for rebalancing"}

            total_value = sum(p.position_value for p in self.positions.values()) + self.cash

            # Calculate optimal weights using MPT
            optimal_weights = self._calculate_optimal_weights()

            actions = []

            for ticker, optimal_weight in optimal_weights.items():
                if ticker not in self.positions:
                    continue

                position = self.positions[ticker]
                current_weight = position.position_value / total_value
                diff_pct = optimal_weight - current_weight

                if abs(diff_pct) > 0.01:  # Only act if > 1% difference
                    actions.append({
                        'ticker': ticker,
                        'current_weight': current_weight,
                        'target_weight': optimal_weight,
                        'action': 'INCREASE' if diff_pct > 0 else 'DECREASE',
                        'adjustment_pct': diff_pct
                    })

            self.last_rebalance_date = datetime.now()
            self._save_state()

            logger.info(f"Rebalancing complete with {len(actions)} adjustments")
            return {
                'actions': actions,
                'timestamp': datetime.now().isoformat(),
                'total_value': total_value
            }

        except Exception as e:
            logger.error(f"Error rebalancing portfolio: {e}")
            return {"action": "ERROR", "reason": str(e)}

    def get_portfolio_summary(self) -> Dict:
        """Get high-level portfolio summary."""
        try:
            metrics = self.calculate_portfolio_metrics()
            total_value = sum(p.position_value for p in self.positions.values()) + self.cash

            position_summary = []
            for ticker, position in self.positions.items():
                weight = position.position_value / total_value if total_value > 0 else 0
                position_summary.append({
                    'ticker': ticker,
                    'shares': position.shares,
                    'entry_price': position.entry_price,
                    'value': position.position_value,
                    'weight': weight,
                    'conviction': position.conviction_score,
                    'sector': position.sector,
                })

            return {
                'total_value': total_value,
                'cash': self.cash,
                'cash_pct': self.cash / total_value if total_value > 0 else 0,
                'num_positions': len(self.positions),
                'positions': position_summary,
                'metrics': {
                    'sharpe_ratio': metrics.sharpe_ratio,
                    'max_drawdown': metrics.max_drawdown,
                    'portfolio_volatility': metrics.portfolio_volatility,
                    'concentration_risk': metrics.concentration_risk,
                },
                'sectors': metrics.sector_concentrations,
            }

        except Exception as e:
            logger.error(f"Error getting portfolio summary: {e}")
            return {}

    def get_risk_warnings(self) -> List[Dict]:
        """Get all active risk warnings."""
        warnings = []

        try:
            metrics = self.calculate_portfolio_metrics()

            # Check sector concentration
            for sector, pct in metrics.sector_concentrations.items():
                if pct > self.risk_constraints.max_sector_pct:
                    warnings.append({
                        'level': 'HIGH',
                        'type': 'SECTOR_CONCENTRATION',
                        'message': f"Sector '{sector}' at {pct:.1%} (limit: {self.risk_constraints.max_sector_pct:.1%})"
                    })

            # Check max drawdown
            if metrics.max_drawdown > self.risk_constraints.max_drawdown_limit:
                warnings.append({
                    'level': 'HIGH',
                    'type': 'DRAWDOWN_EXCEEDED',
                    'message': f"Max drawdown {metrics.max_drawdown:.1%} (limit: {self.risk_constraints.max_drawdown_limit:.1%})"
                })

            # Check correlation
            if metrics.max_correlation > self.risk_constraints.max_correlation_threshold:
                warnings.append({
                    'level': 'MEDIUM',
                    'type': 'HIGH_CORRELATION',
                    'message': f"Position correlation {metrics.max_correlation:.2f} (threshold: {self.risk_constraints.max_correlation_threshold:.2f})"
                })

            # Check diversification
            if len(self.positions) < self.risk_constraints.min_diversification:
                warnings.append({
                    'level': 'LOW',
                    'type': 'LOW_DIVERSIFICATION',
                    'message': f"Only {len(self.positions)} positions (minimum: {self.risk_constraints.min_diversification})"
                })

            # Check cash levels
            cash_pct = self.cash / self.account_value if self.account_value > 0 else 0
            if cash_pct < self.risk_constraints.target_cash_pct / 2:
                warnings.append({
                    'level': 'MEDIUM',
                    'type': 'LOW_CASH',
                    'message': f"Cash at {cash_pct:.1%} (target: {self.risk_constraints.target_cash_pct:.1%})"
                })

            # Check rebalancing needed
            if metrics.needs_rebalancing:
                warnings.append({
                    'level': 'LOW',
                    'type': 'REBALANCING_DUE',
                    'message': f"Portfolio rebalancing due (last: {metrics.days_since_rebalance} days ago)"
                })

        except Exception as e:
            logger.error(f"Error getting risk warnings: {e}")

        return warnings

    def get_position_recommendation(
        self,
        ticker: str,
        conviction_score: float,
        sector: str = ""
    ) -> Dict:
        """
        Get position recommendation based on portfolio constraints.

        Args:
            ticker: Stock ticker
            conviction_score: Conviction score
            sector: Sector name

        Returns:
            Recommendation dict with sizing and warnings
        """
        try:
            max_size = self.risk_constraints.max_position_pct

            # Adjust based on conviction
            if conviction_score >= 0.85:
                recommended_pct = max_size
            elif conviction_score >= 0.75:
                recommended_pct = max_size * 0.9
            elif conviction_score >= 0.65:
                recommended_pct = max_size * 0.7
            else:
                recommended_pct = max_size * 0.5

            # Check sector limit
            current_sector_pct = sum(
                p.position_value / self.account_value
                for p in self.positions.values()
                if p.sector == sector
            )
            max_sector_pct = self.risk_constraints.max_sector_pct
            available_sector_pct = max_sector_pct - current_sector_pct

            # Constrain by sector
            recommended_pct = min(recommended_pct, available_sector_pct)

            position_value = self.account_value * recommended_pct

            warnings = []
            if current_sector_pct + recommended_pct > max_sector_pct * 0.9:
                warnings.append(f"Adding to sector approaching limit")

            if position_value > self.cash:
                warnings.append(f"Insufficient cash (need ${position_value:,.0f}, have ${self.cash:,.0f})")

            return {
                'ticker': ticker,
                'recommended_pct': recommended_pct,
                'recommended_value': position_value,
                'max_conviction_based_pct': max_size * 0.9 if conviction_score >= 0.85 else max_size,
                'current_sector_pct': current_sector_pct,
                'available_sector_pct': available_sector_pct,
                'warnings': warnings,
                'ok_to_add': len(warnings) == 0
            }

        except Exception as e:
            logger.error(f"Error getting position recommendation: {e}")
            return {
                'ticker': ticker,
                'ok_to_add': False,
                'error': str(e)
            }

    # Private methods

    def _calculate_sector_pct(self, sector: str, additional_value: float) -> float:
        """Calculate sector percentage including new position."""
        try:
            total_value = sum(p.position_value for p in self.positions.values()) + self.cash
            current_sector = sum(
                p.position_value for p in self.positions.values()
                if p.sector == sector
            )
            return (current_sector + additional_value) / total_value if total_value > 0 else 0
        except:
            return 0.0

    def _check_correlation(self, ticker: str) -> Optional[str]:
        """Check if new position is highly correlated with existing positions."""
        if len(self.positions) == 0:
            return None

        # Would need price history to calculate correlation
        # For now, return None (no warning)
        return None

    def _calculate_max_drawdown(self) -> float:
        """Calculate maximum portfolio drawdown."""
        try:
            if len(self.metrics_history) < 2:
                return 0.0

            peak = self.metrics_history[0].total_value
            max_dd = 0.0

            for metrics in self.metrics_history:
                if metrics.total_value > peak:
                    peak = metrics.total_value
                dd = (peak - metrics.total_value) / peak if peak > 0 else 0
                max_dd = max(max_dd, dd)

            return max_dd
        except:
            return 0.0

    def _calculate_correlations(self) -> List[float]:
        """Calculate correlations between positions."""
        # Would need price history
        # For now return empty list
        return []

    def _calculate_optimal_weights(self) -> Dict[str, float]:
        """
        Calculate optimal weights using Modern Portfolio Theory.

        Returns:
            Dict of ticker -> optimal weight
        """
        try:
            if len(self.positions) == 0:
                return {}

            # Simple equal-weight for now (MVP)
            # In production, would use Markowitz optimization
            tickers = list(self.positions.keys())
            weight = 1.0 / len(tickers)

            return {ticker: weight for ticker in tickers}

        except Exception as e:
            logger.error(f"Error calculating optimal weights: {e}")
            return {ticker: 1.0 / max(len(self.positions), 1) for ticker in self.positions.keys()}

    def get_current_drawdown(self) -> float:
        """Get current drawdown from peak."""
        if len(self.metrics_history) == 0:
            return 0.0

        peak = max(m.total_value for m in self.metrics_history)
        current = self.metrics_history[-1].total_value if self.metrics_history else self.account_value

        return (peak - current) / peak if peak > 0 else 0.0

    def _save_state(self) -> None:
        """Save portfolio state to disk."""
        try:
            state_file = self.data_dir / 'portfolio_state.json'
            state = {
                'account_value': self.account_value,
                'cash': self.cash,
                'positions': {
                    ticker: {
                        'entry_price': pos.entry_price,
                        'entry_date': pos.entry_date.isoformat(),
                        'shares': pos.shares,
                        'conviction_score': pos.conviction_score,
                        'sector': pos.sector,
                    }
                    for ticker, pos in self.positions.items()
                },
                'last_rebalance_date': self.last_rebalance_date.isoformat(),
            }
            with open(state_file, 'w') as f:
                json.dump(state, f, indent=2)
        except Exception as e:
            logger.warning(f"Failed to save portfolio state: {e}")

    def _load_state(self) -> None:
        """Load portfolio state from disk."""
        try:
            state_file = self.data_dir / 'portfolio_state.json'
            if state_file.exists():
                with open(state_file) as f:
                    state = json.load(f)

                self.cash = state.get('cash', self.account_value)
                self.last_rebalance_date = datetime.fromisoformat(
                    state.get('last_rebalance_date', datetime.now().isoformat())
                )

                for ticker, pos_data in state.get('positions', {}).items():
                    self.positions[ticker] = Position(
                        ticker=ticker,
                        entry_price=pos_data['entry_price'],
                        entry_date=datetime.fromisoformat(pos_data['entry_date']),
                        shares=pos_data['shares'],
                        conviction_score=pos_data['conviction_score'],
                        sector=pos_data.get('sector', ''),
                    )

                logger.info(f"Loaded portfolio state with {len(self.positions)} positions")
        except Exception as e:
            logger.debug(f"No existing portfolio state to load: {e}")


def get_portfolio_manager(
    account_value: float = 100000,
    risk_constraints: Optional[RiskConstraints] = None
) -> PortfolioManager:
    """Factory function to get PortfolioManager instance."""
    return PortfolioManager(account_value, risk_constraints=risk_constraints)
