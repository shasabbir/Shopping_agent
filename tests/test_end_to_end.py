import pytest
from src.graph import run_shopping_agent


def test_end_to_end_laptop_pipeline():
    query = "I need a gaming laptop for AI development under 120000 BDT in Bangladesh"
    result = run_shopping_agent(query)

    # 1. Check requirements
    req = result.get("requirements")
    assert req is not None
    assert req.category == "laptop"
    assert req.budget_max == 120000.0
    assert any("game" in p.lower() or "ai" in p.lower() for p in req.usage_purposes)

    # 2. Check candidate search and extraction
    extracted = result.get("extracted_products", [])
    assert len(extracted) > 0

    # 3. Check recommendations
    recommendations = result.get("recommendations", [])
    assert len(recommendations) > 0

    winner = recommendations[0]
    assert winner.rank == 1
    assert winner.product.url.startswith("http")
    assert bool(winner.product.store)
    assert len(winner.why_buy) > 0
    assert len(winner.why_not_buy) > 0

    # 4. Check final answer formatting
    final_text = result.get("final_answer", "")
    assert "Winner:" in final_text or "Recommendation" in final_text
    assert "BDT" in final_text or "৳" in final_text


def test_end_to_end_phone_pipeline():
    query = "Suggest best phone under 45k taka with great camera"
    result = run_shopping_agent(query)

    req = result.get("requirements")
    assert req is not None
    assert req.category == "smartphone"
    assert req.budget_max == 45000.0

    recommendations = result.get("recommendations", [])
    assert len(recommendations) > 0

    top_phone = recommendations[0]
    assert top_phone.product.price is not None
    assert top_phone.product.price > 0
    assert len(top_phone.why_buy) > 0

    final_text = result.get("final_answer", "")
    assert "Bangladesh" in final_text

