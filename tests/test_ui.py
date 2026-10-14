import pytest
from src.models import RecommendationCard, ProductSpec
from src.ui_helpers import format_bdt_price, get_store_badge_html, build_comparison_dataframe


def test_format_bdt_price():
    assert format_bdt_price(115000.0) == "৳115,000"
    assert format_bdt_price(None) == "Check Retail Link"


def test_store_badge_html():
    badge = get_store_badge_html("Star Tech")
    assert "Star Tech" in badge
    assert "#ef4444" in badge


def test_build_comparison_dataframe():
    card = RecommendationCard(
        rank=1,
        product=ProductSpec(
            name="Apex Men's Sprint Running Shoes",
            store="Apex Footwear",
            price=4990.0,
            url="https://apex4u.com/shoes",
            specs={"Material": "Breathable Mesh", "Sole": "EVA Rubber", "Closure": "Lace-Up"},
            warranty="Standard Retail"
        ),
        verdict="Top Pick ⭐",
        score=9.2,
        why_buy=["Great cushioning"],
        why_not_buy=["Limited color options"],
        who_should_buy="Runners and fitness enthusiasts"
    )
    df = build_comparison_dataframe([card])
    assert len(df) == 1
    assert df.iloc[0]["Product"] == "Apex Men's Sprint Running Shoes"
    assert df.iloc[0]["Price"] == "৳4,990"
    assert df.iloc[0]["Rating"] == "9.2/10"
    assert "Material" in df.columns
    assert df.iloc[0]["Material"] == "Breathable Mesh"


