import re
from typing import List, Dict, Any
from src.models import ShoppingAgentState, UserRequirement, ProductSpec, StoreOffer
from src.database import search_catalog
from src.tools.search import search_bangladesh_products


def search_coordinator_node(state: ShoppingAgentState) -> ShoppingAgentState:
    """
    Search Coordinator: Queries the local multi-seller catalog first.
    If the catalog has indexed products, converts them to canonical ProductSpecs with
    attached multi-store offers. If empty, falls back to open-web discovery.
    """
    req: UserRequirement = state.get("requirements")
    user_query = state.get("user_query", "")
    logs = list(state.get("logs", []))

    # Clean conversational filler while preserving the exact product model / brand / specs
    clean_q = re.sub(
        r"\b(i need|i want|suggest|find|show me|look for|amar|lagbe|er moddhe|bhalo|koto dam)\b",
        "",
        user_query,
        flags=re.IGNORECASE
    )
    clean_q = re.sub(
        r"\b(in best price|at best price|best price|lowest price|best deal|best price in bd|best price in bangladesh|best rate|deal)\b",
        "",
        clean_q,
        flags=re.IGNORECASE
    )
    clean_q = re.sub(r"\s+", " ", clean_q).strip()

    target = clean_q or (req.category if req and req.category else user_query)
    budget_max = req.budget_max if req and req.budget_max else None
    category = req.category if req and req.category else None

    # 1. Search local PostgreSQL / SQLite catalog
    db_results = search_catalog(
        query_text=target,
        category=category,
        budget_max=budget_max,
        limit=12
    )

    extracted_from_db: List[ProductSpec] = []
    if db_results:
        for p in db_results:
            offers_data = p.get("offers", [])
            store_offers = []
            for o in offers_data:
                store_offers.append(StoreOffer(
                    id=o.get("id"),
                    store_name=o.get("store_name", "Local Store"),
                    price_bdt=float(o.get("price_bdt", 0.0)),
                    regular_price_bdt=float(o["regular_price_bdt"]) if o.get("regular_price_bdt") else None,
                    url=o.get("product_url", ""),
                    in_stock=o.get("in_stock", True),
                    warranty=o.get("warranty"),
                    last_checked_at=o.get("last_checked_at"),
                ))

            best_offer = store_offers[0] if store_offers else None
            lowest_p = best_offer.price_bdt if best_offer else p.get("lowest_price")
            in_stock_prices = [o.price_bdt for o in store_offers if o.in_stock]
            highest_p = max(in_stock_prices) if len(in_stock_prices) > 1 else None
            savings_val = (highest_p - lowest_p) if (highest_p and lowest_p and highest_p > lowest_p) else None

            spec_obj = ProductSpec(
                id=p.get("id"),
                name=p.get("canonical_name", target),
                brand=p.get("brand"),
                price=lowest_p,
                currency="BDT",
                store=best_offer.store_name if best_offer else "Multiple Stores",
                url=best_offer.url if best_offer else "",
                image_url=p.get("primary_image_url") or (best_offer.image_url if best_offer else None),
                specs=p.get("specs", {}),
                warranty=best_offer.warranty if best_offer else "Standard Retail",
                in_stock=best_offer.in_stock if best_offer else True,
                offers=store_offers,
                lowest_price=lowest_p,
                highest_price=highest_p,
                savings=savings_val,
            )
            extracted_from_db.append(spec_obj)

        logs.append(f"Catalog DB Search: Found {len(extracted_from_db)} canonical products with multi-store offers.")
        return {
            **state,
            "extracted_products": extracted_from_db,
            "search_queries": [f"DB Search: {target} (Category: {category}, Budget: {budget_max})"],
            "candidate_urls": [],
            "logs": logs,
        }

    # 2. Fallback: If database is brand new / has 0 items, use open-web discovery
    logs.append(f"Catalog DB empty for '{target}'. Initiating fallback web search across Bangladesh stores...")
    queries: List[str] = [target, f"{target} buy online Bangladesh".strip(), f"{target} price in Bangladesh".strip()]
    if budget_max:
        queries.append(f"{target} under {int(budget_max)} BDT Bangladesh".strip())

    results = search_bangladesh_products(queries, max_results_per_query=5)
    logs.append(f"Web fallback found {len(results)} candidate links across open web.")

    return {
        **state,
        "search_queries": queries,
        "candidate_urls": results,
        "logs": logs,
    }
