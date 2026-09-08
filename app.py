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
    page_title="Bangladesh AI Shopping Decision Agent",
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
if "current_query" not in st.session_state:
    st.session_state.current_query = ""

# Sidebar
with st.sidebar:
    st.image("https://img.icons8.com/fluency/96/shopping-bag.png", width=64)
    st.title("🛒 Shopping Agent")
    st.caption("AI Decision Intelligence for Bangladesh Tech Retail")

    st.markdown("---")
    st.subheader("⚙️ Configuration")
    active_model = os.getenv("GEMINI_MODEL", "gemini-3.7-flash")
    st.info(f"**Engine:** `{active_model}`\n\n**Search:** DuckDuckGo + Jina Reader")

    st.markdown("### 🏬 Target Retailers")
    startech = st.checkbox("Star Tech", value=True)
    ryans = st.checkbox("Ryans Computers", value=True)
    daraz = st.checkbox("Daraz BD", value=True)
    pickaboo = st.checkbox("Pickaboo", value=True)

    st.markdown("---")
    st.subheader("🕒 Search History")
    if st.session_state.history:
        for idx, prev_q in enumerate(reversed(st.session_state.history[-5:])):
            if st.button(f"🔍 {prev_q[:28]}...", key=f"hist_{idx}"):
                st.session_state.current_query = prev_q
                st.rerun()
    else:
        st.caption("No previous searches yet.")


# Main Header
st.title("🇧🇩 Bangladesh AI Shopping Decision Agent")
st.markdown(
    "Don't just search links—**compare trade-offs**, understand **value ratings**, "
    "and get expert advice on **official warranties** before you spend your money."
)

# Quick Suggestion Chips
st.markdown("##### ⚡ Quick Scenarios")
col1, col2, col3, col4 = st.columns(4)
with col1:
    if st.button("💻 Gaming Laptop (< 120k BDT)", use_container_width=True):
        st.session_state.current_query = "I need a gaming laptop for AI and gaming under 120000 BDT in Bangladesh"
        st.rerun()
with col2:
    if st.button("📱 Camera Phone (< 45k BDT)", use_container_width=True):
        st.session_state.current_query = "Suggest best smartphone under 45k taka with great camera and battery"
        st.rerun()
with col3:
    if st.button("🖥️ Coding Monitor (< 20k BDT)", use_container_width=True):
        st.session_state.current_query = "Find best IPS monitor under 20000 BDT for programming in Dhaka"
        st.rerun()
with col4:
    if st.button("🇧🇩 amar 35k e phone lagbe", use_container_width=True):
        st.session_state.current_query = "amar 35k er moddhe bhalo camera ebong battery phone lagbe"
        st.rerun()

st.markdown("<br>", unsafe_allow_html=True)

# Search Input Bar
with st.form("search_form", clear_on_submit=False):
    query_input = st.text_input(
        "What are you looking to buy?",
        value=st.session_state.current_query,
        placeholder="e.g. RTX 4060 laptop under 130k taka, or 'amar 40k er moddhe bhalo camera phone lagbe'",
        help="Type in English, Bangla, or Banglish with your budget and priorities."
    )
    submit_button = st.form_submit_button("🔍 Research & Compare Products", type="primary", use_container_width=True)

# Execution logic
if submit_button and query_input.strip():
    query = query_input.strip()
    st.session_state.current_query = query
    if query not in st.session_state.history:
        st.session_state.history.append(query)

    with st.status("🤖 Agent is researching products across Bangladesh stores...", expanded=True) as status:
        st.write("🧠 **1. Requirement Analyzer:** Extracting category, budget, and priorities with Gemini...")
        # Run graph
        result: ShoppingAgentState = run_shopping_agent(query)

        st.write(f"🔎 **2. Search Coordinator:** Searched Bangladesh retailers (Star Tech, Ryans, Daraz, etc.)")
        st.write(f"📄 **3. Product Extractor:** Analyzed candidate pages and normalized BDT specifications")
        st.write(f"⚖️ **4. Recommendation Agent:** Ranked products and calculated value trade-offs")
        status.update(label="✅ Research and Comparison Complete!", state="complete", expanded=False)

    st.session_state.last_result = result


