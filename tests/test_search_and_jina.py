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
    assert identify_store("https://www.aarong.com/clothing/123") == "Aarong"
    assert identify_store("https://apex4u.com/product/shoes") == "Apex Footwear"
    # Dynamic domain inference without hardcoded entry
    assert identify_store("https://custom-boutique.com/item/1") == "Custom Boutique"


def test_extract_bdt_prices():
    text1 = "Regular Price: 115,000৳ Special Cash Price: 112,000 BDT"
    price1 = extract_price_from_text(text1)
    assert price1 in [115000.0, 112000.0]

    text2 = "Samsung Galaxy A55 price in Bangladesh is 46,999 BDT."
    assert extract_price_from_text(text2) == 46999.0

    # Non-price specifications must NEVER decode as prices
    assert extract_price_from_text("RPM: 18000 Approx at No Load") is None
    assert extract_price_from_text("5000 mAh Battery") is None
    assert extract_price_from_text("Size: 42 EU Running Shoes") is None
    assert extract_price_from_text("Intel Core i5-14400 14th Gen Desktop PC") is None

    # Out of stock or TBA notices must return None
    assert extract_price_from_text("Out Of Stock") is None
    assert extract_price_from_text("To be announced") is None
    assert extract_price_from_text("Price: Out Of Stock") is None


def test_extract_specs():
    sample_text = "Lenovo LOQ 15 Gaming Laptop comes with Core i5-12450HX, 16GB DDR5 RAM, 512GB SSD, RTX 4060 8GB Graphics, 15.6 inch FHD 144Hz Display."
    specs = extract_specs_from_text(sample_text)
    assert "RAM" in specs
    assert "16" in specs["RAM"]
    assert "GPU" in specs
    assert "RTX 4060" in specs["GPU"]
    assert "CPU" in specs
    assert "Storage" in specs

    # Non-tech footwear & appliance specs
    shoe_text = "Men's Sprint Running Shoes. Material: Breathable Mesh, Sole: EVA Rubber, Lace-Up Closure."
    shoe_specs = extract_specs_from_text(shoe_text)
    assert "Material" in shoe_specs or "Sole" in shoe_specs or "Closure" in shoe_specs


def test_search_coordinator():
    state: ShoppingAgentState = {
        "user_query": "gaming laptop under 120k",
        "requirements": UserRequirement(
            category="laptop",
            budget_max=120000.0,
            usage_purposes=["gaming"],
            location="Bangladesh",
            preferred_stores=[]
        ),
        "logs": []
    }
    updated = search_coordinator_node(state)
    assert len(updated["search_queries"]) >= 1
    assert len(updated.get("extracted_products", [])) > 0 or len(updated.get("candidate_urls", [])) > 0
    # Zero store bias: queries must not inject specific store names unless explicitly requested
    assert all("Star Tech" not in q for q in updated["search_queries"])

