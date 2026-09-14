import re
import json
from typing import List, Dict, Any, Optional
from src.models import ShoppingAgentState, RecommendationCard, UserRequirement, ProductSpec
from src.llm import get_llm, extract_text_content


ANALYSIS_SYSTEM_PROMPT = """You are an expert tech shopping advisor in Bangladesh.
Your task is to analyze the following candidate products found in live stores for the user's shopping requirement.

User Shopping Intent:
- Category: {category}
- Maximum Budget: {budget}
- Purpose / Usage: {purposes}
- User Query: "{query}"

Candidate Products ({count} products found):
{products_text}

Provide your analysis in clean JSON format matching this schema:
{{
  "winner_index": 0,
  "summary": "2-3 sentence overview of the options and current market pricing",
  "products": [
    {{
      "index": 0,
      "score": 9.2,
      "verdict": "Top Recommendation 🏆",
      "why_buy": ["Primary strength 1", "Strength 2"],
      "why_not_buy": ["Key trade-off or drawback"],
      "who_should_buy": "Ideal buyer for this option",
      "bangladesh_note": "Local retail tip regarding stock or warranty"
    }}
  ]
}}
Respond ONLY with the JSON object.
"""


def format_products_for_llm(products: List[ProductSpec]) -> str:
    lines = []
    for i, p in enumerate(products):
        price_str = f"{p.price:,.0f} BDT" if p.price else "Price on inquiry"
        specs_str = ", ".join(f"{k}: {v}" for k, v in list(p.specs.items())[:6]) or p.raw_snippet or "Standard Specs"
        lines.append(f"[{i}] {p.name} | Store: {p.store} | Price: {price_str} | Specs: {specs_str}")
    return "\n".join(lines)


def heuristic_score_product(product: ProductSpec, req: UserRequirement, index: int) -> float:
    """Calculate heuristic score from 5.0 to 9.8 based on specs and budget."""
    score = 7.5 - (index * 0.2)
    name_lower = product.name.lower()
    specs_str = " ".join(f"{k}: {v}" for k, v in product.specs.items()).lower()

    if req.budget_max and product.price:
        if product.price <= req.budget_max:
            score += 0.8
        else:
            diff = (product.price - req.budget_max) / req.budget_max
            score -= min(2.5, diff * 4.0)

    for p in req.usage_purposes:
        p_lower = p.lower()
        if "ai" in p_lower or "gaming" in p_lower:
            if "rtx 4060" in specs_str or "rtx 4060" in name_lower:
                score += 1.5
            elif "rtx" in specs_str or "rtx" in name_lower:
                score += 0.8
        elif "camera" in p_lower:
            if "ois" in specs_str or "50mp" in specs_str or "200mp" in specs_str:
                score += 1.0

    return round(min(9.8, max(5.0, score)), 1)


def heuristic_reasons(product: ProductSpec, req: UserRequirement) -> tuple[List[str], List[str]]:
    why_buy = []
    why_not = []

    if product.price and req.budget_max:
        if product.price <= req.budget_max:
            why_buy.append(f"Comfortably within target budget (৳{product.price:,.0f} vs ৳{req.budget_max:,.0f})")
        else:
            why_not.append(f"Slightly above target budget (৳{product.price:,.0f})")

    if product.specs:
        key_specs = list(product.specs.items())[:2]
        for k, v in key_specs:
            why_buy.append(f"{k}: {v}")

    if not why_buy:
        why_buy.append("Competitive price and live availability in Bangladesh retail")

    if not why_not:
        why_not.append("Regional outlet stock may vary between Dhaka and other branches")

    return why_buy, why_not


