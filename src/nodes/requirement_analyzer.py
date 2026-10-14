import re
import json
from src.models import ShoppingAgentState, UserRequirement
from src.llm import get_llm


REQUIREMENT_SYSTEM_PROMPT = """You are a universal shopping requirement analyst for Bangladesh e-commerce.
Your job is to analyze user shopping requests (which may be in English, Bangla, or Banglish) and extract structured requirements across ANY product category (e.g., footwear, apparel, kitchen appliances, home & living, cosmetics, consumer electronics, books, groceries, tools, furniture, etc.).

Rules:
1. Identify the target product category or specific item type (e.g. 'footwear', 'kitchen appliance', 'laptop', 'office chair', 'skincare', 'perfume', 'cookware').
2. Extract the maximum budget in BDT (convert 120k -> 120000, 40k -> 40000, taka -> BDT).
3. Identify intended usages, preferences, or target requirements (e.g. running, office, baking, gaming, daily wear, gift).
4. Identify must-have specs or features mentioned by the user (e.g. 'waterproof', 'digital display', 'leather', 'RTX 4060', 'OLED').
5. Detect whether the user language is English ('en'), Bangla ('bn'), or Banglish ('banglish').
6. Default location is Bangladesh.
7. Preferred stores should be empty unless explicitly specified by the user.

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
    """Robust regex-based fallback extractor supporting any product category."""
    q = query.lower()

    # Category detection across major consumer domains
    if any(k in q for k in ["shoe", "shoes", "sneaker", "sneakers", "boot", "boots", "sandal", "sandals", "loafer"]):
        category = "footwear"
    elif any(k in q for k in ["shirt", "t-shirt", "pant", "pants", "jeans", "jacket", "hoodie", "panjabi", "saree", "dress"]):
        category = "clothing"
    elif any(k in q for k in ["air fryer", "fryer", "blender", "oven", "cooker", "kettle", "pot", "pan", "grinder"]):
        category = "kitchen appliance"
    elif any(k in q for k in ["chair", "desk", "table", "sofa", "bed", "wardrobe", "bookshelf"]):
        category = "furniture"
    elif any(k in q for k in ["perfume", "cologne", "sunscreen", "serum", "lotion", "cream", "shampoo", "trimmer"]):
        category = "beauty & personal care"
    elif any(k in q for k in ["laptop", "notebook", "ultrabook", "macbook"]):
        category = "laptop"
    elif any(k in q for k in ["phone", "smartphone", "mobile"]):
        category = "smartphone"
    elif any(k in q for k in ["monitor", "display", "screen"]):
        category = "monitor"
    elif any(k in q for k in ["keyboard", "mouse", "headphone", "earbuds", "speaker", "gadget", "watch"]):
        category = "gadgets"
    else:
        # Generic product extraction
        words = [w for w in re.findall(r"\b[a-zA-Z]{3,}\b", q) if w not in ["need", "want", "suggest", "find", "best", "price", "taka", "bdt", "under", "good", "amar", "lagbe"]]
        category = words[0] if words else "consumer product"

    # Budget extraction
    budget = None
    k_match = re.search(r"(\d+(?:\.\d+)?)\s*(?:k|thousand|hajar|hazar)", q)
    num_match = re.search(r"(\d{3,7})", q)
    if k_match:
        budget = float(k_match.group(1)) * 1000
    elif num_match:
        budget = float(num_match.group(1))

    # Purposes & User Criteria
    purposes = []
    if any(k in q for k in ["game", "gaming", "esports"]):
        purposes.append("gaming")
    if any(k in q for k in ["running", "sports", "gym", "workout", "fitness"]):
        purposes.append("sports & fitness")
    if any(k in q for k in ["ai", "ml", "machine learning", "deep learning"]):
        purposes.append("AI development")
    if any(k in q for k in ["code", "coding", "program", "programming", "developer"]):
        purposes.append("programming")
    if any(k in q for k in ["office", "work"]):
        purposes.append("office & productivity")
    if any(k in q for k in ["baking", "cooking", "kitchen"]):
        purposes.append("cooking & kitchen")
    if any(k in q for k in ["waterproof", "water-resistant"]):
        purposes.append("waterproof")
    if any(k in q for k in ["casual", "daily", "regular"]):
        purposes.append("daily wear")
    if any(k in q for k in ["camera", "photo", "video"]):
        purposes.append("camera")
    if any(k in q for k in ["battery", "backup", "long-lasting"]):
        purposes.append("battery life")
    if not purposes:
        purposes.append("general consumer use")

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
        preferred_stores=[],
        detected_language=lang,
    )

