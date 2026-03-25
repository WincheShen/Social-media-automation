"""LangGraph Agent State definition."""

from typing import Literal, Optional, TypedDict


class AgentState(TypedDict):
    """Shared state across all graph nodes."""

    # --- Identity & Context ---
    account_id: str
    persona: dict  # Full config loaded from Identity Registry
    task: str  # Current task description
    memory: list[dict]  # Historical experience for this account

    # --- Research Phase ---
    research_results: list[dict]  # Retrieved materials & analysis
    data_sources: list[str]  # Data sources used

    # --- Creative Phase ---
    draft_title: str
    draft_content: str
    draft_tags: list[str]
    visual_assets: list[str]  # Generated image file paths

    # --- Safety Check ---
    safety_passed: bool
    safety_issues: list[str]

    # --- Review & Publish ---
    review_mode: Literal["auto", "review", "scheduled"]
    approved: bool
    publish_result: Optional[dict]  # {url, status, timestamp, ...}

    # --- Feedback ---
    post_metrics: Optional[dict]
    feedback_summary: Optional[str]
