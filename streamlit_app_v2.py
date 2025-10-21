"""
Enhanced Streamlit dashboard with improved signal clarity, deduplication, and actionability.
Shows conviction components, multi-insider confidence, entry timing, and actionable recommendations.
"""
import streamlit as st
import pandas as pd
import plotly.graph_objects as go
import plotly.express as px
from datetime import datetime, timedelta
import sys
from pathlib import Path

# Add src to path
sys.path.insert(0, str(Path(__file__).parent))

from src.database import get_recent_transactions, get_database_stats, get_all_recent_transactions, Session, InsiderTransaction
from sqlalchemy import func
from src.analysis.conviction_scorer import ConvictionScorer
from src.analysis.transaction_analyzer import get_transaction_analyzer
from src.analysis.enhanced_conviction_scorer import get_enhanced_conviction_scorer
from src.data_collection.market_data_cache import get_market_cache
from loguru import logger

# Page config
st.set_page_config(
    page_title="Insider Trading Intelligence V2",
    page_icon="🎯",
    layout="wide",
    initial_sidebar_state="expanded"
)

# Custom CSS for better visualization
st.markdown("""
<style>
    .signal-strong { background-color: #1e7e34; color: white; padding: 10px; border-radius: 5px; }
    .signal-buy { background-color: #28a745; color: white; padding: 10px; border-radius: 5px; }
    .signal-accumulate { background-color: #ffc107; color: black; padding: 10px; border-radius: 5px; }
    .signal-watch { background-color: #17a2b8; color: white; padding: 10px; border-radius: 5px; }
    .signal-weak { background-color: #fd7e14; color: white; padding: 10px; border-radius: 5px; }
    .signal-skip { background-color: #dc3545; color: white; padding: 10px; border-radius: 5px; }
    .metric-box { padding: 10px; border-radius: 5px; border-left: 4px solid #0066cc; }
</style>
""", unsafe_allow_html=True)

# Title
st.title("🎯 Insider Trading Intelligence System V2")
st.markdown("**Live insider buying signals with multi-insider confidence, component analysis, and actionable recommendations**")

# Initialize components
@st.cache_resource(ttl=3600)
def load_components():
    """Load analysis components (refreshes every hour)."""
    return {
        'scorer': get_enhanced_conviction_scorer(),
        'analyzer': get_transaction_analyzer(),
        'cache': get_market_cache(),
    }

components = load_components()

# Helper function to check for duplicates
@st.cache_data(ttl=300)  # Cache for 5 minutes
def check_duplicates():
    """Check database for duplicate transactions."""
    session = Session()
    try:
        # Query for potential duplicates
        result = session.query(
            InsiderTransaction.ticker,
            InsiderTransaction.insider_name,
            InsiderTransaction.transaction_date,
            InsiderTransaction.shares,
            InsiderTransaction.price_per_share,
            func.count(InsiderTransaction.id).label('count')
        ).group_by(
            InsiderTransaction.ticker,
            InsiderTransaction.insider_name,
            InsiderTransaction.transaction_date,
            InsiderTransaction.shares,
            InsiderTransaction.price_per_share
        ).having(func.count(InsiderTransaction.id) > 1).all()
        
        return len(result)
    except Exception as e:
        logger.error(f"Failed to check duplicates: {e}")
        return 0
    finally:
        session.close()

# Helper function to load and deduplicate data
@st.cache_data(ttl=3600)  # Cache for 1 hour
def load_deduplicated_data(days_back: int, min_amount: float):
    """Load transactions and apply deduplication."""
    df = get_all_recent_transactions(days=days_back, min_value=min_amount)
    
    if df.empty:
        return df, 0
    
    # Count duplicates before deduplication
    original_count = len(df)
    
    # Deduplicate based on key fields
    df_deduped = df.drop_duplicates(
        subset=['ticker', 'insider_name', 'transaction_date', 'shares', 'price_per_share'],
        keep='first'
    )
    
    duplicates_removed = original_count - len(df_deduped)
    
    return df_deduped, duplicates_removed

# Sidebar Configuration
st.sidebar.header("⚙️ Configuration")

