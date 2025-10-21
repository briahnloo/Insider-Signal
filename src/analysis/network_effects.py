"""Network effects detection - supply chain and sector analysis."""
from typing import Dict, List, Optional, Tuple
from datetime import datetime, timedelta
import time
import yfinance as yf
from loguru import logger

from src.database import get_transactions_by_ticker, get_all_recent_transactions


class NetworkAnalyzer:
    """Analyzes network effects: supply chain, peer clusters, institutional overlap."""

    # Predefined supply chain mappings for major S&P 500 stocks
    # Format: ticker -> (suppliers list, customers list)
    SUPPLY_CHAIN_MAP = {
        "AAPL": {
            "suppliers": ["TSMC", "SK", "QCOM", "SKWS", "ARM", "CUI", "AVGO"],
            "customers": [],  # Direct consumers, not B2B
        },
        "MSFT": {
            "suppliers": ["INTC", "AMD", "QCOM", "NVDA"],
            "customers": ["AMZN", "GOOG"],  # Major cloud customers
        },
        "GOOGL": {
            "suppliers": ["INTC", "AMD", "NVDA", "QCOM"],
            "customers": [],  # B2C advertising, not direct suppliers
        },
        "AMZN": {
            "suppliers": ["ORCL", "INTU", "ADBE"],  # Software infrastructure
            "customers": [],
        },
        "NVDA": {
            "suppliers": ["TSMC", "ASML", "QCOM"],
            "customers": ["AAPL", "MSFT", "GOOGL", "AMZN", "META"],
        },
        "TSLA": {
            "suppliers": ["PANASONIC", "LG"],  # Battery suppliers (limited ticker data)
            "customers": [],
        },
        "META": {
            "suppliers": ["NVDA", "ORCL"],
            "customers": [],
        },
        "NVDA": {
            "suppliers": ["ASML", "QCOM", "TSMC"],
            "customers": ["AAPL", "MSFT", "AMZN", "GOOGL"],
        },
        "AMD": {
            "suppliers": ["TSMC", "ASML"],
            "customers": ["AAPL", "MSFT", "AMZN"],
        },
        "INTC": {
            "suppliers": ["ASML", "TSMC"],
            "customers": ["AAPL", "MSFT", "AMZN"],
        },
        "QCOM": {
            "suppliers": ["TSMC", "SK", "ASML"],
            "customers": ["AAPL", "MSFT", "SAMSUNG"],
        },
        # Add more mappings as needed
    }

    # Sector classifications (simplified - would use proper sector data in production)
    SECTOR_PEERS = {
        "AAPL": ["MSFT", "GOOGL", "META", "AMZN"],  # Tech giants
        "MSFT": ["AAPL", "GOOGL", "AMZN", "META"],
        "JPM": ["BAC", "WFC", "GS", "MS"],  # Financials
        "XOM": ["CVX", "MPC", "PSX"],  # Energy
        "JNJ": ["PFE", "ABBV", "MRK", "LLY"],  # Healthcare
    }

    def __init__(self):
        """Initialize network analyzer."""
        self.cache = {}
        self.cache_time = {}
        self.cache_ttl = 3600  # 1 hour cache

    def _get_cached(self, key: str) -> Optional[Dict]:
        """Get cached data if valid."""
        import time
        if key in self.cache:
            if time.time() - self.cache_time.get(key, 0) < self.cache_ttl:
                return self.cache[key]
        return None

    def _set_cached(self, key: str, data):
        """Cache data with timestamp."""
        import time
        self.cache[key] = data
        self.cache_time[key] = time.time()

    def analyze_supplier_customer_network(
        self,
        ticker: str,
        filing_date: datetime,
        window_days: int = 30,
    ) -> Dict:
        """
        Analyze if suppliers/customers had insider buying around filing date.

        Supply chain buying = demand/supply visibility. When a supplier buys
        before their customer's insider buys, or vice versa, it suggests
        coordination or at least correlated conviction.

        Args:
            ticker: Stock ticker
            filing_date: Date of insider filing
            window_days: Days before/after to check for related insider buying

        Returns:
            Dict with network_score (0-1.0) and insights
        """
        cache_key = f"supply_chain_{ticker}_{filing_date.date()}"
        cached = self._get_cached(cache_key)
        if cached:
            return cached

        try:
            network_score = 0.0
            supplier_buys = []
            customer_buys = []

            # Get supply chain map for this ticker
            supply_chain = self.SUPPLY_CHAIN_MAP.get(ticker.upper(), {})
            suppliers = supply_chain.get("suppliers", [])
            customers = supply_chain.get("customers", [])

            window_start = filing_date - timedelta(days=window_days)
            window_end = filing_date + timedelta(days=window_days)

            # Check supplier insider buying
            for supplier in suppliers:
                try:
                    supplier_txns = get_transactions_by_ticker(
                        supplier, days=window_days * 2
                    )
                    if supplier_txns.empty:
                        continue

                    # Check for buys in window
                    buys_in_window = supplier_txns[
                        (supplier_txns["transaction_type"] == "PURCHASE")
                        & (supplier_txns["transaction_date"] >= window_start)
                        & (supplier_txns["transaction_date"] <= window_end)
                    ]

                    if len(buys_in_window) > 0:
                        supplier_buys.append(
                            {
                                "ticker": supplier,
                                "buy_count": len(buys_in_window),
                                "total_value": buys_in_window["total_value"].sum(),
                            }
                        )

                except Exception as e:
                    logger.debug(f"Error checking supplier {supplier}: {e}")

            # Check customer insider buying
            for customer in customers:
                try:
                    customer_txns = get_transactions_by_ticker(
                        customer, days=window_days * 2
                    )
                    if customer_txns.empty:
                        continue

                    buys_in_window = customer_txns[
                        (customer_txns["transaction_type"] == "PURCHASE")
                        & (customer_txns["transaction_date"] >= window_start)
                        & (customer_txns["transaction_date"] <= window_end)
                    ]

                    if len(buys_in_window) > 0:
                        customer_buys.append(
                            {
                                "ticker": customer,
                                "buy_count": len(buys_in_window),
                                "total_value": buys_in_window["total_value"].sum(),
                            }
                        )

                except Exception as e:
                    logger.debug(f"Error checking customer {customer}: {e}")

            # Score based on activity
            # 1+ supplier buying = +0.3
            if len(supplier_buys) > 0:
                network_score += min(len(supplier_buys) * 0.15, 0.3)

            # 1+ customer buying = +0.3
            if len(customer_buys) > 0:
                network_score += min(len(customer_buys) * 0.15, 0.3)

            # Multiple concurrent buys = additional boost
            if len(supplier_buys) + len(customer_buys) >= 3:
                network_score += 0.2

            network_score = min(network_score, 1.0)

            result = {
                "ticker": ticker,
                "network_score": network_score,
                "supplier_buying": supplier_buys,
                "customer_buying": customer_buys,
                "supplier_count": len(supplier_buys),
                "customer_count": len(customer_buys),
                "total_network_insiders": len(supplier_buys) + len(customer_buys),
            }

            self._set_cached(cache_key, result)
            logger.debug(
                f"{ticker}: Network score {network_score:.3f} "
                f"({len(supplier_buys)} suppliers, {len(customer_buys)} customers)"
            )

            return result

        except Exception as e:
            logger.error(f"Error analyzing supply chain network: {e}")
            return {
                "ticker": ticker,
                "network_score": 0.0,
                "error": str(e),
            }

    def analyze_peer_cluster(
        self,
        ticker: str,
        filing_date: datetime,
        window_days: int = 14,
    ) -> Dict:
        """
        Analyze if same-sector peers had insider buying cluster.

        Sector rotation theory: When multiple insiders in same sector buy,
        it signals rotation into that sector.

        Args:
            ticker: Stock ticker
            filing_date: Date of insider filing
            window_days: Days to check for peer insider buying

        Returns:
            Dict with cluster_score (0-1.0) and peer activity
        """
        cache_key = f"peer_cluster_{ticker}_{filing_date.date()}"
        cached = self._get_cached(cache_key)
        if cached:
            return cached

        try:
            cluster_score = 0.0
            peer_activity = []

            # Get peer tickers
            peers = self.SECTOR_PEERS.get(ticker.upper(), [])
            if not peers:
                logger.debug(f"{ticker}: No peer data available")
                return {
                    "ticker": ticker,
                    "cluster_score": 0.0,
                    "peer_activity": [],
                }

            window_start = filing_date - timedelta(days=window_days)
            window_end = filing_date + timedelta(days=window_days)

            # Check peer insider buying
            for peer in peers:
                try:
                    peer_txns = get_transactions_by_ticker(peer, days=window_days * 2)
                    if peer_txns.empty:
                        continue

                    # Check for buys in window
                    buys_in_window = peer_txns[
                        (peer_txns["transaction_type"] == "PURCHASE")
                        & (peer_txns["transaction_date"] >= window_start)
                        & (peer_txns["transaction_date"] <= window_end)
                    ]

                    if len(buys_in_window) > 0:
                        peer_activity.append(
                            {
                                "ticker": peer,
                                "buy_count": len(buys_in_window),
                                "total_value": buys_in_window["total_value"].sum(),
                            }
                        )

                except Exception as e:
                    logger.debug(f"Error checking peer {peer}: {e}")

            # Score based on peer cluster strength
            # 3+ peers with buys = +0.4
            if len(peer_activity) >= 3:
                cluster_score = 0.4

            # 1-2 peers with buys = +0.2
            elif len(peer_activity) >= 1:
                cluster_score = 0.2

            # Multi-peer cluster boost
            total_peer_buys = sum(p.get("buy_count", 0) for p in peer_activity)
            if total_peer_buys >= 5:
                cluster_score = min(cluster_score + 0.2, 1.0)

            result = {
                "ticker": ticker,
                "cluster_score": cluster_score,
                "peer_activity": peer_activity,
                "active_peer_count": len(peer_activity),
                "total_peer_buys": total_peer_buys,
            }

            self._set_cached(cache_key, result)
            logger.debug(
                f"{ticker}: Sector cluster {cluster_score:.3f} ({len(peer_activity)} peers active)"
            )

            return result

        except Exception as e:
            logger.error(f"Error analyzing peer cluster: {e}")
            return {
                "ticker": ticker,
                "cluster_score": 0.0,
                "error": str(e),
            }

    def analyze_institutional_overlap(self, ticker: str) -> Dict:
        """
        Analyze if top institutional holders have other high-conviction positions.

        Institutional overlap = smart money concentration. If major institutions
        hold multiple high-conviction insider plays, increases signal reliability.

        Args:
            ticker: Stock ticker

        Returns:
            Dict with overlap_score (0-1.0) and institutional details
        """
        cache_key = f"inst_overlap_{ticker}"
        cached = self._get_cached(cache_key)
        if cached:
            return cached

        try:
            overlap_score = 0.0
            shared_institutions = []

            # Get top institutional holders (yfinance limited data)
            try:
                stock = yf.Ticker(ticker)
                # yfinance doesn't provide institutional holders easily
                # In production, would use SEC 13F filings or institutional data
                # For now, use placeholder approach
                logger.debug(
                    f"{ticker}: Institutional holder data not available via yfinance"
                )

                # Placeholder: check if other high-conviction names exist
                # This would integrate with conviction_scorer to find overlap
                # For now, return base score

                result = {
                    "ticker": ticker,
                    "overlap_score": 0.0,
                    "shared_institutions": [],
                    "note": "Requires SEC 13F integration for full functionality",
                }

            except Exception as e:
                logger.debug(f"Error getting institutional data: {e}")
                result = {
                    "ticker": ticker,
                    "overlap_score": 0.0,
                    "error": str(e),
                }

            self._set_cached(cache_key, result)
            return result

        except Exception as e:
            logger.error(f"Error analyzing institutional overlap: {e}")
            return {
                "ticker": ticker,
                "overlap_score": 0.0,
                "error": str(e),
            }

    def get_network_multiplier(self, ticker: str, filing_date: datetime) -> Tuple[float, str]:
        """
        Calculate network effects multiplier for conviction score.

        Network effects boost conviction when supply chain or peers are also buying.

        Args:
            ticker: Stock ticker
            filing_date: Date of insider filing

        Returns:
            Tuple of (multiplier 1.0-1.3x, reason)
        """
        try:
            # Analyze all network components
            supply_chain = self.analyze_supplier_customer_network(ticker, filing_date)
            peer_cluster = self.analyze_peer_cluster(ticker, filing_date)
            inst_overlap = self.analyze_institutional_overlap(ticker)

            # Combined network score
            network_score = (
                supply_chain.get("network_score", 0.0) * 0.4
                + peer_cluster.get("cluster_score", 0.0) * 0.4
                + inst_overlap.get("overlap_score", 0.0) * 0.2
            )

            # Convert to multiplier: 0.0-1.0 → 1.0-1.3x
            multiplier = 1.0 + (network_score * 0.3)

            # Reason string
            reasons = []
            if supply_chain.get("supplier_count", 0) > 0:
                reasons.append(f"{supply_chain['supplier_count']} suppliers buying")
            if supply_chain.get("customer_count", 0) > 0:
                reasons.append(f"{supply_chain['customer_count']} customers buying")
            if peer_cluster.get("active_peer_count", 0) > 0:
                reasons.append(
                    f"Sector cluster ({peer_cluster['active_peer_count']} peers)"
                )

            reason = ", ".join(reasons) if reasons else "No network effects"

            logger.debug(
                f"{ticker}: Network multiplier {multiplier:.3f}x ({reason})"
            )

            return multiplier, reason

        except Exception as e:
            logger.error(f"Error calculating network multiplier: {e}")
            return 1.0, f"Error: {str(e)}"


