import os
import streamlit as st
from dotenv import load_dotenv
from src.graph import run_shopping_agent
from src.models import ShoppingAgentState, UserRequirement
from src.ui_helpers import (
    CUSTOM_CSS,
    build_comparison_dataframe,
    format_bdt_price,
    get_store_badge_html
)

load_dotenv(override=True)

st.set_page_config(
    page_title="AI Shopping Decision & Comparison Agent",
    page_icon="🛒",
    layout="wide",
    initial_sidebar_state="expanded"
)

# Inject custom styling
st.markdown(CUSTOM_CSS, unsafe_allow_html=True)

# Initialize Session State
if "history" not in st.session_state:
    st.session_state.history = []
if "last_result" not in st.session_state:
    st.session_state.last_result = None
if "search_query" not in st.session_state:
    st.session_state.search_query = ""
if "trigger_search" not in st.session_state:
    st.session_state.trigger_search = False

# Sidebar
with st.sidebar:
    st.image("https://img.icons8.com/fluency/96/shopping-bag.png", width=64)
    st.title("🛒 Shopping Agent")
    st.caption("Live 10-Product Search, Element Analysis & Recommendations")

    st.markdown("---")
    st.subheader("⚙️ System Status")
    active_model = os.getenv("GEMINI_MODEL", "gemini-3.5-flash-lite")
    st.info(f"**LLM Engine:** `{active_model}`\n\n**Search:** Live Store Catalog + DuckDuckGo\n\n**Coverage:** 10 Products Analyzed")

    st.markdown("### 🏬 Target Retailers")
    st.checkbox("Star Tech (Live Catalog)", value=True, disabled=True)
    st.checkbox("Ryans Computers", value=True, disabled=True)
    st.checkbox("Daraz Bangladesh", value=True, disabled=True)
    st.checkbox("Pickaboo", value=True, disabled=True)

    st.markdown("---")
    st.subheader("🕒 Search History")
    if st.session_state.history:
        for idx, prev_q in enumerate(reversed(st.session_state.history[-5:])):
            if st.button(f"🔍 {prev_q[:28]}...", key=f"hist_{idx}"):
                st.session_state.search_query = prev_q
                st.session_state.trigger_search = True
                st.rerun()
    else:
        st.caption("No previous searches yet.")


# Main Header
st.title("🛒 Live AI Shopping Decision & Comparison Agent")
st.markdown(
    "Search **10 live products**, extract **real-time page elements & specifications**, "
    "and get an instant **side-by-side comparison matrix** with expert buying recommendations."
)

# Quick Suggestion Chips
st.markdown("##### ⚡ Quick Scenarios")
col1, col2, col3, col4 = st.columns(4)
with col1:
    if st.button("💻 Laptop (< 100k BDT)", use_container_width=True):
        st.session_state.search_query = "laptop under 100000 BDT in Bangladesh"
        st.session_state.trigger_search = True
        st.rerun()
with col2:
    if st.button("⌨️ Mechanical Keyboard (< 5k)", use_container_width=True):
        st.session_state.search_query = "mechanical keyboard under 5000 tk Star Tech"
        st.session_state.trigger_search = True
        st.rerun()
with col3:
    if st.button("📱 Camera Phone (< 45k)", use_container_width=True):
        st.session_state.search_query = "smartphone under 45k taka with great camera and battery"
        st.session_state.trigger_search = True
        st.rerun()
with col4:
    if st.button("🎮 Gaming Laptop (RTX)", use_container_width=True):
        st.session_state.search_query = "gaming laptop under 120k with dedicated GPU"
        st.session_state.trigger_search = True
        st.rerun()

st.markdown("<br>", unsafe_allow_html=True)

# Search Input Form
with st.form("search_form", clear_on_submit=False):
    query_input = st.text_input(
        "What product are you looking to buy?",
        key="search_query",
        placeholder="e.g. laptop under 100000 BDT, mechanical keyboard under 5000 tk, or 'smartphone under 35k'",
        help="Type in English, Bangla, or Banglish with your target product and budget."
    )
    submit_button = st.form_submit_button("🔍 Search 10 Products, Analyze & Compare", type="primary", use_container_width=True)

