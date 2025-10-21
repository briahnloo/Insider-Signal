"""Streamlit dashboard for insider trading signals."""
import streamlit as st
import pandas as pd
import plotly.graph_objects as go
import plotly.express as px
from datetime import datetime, timedelta
import sys
from pathlib import Path

# Add src to path
sys.path.insert(0, str(Path(__file__).parent))

from src.database import get_recent_transactions, get_database_stats
from src.analysis.conviction_scorer import ConvictionScorer
from src.execution.trade_signal import TradeSignalEngine
from src.reporting.historical_analysis import HistoricalAnalyzer
from src.data_collection.market_data_cache import get_market_cache

# Page config
st.set_page_config(
    page_title="Insider Trading Intelligence",
    page_icon="📈",
    layout="wide"
)

# Title
st.title("📈 Insider Trading Intelligence System")
st.markdown("Real-time analysis of insider Form 4 filings using multi-signal conviction scoring")

# Initialize components with TTL for auto-refresh
@st.cache_resource(ttl=3600)  # Cache for 1 hour, then auto-refresh
def load_components():
    """Load analysis components (refreshes every hour)."""
    return {
        'scorer': ConvictionScorer(),
        'engine': TradeSignalEngine(account_value=100000),
        'analyzer': HistoricalAnalyzer(),
        'cache': get_market_cache(),
    }

components = load_components()

# Sidebar
st.sidebar.header("⚙️ Settings")

# Data refresh controls
st.sidebar.subheader("📊 Data Status")

# Show last refresh time
if 'last_refresh' not in st.session_state:
    st.session_state.last_refresh = datetime.now()

st.sidebar.text(f"Last refresh:\n{st.session_state.last_refresh.strftime('%Y-%m-%d %H:%M:%S')}")

# Manual refresh button
if st.sidebar.button("🔄 Refresh Data"):
    st.cache_resource.clear()
    st.session_state.last_refresh = datetime.now()
    st.rerun()

st.sidebar.markdown("---")

# Settings
days_back = st.sidebar.slider("Days to analyze:", 7, 180, 30)
min_conviction = st.sidebar.slider("Min conviction score:", 0.3, 1.0, 0.65, 0.05)
min_amount = st.sidebar.slider("Min transaction amount ($):", 10000, 500000, 50000, 10000)

# Cache stats
st.sidebar.markdown("---")
st.sidebar.subheader("💾 Cache Status")
try:
    cache_stats = components['cache'].get_cache_stats()
    st.sidebar.metric("Cached Tickers", cache_stats.get('total_tickers', 0))
    st.sidebar.metric("Fresh Entries", cache_stats.get('fresh_entries', 0))
    if cache_stats.get('stale_entries', 0) > 0:
        st.sidebar.warning(f"{cache_stats['stale_entries']} stale entries")
except Exception as e:
    st.sidebar.text("Cache stats unavailable")

# Main tabs
tab1, tab2, tab3, tab4 = st.tabs([
    "📊 Current Signals",
    "📈 Historical Analysis",
    "💡 Component Breakdown",
    "📋 Database Stats"
])

