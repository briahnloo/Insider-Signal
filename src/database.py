"""
Database utilities for managing insider trading data.
"""
import sqlite3
from pathlib import Path
from datetime import datetime
from typing import List, Dict, Optional
import pandas as pd
from sqlalchemy import create_engine, Column, Integer, String, Date, Float, DateTime, func, UniqueConstraint
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import sessionmaker
from sqlalchemy.exc import IntegrityError
from loguru import logger

import config

# SQLAlchemy setup
Base = declarative_base()
engine = create_engine(config.DATABASE_URL)
Session = sessionmaker(bind=engine)


class InsiderTransaction(Base):
    """SQLAlchemy model for insider transactions."""
    __tablename__ = 'insider_transactions'
    __table_args__ = (
        UniqueConstraint('ticker', 'insider_name', 'transaction_date', 
                         'shares', 'price_per_share', 
                         name='unique_transaction'),
    )

    id = Column(Integer, primary_key=True)
    ticker = Column(String, nullable=False)
    insider_name = Column(String, nullable=False)
    insider_title = Column(String)
    transaction_date = Column(Date, nullable=False)
    filing_date = Column(Date, nullable=False)
    filing_speed_days = Column(Integer)
    shares = Column(Integer, nullable=False)
    price_per_share = Column(Float)
    total_value = Column(Float, nullable=False)
    transaction_type = Column(String, default='PURCHASE')
    form_4_url = Column(String)
    created_at = Column(DateTime, default=datetime.utcnow)


def initialize_database():
    """Create all tables if they don't exist."""
    try:
        Base.metadata.create_all(engine)
        logger.info("Database initialized successfully")
    except Exception as e:
        logger.error(f"Failed to initialize database: {e}")
        raise


def insert_transaction(transaction_data: Dict) -> Optional[int]:
    """
    Insert a single insider transaction into the database.

    Args:
        transaction_data: Dictionary with transaction details

    Returns:
        Transaction ID if successful, None if duplicate
    """
    session = Session()
    try:
        # Calculate filing speed
        filing_speed = (
            transaction_data['filing_date'] - transaction_data['transaction_date']
        ).days

        transaction = InsiderTransaction(
            ticker=transaction_data['ticker'],
            insider_name=transaction_data['insider_name'],
            insider_title=transaction_data.get('insider_title', ''),
            transaction_date=transaction_data['transaction_date'],
            filing_date=transaction_data['filing_date'],
            filing_speed_days=filing_speed,
            shares=transaction_data['shares'],
            price_per_share=transaction_data.get('price_per_share'),
            total_value=transaction_data['total_value'],
            transaction_type=transaction_data.get('transaction_type', 'PURCHASE'),
            form_4_url=transaction_data.get('form_4_url')
        )
        session.add(transaction)
        session.commit()
        transaction_id = transaction.id
        logger.debug(f"Inserted transaction {transaction_id} for {transaction_data['ticker']}")
        return transaction_id
    except IntegrityError as e:
        session.rollback()
        logger.info(f"Skipped duplicate transaction for {transaction_data['ticker']} - {transaction_data['insider_name']} on {transaction_data['transaction_date']}")
        return None
    except Exception as e:
        session.rollback()
        logger.error(f"Failed to insert transaction: {e}")
        return None
    finally:
        session.close()


def get_recent_transactions(days: int = 30, min_value: float = 0) -> pd.DataFrame:
    """
    Retrieve recent insider transactions.

    Args:
        days: Number of days to look back
        min_value: Minimum transaction value to include

    Returns:
        DataFrame with transaction data
    """
    session = Session()
    try:
        query = session.query(InsiderTransaction).filter(
            InsiderTransaction.total_value >= min_value
        ).order_by(InsiderTransaction.filing_date.desc())

        transactions = query.all()
        data = []
        for t in transactions:
            data.append({
                'id': t.id,
                'ticker': t.ticker,
                'insider_name': t.insider_name,
                'insider_title': t.insider_title,
                'transaction_date': t.transaction_date,
                'filing_date': t.filing_date,
                'filing_speed_days': t.filing_speed_days,
                'shares': t.shares,
                'price_per_share': t.price_per_share,
                'total_value': t.total_value,
                'transaction_type': t.transaction_type
            })

        return pd.DataFrame(data)
    except Exception as e:
        logger.error(f"Failed to retrieve transactions: {e}")
        return pd.DataFrame()
    finally:
        session.close()


def get_transactions_by_ticker(ticker: str, days: int = 90) -> pd.DataFrame:
    """
    Get all insider transactions for a specific ticker.

    Args:
        ticker: Stock ticker symbol
        days: Number of days to look back

    Returns:
        DataFrame with transaction data for the ticker
    """
    session = Session()
    try:
        query = session.query(InsiderTransaction).filter(
            InsiderTransaction.ticker == ticker.upper()
        ).order_by(InsiderTransaction.filing_date.desc())

        transactions = query.all()
        data = []
        for t in transactions:
            data.append({
                'insider_name': t.insider_name,
                'insider_title': t.insider_title,
                'transaction_date': t.transaction_date,
                'filing_date': t.filing_date,
                'filing_speed_days': t.filing_speed_days,
                'shares': t.shares,
                'price_per_share': t.price_per_share,
                'total_value': t.total_value
            })

        return pd.DataFrame(data)
    except Exception as e:
        logger.error(f"Failed to retrieve transactions for {ticker}: {e}")
        return pd.DataFrame()
    finally:
        session.close()


def get_all_recent_transactions(days: int = 30, min_value: float = 0) -> pd.DataFrame:
    """
    Retrieve all recent insider transactions across all tickers.

    Args:
        days: Number of days to look back
        min_value: Minimum transaction value to include

    Returns:
        DataFrame with transaction data
    """
    session = Session()
    try:
        from datetime import timedelta
        cutoff_date = datetime.now() - timedelta(days=days)

        query = session.query(InsiderTransaction).filter(
            InsiderTransaction.filing_date >= cutoff_date.date(),
            InsiderTransaction.total_value >= min_value
        ).order_by(InsiderTransaction.filing_date.desc())

        transactions = query.all()
        data = []
        for t in transactions:
            data.append({
                'ticker': t.ticker,
                'insider_name': t.insider_name,
                'insider_title': t.insider_title,
                'transaction_date': t.transaction_date,
                'filing_date': t.filing_date,
                'filing_speed_days': t.filing_speed_days,
                'shares': t.shares,
                'price_per_share': t.price_per_share,
                'total_value': t.total_value,
                'transaction_type': t.transaction_type
            })

        return pd.DataFrame(data)
    except Exception as e:
        logger.error(f"Failed to retrieve recent transactions: {e}")
        return pd.DataFrame()
    finally:
        session.close()


def get_database_stats() -> Dict:
    """Get basic statistics about the database."""
    session = Session()
    try:
        total = session.query(InsiderTransaction).count()
        unique_tickers = session.query(InsiderTransaction.ticker).distinct().count()
        avg_value = session.query(func.avg(InsiderTransaction.total_value)).scalar()

        # Handle None case when database is empty
        avg_value = avg_value if avg_value is not None else 0.0

        stats = {
            'total_transactions': total,
            'unique_tickers': unique_tickers,
            'average_transaction_value': avg_value
        }
        return stats
    except Exception as e:
        logger.error(f"Failed to get database stats: {e}")
        return {
            'total_transactions': 0,
            'unique_tickers': 0,
            'average_transaction_value': 0.0
        }
    finally:
        session.close()


if __name__ == "__main__":
    initialize_database()
    logger.info("Database schema ready")
