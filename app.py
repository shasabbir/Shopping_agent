import os
import time
from typing import Dict, Any, List, Optional
import streamlit as st
import pandas as pd
from dotenv import load_dotenv

from src.database import (
    init_db,
    get_all_stores,
    get_active_stores,
    add_or_update_store,
    toggle_store_active,
    delete_store,
    get_catalog_stats,
    search_catalog,
    get_frontier_metrics,
    seed_frontier_from_stores,
    reset_failed_frontier_urls,
)
from src.crawler.universal_crawler import UniversalStoreCrawler
from src.crawler.daemon_crawler import (
    start_crawler_daemon,
    stop_crawler_daemon,
    is_crawler_daemon_running,
    get_crawler_daemon,
)
from src.graph import run_shopping_agent
from src.models import ShoppingAgentState, UserRequirement, ProductSpec, StoreOffer
from src.ui_helpers import (
    CUSTOM_CSS,
    build_comparison_dataframe,
    format_bdt_price,
    get_store_badge_html,
    render_sellers_html,
)

load_dotenv(override=True)

# Ensure database tables and seed stores exist
init_db()

st.set_page_config(
    page_title="AI Shopping Assistant | Bangladesh Multi-Store Comparison",
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
if "crawl_logs" not in st.session_state:
    st.session_state.crawl_logs = []

# Fetch current catalog metrics
catalog_stats = get_catalog_stats()

# Sidebar
with st.sidebar:
    st.image("https://img.icons8.com/fluency/96/shopping-bag.png", width=64)
    st.title("🛒 Shopping Agent")
    st.caption("Bangladesh Multi-Store Intelligence & AI Recommendations")

    st.markdown("---")
    st.subheader("📊 Catalog Intelligence")
    col_sb1, col_sb2 = st.columns(2)
    col_sb1.metric("Products", f"{catalog_stats['total_products']}")
    col_sb2.metric("Offers", f"{catalog_stats['total_offers']}")
    st.caption(f"🏪 Active Stores: **{catalog_stats['active_stores']} / {catalog_stats['total_stores']}**")
    if catalog_stats.get("latest_crawl"):
        st.caption(f"🕒 Last Crawled: `{catalog_stats['latest_crawl'][:16].replace('T', ' ')}`")

    st.markdown("---")
    st.subheader("⚙️ System Status")
    active_model = os.getenv("GEMINI_MODEL", "gemini-3.5-flash-lite")
    st.info(f"**Target Market:** Bangladesh (BDT ৳)\n\n**Engine:** Crawlee + LangGraph\n\n**LLM:** `{active_model}`")

    st.markdown("---")
    st.subheader("🕒 Search History")
    if st.session_state.history:
        for idx, prev_q in enumerate(reversed(st.session_state.history[-5:])):
            if st.button(f"🔍 {prev_q[:26]}...", key=f"hist_{idx}"):
                st.session_state.search_query = prev_q
                st.session_state.trigger_search = True
                st.rerun()
    else:
        st.caption("No previous searches yet.")


# Navigation Tabs
tab_assistant, tab_crawler, tab_catalog = st.tabs([
    "🛒 AI Shopping Assistant",
    "🏬 Store Manager & Sequential Crawler",
    "📦 Local Catalog Explorer"
])


# ==============================================================================
# TAB 1: AI SHOPPING ASSISTANT
# ==============================================================================
with tab_assistant:
    st.title("🛒 Universal AI Shopping Decision & Comparison Agent")
    st.markdown(
        "Search fresh products across **25+ Bangladeshi e-commerce websites**. Compare live prices across **multiple sellers**, "
        "verify official vs. shop warranties, and get an instant AI-powered trade-off breakdown."
    )

    # Quick Suggestion Chips across categories
    st.markdown("##### ⚡ Quick Scenarios Across Categories")
    col1, col2, col3, col4 = st.columns(4)
    with col1:
        if st.button("💻 Laptop (< 120k)", use_container_width=True):
            st.session_state.search_query = "gaming laptop under 120k for development"
            st.session_state.trigger_search = True
            st.rerun()
    with col2:
        if st.button("📱 Phone (< 45k)", use_container_width=True):
            st.session_state.search_query = "smartphone under 45k with best camera"
            st.session_state.trigger_search = True
            st.rerun()
    with col3:
        if st.button("👟 Running Shoes (< 5k)", use_container_width=True):
            st.session_state.search_query = "running shoes under 5000 tk in Bangladesh"
            st.session_state.trigger_search = True
            st.rerun()
    with col4:
        if st.button("🍳 Air Fryer (< 10k)", use_container_width=True):
            st.session_state.search_query = "digital air fryer under 10000 BDT in Bangladesh"
            st.session_state.trigger_search = True
            st.rerun()

    st.markdown("<br>", unsafe_allow_html=True)

    # Search Input Form
    with st.form("search_form", clear_on_submit=False):
        query_input = st.text_input(
            "What product are you looking to buy?",
            key="search_query",
            placeholder="e.g. 'gaming laptop under 120k', 'samsung phone under 45k', 'running shoes under 5000', or 'air fryer'",
            help="Type in English, Bangla, or Banglish with any target product and optional budget."
        )
        submit_button = st.form_submit_button("🔍 Search Across Stores, Compare & Advise", type="primary", use_container_width=True)

    # Execution Logic
    should_search = (submit_button and query_input.strip()) or (st.session_state.trigger_search and st.session_state.search_query.strip())
    if should_search:
        st.session_state.trigger_search = False
        query = st.session_state.search_query.strip()
        if query not in st.session_state.history:
            st.session_state.history.append(query)

        with st.status("🤖 Executing LangGraph Multi-Store Decision Pipeline...", expanded=True) as status:
            st.write("🧠 **Step 1: Requirement Analysis** — Understanding category, budget & feature priorities...")
            result: ShoppingAgentState = run_shopping_agent(query)

            st.write("🔎 **Step 2: Catalog Search & Multi-Seller Retrieval** — Matching canonical models & offers...")
            st.write("📄 **Step 3: Element Normalization & Freshness Check** — Verified microdata & store pricing...")
            st.write("⚖️ **Step 4: Gemini Comparative Analysis** — Scoring value, savings & retailer trade-offs...")
            status.update(label="✅ Analysis & Multi-Store Comparison Complete!", state="complete", expanded=False)

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
            m3.metric("Primary Usage", ", ".join(req.usage_purposes).title() if req.usage_purposes else "General")
            m4.metric("Products Ranked", f"{len(recommendations)} Options")

        # Top Pick Hero Section
        if recommendations:
            winner = recommendations[0]
            p_win: ProductSpec = winner.product

            st.markdown("<br>", unsafe_allow_html=True)
            img_col, details_col = st.columns([1, 2.5]) if p_win.image_url else (None, None)

            # Savings and Sellers
            savings_html = f'<span class="savings-chip">⚡ {winner.savings_text}</span>' if winner.savings_text else ''
            sellers_markup = render_sellers_html(p_win.offers, default_store=p_win.store, default_url=p_win.url)

            hero_html = f"""
            <div class="hero-card">
                <div style="display: flex; justify-content: space-between; align-items: center; margin-bottom: 0.5rem;">
                    <span style="font-size: 1.25rem; font-weight: 800; color: #047857;">🏆 TOP RECOMMENDATION (RANK #1)</span>
                    {get_store_badge_html(p_win.store)}
                </div>
                <h2 style="margin: 0.25rem 0 0.5rem 0; font-weight: 700;">
                    <a href="{p_win.url}" target="_blank" style="text-decoration: none; color: #0f172a;">{p_win.name}</a>
                </h2>
                <div style="display: flex; align-items: baseline; gap: 1rem; margin-bottom: 0.75rem; flex-wrap: wrap;">
                    <span class="price-tag">{format_bdt_price(p_win.price)}</span>
                    <span class="score-badge">Value Score: {winner.score} / 10</span>
                    {savings_html}
                    <span style="color: #64748b; font-size: 0.9rem;">Warranty: {p_win.warranty or 'Standard Retail'}</span>
                </div>
                <p style="color: #334155; font-size: 1rem; margin-bottom: 0.5rem;">
                    <strong>Why it wins:</strong> {winner.why_buy[0] if winner.why_buy else 'Delivers superior value for money and verified specs.'}
                </p>
                {sellers_markup}
            </div>
            """

            if img_col and details_col:
                with img_col:
                    st.image(p_win.image_url, width="stretch")
                with details_col:
                    st.markdown(hero_html, unsafe_allow_html=True)
                    st.link_button(f"🛒 Buy on {p_win.store} ({format_bdt_price(p_win.price)})", p_win.url, type="primary")
            else:
                st.markdown(hero_html, unsafe_allow_html=True)
                st.link_button(f"🛒 Buy on {p_win.store} ({format_bdt_price(p_win.price)})", p_win.url, type="primary")

            # Tabs for Deep Dive
            tab_compare, tab_cards, tab_advice, tab_logs = st.tabs([
                "📊 Multi-Seller Comparison Matrix",
                "🛍️ All Ranked Product Cards",
                "🛡️ Bangladesh Buying Advice",
                "🔍 LangGraph Execution Trace"
            ])

            # SUB-TAB 1: COMPARISON TABLE
            with tab_compare:
                st.markdown(f"### 📊 Side-by-Side Comparison Matrix ({len(recommendations)} Products)")
                st.caption("Compare prices, competing sellers, potential savings, specifications, and value ratings at a glance.")
                df_compare = build_comparison_dataframe(recommendations)
                st.dataframe(df_compare, use_container_width=True, hide_index=True)

            # SUB-TAB 2: PRODUCT CARDS
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
                            st.caption(f"⭐ Value Score: {card.score}/10 | Warranty: {p.warranty or 'Standard'}")

                            if p.specs:
                                st.markdown("**Key Specs:**")
                                for k, v in list(p.specs.items())[:4]:
                                    st.markdown(f"<span class='spec-chip'><strong>{k}:</strong> {v}</span>", unsafe_allow_html=True)

                            # Multi-seller pills on each card
                            st.markdown(render_sellers_html(p.offers, default_store=p.store, default_url=p.url), unsafe_allow_html=True)

                            st.markdown("<br>**Why to Buy:**", unsafe_allow_html=True)
                            for r in card.why_buy[:2]:
                                st.markdown(f"✅ <span style='font-size:0.85rem;'>{r}</span>", unsafe_allow_html=True)

                            st.markdown("**Why NOT to Buy:**")
                            for r in card.why_not_buy[:2]:
                                st.markdown(f"⚠️ <span style='font-size:0.85rem; color:#b45309;'>{r}</span>", unsafe_allow_html=True)

                            st.link_button(f"View Best Deal on {p.store}", p.url, use_container_width=True)

            # SUB-TAB 3: BUYING ADVICE
            with tab_advice:
                st.markdown("### 💡 Bangladesh E-Commerce Buying Advice & Retailer Checklist")
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

            # SUB-TAB 4: LOGS & TRACE
            with tab_logs:
                st.markdown("### 🔍 Execution Trace & Pipeline Logs")
                queries_run = res.get("search_queries", [])
                if queries_run:
                    st.markdown("**Queries Executed:**")
                    for q in queries_run:
                        st.code(q, language="text")

                logs = res.get("logs", [])
                if logs:
                    st.markdown("**Pipeline Logs:**")
                    for l in logs:
                        st.caption(f"• {l}")
        else:
            st.warning("No candidate products matched your search. Try broadening your query or running the sequential crawler in the Store Manager tab.")


# ==============================================================================
# TAB 2: STORE MANAGER & SEQUENTIAL CRAWLER
# ==============================================================================
with tab_crawler:
    st.header("🏬 Store Manager & Sequential Crawler")
    st.markdown(
        "Manage your **20–30 target Bangladeshi stores** and trigger automated sequential crawling. "
        "The universal extractor parses Schema.org JSON-LD, OpenGraph, Microdata, and HTML structures **without any store-specific code**."
    )

    # Store Metrics Overview
    all_stores = get_all_stores()
    active_stores = [s for s in all_stores if s["is_active"]]

    sm1, sm2, sm3, sm4 = st.columns(4)
    sm1.metric("Configured Stores", f"{len(all_stores)} Stores")
    sm2.metric("Active Crawl Targets", f"{len(active_stores)} Stores")
    sm3.metric("Indexed Products", f"{catalog_stats['total_products']} Items")
    sm4.metric("Store Offers", f"{catalog_stats['total_offers']} Deals")

    # Continuous Stealth Crawler Section (Anti-Bot Pattern)
    st.subheader("🤖 Continuous Stealth Crawler Daemon (Anti-Bot Pattern)")
    st.markdown(
        "Runs an **interleaved multi-store round-robin** crawler continuously in the background until all product data is gathered. "
        "Rotates TLS client personas, calculates human log-normal delay jitter, and automatically enforces per-host cooldowns to prevent IP blocks."
    )

    daemon_running = is_crawler_daemon_running()
    daemon = get_crawler_daemon()
    frontier_stats = get_frontier_metrics()

    # Metric Row for Frontier & Daemon Health
    fc1, fc2, fc3, fc4, fc5 = st.columns(5)
    fc1.metric("Daemon Status", "🟢 Running" if daemon_running else "⚪ Idle")
    fc2.metric("Queue Pending", f"{frontier_stats['pending']:,} URLs")
    fc3.metric("Indexed / Completed", f"{frontier_stats['completed']:,} URLs")
    fc4.metric("Dead / Retries", f"{frontier_stats.get('dead', 0):,} Dead / {frontier_stats['failed']:,} Failed")
    active_cooldowns = [
        s["name"] for s in active_stores if hasattr(daemon, "circuit_breaker") and not daemon.circuit_breaker.is_eligible(s["id"])
    ] if daemon_running else []
    fc5.metric("Hosts in Cooldown", f"{len(active_cooldowns)} Stores")

    col_d1, col_d2, col_d3 = st.columns([2, 1, 1.2])
    with col_d1:
        speed_choice = st.selectbox(
            "Anti-Bot Cadence Profile:",
            options=["stealth", "normal", "turbo"],
            index=1,
            format_func=lambda x: {
                "stealth": "🛡️ High Stealth (3.0s - 12.0s Log-Normal + 20s Reading Pauses)",
                "normal": "⚡ Balanced (1.8s - 7.5s Log-Normal Jitter)",
                "turbo": "🚀 Turbo (0.8s - 3.5s Rapid Gathering)"
            }.get(x, x),
            disabled=daemon_running
        )
    with col_d2:
        st.write("")
        st.write("")
        if not daemon_running:
            if st.button("▶ Start Continuous Crawler", type="primary", use_container_width=True):
                seed_frontier_from_stores(reset_dead=True)
                reset_failed_frontier_urls()
                start_crawler_daemon(speed_profile=speed_choice)
                st.success("Continuous Stealth Daemon started in background!")
                time.sleep(0.5)
                st.rerun()
        else:
            if st.button("⏹ Stop Daemon", type="secondary", use_container_width=True):
                stop_crawler_daemon()
                st.warning("Stop requested. Daemon will conclude current host cycle.")
                time.sleep(0.5)
                st.rerun()
    with col_d3:
        st.write("")
        st.write("")
        col_btn1, col_btn2 = st.columns(2)
        with col_btn1:
            if st.button("🔄 Refresh", use_container_width=True):
                st.rerun()
        with col_btn2:
            if st.button("♻️ Revive", use_container_width=True, help="Reset dead and failed URLs back to pending"):
                revived = reset_failed_frontier_urls()
                st.toast(f"Revived {revived} URLs back to pending queue!")
                time.sleep(0.5)
                st.rerun()

    if daemon_running:
        status_info = daemon.get_status()
        cur_store = status_info.get("current_store")
        cur_url = status_info.get("current_url")
        if cur_store in ["Idle / Waiting", "Idle / Stopped"] or not cur_store:
            st.info("💤 **Daemon Status:** Standing by. Interleaving hosts or waiting on next eligible items.")
        else:
            st.info(f"⏳ **Active Host:** `{cur_store}` | **Target:** `{cur_url[:75] if cur_url else 'Processing...'}`")
        if active_cooldowns:
            st.warning(f"🛡️ **Hosts currently cooling down (rate-limit protection):** {', '.join(active_cooldowns)}")

    with st.expander("📜 Live Daemon Event Stream & Logs", expanded=daemon_running):
        daemon_logs = daemon.recent_logs if hasattr(daemon, "recent_logs") and daemon.recent_logs else ["Daemon idle. Click 'Start Continuous Crawler' to begin."]
        st.code("\n".join(daemon_logs[-15:]), language="text")

    st.markdown("---")

    # Sequential Crawler Execution Controls
    st.subheader("⚡ Manual Batch Crawler (Single Pass)")
    col_ctl1, col_ctl2 = st.columns([2, 1])

    with col_ctl1:
        st.markdown(
            "Click **Run Sequential Update** to execute an immediate single-pass sweep through active stores."
        )
    with col_ctl2:
        max_items_per_store = st.slider("Max items per store:", min_value=5, max_value=40, value=15, step=5)

    crawl_button = st.button("▶ Run Sequential Update Now", type="primary", use_container_width=True)

    if crawl_button:
        st.session_state.crawl_logs = []
        progress_bar = st.progress(0, text="Initializing universal crawler...")
        status_box = st.empty()
        log_expander = st.expander("📄 Real-Time Crawl Stream Logs", expanded=True)
        log_placeholder = log_expander.empty()

        crawler = UniversalStoreCrawler(max_products_per_store=max_items_per_store, timeout=6.0)

        def ui_progress_callback(event_type: str, data: Dict[str, Any]):
            msg = data.get("message", "")
            st.session_state.crawl_logs.append(f"[{time.strftime('%H:%M:%S')}] {msg}")
            
            # Update progress bar
            if event_type == "store_progress":
                idx = data.get("current_index", 1)
                total = data.get("total_stores", 1)
                pct = int((idx / total) * 100)
                progress_bar.progress(pct, text=f"Crawling Store {idx} of {total}: {data.get('store')}...")
                status_box.info(f"⏳ **Active Store:** `{data.get('store')}` (Step {idx}/{total})")

            # Stream logs
            recent_logs = "\n".join(st.session_state.crawl_logs[-12:])
            log_placeholder.code(recent_logs, language="text")

        with st.spinner("Sequential crawl in progress..."):
            results = crawler.crawl_all_stores_sequentially(
                stores=active_stores,
                progress_callback=ui_progress_callback
            )

        progress_bar.progress(100, text="✅ Sequential crawl completed!")
        status_box.success(f"🎉 Crawled {len(results)} stores! Updated catalog database.")
        st.rerun()

    st.markdown("---")

    # Add New Store Form
    with st.expander("➕ Add a New Bangladeshi Store", expanded=False):
        with st.form("add_store_form", clear_on_submit=True):
            st.write("Enter store details. The universal extractor will automatically discover sitemaps or catalog pages.")
            new_name = st.text_input("Store Name", placeholder="e.g. Unique Tech BD")
            new_url = st.text_input("Store Base URL", placeholder="e.g. https://www.uniquetechbd.com")
            new_sitemap = st.text_input("Optional Sitemap URL", placeholder="e.g. https://www.uniquetechbd.com/sitemap.xml")
            add_submitted = st.form_submit_button("Save Store to Database", type="primary")

            if add_submitted and new_name.strip() and new_url.strip():
                try:
                    add_or_update_store(new_name, new_url, new_sitemap)
                    st.success(f"Store '{new_name}' successfully added!")
                    st.rerun()
                except Exception as e:
                    st.error(f"Error saving store: {e}")

    # Store Inventory Table
    st.subheader(f"📋 Configured Store Roster ({len(all_stores)} Stores)")
    
    table_data = []
    for s in all_stores:
        table_data.append({
            "ID": s["id"],
            "Store Name": s["name"],
            "Active": "✅ Yes" if s["is_active"] else "❌ No",
            "Status": s["status"].upper(),
            "Items Indexed": s["total_products_found"] or 0,
            "Last Crawled": (s["last_crawled_at"][:16].replace("T", " ") if s.get("last_crawled_at") else "Never"),
            "Base URL": s["base_url"],
        })

    df_stores = pd.DataFrame(table_data)
    st.dataframe(df_stores, use_container_width=True, hide_index=True)

    # Store Action Controls
    st.markdown("##### ⚙️ Manage Individual Stores")
    store_options = {f"{s['name']} (ID: {s['id']})": s["id"] for s in all_stores}
    selected_store_label = st.selectbox("Select a store to manage:", list(store_options.keys()))

    if selected_store_label:
        sel_id = store_options[selected_store_label]
        target_s = next(s for s in all_stores if s["id"] == sel_id)

        c_btn1, c_btn2, c_btn3 = st.columns(3)
        with c_btn1:
            toggle_label = "Deactivate Store" if target_s["is_active"] else "Activate Store"
            if st.button(toggle_label, use_container_width=True):
                toggle_store_active(sel_id)
                st.rerun()
        with c_btn2:
            if st.button(f"🔍 Crawl Only {target_s['name']}", use_container_width=True):
                crawler = UniversalStoreCrawler(max_products_per_store=15)
                with st.spinner(f"Crawling {target_s['name']}..."):
                    res = crawler.crawl_single_store(target_s)
                    st.success(f"Crawled {res['offers_upserted']} products from {target_s['name']}!")
                    st.rerun()
        with c_btn3:
            if st.button("🗑️ Delete Store", use_container_width=True):
                delete_store(sel_id)
                st.warning(f"Store {target_s['name']} deleted.")
                st.rerun()


# ==============================================================================
# TAB 3: LOCAL CATALOG EXPLORER
# ==============================================================================
with tab_catalog:
    st.header("📦 Local Product Catalog & Price Intelligence")
    st.markdown(
        "Browse products and store offers indexed in your local database. "
        "View cross-store price spreads, warranty terms, and direct purchase links."
    )

    col_q1, col_q2 = st.columns([3, 1])
    with col_q1:
        cat_search = st.text_input("Filter indexed products:", placeholder="e.g. Lenovo, Samsung, Air Fryer, RTX 4050")
    with col_q2:
        cat_filter = st.selectbox("Category:", ["all", "laptop", "smartphone", "footwear", "kitchen appliance", "gadgets", "general"])

    category_arg = None if cat_filter == "all" else cat_filter
    matching_products = search_catalog(query_text=cat_search or "", category=category_arg, limit=30)

    st.markdown(f"**Found {len(matching_products)} products in local database:**")

    for p in matching_products:
        with st.container(border=True):
            p_cols = st.columns([1, 4])
            with p_cols[0]:
                if p.get("primary_image_url"):
                    st.image(p["primary_image_url"], width="stretch")
                else:
                    st.image("https://img.icons8.com/fluency/96/box.png", width=80)
            with p_cols[1]:
                lowest_price_str = format_bdt_price(p.get("lowest_price"))
                st.subheader(p["canonical_name"])
                st.markdown(f"<span class='price-tag'>{lowest_price_str}</span> <span style='color:#64748b;'>({p.get('offers_count', 0)} store offers)</span>", unsafe_allow_html=True)
                
                # Render offers
                offers = [StoreOffer(**o) for o in p.get("offers", [])]
                st.markdown(render_sellers_html(offers), unsafe_allow_html=True)

                if p.get("specs"):
                    for k, v in list(p["specs"].items())[:4]:
                        st.markdown(f"<span class='spec-chip'><strong>{k}:</strong> {v}</span>", unsafe_allow_html=True)
