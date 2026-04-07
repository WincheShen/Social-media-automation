"""LangGraph workflow definition — main graph construction."""

from langgraph.graph import END, StateGraph

from src.graph.state import AgentState
from src.nodes.analyst import traffic_analyst
from src.nodes.context_loader import persona_context_loader
from src.nodes.creative_engine import creative_engine
from src.nodes.execution import browser_publish
from src.nodes.feedback import feedback_memory_update
from src.nodes.monitor import post_publish_monitor
from src.nodes.research_engine import multi_vlm_research
from src.nodes.review_gate import review_gate
from src.nodes.safety_check import content_safety_check


def _route_after_safety(state: AgentState) -> str:
    """Route based on safety check result."""
    if state["safety_passed"]:
        return "review_gate"
    return "feedback"


def _route_after_review(state: AgentState) -> str:
    """Route based on review approval."""
    if state["approved"]:
        return "execute"
    return "feedback"


def build_graph() -> StateGraph:
    """Construct and return the compiled LangGraph workflow."""

    graph = StateGraph(AgentState)

    # --- Register nodes ---
    graph.add_node("context_loader", persona_context_loader)
    graph.add_node("analyst", traffic_analyst)
    graph.add_node("research", multi_vlm_research)
    graph.add_node("creative", creative_engine)
    graph.add_node("safety_check", content_safety_check)
    graph.add_node("review_gate", review_gate)
    graph.add_node("execute", browser_publish)
    graph.add_node("monitor", post_publish_monitor)
    graph.add_node("feedback", feedback_memory_update)

    # --- Define edges ---
    graph.set_entry_point("context_loader")

    graph.add_edge("context_loader", "analyst")
    graph.add_edge("analyst", "research")
    graph.add_edge("research", "creative")
    graph.add_edge("creative", "safety_check")

    # Conditional: safety → review or feedback
    graph.add_conditional_edges("safety_check", _route_after_safety)

    # Conditional: review → execute or feedback
    graph.add_conditional_edges("review_gate", _route_after_review)

    graph.add_edge("execute", "monitor")
    graph.add_edge("monitor", "feedback")
    graph.add_edge("feedback", END)

    return graph.compile()
