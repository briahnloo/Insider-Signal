"""
Insider Track Record Scoring - Individual insider performance tracking.

Instead of treating all insiders equally, this module tracks each insider's
historical performance: win rate, average return, timing accuracy, etc.

Example:
  - CEO at AAPL: 78% win rate, +12.5% avg return (strong signal)
  - CFO at XYZ: 32% win rate, -4.2% avg return (weak/negative signal)

When these insiders make new trades, we weight them by their track record.
This is a key differentiator - most systems give all insiders equal weight.
"""

from typing import Dict, List, Optional, Tuple
from datetime import datetime, timedelta
from dataclasses import dataclass, field
from loguru import logger
import pandas as pd
from functools import lru_cache
import json


@dataclass
class InsiderRecord:
    """Historical performance record for a single insider."""
    insider_name: str
    company_ticker: str
    win_count: int = 0
    loss_count: int = 0
    neutral_count: int = 0
    total_return: float = 0.0
    best_trade: float = -1.0
    worst_trade: float = 1.0
    avg_holding_days: float = 0.0
    last_transaction_date: Optional[datetime] = None
    last_activity: Optional[datetime] = None

    def __post_init__(self):
        """Initialize computed fields."""
        self._update_computed()

    def _update_computed(self):
        """Update all computed metrics."""
        pass

    @property
    def total_transactions(self) -> int:
        """Total number of tracked transactions."""
        return self.win_count + self.loss_count + self.neutral_count

    @property
    def win_rate(self) -> float:
        """Win rate as fraction [0, 1]."""
        if self.total_transactions == 0:
            return 0.0
        return self.win_count / self.total_transactions

    @property
    def win_rate_pct(self) -> str:
        """Win rate as percentage string."""
        return f"{self.win_rate * 100:.1f}%"

    @property
    def avg_return(self) -> float:
        """Average return per transaction."""
        if self.total_transactions == 0:
            return 0.0
        return self.total_return / self.total_transactions

    @property
    def avg_return_pct(self) -> str:
        """Average return as percentage string."""
        return f"{self.avg_return * 100:+.2f}%"

    @property
    def credibility_score(self) -> float:
        """
        Score 0-1 indicating insider credibility based on track record.

        Factors:
        - Win rate (50% weight): Higher is better
        - Sample size (50% weight): More samples = more reliable
        """
        if self.total_transactions < 1:
            return 0.0  # Not enough data

        # Win rate component (50%)
        # 50% win rate = 0.0, 100% win rate = 1.0
        win_rate_component = (self.win_rate - 0.5) * 2.0
        win_rate_component = max(0.0, min(1.0, win_rate_component))

        # Sample size component (50%)
        # 10+ trades = full confidence
        size_component = min(1.0, self.total_transactions / 10.0)

        score = (
            win_rate_component * 0.50 +
            size_component * 0.50
        )

        return min(1.0, max(0.0, score))

    @property
    def credibility_level(self) -> str:
        """Credibility level as readable string."""
        score = self.credibility_score
        if score >= 0.8:
            return "ELITE"
        elif score >= 0.6:
            return "STRONG"
        elif score >= 0.4:
            return "MODERATE"
        elif score >= 0.2:
            return "WEAK"
        else:
            return "UNPROVEN"

    @property
    def confidence_multiplier(self) -> float:
        """
        Multiplier for conviction score based on insider credibility.

        Range: 0.4x - 1.5x
        - 0.4x: Insider with negative track record (avoid/discount)
        - 1.0x: Average insider (baseline)
        - 1.5x: Elite insider with strong track record
        """
        return 0.4 + (self.credibility_score * 1.1)  # Maps [0, 1] to [0.4, 1.5]

    def record_transaction(
        self,
        entry_price: float,
        exit_price: float,
        holding_days: int,
        outcome: str = 'neutral'  # 'win', 'loss', or 'neutral'
    ) -> None:
        """
        Record a completed transaction for this insider.

        Args:
            entry_price: Price at insider transaction
            exit_price: Price at exit
            holding_days: Days held
            outcome: Whether it was a win, loss, or neutral
        """
        ret = (exit_price - entry_price) / entry_price

        if outcome == 'win':
            self.win_count += 1
        elif outcome == 'loss':
            self.loss_count += 1
        else:
            self.neutral_count += 1

        self.total_return += ret
        self.best_trade = max(self.best_trade, ret)
        self.worst_trade = min(self.worst_trade, ret)

        # Update average holding days
        if self.total_transactions > 0:
            self.avg_holding_days = (
                (self.avg_holding_days * (self.total_transactions - 1) + holding_days) /
                self.total_transactions
            )
        else:
            self.avg_holding_days = holding_days

        self.last_transaction_date = datetime.now()

    def is_recent_activity(self, days: int = 90) -> bool:
        """Check if insider has had recent activity."""
        if self.last_activity is None:
            return False
        return (datetime.now() - self.last_activity).days <= days

    def to_dict(self) -> Dict:
        """Convert to dictionary for serialization."""
        return {
            'insider_name': self.insider_name,
            'company_ticker': self.company_ticker,
            'win_count': self.win_count,
            'loss_count': self.loss_count,
            'neutral_count': self.neutral_count,
            'total_transactions': self.total_transactions,
            'win_rate': self.win_rate,
            'win_rate_pct': self.win_rate_pct,
            'avg_return': self.avg_return,
            'avg_return_pct': self.avg_return_pct,
            'credibility_score': self.credibility_score,
            'credibility_level': self.credibility_level,
            'confidence_multiplier': self.confidence_multiplier,
            'best_trade': self.best_trade,
            'worst_trade': self.worst_trade,
            'avg_holding_days': self.avg_holding_days,
        }