# Display Results
if st.session_state.last_result:
    res = st.session_state.last_result
    req: UserRequirement = res.get("requirements")
    recommendations = res.get("recommendations", [])

    st.markdown("---")

    # Intent Summary Banner
    if req:
        st.subheader("📋 Parsed Shopping Intent")
        m1, m2, m3, m4 = st.columns(4)
        m1.metric("Target Category", req.category.capitalize())
        m2.metric("Max Budget", f"{req.budget_max:,.0f} BDT" if req.budget_max else "Flexible")
        m3.metric("Primary Usage", ", ".join(req.usage_purposes).title())
        m4.metric("Language Detected", req.detected_language.upper())

    # Top Pick Hero Section
    if recommendations:
        winner = recommendations[0]
        p_win = winner.product

        st.markdown("<br>", unsafe_allow_html=True)
        st.markdown(f"""
        <div class="hero-card">
            <div style="display: flex; justify-content: space-between; align-items: center; margin-bottom: 0.5rem;">
                <span style="font-size: 1.25rem; font-weight: 700; color: #047857;">🏆 TOP RECOMMENDATION</span>
                {get_store_badge_html(p_win.store)}
            </div>
            <h2 style="margin: 0.25rem 0 0.75rem 0; font-weight: 700;">
                <a href="{p_win.url}" target="_blank" style="text-decoration: none; color: #111827;">{p_win.name}</a>
            </h2>
            <div style="display: flex; align-items: baseline; gap: 1rem; margin-bottom: 1rem;">
                <span class="price-tag">{format_bdt_price(p_win.price)}</span>
                <span style="background: #e0f2fe; color: #0369a1; padding: 4px 10px; border-radius: 8px; font-weight: 600; font-size: 0.9rem;">
                    Score: {winner.score} / 10
                </span>
                <span style="color: #4b5563; font-size: 0.9rem;">Warranty: {p_win.warranty or 'Standard Retail'}</span>
            </div>
            <p style="color: #374151; font-size: 0.95rem; margin-bottom: 0.75rem;">
                <strong>Why it wins:</strong> {winner.why_buy[0] if winner.why_buy else 'Best overall value for your requirements.'}
            </p>
        </div>
        """, unsafe_allow_html=True)

        st.link_button(f"🛒 View {p_win.name[:35]}... on {p_win.store}", p_win.url, type="primary")

        # Tabs for Deep Dive
        tab1, tab2, tab3, tab4 = st.tabs([
            "🛍️ Curated Products", 
            "📊 Side-by-Side Comparison", 
            "🛡️ BD Buying Advice", 
            "🔍 Agent Logs & Links"
        ])

        # TAB 1: PRODUCT CARDS
        with tab1:
            st.markdown("### All Ranked Recommendations")
            cols = st.columns(min(len(recommendations), 3))
            for idx, card in enumerate(recommendations):
                col = cols[idx % len(cols)]
                p = card.product
                with col:
                    with st.container(border=True):
                        st.markdown(f"**#{card.rank} {card.verdict}**")
                        st.markdown(get_store_badge_html(p.store), unsafe_allow_html=True)
                        st.subheader(p.name)
                        st.markdown(f"<span class='price-tag'>{format_bdt_price(p.price)}</span>", unsafe_allow_html=True)
                        st.caption(f"⭐ Rating: {card.score}/10 | Warranty: {p.warranty or 'Standard'}")

                        if p.specs:
                            st.markdown("**Specs:**")
                            for k, v in p.specs.items():
                                st.markdown(f"- **{k}:** `{v}`")

                        st.markdown("**Why Buy:**")
                        for r in card.why_buy:
                            st.markdown(f"✅ <span style='font-size:0.85rem;'>{r}</span>", unsafe_allow_html=True)

                        st.markdown("**Why NOT to Buy:**")
                        for r in card.why_not_buy:
                            st.markdown(f"⚠️ <span style='font-size:0.85rem; color:#b45309;'>{r}</span>", unsafe_allow_html=True)

                        st.caption(f"💡 {card.bangladesh_note}")
                        st.link_button(f"Open in {p.store}", p.url, use_container_width=True)

        # TAB 2: SIDE-BY-SIDE COMPARISON
        with tab2:
            st.markdown("### Side-by-Side Feature Matrix")
            df_compare = build_comparison_dataframe(recommendations)
            st.dataframe(df_compare, use_container_width=True, hide_index=True)

        # TAB 3: BANGLADESH BUYING ADVICE
        with tab3:
            st.markdown("### 💡 Bangladesh Buyer Guidance & Retailer Checklist")
            st.info("""
            **1. Official vs. Unofficial Warranty Check:**
            - Always ask the retailer whether the listed price is for **Official Distributor Warranty** (e.g. Star Tech / Ryans official brand import) or **Seller Shop Warranty**.
            - Unofficial units are often ৳5,000 - ৳25,000 cheaper but may not cover screen replacement or motherboard repairs.
            
            **2. Branch Stock Verification:**
            - Central Dhaka warehouses often have stock that individual branch outlets (e.g. Uttara, Chattogram, Rajshahi) have not yet received.
            - Call the specific outlet before visiting to confirm on-shelf readiness.
            
            **3. Cash Discount vs. EMI:**
            - Most Bangladeshi tech stores offer a 2% - 5% discount for direct cash/bKash payment compared to card EMI.
            """)

        # TAB 4: TRANSPARENCY & AGENT LOGS
        with tab4:
            st.markdown("### 🔍 Execution Trace & Discovered URLs")
            queries_run = res.get("search_queries", [])
            if queries_run:
                st.markdown("**Search Queries Executed:**")
                for q in queries_run:
                    st.code(q, language="text")

            candidate_urls = res.get("candidate_urls", [])
            if candidate_urls:
                st.markdown("**Discovered URLs:**")
                for c in candidate_urls:
                    st.markdown(f"- [{c.get('title')}]({c.get('url')}) `({c.get('store')})`")

            logs = res.get("logs", [])
            if logs:
                st.markdown("**LangGraph Execution Logs:**")
                for l in logs:
                    st.caption(f"• {l}")
    else:
        st.warning("No candidate products matched your exact search criteria. Please try relaxing the budget or broadening the keywords.")

