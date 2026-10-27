from typing import List, Dict, Any, Optional
import pandas as pd
from src.models import RecommendationCard, ProductSpec, StoreOffer


STORE_PALETTE = [
    "#2563eb", "#7c3aed", "#059669", "#d97706", "#dc2626",
    "#0891b2", "#db2777", "#4f46e5", "#0d9488", "#ea580c"
]

STORE_COLORS = {
    "Star Tech": "#ef4444",
    "Ryans Computers": "#2563eb",
    "Daraz Bangladesh": "#f97316",
    "Pickaboo": "#10b981",
    "TechLand BD": "#8b5cf6",
    "Gadget & Gear": "#ec4899",
    "Apple Gadgets BD": "#0ea5e9",
    "BDStall": "#14b8a6",
    "Vibe Gaming": "#a855f7",
    "Apex Footwear": "#059669",
    "Bata Bangladesh": "#dc2626",
    "Aarong": "#b91c1c",
    "Singer Bangladesh": "#e11d48",
    "Walton Plaza": "#1d4ed8",
    "Transcom Digital": "#0369a1",
    "Skyland BD": "#0284c7",
    "Custom Mac BD": "#475569",
}


def get_store_badge_html(store_name: str) -> str:
    """Generate inline styled badge for any retail store with consistent colors."""
    if store_name in STORE_COLORS:
        color = STORE_COLORS[store_name]
    else:
        color_idx = abs(hash(store_name)) % len(STORE_PALETTE)
        color = STORE_PALETTE[color_idx]

    return f"""<span style="background-color: {color}; color: white; padding: 3px 10px; border-radius: 9999px; font-size: 0.75rem; font-weight: 600; text-transform: uppercase; letter-spacing: 0.025em;">{store_name}</span>"""


def format_bdt_price(price: float | None) -> str:
    """Format numeric price into clean BDT string."""
    if price is None:
        return "Check Retail Link"
    return f"৳{price:,.0f}"


def render_sellers_html(offers: List[StoreOffer], default_store: str = "", default_url: str = "") -> str:
    """Render interactive multi-seller price comparison card with direct verified store links."""
    if not offers:
        if default_store and default_url:
            return f"""
            <div style="margin-top: 0.75rem;">
                <span style="font-size: 0.85rem; font-weight: 700; color: #475569;">Verified Seller:</span>
                <div style="margin-top: 0.35rem;">
                    <a href="{default_url}" target="_blank" class="seller-pill best-deal-pill">
                        <strong>{default_store}</strong> &bull; Direct Retail Link
                    </a>
                </div>
            </div>
            """
        return ""

    # Sort offers: lowest price first
    sorted_offers = sorted(offers, key=lambda o: (not o.in_stock, o.price_bdt))
    min_price = sorted_offers[0].price_bdt

    pills = []
    for idx, o in enumerate(sorted_offers):
        is_lowest = (o.price_bdt == min_price)
        store_color = STORE_COLORS.get(o.store_name, "#2563eb")
        
        lowest_tag = '<span class="lowest-badge">BEST PRICE</span>' if is_lowest else ''
        stock_tag = '' if o.in_stock else '<span style="color:#ef4444; font-size:0.75rem;">(Out of Stock)</span>'

        pill_html = f"""
        <a href="{o.url}" target="_blank" class="seller-pill {'best-deal-pill' if is_lowest else ''}">
            <span class="store-dot" style="background-color: {store_color};"></span>
            <strong>{o.store_name}</strong>
            <span class="seller-price-val">৳{o.price_bdt:,.0f}</span>
            {lowest_tag}
            {stock_tag}
        </a>
        """
        pills.append(pill_html)

    return f"""
    <div class="sellers-block">
        <div style="display: flex; justify-content: space-between; align-items: center; margin-bottom: 0.5rem;">
            <span style="font-size: 0.85rem; font-weight: 700; color: #1e293b; text-transform: uppercase; letter-spacing: 0.05em;">
                🏪 Available Sellers ({len(offers)} Stores)
            </span>
            <span style="font-size: 0.8rem; color: #64748b;">Click seller to buy directly</span>
        </div>
        <div class="sellers-flex">
            {''.join(pills)}
        </div>
    </div>
    """