class InsiderTrackRecordTracker:
    """
    Tracks performance history for individual insiders across all companies.

    Attributes:
        insider_records: Dict mapping (insider_name, ticker) -> InsiderRecord
        last_update: Timestamp of last update
    """

    def __init__(self):
        """Initialize tracker."""
        self.insider_records: Dict[Tuple[str, str], InsiderRecord] = {}
        self.last_update: Optional[datetime] = None

    def get_or_create_record(self, insider_name: str, ticker: str) -> InsiderRecord:
        """Get existing record or create new one."""
        key = (insider_name, ticker)
        if key not in self.insider_records:
            self.insider_records[key] = InsiderRecord(
                insider_name=insider_name,
                company_ticker=ticker
            )
        return self.insider_records[key]

    def record_transaction(
        self,
        insider_name: str,
        ticker: str,
        entry_price: float,
        exit_price: float,
        holding_days: int,
        outcome: str = 'neutral'
    ) -> InsiderRecord:
        """
        Record a completed transaction.

        Returns the updated InsiderRecord.
        """
        record = self.get_or_create_record(insider_name, ticker)
        record.record_transaction(entry_price, exit_price, holding_days, outcome)
        self.last_update = datetime.now()
        return record

    def get_insider_score(self, insider_name: str, ticker: Optional[str] = None) -> float:
        """
        Get current credibility score for an insider.

        If ticker is provided, returns score for that insider at that company.
        Otherwise, returns average score across all companies.
        """
        if ticker:
            record = self.insider_records.get((insider_name, ticker))
            if record:
                return record.credibility_score
            return 0.0
        else:
            # Average across all companies
            records = [r for (name, _), r in self.insider_records.items() if name == insider_name]
            if not records:
                return 0.0
            return sum(r.credibility_score for r in records) / len(records)

    def get_insider_multiplier(self, insider_name: str, ticker: Optional[str] = None) -> float:
        """
        Get confidence multiplier for an insider.

        Range: 0.4x - 1.5x
        """
        if ticker:
            record = self.insider_records.get((insider_name, ticker))
            if record:
                return record.confidence_multiplier
            return 1.0  # Default to neutral if unknown
        else:
            # Average across all companies
            records = [r for (name, _), r in self.insider_records.items() if name == insider_name]
            if not records:
                return 1.0
            return sum(r.confidence_multiplier for r in records) / len(records)

    def get_elite_insiders(self, score_threshold: float = 0.7) -> List[Tuple[str, str, InsiderRecord]]:
        """Get all insiders with credibility score above threshold."""
        elite = []
        for (name, ticker), record in self.insider_records.items():
            if record.credibility_score >= score_threshold:
                elite.append((name, ticker, record))
        return sorted(elite, key=lambda x: x[2].credibility_score, reverse=True)

    def get_weak_insiders(self, score_threshold: float = 0.3) -> List[Tuple[str, str, InsiderRecord]]:
        """Get all insiders with credibility score below threshold."""
        weak = []
        for (name, ticker), record in self.insider_records.items():
            if record.credibility_score < score_threshold:
                weak.append((name, ticker, record))
        return sorted(weak, key=lambda x: x[2].credibility_score)

    def generate_report(self) -> str:
        """Generate readable report of top/bottom insiders."""
        lines = []
        lines.append("\n" + "="*100)
        lines.append("INSIDER TRACK RECORD REPORT")
        lines.append("="*100)

        # Top performers
        elite = self.get_elite_insiders(0.6)
        if elite:
            lines.append("\n📈 TOP PERFORMERS (Credibility ≥ 60%):")
            lines.append("-" * 100)
            lines.append(f"{'Insider':<25} {'Company':<10} {'Trades':<8} {'Win %':<10} {'Avg Return':<12} {'Level':<12}")
            lines.append("-" * 100)
            for name, ticker, record in elite[:10]:
                lines.append(
                    f"{name:<25} {ticker:<10} {record.total_transactions:<8} "
                    f"{record.win_rate_pct:<10} {record.avg_return_pct:<12} {record.credibility_level:<12}"
                )

        # Bottom performers
        weak = self.get_weak_insiders(0.3)
        if weak:
            lines.append("\n📉 WEAK PERFORMERS (Credibility < 30%):")
            lines.append("-" * 100)
            lines.append(f"{'Insider':<25} {'Company':<10} {'Trades':<8} {'Win %':<10} {'Avg Return':<12} {'Level':<12}")
            lines.append("-" * 100)
            for name, ticker, record in weak[:10]:
                lines.append(
                    f"{name:<25} {ticker:<10} {record.total_transactions:<8} "
                    f"{record.win_rate_pct:<10} {record.avg_return_pct:<12} {record.credibility_level:<12}"
                )

        lines.append("\n" + "="*100)
        return "\n".join(lines)

    def to_dict(self) -> Dict:
        """Convert all records to dictionary for serialization."""
        return {
            f"{name}@{ticker}": record.to_dict()
            for (name, ticker), record in self.insider_records.items()
        }