# Execution Logic
should_search = (submit_button and query_input.strip()) or (st.session_state.trigger_search and st.session_state.search_query.strip())
if should_search:
    st.session_state.trigger_search = False
    query = st.session_state.search_query.strip()
    if query not in st.session_state.history:
        st.session_state.history.append(query)

    with st.status("🤖 Executing 4-Step Decision Pipeline...", expanded=True) as status:
        st.write("🧠 **Step 1: Requirement Analysis** — Understanding category, budget & feature priorities...")
        result: ShoppingAgentState = run_shopping_agent(query)

        st.write("🔎 **Step 2: Live Search (10+ Products)** — Discovered candidate links across live Bangladesh stores...")
        st.write("📄 **Step 3: Page Element Extraction** — Extracted title, price, specs, image & store details...")
        st.write("⚖️ **Step 4: Gemini Comparative Analysis** — Calculated value ratings and side-by-side trade-offs...")
        status.update(label="✅ 10 Products Researched, Analyzed & Compared!", state="complete", expanded=False)

    st.session_state.last_result = result


# Display Results
if st.session_state.last_result:
    res = st.session_state.last_result
    req: UserRequirement = res.get("requirements")
    recommendations = res.get("recommendations", [])
    extracted_products = res.get("extracted_products", [])

    st.markdown("---")

    # Intent Summary Banner
    if req:
        st.subheader("📋 Parsed Shopping Intent")
        m1, m2, m3, m4 = st.columns(4)
        m1.metric("Target Category", req.category.capitalize())
        m2.metric("Max Budget", f"{req.budget_max:,.0f} BDT" if req.budget_max else "Flexible")
        m3.metric("Primary Usage", ", ".join(req.usage_purposes).title() if req.usage_purposes else "General")
        m4.metric("Products Analyzed", f"{len(recommendations)} Items")

    # Top Pick Hero Section
    if recommendations:
        winner = recommendations[0]
        p_win = winner.product

        st.markdown("<br>", unsafe_allow_html=True)
        img_col, details_col = st.columns([1, 3]) if p_win.image_url else (None, None)

        hero_html = f"""
        <div class="hero-card">
            <div style="display: flex; justify-content: space-between; align-items: center; margin-bottom: 0.5rem;">
                <span style="font-size: 1.25rem; font-weight: 800; color: #047857;">🏆 TOP RECOMMENDATION (RANK #1)</span>
                {get_store_badge_html(p_win.store)}
            </div>
            <h2 style="margin: 0.25rem 0 0.75rem 0; font-weight: 700;">
                <a href="{p_win.url}" target="_blank" style="text-decoration: none; color: #0f172a;">{p_win.name}</a>
            </h2>
            <div style="display: flex; align-items: baseline; gap: 1rem; margin-bottom: 1rem;">
                <span class="price-tag">{format_bdt_price(p_win.price)}</span>
                <span class="score-badge">Value Score: {winner.score} / 10</span>
                <span style="color: #64748b; font-size: 0.9rem;">Warranty: {p_win.warranty or 'Standard Retail'}</span>
            </div>
            <p style="color: #334155; font-size: 1rem; margin-bottom: 0.5rem;">
                <strong>Why it wins:</strong> {winner.why_buy[0] if winner.why_buy else 'Delivers superior value for money and verified specs.'}
            </p>
        </div>
        """

        if img_col and details_col:
            with img_col:
                st.image(p_win.image_url, width="stretch")
            with details_col:
                st.markdown(hero_html, unsafe_allow_html=True)
                st.link_button(f"🛒 Buy / View on {p_win.store}", p_win.url, type="primary")
        else:
            st.markdown(hero_html, unsafe_allow_html=True)
            st.link_button(f"🛒 Buy / View on {p_win.store}", p_win.url, type="primary")

        # Tabs for Deep Dive
        tab_compare, tab_cards, tab_advice, tab_logs = st.tabs([
            "📊 Side-by-Side Comparison (10 Products)",
            "🛍️ All Ranked Product Cards",
            "🛡️ BD Buying Advice",
            "🔍 Agent Logs & Raw Elements"
        ])

        # TAB 1: SIDE-BY-SIDE COMPARISON TABLE
        with tab_compare:
            st.markdown(f"### 📊 Side-by-Side Comparison Matrix ({len(recommendations)} Products)")
            st.caption("Compare prices, specifications, value scores, advantages, and trade-offs at a glance.")
            df_compare = build_comparison_dataframe(recommendations)
            st.dataframe(df_compare, use_container_width=True, hide_index=True)

        # TAB 2: PRODUCT CARDS
        with tab_cards:
            st.markdown(f"### 🛍️ Detailed Product Breakdown ({len(recommendations)} Items)")
            cols = st.columns(3)
            for idx, card in enumerate(recommendations):
                col = cols[idx % 3]
                p = card.product
                with col:
                    with st.container(border=True):
                        st.markdown(f"**#{card.rank} {card.verdict}**")
                        st.markdown(get_store_badge_html(p.store), unsafe_allow_html=True)

                        if p.image_url:
                            st.image(p.image_url, width="stretch")

                        st.subheader(p.name)
                        st.markdown(f"<span class='price-tag'>{format_bdt_price(p.price)}</span>", unsafe_allow_html=True)
                        st.caption(f"⭐ Rating: {card.score}/10 | Warranty: {p.warranty or 'Standard'}")

                        if p.specs:
                            st.markdown("**Key Elements & Specs:**")
                            for k, v in list(p.specs.items())[:5]:
                                st.markdown(f"<span class='spec-chip'><strong>{k}:</strong> {v}</span>", unsafe_allow_html=True)

                        st.markdown("<br>**Why to Buy:**", unsafe_allow_html=True)
                        for r in card.why_buy[:2]:
                            st.markdown(f"✅ <span style='font-size:0.85rem;'>{r}</span>", unsafe_allow_html=True)

                        st.markdown("**Why NOT to Buy:**")
                        for r in card.why_not_buy[:2]:
                            st.markdown(f"⚠️ <span style='font-size:0.85rem; color:#b45309;'>{r}</span>", unsafe_allow_html=True)

                        st.caption(f"💡 {card.bangladesh_note}")
                        st.link_button(f"Open in {p.store}", p.url, use_container_width=True)

        # TAB 3: BANGLADESH BUYING ADVICE
        with tab_advice:
            st.markdown("### 💡 Bangladesh Tech Buying Advice & Checklist")
            st.info("""
            **1. Official Distributor vs. Gray Market Warranty:**
            - Always verify whether the listed price includes **Official Brand Warranty** (e.g., Star Tech / Ryans official import) or an unofficial shop warranty.
            - Unofficial units might save ৳3,000 - ৳20,000 upfront, but lack official replacement parts or warranty service centers.

            **2. Outlet Stock Verification:**
            - Central warehouses (e.g. IDB Bhaban, Multiplan Center, Elephant Road) often have products that local branches (Uttara, Chattogram, Sylhet) have not received yet.
            - Call the specific outlet before visiting to confirm on-shelf readiness.

            **3. Cash Discount vs. EMI:**
            - Retailers in Bangladesh commonly offer a 2% to 5% instant discount for direct Cash or bKash payment compared to card EMI payment.
            """)

        # TAB 4: TRANSPARENCY & RAW LOGS
        with tab_logs:
            st.markdown("### 🔍 Execution Trace & Extracted Elements")
            queries_run = res.get("search_queries", [])
            if queries_run:
                st.markdown("**Queries Executed:**")
                for q in queries_run:
                    st.code(q, language="text")

            candidate_urls = res.get("candidate_urls", [])
            if candidate_urls:
                st.markdown(f"**Discovered Candidate URLs ({len(candidate_urls)}):**")
                for c in candidate_urls:
                    st.markdown(f"- [{c.get('title')}]({c.get('url')}) `({c.get('store')})`")

            logs = res.get("logs", [])
            if logs:
                st.markdown("**Pipeline Logs:**")
                for l in logs:
                    st.caption(f"• {l}")
    else:
        st.warning("No candidate products matched your search. Please try broadening your search query.")
