from typing import List
from src.models import ShoppingAgentState, UserRequirement
from src.tools.search import search_bangladesh_products


def search_coordinator_node(state: ShoppingAgentState) -> ShoppingAgentState:
    """Generate high-yield product search queries for Bangladesh stores."""
    req: UserRequirement = state.get("requirements")

    queries: List[str] = []
    if req:
        cat = req.category
        budget_str = f"under {int(req.budget_max)} BDT" if req.budget_max else ""
        purpose_str = " ".join(req.usage_purposes[:2])

        if cat == "laptop":
            queries.append(f"gaming laptop {budget_str} Star Tech Bangladesh price")
            queries.append(f"RTX laptop {budget_str} Ryans Computers BD")
            queries.append(f"Lenovo LOQ Asus TUF price in BD Star Tech")
        elif cat == "smartphone":
            queries.append(f"smartphone {budget_str} Star Tech price in BD")
            queries.append(f"camera phone {budget_str} Ryans Pickaboo Bangladesh")
            queries.append(f"Samsung Redmi {budget_str} price in BD")
        else:
            queries.append(f"{cat} {purpose_str} {budget_str} Star Tech Bangladesh")
            queries.append(f"{cat} {purpose_str} {budget_str} Ryans Computers BD")
    else:
        queries.append(state.get("user_query", "best tech products Bangladesh"))

    # Execute search
    results = search_bangladesh_products(queries, max_results_per_query=3)

    logs = list(state.get("logs", []))
    logs.append(f"Search coordinator ran {len(queries)} queries, discovered {len(results)} candidate links.")

    return {
        **state,
        "search_queries": queries,
        "candidate_urls": results,
        "logs": logs,
    }