# Settings
min_conviction = st.sidebar.slider("🎯 Minimum Conviction Score:", 0.30, 1.0, 0.60, 0.05)
days_back = st.sidebar.slider("📅 Days to Analyze:", 7, 180, 30)
min_amount = st.sidebar.slider("💰 Min Transaction ($):", 10000, 500000, 50000, 10000)

st.sidebar.markdown("---")

# Data status
st.sidebar.subheader("📊 Data Status")
if 'last_refresh' not in st.session_state:
    st.session_state.last_refresh = datetime.now()

refresh_time = st.session_state.last_refresh.strftime('%H:%M:%S')
st.sidebar.text(f"Last refresh: {refresh_time}")

if st.sidebar.button("🔄 Refresh Data", use_container_width=True):
    st.cache_resource.clear()
    st.session_state.last_refresh = datetime.now()
    st.rerun()

# Database health check
st.sidebar.markdown("---")
st.sidebar.subheader("🗄️ Database Health")

# Check for duplicates
duplicate_count = check_duplicates()
if duplicate_count > 0:
    st.sidebar.error(f"⚠️ {duplicate_count} duplicate groups found")
    if st.sidebar.button("🧹 Clean Duplicates", use_container_width=True):
        # Run the migration script
        import subprocess
        import sys
        from pathlib import Path
        
        try:
            result = subprocess.run([
                sys.executable, 
                str(Path(__file__).parent / "scripts" / "fix_duplicate_transactions.py")
            ], capture_output=True, text=True, timeout=60)
            
            if result.returncode == 0:
                st.sidebar.success("✅ Duplicates cleaned successfully")
                st.cache_data.clear()  # Clear cache to refresh data
                st.rerun()
            else:
                st.sidebar.error(f"❌ Cleanup failed: {result.stderr}")
        except Exception as e:
            st.sidebar.error(f"❌ Error running cleanup: {e}")
else:
    st.sidebar.success("✅ No duplicates found")

# Cache stats
st.sidebar.markdown("---")
st.sidebar.subheader("💾 Cache Status")
try:
    cache_stats = components['cache'].get_cache_stats()
    st.sidebar.metric("Cached Tickers", cache_stats.get('total_tickers', 0))
    st.sidebar.metric("Fresh Data", cache_stats.get('fresh_entries', 0))
    if cache_stats.get('stale_entries', 0) > 0:
        st.sidebar.warning(f"⚠️ {cache_stats['stale_entries']} stale entries")
except Exception as e:
    st.sidebar.text("Cache stats unavailable")

# Main tabs
tab1, tab2, tab3, tab4, tab5 = st.tabs([
    "🔥 Trading Signals (Premium)",
    "📊 Signal Analysis",
    "💡 Component Breakdown",
    "👥 Multi-Insider Patterns",
    "📋 Database Stats"
])

