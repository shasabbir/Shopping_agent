from typing import List
from src.models import ShoppingAgentState, RecommendationCard, UserRequirement, ProductSpec
from src.llm import get_llm


RECOMMENDATION_PROMPT = """You are a senior tech buyer and decision advisor in Bangladesh.
Review the following user requirement and candidate products found in Bangladesh stores.

User Requirement:
- Category: {category}
- Maximum Budget: {budget} BDT
- Usages / Purposes: {purposes}
- Priorities: {priorities}

Candidate Products:
{products_text}

Provide:
1. Winner recommendation (which product to buy and why).
2. Honest "Why NOT to buy" reasons for each product.
3. Bangladesh-specific market advice (e.g. official vs gray market warranty, Star Tech vs Ryans stock).
"""


def score_product(product: ProductSpec, req: UserRequirement) -> float:
    """Calculate heuristic score from 1.0 to 10.0 based on specs, budget, and purpose."""
    score = 7.0
    specs_str = " ".join(f"{k}: {v}" for k, v in product.specs.items()).lower()
    name_lower = product.name.lower()

    # Budget penalty or bonus
    if req.budget_max and product.price:
        if product.price <= req.budget_max:
            # Under budget is rewarded
            score += 0.8
        else:
            # Over budget is penalized
            diff_ratio = (product.price - req.budget_max) / req.budget_max
            score -= min(2.5, diff_ratio * 5.0)

    # Purpose-based scoring
    for p in req.usage_purposes:
        p_lower = p.lower()
        if "ai" in p_lower or "ml" in p_lower or "deep learning" in p_lower:
            if "rtx 4060" in specs_str or "rtx 4060" in name_lower:
                score += 1.5
            elif "rtx 4050" in specs_str or "rtx 4050" in name_lower:
                score += 0.8
            elif "rtx" in specs_str or "rtx" in name_lower:
                score += 0.5
        elif "game" in p_lower or "gaming" in p_lower:
            if "rtx 4060" in specs_str or "rtx 4070" in specs_str:
                score += 1.3
            elif "rtx" in specs_str or "rtx" in name_lower:
                score += 0.8
            if "144hz" in specs_str or "165hz" in specs_str or "120hz" in specs_str:
                score += 0.4
        elif "camera" in p_lower:
            if "ois" in specs_str or "50mp" in specs_str or "200mp" in specs_str:
                score += 1.2
            if "samsung" in name_lower or "pixel" in name_lower or "apple" in name_lower:
                score += 0.5

    # RAM scoring
    if "16gb" in specs_str:
        score += 0.5
    elif "8gb" in specs_str and req.category == "laptop":
        score -= 0.5

    return round(min(9.8, max(5.0, score)), 1)


def generate_why_buy_and_not(product: ProductSpec, req: UserRequirement) -> tuple[List[str], List[str]]:
    """Generate honest reasons to buy and avoid."""
    why_buy = []
    why_not_buy = []
    specs = product.specs

    if product.price and req.budget_max and product.price <= req.budget_max:
        why_buy.append(f"Comfortably fits within budget ({product.price:,.0f} BDT vs {req.budget_max:,.0f} BDT max)")

    if "GPU" in specs:
        why_buy.append(f"Dedicated graphics: {specs['GPU']} delivers strong gaming & CUDA acceleration")
    if "RAM" in specs and "16" in specs["RAM"]:
        why_buy.append("16GB RAM provides smooth multitasking without requiring immediate upgrade")
    if "Camera" in specs:
        why_buy.append(f"High resolution sensor ({specs['Camera']}) for photography and social media")
    if product.warranty:
        why_buy.append(f"Includes {product.warranty}")

    if not why_buy:
        why_buy.append("Solid feature set compared to similar options in Bangladesh stores")

    # Why not buy reasons
    if product.price and req.budget_max and product.price > req.budget_max:
        why_not_buy.append(f"Exceeds target budget by {product.price - req.budget_max:,.0f} BDT")
    if "rtx 4050" in str(specs.get("GPU", "")).lower():
        why_not_buy.append("6GB VRAM on RTX 4050 may become a bottleneck for heavy local AI LLM fine-tuning or future AAA games")
    if "rtx 3050" in str(specs.get("GPU", "")).lower():
        why_not_buy.append("Previous generation RTX 3050 offers ~30-40% lower compute and gaming power than RTX 40-series")
    if "8gb" in str(specs.get("RAM", "")).lower() and req.category == "laptop":
        why_not_buy.append("8GB single-channel RAM is tight; you will need to spend an extra ৳3,500-৳4,500 for an additional RAM stick")

    if not why_not_buy:
        why_not_buy.append("Stock availability may fluctuate between Dhaka and regional branches")

    return why_buy, why_not_buy


