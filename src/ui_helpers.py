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
}


def get_store_badge_html(store_name: str) -> str:
    """Generate inline styled badge for retail store."""
    color = STORE_COLORS.get(store_name, "#6b7280")
    return f"""<span style="background-color: {color}; color: white; padding: 2px 8px; border-radius: 9999px; font-size: 0.75rem; font-weight: 600; text-transform: uppercase;">{store_name}</span>"""


def format_bdt_price(price: float | None) -> str:
    """Format numeric price into clean BDT string."""
    if price is None:
        return "Check Retail Link"
    return f"৳{price:,.0f}"


def build_comparison_dataframe(recommendations: List[RecommendationCard]) -> pd.DataFrame:
    """Transform list of recommendations into a structured comparison table."""
    data = []
    for card in recommendations:
        p: ProductSpec = card.product
        specs = p.specs
        
        row = {
            "Rank": f"#{card.rank}",
            "Product": p.name,
            "Store": p.store,
            "Price": format_bdt_price(p.price),
            "Rating": f"{card.score}/10",
            "Verdict": card.verdict,
            "Warranty": p.warranty or "Standard Retail",
            "Processor": specs.get("CPU", "N/A"),
            "Graphics / Camera": specs.get("GPU") or specs.get("Camera") or "N/A",
            "RAM": specs.get("RAM", "N/A"),
            "Storage": specs.get("Storage", "N/A"),
            "Top Advantage": card.why_buy[0] if card.why_buy else "Good balance",
            "Trade-off Caution": card.why_not_buy[0] if card.why_not_buy else "Standard warranty applies",
        }
        data.append(row)

    return pd.DataFrame(data)


CUSTOM_CSS = """
<style>
/* Clean card styling */
.product-card {
    border: 1px solid #e5e7eb;
    border-radius: 12px;
    padding: 1.25rem;
    margin-bottom: 1rem;
    background-color: #ffffff;
    box-shadow: 0 1px 3px rgba(0,0,0,0.05);
    transition: transform 0.15s ease, box-shadow 0.15s ease;
}
.product-card:hover {
    transform: translateY(-2px);
    box-shadow: 0 4px 6px -1px rgba(0,0,0,0.1);
}
.hero-card {
    border: 2px solid #10b981;
    border-radius: 14px;
    background: linear-gradient(135deg, #f0fdf4 0%, #ffffff 100%);
    padding: 1.5rem;
    margin-bottom: 1.5rem;
}
.price-tag {
    font-size: 1.5rem;
    font-weight: 700;
    color: #059669;
}
.spec-chip {
    display: inline-block;
    background-color: #f3f4f6;
    color: #374151;
    padding: 2px 8px;
    border-radius: 6px;
    font-size: 0.8rem;
    margin-right: 4px;
    margin-bottom: 4px;
}
</style>
"""