# ============= TAB 1: TRADING SIGNALS =============
with tab1:
    st.header("🎯 Current Trading Signals")

    try:
        # Load and deduplicate transactions
        df, duplicates_removed = load_deduplicated_data(days_back, min_amount)

        if df.empty:
            st.warning("No insider transactions found for the selected period")
        else:
            # Show deduplication info if duplicates were removed
            if duplicates_removed > 0:
                st.info(f"📊 Displaying {len(df)} unique transactions ({duplicates_removed} duplicates removed from display)")
            # Deduplicate and group transactions
            transactions = []
            for _, row in df.iterrows():
                transactions.append({
                    'ticker': row['ticker'],
                    'insider_name': row['insider_name'],
                    'insider_title': row.get('insider_title', ''),
                    'shares': row['shares'],
                    'total_value': row['total_value'],
                    'filing_speed_days': row['filing_speed_days'],
                    'transaction_date': row['transaction_date'],
                    'price_per_share': row.get('price_per_share', 0),
                })

            # Deduplicate
            unique_txns = components['analyzer'].deduplicate_and_group_transactions(transactions)

            if not unique_txns:
                st.warning("No unique transactions after deduplication")
            else:
                # Score each transaction
                scored_signals = []

                for txn in unique_txns:
                    try:
                        # Calculate enhanced conviction score
                        ticker = txn['ticker']
                        score_result = components['scorer'].calculate_enhanced_conviction_score(
                            ticker=ticker,
                            filing_speed_days=txn['filing_speed_days'],
                            insider_name=txn['insider_name'],
                            transaction_date=txn['transaction_date'],
                        )

                        conviction_score = score_result['conviction_score']

                        # Multi-insider analysis
                        multi_insider = components['analyzer'].analyze_multi_insider_accumulation(
                            ticker, unique_txns
                        )
                        confidence_mult = multi_insider['confidence_multiplier']

                        # Categorize signal
                        category, action, emoji = components['analyzer'].categorize_signal(
                            conviction_score, confidence_mult
                        )

                        # Entry timing
                        market_data = components['cache'].get_cached_info(ticker)
                        current_price = market_data.get('current_price', 0) if market_data else 0
                        price_at_txn = txn.get('price_per_share', current_price)

                        timing_info = components['analyzer'].analyze_entry_timing(
                            ticker, txn['transaction_date'], current_price, price_at_txn
                        )

                        scored_signals.append({
                            'ticker': ticker,
                            'insider': txn['insider_name'],
                            'title': txn.get('insider_title', ''),
                            'amount': txn['total_value'],
                            'shares': txn['grouped_shares'] if txn.get('is_grouped') else txn['shares'],
                            'conviction': conviction_score,
                            'adjusted_conviction': min(conviction_score * confidence_mult, 1.0),
                            'category': category,
                            'action': action,
                            'emoji': emoji,
                            'multi_insider_count': multi_insider['insider_count'],
                            'confidence_mult': confidence_mult,
                            'timing': timing_info['timing_category'],
                            'timing_desc': timing_info['timing_description'],
                            'duplicates': txn.get('duplicate_count', 1),
                            'components': score_result['component_scores'],
                            'component_details': score_result['components'],
                            'full_result': score_result,
                        })

                    except Exception as e:
                        logger.debug(f"Error scoring {txn.get('ticker')}: {e}")
                        continue

                # Filter by minimum conviction
                valid_signals = [s for s in scored_signals if s['adjusted_conviction'] >= min_conviction]

                if valid_signals:
                    # Sort by adjusted conviction (descending)
                    valid_signals.sort(key=lambda x: x['adjusted_conviction'], reverse=True)

                    # Summary metrics
                    st.markdown("### 📈 Signal Summary")
                    col1, col2, col3, col4, col5 = st.columns(5)

                    with col1:
                        strong_buy_count = len([s for s in valid_signals if s['category'] == 'STRONG_BUY'])
                        st.metric("🔥 Strong Buy", strong_buy_count, delta=f"Score ≥ 0.85")

                    with col2:
                        buy_count = len([s for s in valid_signals if s['category'] == 'BUY'])
                        st.metric("✅ Buy", buy_count, delta=f"Score ≥ 0.75")

                    with col3:
                        accum_count = len([s for s in valid_signals if s['category'] == 'ACCUMULATE'])
                        st.metric("👍 Accumulate", accum_count, delta=f"Score ≥ 0.65")

                    with col4:
                        watch_count = len([s for s in valid_signals if s['category'] == 'WATCH'])
                        st.metric("👀 Watch", watch_count, delta=f"Score ≥ 0.60")

                    with col5:
                        avg_score = sum(s['adjusted_conviction'] for s in valid_signals) / len(valid_signals)
                        st.metric("📊 Avg Score", f"{avg_score:.3f}", delta=f"Adjusted")

                    st.markdown("---")

                    # Signal breakdown for top signals
                    if len(valid_signals) > 0:
                        st.markdown("### 🔍 Signal Breakdown - Why These Are Strong Buys")
                        
                        # Show breakdown for top 3 signals
                        for i, sig in enumerate(valid_signals[:3]):
                            if sig['category'] in ['STRONG_BUY', 'BUY']:
                                with st.expander(f"🎯 {sig['ticker']} - {sig['category']} (Score: {sig['adjusted_conviction']:.3f})"):
                                    signal_explanation = components['analyzer'].generate_signal_explanation(
                                        sig['full_result'], sig['ticker']
                                    )
                                    
                                    # Display key reasons
                                    st.markdown("**Key Reasons for Strong Buy Signal:**")
                                    
                                    if signal_explanation['strong_signals']:
                                        for signal in signal_explanation['strong_signals'][:3]:
                                            component_name = signal['component'].replace('_', ' ').title()
                                            multiplier_text = f" (×{signal['multiplier']:.2f})" if signal['multiplier'] != 1.0 else ""
                                            
                                            st.write(f"✅ **{component_name}**{multiplier_text} - Score: {signal['score']:.2f}")
                                    
                                    # Show supporting signals
                                    if signal_explanation['moderate_signals']:
                                        st.markdown("**Supporting Factors:**")
                                        for signal in signal_explanation['moderate_signals'][:2]:
                                            component_name = signal['component'].replace('_', ' ').title()
                                            st.write(f"⚠️ **{component_name}** - Score: {signal['score']:.2f}")
                                    
                                    # Summary
                                    total_strong = signal_explanation['total_strong']
                                    if total_strong >= 3:
                                        st.success(f"🎯 **Exceptional**: {total_strong} strong signals align")
                                    elif total_strong >= 2:
                                        st.info(f"✅ **Strong**: {total_strong} strong signals align")
                                    else:
                                        st.warning(f"⚠️ **Moderate**: {total_strong} strong signals")

                    st.markdown("---")

                    # Detailed signals table
                    st.markdown("### 🎯 Detailed Signals Table")

                    # Create display dataframe
                    display_data = []
                    for sig in valid_signals:
                        display_data.append({
                            'Signal': f"{sig['emoji']} {sig['category']}",
                            'Ticker': sig['ticker'],
                            'Insider': sig['insider'],
                            'Title': sig['title'],
                            'Amount': f"${sig['amount']:,.0f}",
                            'Shares': f"{sig['shares']:,}",
                            'Base Score': f"{sig['conviction']:.3f}",
                            'Adjusted': f"{sig['adjusted_conviction']:.3f}",
                            'Confidence': f"{sig['confidence_mult']:.2f}x",
                            'Insiders': f"{sig['multi_insider_count']}",
                            'Timing': sig['timing'],
                            'Action': sig['action'],
                        })

                    display_df = pd.DataFrame(display_data)
                    st.dataframe(display_df, use_container_width=True, hide_index=True)

                    # Expand details for each signal
                    st.markdown("### 📋 Detailed Analysis per Signal")

                    for i, sig in enumerate(valid_signals[:5]):  # Show top 5 details
                        with st.expander(f"{sig['emoji']} {sig['ticker']} - {sig['category']} ({sig['adjusted_conviction']:.3f})"):
                            col1, col2, col3 = st.columns(3)

                            with col1:
                                st.markdown(f"**Ticker:** {sig['ticker']}")
                                st.markdown(f"**Insider:** {sig['insider']}")
                                st.markdown(f"**Title:** {sig['title']}")
                                st.markdown(f"**Amount:** ${sig['amount']:,.0f}")

                            with col2:
                                st.markdown(f"**Base Score:** {sig['conviction']:.3f}")
                                st.markdown(f"**Adjusted:** {sig['adjusted_conviction']:.3f}")
                                st.markdown(f"**Confidence:** {sig['confidence_mult']:.2f}x")
                                st.markdown(f"**Multi-Insider:** {sig['multi_insider_count']}")

                            with col3:
                                st.markdown(f"**Timing:** {sig['timing_desc']}")
                                st.markdown(f"**Category:** {sig['category']}")
                                st.markdown(f"**Duplicates:** {sig['duplicates']}")
                                st.markdown(f"**Action:** {sig['action']}")

                            # Signal breakdown - why this is a strong buy
                            st.markdown("#### 🎯 Why This Is A Strong Buy:")
                            
                            # Generate signal explanation
                            signal_explanation = components['analyzer'].generate_signal_explanation(
                                sig['full_result'], sig['ticker']
                            )
                            
                            # Display strong signals
                            if signal_explanation['strong_signals']:
                                st.markdown("**🔥 Strong Signals:**")
                                for signal in signal_explanation['strong_signals'][:3]:  # Top 3
                                    component_name = signal['component'].replace('_', ' ').title()
                                    multiplier_text = f" (×{signal['multiplier']:.2f})" if signal['multiplier'] != 1.0 else ""
                                    
                                    col1, col2, col3 = st.columns([3, 1, 1])
                                    with col1:
                                        st.write(f"✅ **{component_name}**{multiplier_text}")
                                    with col2:
                                        st.write(f"Score: {signal['score']:.2f}")
                                    with col3:
                                        st.write(f"Impact: {signal['impact']:.3f}")
                            
                            # Display moderate signals if any
                            if signal_explanation['moderate_signals']:
                                st.markdown("**⚠️ Supporting Signals:**")
                                for signal in signal_explanation['moderate_signals'][:2]:  # Top 2
                                    component_name = signal['component'].replace('_', ' ').title()
                                    col1, col2 = st.columns([3, 1])
                                    with col1:
                                        st.write(f"⚠️ **{component_name}**")
                                    with col2:
                                        st.write(f"Score: {signal['score']:.2f}")
                            
                            # Summary
                            total_strong = signal_explanation['total_strong']
                            total_moderate = signal_explanation['total_moderate']
                            
                            if total_strong >= 3:
                                st.success(f"🎯 **Exceptional Signal**: {total_strong} strong signals + {total_moderate} supporting signals")
                            elif total_strong >= 2:
                                st.info(f"✅ **Strong Signal**: {total_strong} strong signals + {total_moderate} supporting signals")
                            else:
                                st.warning(f"⚠️ **Moderate Signal**: {total_strong} strong signals + {total_moderate} supporting signals")
                            
                            # Detailed component breakdown (collapsible)
                            with st.expander("📊 Detailed Component Analysis"):
                                components_str = components['analyzer'].generate_component_breakdown(
                                    sig['full_result'], sig['ticker']
                                )
                                st.code(components_str)

                    # Download signals
                    st.markdown("---")
                    csv = display_df.to_csv(index=False)
                    st.download_button(
                        label="📥 Download all signals (CSV)",
                        data=csv,
                        file_name=f"insider_signals_{datetime.now().strftime('%Y%m%d_%H%M%S')}.csv",
                        mime="text/csv",
                        use_container_width=True
                    )

                else:
                    st.info(f"No signals with conviction ≥ {min_conviction:.2f} found")

    except Exception as e:
        st.error(f"Error generating signals: {str(e)}")
        logger.error(f"Streamlit error: {e}")


