import pytest
from src.nodes.requirement_analyzer import fallback_extract_requirement, requirement_analyzer_node
from src.models import ShoppingAgentState


def test_laptop_requirement_extraction():
    query = "I need a gaming laptop for AI development under 120k BDT"
    req = fallback_extract_requirement(query)
    assert req.category == "laptop"
    assert req.budget_max == 120000.0
    assert "gaming" in req.usage_purposes
    assert "AI development" in req.usage_purposes
    assert req.detected_language == "en"


def test_phone_requirement_extraction():
    query = "Suggest a smartphone under 45000 taka with good camera and battery"
    req = fallback_extract_requirement(query)
    assert req.category == "smartphone"
    assert req.budget_max == 45000.0
    assert "camera" in req.usage_purposes
    assert "battery life" in req.usage_purposes


def test_bangla_banglish_detection():
    query_bn = "আমার ৫০ হাজার টাকার মধ্যে ভালো ল্যাপটপ লাগবে"
    req_bn = fallback_extract_requirement(query_bn)
    assert req_bn.detected_language == "bn"

    query_banglish = "amar 30k er moddhe bhalo phone lagbe"
    req_bg = fallback_extract_requirement(query_banglish)
    assert req_bg.detected_language == "banglish"
    assert req_bg.budget_max == 30000.0


def test_requirement_analyzer_node():
    state: ShoppingAgentState = {
        "user_query": "Need monitor under 20000 for coding",
        "logs": []
    }
    result_state = requirement_analyzer_node(state)
    assert "requirements" in result_state
    req = result_state["requirements"]
    assert req.category == "monitor"
    assert req.budget_max == 20000.0
    assert len(result_state["logs"]) > 0

