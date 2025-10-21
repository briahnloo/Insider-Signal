"""Trade performance tracking and analytics."""
from typing import Dict, List
from datetime import datetime
import pandas as pd
from loguru import logger
from sqlalchemy import create_engine, Column, Integer, String, Float, DateTime
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import sessionmaker
import config

Base = declarative_base()
engine = create_engine(config.DATABASE_URL)
Session = sessionmaker(bind=engine)


class Trade(Base):
    """SQLAlchemy model for completed trades."""
    __tablename__ = 'completed_trades'

    id = Column(Integer, primary_key=True)
    ticker = Column(String, nullable=False)
    signal_date = Column(DateTime, nullable=False)
    entry_date = Column(DateTime)
    entry_price = Column(Float)
    exit_date = Column(DateTime)
    exit_price = Column(Float)
    shares = Column(Integer)
    conviction_score = Column(Float)
    position_size_pct = Column(Float)
    profit_loss = Column(Float)
    profit_loss_pct = Column(Float)
    return_pct = Column(Float)
    status = Column(String)  # open, closed, stopped_out
    created_at = Column(DateTime, default=datetime.utcnow)


class PerformanceTracker:
    """Tracks trading performance."""

    def __init__(self):
        Base.metadata.create_all(engine)

    def log_trade(self, trade_data: Dict) -> int:
        """
        Log a new trade.

        Args:
            trade_data: Dict with trade information

        Returns:
            Trade ID
        """
        session = Session()
        try:
            trade = Trade(
                ticker=trade_data['ticker'],
                signal_date=trade_data.get('signal_date', datetime.now()),
                entry_date=trade_data.get('entry_date'),
                entry_price=trade_data.get('entry_price'),
                conviction_score=trade_data.get('conviction_score'),
                position_size_pct=trade_data.get('position_size_pct'),
                shares=trade_data.get('shares'),
                status='open',
            )
            session.add(trade)
            session.commit()
            trade_id = trade.id
            logger.info(f"Logged trade {trade_id}: {trade_data['ticker']}")
            return trade_id
        except Exception as e:
            logger.error(f"Error logging trade: {e}")
            session.rollback()
            return None
        finally:
            session.close()

    def close_trade(
        self,
        trade_id: int,
        exit_price: float,
        exit_date: datetime = None,
    ) -> Dict:
        """
        Close an open trade.

        Args:
            trade_id: Trade ID
            exit_price: Exit price
            exit_date: Exit date

        Returns:
            Dict with trade results
        """
        session = Session()
        try:
            trade = session.query(Trade).filter(Trade.id == trade_id).first()

            if not trade:
                return {'error': 'Trade not found'}

            trade.exit_price = exit_price
            trade.exit_date = exit_date or datetime.now()

            if trade.entry_price and trade.shares:
                trade.profit_loss = (exit_price - trade.entry_price) * trade.shares
                trade.profit_loss_pct = (
                    (exit_price - trade.entry_price) / trade.entry_price * 100
                )
                trade.return_pct = trade.profit_loss_pct

            # Determine status
            if trade.profit_loss < 0:
                trade.status = 'stopped_out'
            else:
                trade.status = 'closed'

            session.commit()

            result = {
                'trade_id': trade_id,
                'ticker': trade.ticker,
                'entry_price': trade.entry_price,
                'exit_price': exit_price,
                'profit_loss': trade.profit_loss,
                'profit_loss_pct': trade.profit_loss_pct,
                'status': trade.status,
            }

            logger.info(
                f"Closed trade {trade_id}: "
                f"${trade.profit_loss:,.0f} ({trade.profit_loss_pct:.2f}%)"
            )

            return result

        except Exception as e:
            logger.error(f"Error closing trade: {e}")
            session.rollback()
            return {'error': str(e)}
        finally:
            session.close()

    def get_performance_stats(self) -> Dict:
        """Calculate trading performance statistics."""
        session = Session()
        try:
            trades = session.query(Trade).filter(Trade.status != 'open').all()

            if not trades:
                return {
                    'total_trades': 0,
                    'winning_trades': 0,
                    'losing_trades': 0,
                    'win_rate': 0,
                    'avg_return': 0,
                    'total_return': 0,
                }

            closed_trades = [t for t in trades if t.status == 'closed']
            stopped_trades = [t for t in trades if t.status == 'stopped_out']

            total = len(trades)
            winners = sum(1 for t in trades if t.profit_loss > 0)
            losers = sum(1 for t in trades if t.profit_loss < 0)

            returns = [t.profit_loss_pct for t in trades if t.profit_loss_pct]
            avg_return = sum(returns) / len(returns) if returns else 0
            total_return = sum(t.profit_loss for t in trades if t.profit_loss)

            win_rate = (winners / total * 100) if total > 0 else 0

            # Calculate Sharpe ratio (simplified)
            if len(returns) > 1:
                import numpy as np
                returns_array = np.array(returns)
                sharpe = np.mean(returns_array) / (np.std(returns_array) + 1e-6)
            else:
                sharpe = 0

            stats = {
                'total_trades': total,
                'winning_trades': winners,
                'losing_trades': losers,
                'closed_trades': len(closed_trades),
                'stopped_out': len(stopped_trades),
                'win_rate': win_rate,
                'avg_return_pct': avg_return,
                'total_return_pct': sum(returns) if returns else 0,
                'sharpe_ratio': sharpe,
                'total_profit_loss': total_return,
            }

            logger.info(f"Performance: {win_rate:.1f}% win rate ({winners}/{total})")
            return stats

        except Exception as e:
            logger.error(f"Error calculating stats: {e}")
            return {}
        finally:
            session.close()

    def get_open_trades(self) -> pd.DataFrame:
        """Get all open trades."""
        session = Session()
        try:
            trades = session.query(Trade).filter(Trade.status == 'open').all()
            data = []
            for t in trades:
                data.append({
                    'id': t.id,
                    'ticker': t.ticker,
                    'entry_price': t.entry_price,
                    'shares': t.shares,
                    'conviction_score': t.conviction_score,
                    'entry_date': t.entry_date,
                })
            return pd.DataFrame(data)
        except Exception as e:
            logger.error(f"Error fetching open trades: {e}")
            return pd.DataFrame()
        finally:
            session.close()


if __name__ == "__main__":
    tracker = PerformanceTracker()
    stats = tracker.get_performance_stats()
    print(f"Performance Stats: {stats}")
