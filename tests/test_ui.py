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
            name="Lenovo LOQ 15",
            store="Star Tech",
            price=118000.0,
            url="https://startech.com.bd/loq",
            specs={"GPU": "RTX 4060", "RAM": "16GB", "CPU": "Core i5"},
            warranty="2 Years Official"
        ),
        verdict="Top Pick ⭐",
        score=9.2,
        why_buy=["Great GPU value"],
        why_not_buy=["Runs warm under full load"],
        who_should_buy="Gamers and AI developers"
    )
    df = build_comparison_dataframe([card])
    assert len(df) == 1
    assert df.iloc[0]["Product"] == "Lenovo LOQ 15"
    assert df.iloc[0]["Price"] == "৳118,000"
    assert df.iloc[0]["Rating"] == "9.2/10"
    assert df.iloc[0]["Warranty"] == "2 Years Official"