def build_comparison_dataframe(recommendations: List[RecommendationCard]) -> pd.DataFrame:
    """Transform recommendations into an adaptive comparison table with multi-seller comparison."""
    if not recommendations:
        return pd.DataFrame()

    # Discover top 3-4 most common specification keys across all products
    key_frequency = {}
    for card in recommendations:
        for k in card.product.specs.keys():
            if k and len(k) <= 25 and not k.startswith("Highlight") and not k.startswith("Feature"):
                key_frequency[k] = key_frequency.get(k, 0) + 1

    top_keys = [k for k, _ in sorted(key_frequency.items(), key=lambda item: item[1], reverse=True)[:3]]

    data = []
    for card in recommendations:
        p: ProductSpec = card.product
        specs = p.specs or {}

        # Competing sellers summary
        if p.offers and len(p.offers) > 1:
            sellers_str = " | ".join(f"{o.store_name}: ৳{o.price_bdt:,.0f}" for o in p.offers[:3])
            if len(p.offers) > 3:
                sellers_str += f" (+{len(p.offers)-3} more)"
        else:
            sellers_str = p.store

        savings_str = f"৳{p.savings:,.0f}" if p.savings else "Best Single Offer"

        row = {
            "Rank": f"#{card.rank}",
            "Product": p.name,
            "Price": format_bdt_price(p.price),
            "Best Price": format_bdt_price(p.price),
            "Best Store": p.store,
            "All Sellers": sellers_str,
            "Potential Savings": savings_str,
            "Rating": f"{card.score}/10",
            "Verdict": card.verdict,
        }

        # Inject dynamic attribute columns
        if top_keys:
            for k in top_keys:
                row[k] = specs.get(k, "—")
        else:
            row["Specifications"] = ", ".join(f"{k}: {v}" for k, v in list(specs.items())[:3]) or "Standard Details"

        row["Warranty"] = p.warranty or "Standard Retail"
        row["Top Advantage"] = card.why_buy[0] if card.why_buy else "Solid all-rounder"

        data.append(row)

    return pd.DataFrame(data)


CUSTOM_CSS = """
<style>
/* Modern, vibrant styling */
.main {
    background-color: #f8fafc;
}
.product-card {
    border: 1px solid #e2e8f0;
    border-radius: 14px;
    padding: 1.25rem;
    margin-bottom: 1rem;
    background-color: #ffffff;
    box-shadow: 0 2px 4px rgba(0,0,0,0.04);
    transition: transform 0.15s ease, box-shadow 0.15s ease;
}
.product-card:hover {
    transform: translateY(-2px);
    box-shadow: 0 10px 15px -3px rgba(0, 0, 0, 0.08);
}
.hero-card {
    border: 2px solid #10b981;
    border-radius: 16px;
    background: linear-gradient(135deg, #ecfdf5 0%, #ffffff 100%);
    padding: 1.75rem;
    margin-bottom: 1.5rem;
    box-shadow: 0 4px 6px -1px rgba(16, 185, 129, 0.1);
}
.price-tag {
    font-size: 1.6rem;
    font-weight: 800;
    color: #059669;
}
.score-badge {
    background: #e0f2fe;
    color: #0369a1;
    padding: 4px 10px;
    border-radius: 8px;
    font-weight: 700;
    font-size: 0.9rem;
}
.savings-chip {
    background: #fef3c7;
    color: #b45309;
    padding: 4px 10px;
    border-radius: 8px;
    font-weight: 700;
    font-size: 0.85rem;
    border: 1px solid #fde68a;
}
.spec-chip {
    display: inline-block;
    background-color: #f1f5f9;
    color: #334155;
    padding: 3px 8px;
    border-radius: 6px;
    font-size: 0.8rem;
    font-weight: 500;
    margin-right: 4px;
    margin-bottom: 4px;
}
.sellers-block {
    background: #f8fafc;
    border: 1px solid #e2e8f0;
    border-radius: 12px;
    padding: 0.85rem;
    margin-top: 0.85rem;
    margin-bottom: 0.85rem;
}
.sellers-flex {
    display: flex;
    flex-wrap: wrap;
    gap: 0.5rem;
}
.seller-pill {
    display: inline-flex;
    align-items: center;
    gap: 0.45rem;
    background: #ffffff;
    border: 1px solid #cbd5e1;
    border-radius: 8px;
    padding: 0.45rem 0.75rem;
    font-size: 0.85rem;
    color: #1e293b;
    text-decoration: none;
    transition: all 0.15s ease;
}
.seller-pill:hover {
    border-color: #0284c7;
    background: #f0f9ff;
    text-decoration: none;
    transform: translateY(-1px);
}
.best-deal-pill {
    border: 1.5px solid #10b981;
    background: #f0fdf4;
}
.store-dot {
    width: 8px;
    height: 8px;
    border-radius: 50%;
    display: inline-block;
}
.seller-price-val {
    font-weight: 700;
    color: #0f172a;
}
.lowest-badge {
    background: #10b981;
    color: white;
    font-size: 0.65rem;
    font-weight: 700;
    padding: 2px 6px;
    border-radius: 4px;
    text-transform: uppercase;
}
.stat-card {
    background: white;
    border: 1px solid #e2e8f0;
    border-radius: 12px;
    padding: 1rem;
    text-align: center;
    box-shadow: 0 1px 3px rgba(0,0,0,0.05);
}
.stat-val {
    font-size: 1.75rem;
    font-weight: 800;
    color: #0f172a;
}
.stat-label {
    font-size: 0.85rem;
    color: #64748b;
    font-weight: 600;
}
</style>
"""
