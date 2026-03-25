"""Node 4: Content Safety Check

Performs compliance and safety checks on generated content:
- Sensitive word filtering (common + track-specific)
- Financial compliance (disclaimers, no absolute claims)
- Content deduplication (embedding similarity)
- Image compliance (watermark, size)
"""

from __future__ import annotations

import logging
from pathlib import Path

import yaml

from src.graph.state import AgentState

logger = logging.getLogger(__name__)

SENSITIVE_WORDS_DIR = Path("config/sensitive_words")


def _load_sensitive_words(track: str) -> set[str]:
    """Load combined sensitive word list (common + track-specific)."""
    words: set[str] = set()

    common_path = SENSITIVE_WORDS_DIR / "common.yaml"
    if common_path.exists():
        with open(common_path, "r", encoding="utf-8") as f:
            data = yaml.safe_load(f) or {}
            words.update(data.get("words", []))

    track_path = SENSITIVE_WORDS_DIR / f"{track}.yaml"
    if track_path.exists():
        with open(track_path, "r", encoding="utf-8") as f:
            data = yaml.safe_load(f) or {}
            words.update(data.get("words", []))

    return words


def _check_sensitive_words(text: str, words: set[str]) -> list[str]:
    """Return list of detected sensitive words in the text."""
    found = []
    for word in words:
        if word in text:
            found.append(word)
    return found


def _check_finance_compliance(text: str, track: str) -> list[str]:
    """Check financial content compliance rules."""
    issues = []
    if track != "finance":
        return issues

    absolute_claims = ["一定涨", "稳赚", "保证收益", "必涨", "翻倍", "暴涨"]
    for claim in absolute_claims:
        if claim in text:
            issues.append(f"金融合规: 包含断言性表述 '{claim}'")

    return issues


async def content_safety_check(state: AgentState) -> dict:
    """Graph node: perform safety and compliance checks."""
    persona = state["persona"]
    track = persona.get("track", "")
    title = state.get("draft_title", "")
    content = state.get("draft_content", "")
    full_text = f"{title}\n{content}"

    logger.info("[Node 4] Safety check for account: %s", state["account_id"])

    issues: list[str] = []

    # 1. Sensitive word check
    sensitive_words = _load_sensitive_words(track)
    extra_words = persona.get("sensitive_words_extra", [])
    sensitive_words.update(extra_words)
    found_words = _check_sensitive_words(full_text, sensitive_words)
    if found_words:
        issues.extend([f"敏感词: '{w}'" for w in found_words])

    # 2. Finance compliance
    issues.extend(_check_finance_compliance(full_text, track))

    # 3. Content deduplication
    # TODO: Implement embedding-based dedup against recent posts

    # 4. Image compliance
    # TODO: Implement watermark detection and size validation

    safety_passed = len(issues) == 0

    if not safety_passed:
        logger.warning("[Node 4] Safety issues found: %s", issues)
    else:
        logger.info("[Node 4] Safety check passed.")

    return {
        "safety_passed": safety_passed,
        "safety_issues": issues,
    }