if __name__ == "__main__":
    analyzer = NetworkAnalyzer()

    # Test network analysis
    ticker = "AAPL"
    filing_date = datetime.now()

    print(f"\n=== Network Effects Analysis for {ticker} ===\n")

    # Supply chain analysis
    supply_chain = analyzer.analyze_supplier_customer_network(ticker, filing_date)
    print(f"Supply Chain Network Score: {supply_chain['network_score']:.3f}")
    print(f"  Suppliers buying: {supply_chain['supplier_count']}")
    print(f"  Customers buying: {supply_chain['customer_count']}")

    # Peer cluster analysis
    peer_cluster = analyzer.analyze_peer_cluster(ticker, filing_date)
    print(f"\nPeer Cluster Score: {peer_cluster['cluster_score']:.3f}")
    print(f"  Active peers: {peer_cluster['active_peer_count']}")
    print(f"  Total peer buys: {peer_cluster['total_peer_buys']}")

    # Institutional overlap analysis
    inst_overlap = analyzer.analyze_institutional_overlap(ticker)
    print(f"\nInstitutional Overlap Score: {inst_overlap['overlap_score']:.3f}")

    # Network multiplier
    multiplier, reason = analyzer.get_network_multiplier(ticker, filing_date)
    print(f"\nNetwork Multiplier: {multiplier:.3f}x")
    print(f"Reason: {reason}")
