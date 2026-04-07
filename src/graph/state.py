"""LangGraph Agent State definition."""

from typing import Literal, Optional, TypedDict


class AgentState(TypedDict):
    """Shared state across all graph nodes."""

    # --- Identity & Context ---
    account_id: str
    persona: dict  # Full config loaded from Identity Registry
    task: str  # Current task description
    memory: list[dict]  # Historical experience for this account

    # --- Analyst Phase (traffic attribution + topic selection) ---
    traffic_analysis: Optional[dict]   # Attribution report: high/low performers + reasoning
    suggested_topic: Optional[str]     # AI-recommended topic for today based on attribution

    # --- Research Phase ---
    research_results: list[dict]  # Retrieved materials & analysis
    data_sources: list[str]  # Data sources used

    # --- Creative Phase ---
    draft_title: str
    draft_content: str
    draft_tags: list[str]
    visual_assets: list[str]  # Generated image file paths
    image_gen_prompt: Optional[str]  # Strategist's recommended image generation prompt

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