# ============= TAB 2: SIGNAL ANALYSIS =============
with tab2:
    st.header("📊 Signal Category Analysis")

    try:
        df, _ = load_deduplicated_data(days_back, min_amount)

        if not df.empty:
            # Prepare data for analysis
            transactions = []
            for _, row in df.iterrows():
                transactions.append({
                    'ticker': row['ticker'],
                    'insider_name': row['insider_name'],
                    'shares': row['shares'],
                    'total_value': row['total_value'],
                    'filing_speed_days': row['filing_speed_days'],
                    'transaction_date': row['transaction_date'],
                    'price_per_share': row.get('price_per_share', 0),
                })

            unique_txns = components['analyzer'].deduplicate_and_group_transactions(transactions)

            # Calculate signal distribution
            signal_dist = {'STRONG_BUY': 0, 'BUY': 0, 'ACCUMULATE': 0, 'WATCH': 0, 'WEAK_BUY': 0, 'SKIP': 0}
            conviction_scores = []

            for txn in unique_txns:
                try:
                    score_result = components['scorer'].calculate_enhanced_conviction_score(
                        ticker=txn['ticker'],
                        filing_speed_days=txn['filing_speed_days'],
                        insider_name=txn['insider_name'],
                        transaction_date=txn['transaction_date'],
                    )
                    conviction_scores.append(score_result['conviction_score'])

                    category, _, _ = components['analyzer'].categorize_signal(
                        score_result['conviction_score'], 1.0
                    )
                    signal_dist[category] = signal_dist.get(category, 0) + 1
                except:
                    pass

            # Charts
            col1, col2 = st.columns(2)

            with col1:
                st.markdown("#### Signal Distribution")
                filtered_dist = {k: v for k, v in signal_dist.items() if v > 0}
                if filtered_dist:
                    fig = go.Figure(data=[go.Bar(
                        x=list(filtered_dist.keys()),
                        y=list(filtered_dist.values()),
                        marker_color=['#1e7e34', '#28a745', '#ffc107', '#17a2b8', '#fd7e14', '#dc3545'][:len(filtered_dist)]
                    )])
                    fig.update_layout(
                        title="Signals by Category",
                        xaxis_title="Signal Type",
                        yaxis_title="Count",
                        height=400,
                        showlegend=False
                    )
                    st.plotly_chart(fig, use_container_width=True)

            with col2:
                st.markdown("#### Conviction Score Distribution")
                if conviction_scores:
                    fig = go.Figure(data=[go.Histogram(
                        x=conviction_scores,
                        nbinsx=20,
                        marker_color='#0066cc'
                    )])
                    fig.update_layout(
                        title="Conviction Score Histogram",
                        xaxis_title="Conviction Score",
                        yaxis_title="Frequency",
                        height=400,
                        showlegend=False
                    )
                    st.plotly_chart(fig, use_container_width=True)

        else:
            st.warning("No transactions available for analysis")

    except Exception as e:
        st.error(f"Error in analysis: {str(e)}")