def recommendation_agent_node(state: ShoppingAgentState) -> ShoppingAgentState:
    """Evaluate products, assign rankings, generate trade-offs and final buyer report."""
    req = state.get("requirements") or UserRequirement(category="tech", usage_purposes=["general"])
    products = state.get("extracted_products", [])

    if not products:
        final_answer = "No matching products could be found for your criteria in Bangladesh stores. Please try broadening your budget or search terms."
        return {
            **state,
            "recommendations": [],
            "final_answer": final_answer,
            "logs": list(state.get("logs", [])) + ["Recommendation agent: no products available to rank."],
        }

    # Score and rank products
    scored_products = []
    for p in products:
        score = score_product(p, req)
        why_buy, why_not_buy = generate_why_buy_and_not(p, req)
        scored_products.append((score, p, why_buy, why_not_buy))

    # Sort descending by score
    scored_products.sort(key=lambda x: x[0], reverse=True)

    recommendation_cards: List[RecommendationCard] = []
    verdicts = ["Top Recommendation ⭐", "Best Value Alternative 🥈", "Budget-Friendly Pick 🥉"]

    for idx, (score, product, why_buy, why_not_buy) in enumerate(scored_products):
        verdict = verdicts[idx] if idx < len(verdicts) else f"Option #{idx+1}"
        card = RecommendationCard(
            rank=idx + 1,
            product=product,
            verdict=verdict,
            score=score,
            why_buy=why_buy,
            why_not_buy=why_not_buy,
            who_should_buy=f"Buyers prioritizing {', '.join(req.usage_purposes)} who shop at {product.store}.",
            bangladesh_note=f"Available via {product.store}. Verify whether price includes official brand warranty before purchasing."
        )
        recommendation_cards.append(card)

    # Format the final Markdown response
    top_pick = recommendation_cards[0]
    lines = []
    lines.append(f"# 🛒 Bangladesh Shopping Assistant Recommendation\n")
    lines.append(f"**Target:** {req.category.capitalize()} | **Budget:** {f'{req.budget_max:,.0f} BDT' if req.budget_max else 'Flexible'} | **Focus:** {', '.join(req.usage_purposes).title()}\n")
    lines.append(f"### 🏆 Winner: [{top_pick.product.name}]({top_pick.product.url})")
    lines.append(f"- **Store:** {top_pick.product.store}")
    lines.append(f"- **Price:** {f'{top_pick.product.price:,.0f} BDT' if top_pick.product.price else 'Check Store Link'}")
    lines.append(f"- **Value Rating:** {top_pick.score} / 10\n")

    lines.append("#### Curated Recommendations:")
    for card in recommendation_cards:
        p = card.product
        price_str = f"৳{p.price:,.0f}" if p.price else "Check Link"
        specs_str = " | ".join(f"**{k}**: {v}" for k, v in p.specs.items()) or "Standard Specs"
        lines.append(f"### {card.rank}. [{p.name}]({p.url}) — `{card.verdict}`")
        lines.append(f"- **Store:** {p.store} | **Price:** **{price_str}** | **Score:** `{card.score}/10`")
        lines.append(f"- **Specs:** {specs_str}")
        lines.append(f"- **Warranty:** {p.warranty or 'Standard retail warranty'}")
        lines.append(f"- **Why Buy:**")
        for reason in card.why_buy:
            lines.append(f"  - ✅ {reason}")
        lines.append(f"- **Why NOT to Buy:**")
        for reason in card.why_not_buy:
            lines.append(f"  - ⚠️ {reason}")
        lines.append(f"- **Bangladesh Buying Tip:** {card.bangladesh_note}\n")

    lines.append("---")
    lines.append("### 💡 Bangladesh Buyer Guidance:")
    lines.append("1. **Verify Official vs Seller Warranty:** Always ask the retail shop if the price includes the official brand warranty (e.g., Ryans/Star Tech official distribution) or an unofficial shop warranty.")
    lines.append("2. **Physical Stock Check:** Call the outlet before visiting as Dhaka central stock may differ from local branch inventory.")

    final_answer = "\n".join(lines)

    logs = list(state.get("logs", []))
    logs.append(f"Recommendation agent ranked {len(recommendation_cards)} cards. Winner: {top_pick.product.name}")

    return {
        **state,
        "recommendations": recommendation_cards,
        "final_answer": final_answer,
        "logs": logs,
    }

