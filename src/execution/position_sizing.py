"""Dynamic position sizing based on conviction and risk."""
from typing import Dict
from loguru import logger
import config


class PositionSizer:
    """Calculates position sizes based on conviction and account risk."""

    def __init__(self, account_value: float = 100000):
        """
        Initialize position sizer.

        Args:
            account_value: Total account value
        """
        self.account_value = account_value

    def calculate_position_size(
        self,
        conviction_score: float,
        price: float,
        stop_loss_pct: float = 8.0,
        catalyst_date: bool = False,
    ) -> Dict:
        """
        Calculate position size based on conviction and risk management.

        Args:
            conviction_score: Conviction score (0-1)
            price: Stock entry price
            stop_loss_pct: Stop loss percentage
            catalyst_date: True if catalyst event (earnings, etc) soon

        Returns:
            Dict with position sizing info
        """
        try:
            # Base position size from conviction
            if conviction_score >= 0.85:
                base_pct = config.MAX_POSITION_SIZE  # 4.5%
            elif conviction_score >= 0.75:
                base_pct = config.MAX_POSITION_SIZE * 0.90  # 4.05%
            elif conviction_score >= 0.65:
                base_pct = config.BASE_POSITION_SIZE * 1.5  # 3.75%
            elif conviction_score >= 0.55:
                base_pct = config.BASE_POSITION_SIZE  # 2.5%
            elif conviction_score >= 0.45:
                base_pct = config.BASE_POSITION_SIZE * 0.66  # 1.66%
            else:
                base_pct = config.BASE_POSITION_SIZE * 0.33  # 0.83%

            # Adjust for catalyst
            if catalyst_date:
                base_pct *= 0.75  # Reduce size into catalyst

            # Calculate position value and shares
            position_value = self.account_value * base_pct
            shares = int(position_value / price)

            # Calculate risk metrics
            stop_loss_price = price * (1 - stop_loss_pct / 100)
            risk_per_share = price - stop_loss_price
            total_risk = shares * risk_per_share
            risk_pct_of_account = (total_risk / self.account_value) * 100

            # Risk-reward analysis
            for target_upside in [10, 15, 20, 25, 30]:
                target_price = price * (1 + target_upside / 100)
                reward = (target_price - price) * shares
                reward_pct = (reward / total_risk) if total_risk > 0 else 0
                rr_ratio = reward_pct / 1.0  # 1x risk basis

                if target_upside == 15:  # Store 15% target
                    target_15_rr = rr_ratio

            return {
                'conviction_score': conviction_score,
                'position_size_pct': base_pct * 100,
                'position_value': position_value,
                'shares': shares,
                'entry_price': price,
                'stop_loss_price': stop_loss_price,
                'stop_loss_pct': stop_loss_pct,
                'risk_per_share': risk_per_share,
                'total_risk': total_risk,
                'risk_pct_of_account': risk_pct_of_account,
                'target_prices': {
                    '10%': price * 1.10,
                    '15%': price * 1.15,
                    '20%': price * 1.20,
                    '25%': price * 1.25,
                    '30%': price * 1.30,
                },
                'sizing_recommendation': self._sizing_recommendation(
                    conviction_score, risk_pct_of_account
                ),
            }

        except Exception as e:
            logger.error(f"Error calculating position size: {e}")
            return {'error': str(e)}

    def _sizing_recommendation(
        self, conviction: float, risk_pct: float
    ) -> str:
        """Generate position sizing recommendation."""
        if risk_pct > 3:
            return 'REDUCE_SIZE - Risk too high'
        elif conviction >= 0.80 and risk_pct <= 2:
            return 'FULL_SIZE - Optimal'
        elif conviction >= 0.65 and risk_pct <= 2.5:
            return 'FULL_SIZE - Good'
        elif conviction >= 0.55:
            return 'THREE_QUARTER_SIZE - Moderate conviction'
        else:
            return 'HALF_SIZE - Low conviction'

    def calculate_ladder_positions(
        self,
        conviction_score: float,
        price: float,
        rungs: int = 3,
    ) -> Dict:
        """
        Calculate ladder position entries.

        Args:
            conviction_score: Conviction score
            price: Current price
            rungs: Number of entry levels (default 3)

        Returns:
            Dict with ladder entry prices
        """
        total_sizing = self.calculate_position_size(conviction_score, price)
        total_shares = total_sizing.get('shares', 0)
        shares_per_rung = total_shares // rungs

        ladder = {
            'total_shares': total_shares,
            'rungs': rungs,
            'shares_per_rung': shares_per_rung,
            'entries': [],
        }

        for i in range(rungs):
            pct_below = 2 + (i * 1.5)  # 2%, 3.5%, 5% below
            entry_price = price * (1 - pct_below / 100)
            ladder['entries'].append({
                'rung': i + 1,
                'entry_price': entry_price,
                'shares': shares_per_rung,
                'percentage_below_market': pct_below,
            })

        return ladder


if __name__ == "__main__":
    sizer = PositionSizer(account_value=100000)

    # Test position sizing
    sizing = sizer.calculate_position_size(
        conviction_score=0.75,
        price=150,
        stop_loss_pct=8,
        catalyst_date=False,
    )

    print(f"Position: {sizing['shares']} shares @ ${sizing['entry_price']:.2f}")
    print(f"Position Size: {sizing['position_size_pct']:.2f}% of account")
    print(f"Total Risk: ${sizing['total_risk']:,.2f}")
    print(f"Risk/Reward @ 15%: {sizing['target_prices']['15%']:.2f}")
    print(f"Recommendation: {sizing['sizing_recommendation']}")

    # Test ladder
    ladder = sizer.calculate_ladder_positions(0.75, 150, rungs=3)
    print(f"\nLadder Entries ({ladder['rungs']} rungs):")
    for entry in ladder['entries']:
        print(
            f"  Rung {entry['rung']}: "
            f"${entry['entry_price']:.2f} ({entry['shares']} shares)"
        )
