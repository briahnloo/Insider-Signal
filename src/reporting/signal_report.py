"""Generate HTML reports of opportunities."""
from typing import List, Dict
from datetime import datetime
from loguru import logger
from pathlib import Path


class SignalReportGenerator:
    """Generates HTML reports of trading signals."""

    def __init__(self, report_dir: str = "reports"):
        self.report_dir = Path(report_dir)
        self.report_dir.mkdir(exist_ok=True)

    def generate_daily_report(self, signals: List[Dict]) -> str:
        """
        Generate HTML report of daily signals.

        Args:
            signals: List of trade signals

        Returns:
            Path to generated report
        """
        try:
            # Filter valid signals
            valid_signals = [s for s in signals if s.get('signal') != 'ERROR']

            if not valid_signals:
                logger.warning("No valid signals for report")
                return None

            # Sort by conviction
            valid_signals.sort(
                key=lambda x: x.get('conviction_score', 0),
                reverse=True
            )

            # Generate HTML
            html = self._generate_html(valid_signals)

            # Save report
            timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
            report_path = self.report_dir / f"signals_{timestamp}.html"
            report_path.write_text(html)

            logger.info(f"Report generated: {report_path}")
            return str(report_path)

        except Exception as e:
            logger.error(f"Error generating report: {e}")
            return None

    def _generate_html(self, signals: List[Dict]) -> str:
        """Generate HTML content."""
        style = """
        <style>
            body { font-family: Arial, sans-serif; margin: 20px; background-color: #f5f5f5; }
            .header { background-color: #1a1a1a; color: white; padding: 20px; border-radius: 5px; }
            .container { max-width: 1200px; margin: 0 auto; }
            .signal-card { background-color: white; margin: 15px 0; padding: 15px; border-radius: 5px; box-shadow: 0 2px 4px rgba(0,0,0,0.1); border-left: 4px solid #2196F3; }
            .signal-card.strong_buy { border-left-color: #4CAF50; }
            .signal-card.buy { border-left-color: #8BC34A; }
            .signal-card.weak_buy { border-left-color: #FFC107; }
            .signal-card.neutral { border-left-color: #999; }
            .ticker { font-size: 20px; font-weight: bold; color: #1a1a1a; }
            .signal { display: inline-block; padding: 5px 10px; border-radius: 3px; margin-left: 10px; color: white; }
            .signal.strong_buy { background-color: #4CAF50; }
            .signal.buy { background-color: #8BC34A; }
            .signal.weak_buy { background-color: #FFC107; }
            .signal.neutral { background-color: #999; }
            .metric { display: inline-block; margin-right: 20px; }
            .metric-label { font-size: 12px; color: #666; }
            .metric-value { font-size: 16px; font-weight: bold; }
            .insider-info { background-color: #f9f9f9; padding: 10px; margin: 10px 0; border-radius: 3px; font-size: 14px; }
            .entry-info { background-color: #e3f2fd; padding: 10px; margin: 10px 0; border-radius: 3px; }
            .position-info { background-color: #fff3e0; padding: 10px; margin: 10px 0; border-radius: 3px; }
            .footer { text-align: center; color: #666; margin-top: 30px; font-size: 12px; }
        </style>
        """

        rows = []
        for sig in signals:
            ticker = sig.get('ticker', 'N/A')
            signal = sig.get('signal', 'NEUTRAL')
            score = sig.get('conviction_score', 0)

            insider = sig.get('insider_info', {})
            entry = sig.get('entry', {})
            position = sig.get('position', {})

            row = f"""
            <div class="signal-card {signal.lower()}">
                <div>
                    <span class="ticker">{ticker}</span>
                    <span class="signal {signal.lower()}">{signal}</span>
                </div>
                <div style="margin-top: 10px;">
                    <div class="metric">
                        <div class="metric-label">Conviction Score</div>
                        <div class="metric-value">{score:.3f}</div>
                    </div>
                    <div class="metric">
                        <div class="metric-label">Entry Strategy</div>
                        <div class="metric-value">{entry.get('strategy', 'N/A')}</div>
                    </div>
                    <div class="metric">
                        <div class="metric-label">Position Size</div>
                        <div class="metric-value">{position.get('size_pct', 0):.2f}%</div>
                    </div>
                </div>

                <div class="insider-info">
                    <strong>Insider:</strong> {insider.get('name', 'N/A')} ({insider.get('title', 'N/A')})<br>
                    <strong>Amount:</strong> ${insider.get('amount', 0):,.0f} |
                    <strong>Shares:</strong> {insider.get('shares', 0):,} |
                    <strong>Filing Speed:</strong> {insider.get('filing_speed_days', 0)} days
                </div>

                <div class="entry-info">
                    <strong>Entry:</strong> {entry.get('reason', 'N/A')}<br>
                    <strong>Current Price:</strong> ${entry.get('current_price', 0):.2f}
                </div>

                <div class="position-info">
                    <strong>Position:</strong> {position.get('shares', 0)} shares @ ${position.get('entry_price', 0):.2f}<br>
                    <strong>Stop Loss:</strong> ${position.get('stop_loss', 0):.2f} |
                    <strong>Risk:</strong> ${position.get('risk_amount', 0):,.0f}
                </div>
            </div>
            """
            rows.append(row)

        html = f"""
        <!DOCTYPE html>
        <html>
        <head>
            <title>Trading Signals Report</title>
            <meta charset="UTF-8">
            <meta name="viewport" content="width=device-width, initial-scale=1.0">
            {style}
        </head>
        <body>
            <div class="container">
                <div class="header">
                    <h1>Insider Trading Signals</h1>
                    <p>Generated: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}</p>
                    <p>Total Signals: {len(signals)}</p>
                </div>

                {''.join(rows)}

                <div class="footer">
                    <p>This dashboard analyzes insider Form 4 filings using multi-signal conviction scoring. Always conduct your own research before trading.</p>
                </div>
            </div>
        </body>
        </html>
        """

        return html

    def generate_summary(self, signals: List[Dict]) -> str:
        """Generate text summary of signals."""
        summary = f"Signal Summary - {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n"
        summary += "=" * 60 + "\n\n"

        # Count by signal type
        signal_counts = {}
        for sig in signals:
            signal_type = sig.get('signal', 'ERROR')
            signal_counts[signal_type] = signal_counts.get(signal_type, 0) + 1

        summary += "Signal Breakdown:\n"
        for sig_type, count in sorted(signal_counts.items(), reverse=True):
            summary += f"  {sig_type}: {count}\n"

        summary += f"\nTotal Signals: {len(signals)}\n"
        summary += f"Actionable (Buy+): {sum(s['conviction_score'] > 0.6 for s in signals if 'conviction_score' in s)}\n"

        return summary


if __name__ == "__main__":
    generator = SignalReportGenerator()

    # Test signals
    test_signals = [
        {
            'ticker': 'AAPL',
            'signal': 'STRONG_BUY',
            'conviction_score': 0.85,
            'insider_info': {'name': 'Tim Cook', 'title': 'CEO', 'amount': 1500000, 'shares': 10000, 'filing_speed_days': 0},
            'entry': {'strategy': 'immediate', 'reason': 'High conviction', 'current_price': 150},
            'position': {'shares': 1000, 'entry_price': 150, 'stop_loss': 138, 'size_pct': 3.5, 'risk_amount': 12000},
        }
    ]

    report_path = generator.generate_daily_report(test_signals)
    print(f"Report generated: {report_path}")