# ============= TAB 3: COMPONENT BREAKDOWN =============
with tab3:
    st.header("💡 Signal Component Analysis")

    try:
        df, _ = load_deduplicated_data(days_back, min_amount)

        if not df.empty:
            # Select ticker
            tickers = sorted(df['ticker'].unique())
            selected_ticker = st.selectbox("Select Ticker:", tickers)

            # Get transactions for ticker
            ticker_df = df[df['ticker'] == selected_ticker]

            if not ticker_df.empty:
                trans = ticker_df.iloc[0]

                # Calculate score
                result = components['scorer'].calculate_enhanced_conviction_score(
                    ticker=selected_ticker,
                    filing_speed_days=trans['filing_speed_days'],
                    insider_name=trans['insider_name'],
                    transaction_date=trans['transaction_date'],
                )

                st.markdown(f"### {selected_ticker} Component Analysis")

                col1, col2, col3, col4 = st.columns(4)
                with col1:
                    st.metric("Overall Score", f"{result['conviction_score']:.3f}")
                with col2:
                    st.metric("Signal Strength", result.get('signal_strength', 'N/A'))
                with col3:
                    st.metric("Insider", trans['insider_name'])
                with col4:
                    st.metric("Amount", f"${trans['total_value']:,.0f}")

                st.markdown("---")

                # Component radar chart
                st.markdown("#### Component Scores Radar")
                components_data = result.get('component_scores', {})

                if components_data:
                    fig = go.Figure(data=[
                        go.Scatterpolar(
                            r=list(components_data.values()),
                            theta=[k.replace('_', ' ').title() for k in components_data.keys()],
                            fill='toself',
                            name='Score',
                            marker_color='#0066cc'
                        )
                    ])
                    fig.update_layout(
                        height=500,
                        polar=dict(radialaxis=dict(visible=True, range=[0, 1]))
                    )
                    st.plotly_chart(fig, use_container_width=True)

                # Detailed component breakdown
                st.markdown("#### Detailed Component Breakdown")
                breakdown_text = components['analyzer'].generate_component_breakdown(result, selected_ticker)
                st.code(breakdown_text, language="text")

        else:
            st.warning("No transactions available")

    except Exception as e:
        st.error(f"Error: {str(e)}")


