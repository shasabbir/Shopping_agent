import re
import json
from src.models import ShoppingAgentState, UserRequirement
from src.llm import get_llm


REQUIREMENT_SYSTEM_PROMPT = """You are a shopping requirement analyst for Bangladesh e-commerce.
Your job is to analyze user shopping requests (which may be in English, Bangla, or Banglish) and extract structured requirements.

Rules:
1. Identify the target product category (e.g. 'laptop', 'smartphone', 'monitor', etc.).
2. Extract the maximum budget in BDT (convert 120k -> 120000, 40k -> 40000, taka -> BDT).
3. Identify intended usages (e.g. gaming, AI development, programming, office, camera, battery).
4. Identify must-have specs mentioned by the user (e.g. 'RTX 4060', '16GB RAM', 'OLED').
5. Detect whether the user language is English ('en'), Bangla ('bn'), or Banglish ('banglish').

User query: {query}
"""


def requirement_analyzer_node(state: ShoppingAgentState) -> ShoppingAgentState:
    """Extract structured shopping intent and constraints from user query."""
    query = state.get("user_query", "")
    llm = get_llm()

    try:
        # Attempt structured output extraction
        structured_llm = llm.with_structured_output(UserRequirement)
        requirement = structured_llm.invoke(REQUIREMENT_SYSTEM_PROMPT.format(query=query))
        if not isinstance(requirement, UserRequirement):
            requirement = UserRequirement(**dict(requirement))
    except Exception as e:
        print(f"[Requirement Analyzer] Structured call fallback: {e}")
        requirement = fallback_extract_requirement(query)

    logs = list(state.get("logs", []))
    logs.append(f"Requirements parsed: Category={requirement.category}, Budget={requirement.budget_max} BDT, Purposes={requirement.usage_purposes}")

    return {
        **state,
        "requirements": requirement,
        "logs": logs,
    }


def fallback_extract_requirement(query: str) -> UserRequirement:
    """Robust regex-based fallback extractor."""
    q = query.lower()

    # Category detection
    if any(k in q for k in ["laptop", "notebook", "ultrabook"]):
        category = "laptop"
    elif any(k in q for k in ["phone", "smartphone", "mobile"]):
        category = "smartphone"
    elif any(k in q for k in ["monitor", "display", "screen"]):
        category = "monitor"
    else:
        category = "electronics"

    # Budget extraction
    budget = None
    k_match = re.search(r"(\d+(?:\.\d+)?)\s*(?:k|thousand|hajar|hazar)", q)
    num_match = re.search(r"(\d{4,7})", q)
    if k_match:
        budget = float(k_match.group(1)) * 1000
    elif num_match:
        budget = float(num_match.group(1))

    # Purposes
    purposes = []
    if any(k in q for k in ["game", "gaming", "esports"]):
        purposes.append("gaming")
    if any(k in q for k in ["ai", "ml", "machine learning", "deep learning", "cuda"]):
        purposes.append("AI development")
    if any(k in q for k in ["code", "coding", "program", "developer"]):
        purposes.append("programming")
    if any(k in q for k in ["camera", "photo", "video"]):
        purposes.append("camera")
    if any(k in q for k in ["battery", "backup", "long-lasting"]):
        purposes.append("battery life")
    if not purposes:
        purposes.append("general daily use")

    # Language detection
    has_bangla_script = bool(re.search(r"[\u0980-\u09FF]", query))
    has_banglish_words = bool(re.search(r"\b(amar|amake|lagbe|taka|bhalo|koto|dam)\b", q))
    if has_bangla_script:
        lang = "bn"
    elif has_banglish_words:
        lang = "banglish"
    else:
        lang = "en"

    return UserRequirement(
        category=category,
        budget_max=budget,
        currency="BDT",
        location="Bangladesh",
        usage_purposes=purposes,
        priorities=purposes[:2],
        must_have_specs=[],
        preferred_stores=["Star Tech", "Ryans", "Daraz"],
        detected_language=lang,
    )

