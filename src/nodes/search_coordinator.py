import re
from typing import List
from src.models import ShoppingAgentState, UserRequirement
from src.tools.search import search_bangladesh_products


def search_coordinator_node(state: ShoppingAgentState) -> ShoppingAgentState:
    """Generate high-yield product search queries and gather candidate products."""
    req: UserRequirement = state.get("requirements")
    user_query = state.get("user_query", "")

    # Clean conversational filler while preserving the exact product model / brand / specs
    clean_q = re.sub(r"\b(i need|i want|suggest|find|show me|look for|amar|lagbe|er moddhe|bhalo|koto dam)\b", "", user_query, flags=re.IGNORECASE)
    clean_q = re.sub(r"\b(in best price|at best price|best price|lowest price|best deal|best price in bd|best price in bangladesh|best rate|deal)\b", "", clean_q, flags=re.IGNORECASE)
    clean_q = re.sub(r"\s+", " ", clean_q).strip()

    # Determine core search term
    target = clean_q or (req.category if req and req.category else user_query)
    budget_str = f"under {int(req.budget_max)}" if req and req.budget_max else ""

    queries: List[str] = []

    # Primary exact search
    queries.append(target)

    # Bangladesh store & price specific queries
    queries.append(f"{target} price in bangladesh".strip())
    queries.append(f"{target} Star Tech Ryans Bangladesh".strip())

    if budget_str and budget_str not in target.lower():
        queries.append(f"{target} {budget_str}".strip())

    # Execute search - retrieve candidate products with priority on exact target
    results = search_bangladesh_products(queries, max_results_per_query=5)

    logs = list(state.get("logs", []))
    logs.append(f"Search coordinator ran queries for '{target}': {queries}. Found {len(results)} candidate links.")

    return {
        **state,
        "search_queries": queries,
        "candidate_urls": results,
        "logs": logs,
    }
