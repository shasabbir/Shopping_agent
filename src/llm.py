import os
import re
import json
from typing import Optional, Any
from dotenv import load_dotenv

load_dotenv(override=True)

def get_llm(model: Optional[str] = None, temperature: float = 0.2):
    """Returns a ChatGoogleGenerativeAI instance if GEMINI_API_KEY is available,
    otherwise returns a MockShoppingLLM for deterministic offline execution."""
    api_key = os.getenv("GEMINI_API_KEY", "").strip()
    model_name = model or os.getenv("GEMINI_MODEL", "gemini-3.7-flash")

    if api_key and not api_key.startswith("your_"):
        try:
            from langchain_google_genai import ChatGoogleGenerativeAI
            return ChatGoogleGenerativeAI(
                model=model_name,
                google_api_key=api_key,
                temperature=temperature,
            )
        except Exception as e:
            print(f"[Warning] Failed to initialize ChatGoogleGenerativeAI: {e}. Falling back to MockShoppingLLM.")

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
                # Parse JSON if enclosed in markdown
                match = re.search(r"```(?:json)?\s*([\s\S]*?)\s*```", raw)
                json_str = match.group(1) if match else raw
                try:
                    data = json.loads(json_str)
                    return self.schema(**data)
                except Exception:
                    # Fallback default construction
                    return self.parent._generate_structured_fallback(self.schema, str(prompt))

        return StructuredMock(self, schema)

    def _generate_response(self, prompt_text: str) -> str:
        prompt_lower = prompt_text.lower()
        if "requirement" in prompt_lower or "extract" in prompt_lower:
            # Isolate the user query to avoid matching words from the system instructions
            query_match = re.search(r"user query:\s*(.*)", prompt_text, re.IGNORECASE)
            query_text = query_match.group(1).lower() if query_match else prompt_lower

            # Check category from the user query
            if any(k in query_text for k in ["laptop", "notebook", "ultrabook", "macbook"]):
                category = "laptop"
            elif any(k in query_text for k in ["phone", "smartphone", "mobile"]):
                category = "smartphone"
            elif any(k in query_text for k in ["monitor", "display", "screen"]):
                category = "monitor"
            else:
                category = "laptop"

            budget = 100000.0
            # Detect numbers like 120k, 120000, 40k in user query
            k_match = re.search(r"(\d+(?:\.\d+)?)\s*(?:k|thousand)", query_text)
            num_match = re.search(r"(\d{4,7})", query_text)
            if k_match:
                budget = float(k_match.group(1)) * 1000
            elif num_match:
                budget = float(num_match.group(1))

            purposes = []
            if "game" in query_text or "gaming" in query_text:
                purposes.append("gaming")
            if "ai" in query_text or "ml" in query_text or "deep learning" in query_text:
                purposes.append("AI development")
            if "code" in query_text or "programming" in query_text or "coding" in query_text:
                purposes.append("programming")
            if "camera" in query_text or "photo" in query_text:
                purposes.append("camera")
            if "battery" in query_text:
                purposes.append("battery life")
            if not purposes:
                purposes.append("general daily use")

            # Language detection
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
                "preferred_stores": ["Star Tech", "Ryans", "Daraz"],
                "detected_language": detected_lang
            })

        # Recommendation / trade-off prompt
        return json.dumps({
            "summary": "Compared candidate options from top Bangladesh retailers.",
            "winner": "Lenovo LOQ 15" if "laptop" in prompt_lower else "Samsung Galaxy A55",
            "reasoning": "Offers the best performance-to-price ratio in the current Bangladesh market."
        })

    def _generate_structured_fallback(self, schema: Any, prompt_text: str):
        data = json.loads(self._generate_response(prompt_text))
        return schema(**data)

