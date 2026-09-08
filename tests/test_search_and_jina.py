import pytest
from src.tools.search import identify_store, search_bangladesh_products
from src.nodes.product_extractor import extract_price_from_text, extract_specs_from_text, parse_page_to_product
from src.nodes.search_coordinator import search_coordinator_node
from src.models import ShoppingAgentState, UserRequirement


def test_identify_bangladesh_stores():
    assert identify_store("https://www.startech.com.bd/product/123") == "Star Tech"
    assert identify_store("https://ryans.com/item/456") == "Ryans Computers"
    assert identify_store("https://www.daraz.com.bd/products/789") == "Daraz Bangladesh"
    assert identify_store("https://pickaboo.com/product/phone") == "Pickaboo"


def test_extract_bdt_prices():
    text1 = "Regular Price: 115,000৳ Special Cash Price: 112,000 BDT"
    price1 = extract_price_from_text(text1)
    assert price1 in [115000.0, 112000.0]

    text2 = "Samsung Galaxy A55 price in Bangladesh is 46,999 BDT."
    assert extract_price_from_text(text2) == 46999.0


def test_extract_specs():
    sample_text = "Lenovo LOQ 15 Gaming Laptop comes with Core i5-12450HX, 16GB DDR5 RAM, 512GB SSD, RTX 4060 8GB Graphics, 15.6 inch FHD 144Hz Display."
    specs = extract_specs_from_text(sample_text)
    assert "RAM" in specs
    assert "16" in specs["RAM"]
    assert "GPU" in specs
    assert "RTX 4060" in specs["GPU"]
    assert "CPU" in specs
    assert "Storage" in specs


def test_search_coordinator():
    state: ShoppingAgentState = {
        "user_query": "gaming laptop under 120k",
        "requirements": UserRequirement(
            category="laptop",
            budget_max=120000.0,
            usage_purposes=["gaming"],
            location="Bangladesh"
        ),
        "logs": []
    }
    updated = search_coordinator_node(state)
    assert len(updated["search_queries"]) >= 2
    assert len(updated["candidate_urls"]) > 0
    assert any("Star Tech" in r["store"] or "Ryans" in r["store"] for r in updated["candidate_urls"])

