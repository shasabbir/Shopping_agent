from typing import List, Dict, Any
import pandas as pd
from src.models import RecommendationCard, ProductSpec


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
}


def get_store_badge_html(store_name: str) -> str:
    """Generate inline styled badge for retail store."""
    color = STORE_COLORS.get(store_name, "#6b7280")
    return f"""<span style="background-color: {color}; color: white; padding: 3px 10px; border-radius: 9999px; font-size: 0.75rem; font-weight: 600; text-transform: uppercase; letter-spacing: 0.025em;">{store_name}</span>"""


def format_bdt_price(price: float | None) -> str:
    """Format numeric price into clean BDT string."""
    if price is None:
        return "Check Retail Link"
    return f"৳{price:,.0f}"


def build_comparison_dataframe(recommendations: List[RecommendationCard]) -> pd.DataFrame:
    """Transform list of up to 10 recommendations into a structured comparison table."""
    data = []
    for card in recommendations:
        p: ProductSpec = card.product
        specs = p.specs or {}
        
        # Determine key specs based on product type
        spec_items = list(specs.items())
        spec_1 = specs.get("CPU") or specs.get("Switch Type") or (f"{spec_items[0][0]}: {spec_items[0][1]}" if len(spec_items) > 0 else "N/A")
        spec_2 = specs.get("GPU") or specs.get("Camera") or specs.get("Lighting") or (f"{spec_items[1][0]}: {spec_items[1][1]}" if len(spec_items) > 1 else "N/A")
        spec_3 = specs.get("RAM") or specs.get("Connectivity") or (f"{spec_items[2][0]}: {spec_items[2][1]}" if len(spec_items) > 2 else "N/A")
        spec_4 = specs.get("Storage") or specs.get("Display") or specs.get("Key Count") or (f"{spec_items[3][0]}: {spec_items[3][1]}" if len(spec_items) > 3 else "N/A")

        row = {
            "Rank": f"#{card.rank}",
            "Product": p.name,
            "Store": p.store,
            "Price": format_bdt_price(p.price),
            "Rating": f"{card.score}/10",
            "Verdict": card.verdict,
            "Spec #1": spec_1,
            "Spec #2": spec_2,
            "Spec #3": spec_3,
            "Spec #4": spec_4,
            "Warranty": p.warranty or "Standard Retail",
            "Top Advantage": card.why_buy[0] if card.why_buy else "Solid all-rounder",
            "Key Trade-off": card.why_not_buy[0] if card.why_not_buy else "Check local stock",
        }
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
