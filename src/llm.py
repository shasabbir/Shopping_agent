import os
import re
import json
from typing import Optional, Any
from dotenv import load_dotenv

load_dotenv(override=True)


def extract_text_content(response: Any) -> str:
    """Extract plain text string from LLM response whether it is a string,
    AIMessage, or list of content blocks."""
    if hasattr(response, "content"):
        content = response.content
    else:
        content = response

    if isinstance(content, str):
        return content
    elif isinstance(content, list):
        parts = []
        for block in content:
            if isinstance(block, dict) and "text" in block:
                parts.append(block["text"])
            elif isinstance(block, str):
                parts.append(block)
        return "\n".join(parts)
    return str(content)


def get_llm(model: Optional[str] = None, temperature: float = 0.2):
    """Returns a ChatGoogleGenerativeAI instance if GEMINI_API_KEY is available,
    with multi-model fallback, otherwise returns MockShoppingLLM for deterministic offline tests."""
    api_key = os.getenv("GEMINI_API_KEY", "").strip()
    preferred_model = model or os.getenv("GEMINI_MODEL", "gemini-3.5-flash-lite")

    if api_key and not api_key.startswith("your_"):
        candidate_models = [preferred_model]
        for fallback in ["gemini-3.5-flash-lite", "gemini-3.6-flash", "gemini-flash-latest"]:
            if fallback not in candidate_models:
                candidate_models.append(fallback)

        from langchain_google_genai import ChatGoogleGenerativeAI
        for m in candidate_models:
            try:
                llm = ChatGoogleGenerativeAI(
                    model=m,
                    google_api_key=api_key,
                    temperature=temperature,
                )
                return llm
            except Exception as e:
                print(f"[Warning] Failed to initialize ChatGoogleGenerativeAI with model {m}: {e}")
                continue

    return MockShoppingLLM()


class MockShoppingLLM:
    """Deterministic mock LLM for offline testing and demonstration without an API key."""

    def invoke(self, prompt: Any) -> Any:
        text = str(prompt)
        content = self._generate_response(text)
        
        class MockMessage:
            def __init__(self, content):
                self.content = content
        return MockMessage(content)

    def with_structured_output(self, schema: Any):
        class StructuredMock:
            def __init__(self, parent, schema):
                self.parent = parent
                self.schema = schema

            def invoke(self, prompt: Any):
                raw = self.parent.invoke(prompt).content
                match = re.search(r"```(?:json)?\s*([\s\S]*?)\s*```", raw)
                json_str = match.group(1) if match else raw
                try:
                    data = json.loads(json_str)
                    return self.schema(**data)
                except Exception:
                    return self.parent._generate_structured_fallback(self.schema, str(prompt))

        return StructuredMock(self, schema)

    def _generate_response(self, prompt_text: str) -> str:
        prompt_lower = prompt_text.lower()
        if "requirement" in prompt_lower or "extract" in prompt_lower:
            query_match = re.search(r"user query:\s*(.*)", prompt_text, re.IGNORECASE)
            query_text = query_match.group(1).lower() if query_match else prompt_lower

            if any(k in query_text for k in ["shoe", "sneaker", "boot", "loafer"]):
                category = "footwear"
            elif any(k in query_text for k in ["shirt", "pant", "jacket", "dress", "panjabi"]):
                category = "clothing"
            elif any(k in query_text for k in ["air fryer", "blender", "oven", "cooker", "kettle"]):
                category = "kitchen appliance"
            elif any(k in query_text for k in ["chair", "desk", "table", "sofa"]):
                category = "furniture"
            elif any(k in query_text for k in ["perfume", "sunscreen", "serum", "lotion"]):
                category = "beauty & personal care"
            elif any(k in query_text for k in ["laptop", "notebook", "macbook"]):
                category = "laptop"
            elif any(k in query_text for k in ["phone", "smartphone", "mobile"]):
                category = "smartphone"
            else:
                words = [w for w in re.findall(r"\b[a-zA-Z]{3,}\b", query_text) if w not in ["need", "want", "suggest", "find", "best", "price", "taka", "bdt", "under", "good", "amar", "lagbe"]]
                category = words[0] if words else "consumer product"

            budget = 50000.0
            k_match = re.search(r"(\d+(?:\.\d+)?)\s*(?:k|thousand)", query_text)
            num_match = re.search(r"(\d{3,7})", query_text)
            if k_match:
                budget = float(k_match.group(1)) * 1000
            elif num_match:
                budget = float(num_match.group(1))

            purposes = []
            if "game" in query_text or "gaming" in query_text:
                purposes.append("gaming")
            if "run" in query_text or "sport" in query_text or "fitness" in query_text:
                purposes.append("sports & fitness")
            if "office" in query_text or "work" in query_text or "code" in query_text:
                purposes.append("office & productivity")
            if "cook" in query_text or "kitchen" in query_text or "bake" in query_text:
                purposes.append("kitchen & cooking")
            if "waterproof" in query_text:
                purposes.append("waterproof")
            if not purposes:
                purposes.append("general consumer use")

            has_bangla_script = bool(re.search(r"[\u0980-\u09FF]", query_text))
            has_banglish_words = bool(re.search(r"\b(amar|amake|lagbe|bhalo|koto|dam)\b", query_text))
            if has_bangla_script:
                detected_lang = "bn"
            elif has_banglish_words:
                detected_lang = "banglish"
            else:
                detected_lang = "en"

            return json.dumps({
                "category": category,
                "budget_max": budget,
                "budget_min": None,
                "currency": "BDT",
                "location": "Bangladesh",
                "usage_purposes": purposes,
                "priorities": purposes[:2],
                "must_have_specs": [],
                "preferred_stores": [],
                "detected_language": detected_lang
            })

        return json.dumps({
            "winner_index": 0,
            "summary": "Compared candidate options discovered across Bangladesh online retailers.",
            "products": [
                {
                    "index": 0,
                    "score": 9.2,
                    "verdict": "Top Recommendation 🏆",
                    "why_buy": ["Strong value for price in the current market", "Well reviewed by customers"],
                    "why_not_buy": ["Check local outlet or online delivery readiness"],
                    "who_should_buy": "Buyers looking for reliable quality within budget",
                    "buyer_advice": "Verify return policy and cash/bKash discounts before purchasing"
                }
            ]
        })

    def _generate_structured_fallback(self, schema: Any, prompt_text: str):
        data = json.loads(self._generate_response(prompt_text))
        return schema(**data)
