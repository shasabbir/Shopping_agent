from typing import List, Dict, Any
import pandas as pd
from src.models import RecommendationCard, ProductSpec


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
}


def get_store_badge_html(store_name: str) -> str:
    """Generate inline styled badge for any retail store with consistent colors."""
    if store_name in STORE_COLORS:
        color = STORE_COLORS[store_name]
    else:
        # Deterministic color hash for any newly discovered store domain
        color_idx = abs(hash(store_name)) % len(STORE_PALETTE)
        color = STORE_PALETTE[color_idx]

    return f"""<span style="background-color: {color}; color: white; padding: 3px 10px; border-radius: 9999px; font-size: 0.75rem; font-weight: 600; text-transform: uppercase; letter-spacing: 0.025em;">{store_name}</span>"""


def format_bdt_price(price: float | None) -> str:
    """Format numeric price into clean BDT string."""
    if price is None:
        return "Check Retail Link"
    return f"৳{price:,.0f}"


def build_comparison_dataframe(recommendations: List[RecommendationCard]) -> pd.DataFrame:
    """Transform recommendations into an adaptive comparison table with dynamic attribute columns."""
    if not recommendations:
        return pd.DataFrame()

    # Discover top 3-4 most common specification keys across all products
    key_frequency = {}
    for card in recommendations:
        for k in card.product.specs.keys():
            if k and len(k) <= 25 and not k.startswith("Highlight") and not k.startswith("Feature"):
                key_frequency[k] = key_frequency.get(k, 0) + 1

    # Sort keys by frequency across products
    top_keys = [k for k, _ in sorted(key_frequency.items(), key=lambda item: item[1], reverse=True)[:4]]

    data = []
    for card in recommendations:
        p: ProductSpec = card.product
        specs = p.specs or {}

        row = {
            "Rank": f"#{card.rank}",
            "Product": p.name,
            "Store": p.store,
            "Price": format_bdt_price(p.price),
            "Rating": f"{card.score}/10",
            "Verdict": card.verdict,
        }

        # Inject dynamic attribute columns
        if top_keys:
            for k in top_keys:
                row[k] = specs.get(k, "—")
        else:
            # Fallback if no structured keys discovered
            row["Specifications"] = ", ".join(f"{k}: {v}" for k, v in list(specs.items())[:3]) or "Standard Details"

        row["Warranty"] = p.warranty or "Standard Retail"
        row["Top Advantage"] = card.why_buy[0] if card.why_buy else "Solid all-rounder"
        row["Key Trade-off"] = card.why_not_buy[0] if card.why_not_buy else "Check local stock"

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
    font-size: 1.5rem;
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
</style>
"""