# ============= TAB 4: MULTI-INSIDER PATTERNS =============
with tab4:
    st.header("👥 Multi-Insider Accumulation Patterns")

    try:
        df, _ = load_deduplicated_data(days_back, min_amount)

        if not df.empty:
            transactions = []
            for _, row in df.iterrows():
                transactions.append({
                    'ticker': row['ticker'],
                    'insider_name': row['insider_name'],
                    'shares': row['shares'],
                    'total_value': row['total_value'],
                    'filing_speed_days': row['filing_speed_days'],
                    'transaction_date': row['transaction_date'],
                })

            unique_txns = components['analyzer'].deduplicate_and_group_transactions(transactions)

            # Analyze each ticker for multi-insider patterns
            multi_insider_analysis = []

            for ticker in df['ticker'].unique():
                analysis = components['analyzer'].analyze_multi_insider_accumulation(ticker, unique_txns)

                if analysis['multiple_insiders']:
                    multi_insider_analysis.append({
                        'ticker': ticker,
                        'insiders': analysis['insider_count'],
                        'transactions': analysis['total_transactions'],
                        'confidence_boost': f"{(analysis['confidence_multiplier'] - 1) * 100:.0f}%",
                        'interpretation': analysis['interpretation'],
                        'names': ', '.join(analysis['insider_names'][:3]),
                    })

            if multi_insider_analysis:
                st.markdown(f"### Found {len(multi_insider_analysis)} Stocks with Multiple Insider Activity")

                analysis_df = pd.DataFrame(multi_insider_analysis)
                st.dataframe(analysis_df, use_container_width=True, hide_index=True)

                # Expand details
                st.markdown("### Details")
                for analysis in multi_insider_analysis:
                    with st.expander(f"{analysis['ticker']}: {analysis['interpretation']}"):
                        st.markdown(f"**Insiders:** {', '.join(analysis['names'])}")
                        st.markdown(f"**Count:** {analysis['insiders']}")
                        st.markdown(f"**Confidence Boost:** {analysis['confidence_boost']}")

            else:
                st.info("No multi-insider accumulation patterns detected in this period")

        else:
            st.warning("No transactions available")

    except Exception as e:
        st.error(f"Error: {str(e)}")