def recommendation_agent_node(state: ShoppingAgentState) -> ShoppingAgentState:
    """Analyze up to 10 extracted products using Gemini LLM, rank them, and generate comparison."""
    products = state.get("extracted_products", [])
    req = state.get("requirements") or UserRequirement(category="tech", usage_purposes=["general"])
    user_query = state.get("user_query", "")

    if not products:
        return {
            **state,
            "recommendations": [],
            "final_answer": "No products could be extracted. Please refine your query or budget.",
            "logs": list(state.get("logs", [])) + ["Recommendation agent: no products extracted."],
        }

    # Prepare LLM analysis
    llm = get_llm()
    products_text = format_products_for_llm(products)
    prompt = ANALYSIS_SYSTEM_PROMPT.format(
        category=req.category,
        budget=f"{req.budget_max:,.0f} BDT" if req.budget_max else "Flexible",
        purposes=", ".join(req.usage_purposes) if req.usage_purposes else "General tech purchase",
        query=user_query,
        count=len(products),
        products_text=products_text,
    )

    analysis_data = {}
    try:
        resp = llm.invoke(prompt)
        text = extract_text_content(resp)
        match = re.search(r"```(?:json)?\s*([\s\S]*?)\s*```", text)
        json_str = match.group(1) if match else text
        analysis_data = json.loads(json_str)
    except Exception as e:
        print(f"[Recommendation Agent] LLM comparative analysis fallback: {e}")

    llm_products_map = {}
    if isinstance(analysis_data, dict) and "products" in analysis_data:
        for p_info in analysis_data["products"]:
            idx = p_info.get("index")
            if idx is not None and 0 <= idx < len(products):
                llm_products_map[idx] = p_info

    # Build recommendations for all 10 products
    recommendation_cards: List[RecommendationCard] = []
    verdicts_default = [
        "🏆 Top Recommendation",
        "🥈 Best Value Alternative",
        "🥉 Best Budget Pick",
        "⚡ High Performance Pick",
        "💎 Premium Choice",
        "✨ Solid Contender",
        "🔍 Feature-Rich Alternative",
        "🏷️ Value Option",
        "📦 Reliable Choice",
        "💡 Budget Option"
    ]

    for idx, prod in enumerate(products):
        llm_info = llm_products_map.get(idx, {})
        score = llm_info.get("score") or heuristic_score_product(prod, req, idx)
        verdict = llm_info.get("verdict") or (verdicts_default[idx] if idx < len(verdicts_default) else f"Option #{idx+1}")
        
        why_buy = llm_info.get("why_buy")
        why_not = llm_info.get("why_not_buy")
        if not why_buy or not why_not:
            h_buy, h_not = heuristic_reasons(prod, req)
            why_buy = why_buy or h_buy
            why_not = why_not or h_not

        who_should_buy = llm_info.get("who_should_buy") or f"Buyers seeking {req.category} at {prod.store}."
        bd_note = llm_info.get("bangladesh_note") or f"Available via {prod.store}. Inquire about official distributor warranty."

        card = RecommendationCard(
            rank=idx + 1,
            product=prod,
            verdict=verdict,
            score=round(float(score), 1),
            why_buy=why_buy,
            why_not_buy=why_not,
            who_should_buy=who_should_buy,
            bangladesh_note=bd_note
        )
        recommendation_cards.append(card)

    # Sort descending by score
    recommendation_cards.sort(key=lambda x: x.score, reverse=True)
    for rank_idx, card in enumerate(recommendation_cards):
        card.rank = rank_idx + 1

    top_pick = recommendation_cards[0]

    # Build formatted markdown summary
    lines = [
        f"# 🛒 Bangladesh Tech Shopping Analysis & Comparison ({len(recommendation_cards)} Products Analyzed)\n",
        f"**Target:** {req.category.capitalize()} | **Budget:** {f'{req.budget_max:,.0f} BDT' if req.budget_max else 'Flexible'} | **Priorities:** {', '.join(req.usage_purposes).title()}\n",
        f"### 🏆 Top Winner: [{top_pick.product.name}]({top_pick.product.url})",
        f"- **Store:** {top_pick.product.store} | **Price:** {f'৳{top_pick.product.price:,.0f}' if top_pick.product.price else 'Check Retail Link'}",
        f"- **Value Rating:** {top_pick.score} / 10",
        f"- **Winning Advantage:** {top_pick.why_buy[0] if top_pick.why_buy else 'Best overall balance'}\n",
        "### 📊 All 10 Candidate Products Ranked:"
    ]

    for c in recommendation_cards:
        p = c.product
        price_str = f"৳{p.price:,.0f}" if p.price else "Check Retail Link"
        lines.append(f"**#{c.rank} [{p.name}]({p.url})** — `{c.verdict}`")
        lines.append(f"- **Store:** {p.store} | **Price:** {price_str} | **Rating:** `{c.score}/10`")
        if c.why_buy:
            lines.append(f"- ✅ **Why to buy:** {c.why_buy[0]}")
        if c.why_not_buy:
            lines.append(f"- ⚠️ **Why NOT to buy:** {c.why_not_buy[0]}")
        lines.append("")

    lines.append("---")
    lines.append("### 💡 Bangladesh Buyer Guidance & Retailer Checklist:")
    lines.append("1. **Official vs. Unofficial Warranty Check:** Always verify whether the listed price includes Official Distributor Warranty or Seller Shop Warranty.")
    lines.append("2. **Outlet Stock Verification:** Call the branch before visiting to confirm on-shelf readiness.")
    lines.append("3. **Payment Discounts:** Most Bangladesh tech stores offer a 2% - 5% discount for cash/bKash payment compared to EMI.")

    summary_text = analysis_data.get("summary", "Analyzed and ranked the top 10 products from Bangladesh retailers.")
    final_answer = "\n".join(lines)

    logs = list(state.get("logs", []))
    logs.append(f"Recommendation agent scored and ranked {len(recommendation_cards)} products. Winner: {top_pick.product.name}")

    return {
        **state,
        "recommendations": recommendation_cards,
        "comparison_summary": summary_text,
        "final_answer": final_answer,
        "logs": logs,
    }
