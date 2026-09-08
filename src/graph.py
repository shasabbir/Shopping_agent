from langgraph.graph import StateGraph, START, END
from src.models import ShoppingAgentState
from src.nodes.requirement_analyzer import requirement_analyzer_node
from src.nodes.search_coordinator import search_coordinator_node
from src.nodes.product_extractor import product_extractor_node
from src.nodes.recommendation_agent import recommendation_agent_node


def build_shopping_graph() -> StateGraph:
    """Builds and compiles the 4-node Bangladesh Shopping Decision LangGraph."""
    builder = StateGraph(ShoppingAgentState)

    # Add Nodes
    builder.add_node("requirement_analyzer", requirement_analyzer_node)
    builder.add_node("search_coordinator", search_coordinator_node)
    builder.add_node("product_extractor", product_extractor_node)
    builder.add_node("recommendation_agent", recommendation_agent_node)

    # Add Edges
    builder.add_edge(START, "requirement_analyzer")
    builder.add_edge("requirement_analyzer", "search_coordinator")
    builder.add_edge("search_coordinator", "product_extractor")
    builder.add_edge("product_extractor", "recommendation_agent")
    builder.add_edge("recommendation_agent", END)

    return builder.compile()


# Compiled singleton instance
shopping_agent_graph = build_shopping_graph()


def run_shopping_agent(user_query: str) -> ShoppingAgentState:
    """Convenience helper to invoke the LangGraph agent for a user query."""
    initial_state: ShoppingAgentState = {
        "user_query": user_query,
        "logs": [],
    }
    return shopping_agent_graph.invoke(initial_state)