def get_insider_track_record_tracker() -> InsiderTrackRecordTracker:
    """Factory function to get tracker instance."""
    return InsiderTrackRecordTracker()


# Example usage and testing
if __name__ == "__main__":
    tracker = get_insider_track_record_tracker()

    # Simulate some transactions
    # CEO at AAPL - strong performer
    tracker.record_transaction("Tim Cook", "AAPL", 100, 112, 30, 'win')
    tracker.record_transaction("Tim Cook", "AAPL", 105, 118, 25, 'win')
    tracker.record_transaction("Tim Cook", "AAPL", 110, 115, 20, 'win')
    tracker.record_transaction("Tim Cook", "AAPL", 115, 112, 15, 'loss')

    # CFO at XYZ - weak performer
    tracker.record_transaction("Jane Doe", "XYZ", 50, 48, 20, 'loss')
    tracker.record_transaction("Jane Doe", "XYZ", 52, 50, 25, 'loss')
    tracker.record_transaction("Jane Doe", "XYZ", 55, 54, 18, 'neutral')

    # Print report
    print(tracker.generate_report())

    # Get multipliers for new transactions
    print("\nConfidence Multipliers:")
    print(f"  Tim Cook (AAPL): {tracker.get_insider_multiplier('Tim Cook', 'AAPL')}x")
    print(f"  Jane Doe (XYZ): {tracker.get_insider_multiplier('Jane Doe', 'XYZ')}x")