# TAB 1: Current Signals
with tab1:
    st.header("Current Trading Signals")

    try:
        # Load transactions
        df = get_recent_transactions(days=days_back, min_value=min_amount)

        if df.empty:
            st.warning("No transactions found for the selected period")
        else:
            # Generate signals
            transactions = []
            for _, row in df.iterrows():
                trans = {
                    'ticker': row['ticker'],
                    'insider_name': row['insider_name'],
                    'insider_title': row['insider_title'],
                    'shares': row['shares'],
                    'total_value': row['total_value'],
                    'filing_speed_days': row['filing_speed_days'],
                    'transaction_date': row['transaction_date'],
                }
                transactions.append(trans)

            signals = components['engine'].batch_generate_signals(transactions)

            # Filter by conviction
            valid_signals = [
                s for s in signals
                if s.get('conviction_score', 0) >= min_conviction
                and s.get('signal') != 'ERROR'
            ]

            if valid_signals:
                # Display stats
                col1, col2, col3, col4 = st.columns(4)
                with col1:
                    strong_buy = len([s for s in valid_signals if s.get('signal') == 'STRONG_BUY'])
                    st.metric("Strong Buy", strong_buy)
                with col2:
                    buy = len([s for s in valid_signals if s.get('signal') == 'BUY'])
                    st.metric("Buy", buy)
                with col3:
                    weak_buy = len([s for s in valid_signals if s.get('signal') == 'WEAK_BUY'])
                    st.metric("Weak Buy", weak_buy)
                with col4:
                    avg_score = sum(s.get('conviction_score', 0) for s in valid_signals) / len(valid_signals)
                    st.metric("Avg Score", f"{avg_score:.3f}")

                # Display signals table
                st.subheader("Detailed Signals")
                signal_data = []
                for sig in valid_signals:
                    signal_data.append({
                        'Ticker': sig.get('ticker'),
                        'Signal': sig.get('signal'),
                        'Conviction': f"{sig.get('conviction_score', 0):.3f}",
                        'Insider': sig.get('insider_info', {}).get('name', 'N/A'),
                        'Amount': f"${sig.get('insider_info', {}).get('amount', 0):,.0f}",
                        'Entry': sig.get('entry', {}).get('strategy', 'N/A'),
                        'Position %': f"{sig.get('position', {}).get('size_pct', 0):.2f}%",
                        'Risk': f"${sig.get('position', {}).get('risk_amount', 0):,.0f}",
                    })

                st.dataframe(signal_data, use_container_width=True)

                # Download report
                csv = pd.DataFrame(signal_data).to_csv(index=False)
                st.download_button(
                    label="📥 Download signals as CSV",
                    data=csv,
                    file_name=f"signals_{datetime.now().strftime('%Y%m%d_%H%M%S')}.csv",
                    mime="text/csv"
                )
            else:
                st.info(f"No signals with conviction >= {min_conviction}")

    except Exception as e:
        st.error(f"Error generating signals: {e}")

# TAB 2: Historical Analysis
with tab2:
    st.header("Historical Analysis")

    try:
        backtest = components['analyzer'].backtest_conviction_scoring(days_back=days_back)

        if 'error' in backtest:
            st.warning(f"Backtest error: {backtest['error']}")
        else:
            col1, col2, col3, col4 = st.columns(4)
            with col1:
                st.metric("Transactions", backtest.get('transactions_analyzed', 0))
            with col2:
                st.metric("Actionable Signals", backtest.get('actionable_signals', 0))
            with col3:
                st.metric("Actionable %", f"{backtest.get('actionable_pct', 0):.1f}%")
            with col4:
                dist = backtest.get('conviction_distribution', {})
                st.metric("Avg Score", f"{dist.get('mean', 0):.3f}")

            # Conviction distribution chart
            st.subheader("Conviction Score Distribution")

            signal_breakdown = backtest.get('signal_breakdown', {})
            if signal_breakdown:
                fig = go.Figure(data=[
                    go.Bar(
                        x=list(signal_breakdown.keys()),
                        y=list(signal_breakdown.values()),
                        marker_color=['#4CAF50', '#8BC34A', '#FFC107', '#FF9800', '#F44336']
                    )
                ])
                fig.update_layout(
                    title="Signals by Conviction Level",
                    xaxis_title="Signal Strength",
                    yaxis_title="Count",
                    height=400
                )
                st.plotly_chart(fig, use_container_width=True)

            # Top candidates
            st.subheader("Top Candidates")
            candidates = components['analyzer'].find_top_scoring_candidates(
                days_back=days_back,
                min_conviction=min_conviction
            )

            if candidates:
                cand_data = pd.DataFrame(candidates[:10])
                st.dataframe(cand_data, use_container_width=True)
            else:
                st.info("No candidates meeting criteria")

    except Exception as e:
        st.error(f"Error in analysis: {e}")