# ============= TAB 5: DATABASE STATS =============
with tab5:
    st.header("📋 Database Statistics")

    try:
        stats = get_database_stats()
        recent_df, _ = load_deduplicated_data(days_back, min_amount)

        col1, col2, col3, col4 = st.columns(4)
        with col1:
            st.metric("Total Transactions", stats.get('total_transactions', 0))
        with col2:
            st.metric("Unique Tickers", stats.get('unique_tickers', 0))
        with col3:
            st.metric("Recent (30d)", len(recent_df))
        with col4:
            avg = stats.get('average_transaction_value', 0)
            st.metric("Avg Transaction", f"${avg:,.0f}")

        st.markdown("---")

        if not recent_df.empty:
            # Filing speed
            st.markdown("### Filing Speed Distribution")
            speed_dist = recent_df['filing_speed_days'].value_counts().sort_index()

            fig = go.Figure(data=[go.Bar(x=speed_dist.index.astype(str), y=speed_dist.values, marker_color='#0066cc')])
            fig.update_xaxes(title_text="Days to File")
            fig.update_yaxes(title_text="Count")
            fig.update_layout(height=400, showlegend=False)
            st.plotly_chart(fig, use_container_width=True)

            # Top tickers
            st.markdown("### Top Tickers by Transaction Value")
            top_tickers = recent_df.groupby('ticker')['total_value'].sum().sort_values(ascending=False).head(10)

            fig = px.bar(
                x=top_tickers.values,
                y=top_tickers.index,
                orientation='h',
                labels={'x': 'Total Value ($)', 'y': 'Ticker'},
                title="Top 10 Tickers",
                color=top_tickers.values,
                color_continuous_scale='Blues'
            )
            fig.update_layout(height=400, showlegend=False)
            st.plotly_chart(fig, use_container_width=True)

        else:
            st.info("No recent transactions")

    except Exception as e:
        st.error(f"Error: {str(e)}")

# Footer
st.markdown("---")
st.markdown("""
### 📖 How to Use This Dashboard

1. **Trading Signals Tab**: View all current insider buying signals categorized by conviction level and actionability
2. **Signal Analysis Tab**: Analyze the distribution of signals and conviction scores
3. **Component Breakdown Tab**: Deep dive into individual components of a specific ticker's conviction score
4. **Multi-Insider Tab**: Find stocks with multiple insiders buying (highest confidence trades)
5. **Database Stats**: See overall database health and top performing tickers

**Signal Categories:**
- 🔥 **Strong Buy** (≥0.85): Execute immediately - all signals aligned
- ✅ **Buy** (≥0.75): High confidence insider signal
- 👍 **Accumulate** (≥0.65): Good setup to build position
- 👀 **Watch** (≥0.60): Monitor for strengthening signals
- ❓ **Weak Buy** (≥0.50): Risky, mixed signals
- ❌ **Skip** (<0.50): Too many red flags

**Confidence Multipliers:**
- 1x = Single insider (standard)
- 1.25x = 2 insiders buying
- 1.4x = 3+ insiders buying together

Always conduct your own research before trading. Past performance ≠ future results.
""")