# TAB 3: Component Breakdown
with tab3:
    st.header("Signal Component Analysis")

    try:
        df = get_recent_transactions(days=days_back, min_value=min_amount)

        if not df.empty:
            # Select a transaction to analyze
            ticker = st.selectbox(
                "Select ticker to analyze:",
                df['ticker'].unique()
            )

            trans = df[df['ticker'] == ticker].iloc[0]

            # Score and analyze
            result = components['scorer'].calculate_conviction_score(
                ticker=ticker,
                filing_speed_days=trans['filing_speed_days'],
                insider_name=trans['insider_name'],
                transaction_date=trans['transaction_date'],
            )

            st.subheader(f"{ticker} Analysis")

            col1, col2, col3, col4 = st.columns(4)
            with col1:
                st.metric("Conviction Score", f"{result['conviction_score']:.3f}")
            with col2:
                st.metric("Signal Strength", result.get('signal_strength', 'N/A'))
            with col3:
                st.metric("Insider", trans['insider_name'])
            with col4:
                st.metric("Amount", f"${trans['total_value']:,.0f}")

            # Component scores
            st.subheader("Component Breakdown")
            components_data = result.get('component_scores', {})

            if components_data:
                fig = go.Figure(data=[
                    go.Scatterpolar(
                        r=list(components_data.values()),
                        theta=list(components_data.keys()),
                        fill='toself',
                        name='Score'
                    )
                ])
                fig.update_layout(height=400)
                st.plotly_chart(fig, use_container_width=True)

                # Component details
                for comp_name, score in components_data.items():
                    st.write(f"**{comp_name.replace('_', ' ').title()}**: {score:.3f}")

        else:
            st.warning("No transactions available")

    except Exception as e:
        st.error(f"Error in analysis: {e}")

# TAB 4: Database Stats
with tab4:
    st.header("Database Statistics")

    try:
        stats = get_database_stats()
        recent_df = get_recent_transactions(days=days_back, min_value=min_amount)

        col1, col2, col3, col4 = st.columns(4)
        with col1:
            st.metric("Total Transactions", stats.get('total_transactions', 0))
        with col2:
            st.metric("Unique Tickers", stats.get('unique_tickers', 0))
        with col3:
            st.metric("Recent Transactions", len(recent_df))
        with col4:
            avg = stats.get('average_transaction_value', 0)
            st.metric("Avg Transaction", f"${avg:,.0f}")

        # Recent activity
        st.subheader("Recent Activity")

        if not recent_df.empty:
            # Filing speed distribution
            st.write("**Filing Speed Distribution**")
            speed_dist = recent_df['filing_speed_days'].value_counts().sort_index()

            fig = go.Figure(data=[
                go.Bar(x=speed_dist.index.astype(str), y=speed_dist.values)
            ])
            fig.update_xaxes(title_text="Days to File")
            fig.update_yaxes(title_text="Count")
            st.plotly_chart(fig, use_container_width=True)

            # Top tickers
            st.write("**Top Tickers by Transaction Value**")
            top_tickers = recent_df.groupby('ticker')['total_value'].sum().sort_values(ascending=False).head(10)

            fig = px.bar(
                x=top_tickers.values,
                y=top_tickers.index,
                orientation='h',
                labels={'x': 'Total Value ($)', 'y': 'Ticker'}
            )
            st.plotly_chart(fig, use_container_width=True)

        else:
            st.info("No recent transactions")

    except Exception as e:
        st.error(f"Error loading stats: {e}")

# Footer
st.markdown("---")

col1, col2, col3 = st.columns(3)
with col1:
    db_stats = get_database_stats()
    st.metric("Database Transactions", db_stats.get('total_transactions', 0))
with col2:
    st.metric("Unique Tickers", db_stats.get('unique_tickers', 0))
with col3:
    avg_val = db_stats.get('average_transaction_value', 0)
    st.metric("Avg Transaction", f"${avg_val:,.0f}")

st.markdown("""
This dashboard analyzes insider Form 4 filings using multi-signal conviction scoring.
Data refreshes automatically every hour or use the refresh button in the sidebar.
Always conduct your own research before trading.
""")
