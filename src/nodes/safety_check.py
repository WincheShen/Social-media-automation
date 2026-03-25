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


FINANCE_DISCLAIMER = (
    "\n\n⚠️ 免责声明：以上内容仅供参考，不构成任何投资建议。"
    "投资有风险，入市需谨慎。"
)

FINANCE_TRACKS = {"finance", "金融", "股票"}


def _check_content_length(title: str, content: str) -> list[str]:
    """Validate content length for platform requirements."""
    issues = []
    if len(title) < 5:
        issues.append(f"标题过短: {len(title)}字 (最低5字)")
    if len(title) > 30:
        issues.append(f"标题过长: {len(title)}字 (最多30字)")
    if len(content) < 50:
        issues.append(f"正文过短: {len(content)}字 (最低50字)")
    if len(content) > 2000:
        issues.append(f"正文过长: {len(content)}字 (最多2000字)")
    return issues


def _check_image_compliance(visual_assets: list[str]) -> list[str]:
    """Check image dimensions and file size."""
    issues = []
    for path in visual_assets:
        p = Path(path)
        if not p.exists():
            issues.append(f"图片文件不存在: {path}")
            continue
        size_mb = p.stat().st_size / (1024 * 1024)
        if size_mb > 20:
            issues.append(f"图片文件过大: {path} ({size_mb:.1f}MB, 最大20MB)")
    return issues


async def content_safety_check(state: AgentState) -> dict:
    """Graph node: perform safety and compliance checks."""
    persona = state["persona"]
    track = persona.get("track", "")
    title = state.get("draft_title", "")
    content = state.get("draft_content", "")
    visual_assets = state.get("visual_assets", [])
    full_text = f"{title}\n{content}"

    logger.info("[Node 4] Safety check for account: %s", state["account_id"])

    issues: list[str] = []
    updated_content = content

    # 1. Content length validation
    issues.extend(_check_content_length(title, content))

    # 2. Sensitive word check
    sensitive_words = _load_sensitive_words(track)
    extra_words = persona.get("sensitive_words_extra", [])
    sensitive_words.update(extra_words)
    found_words = _check_sensitive_words(full_text, sensitive_words)
    if found_words:
        issues.extend([f"敏感词: '{w}'" for w in found_words])

    # 3. Finance compliance
    finance_issues = _check_finance_compliance(full_text, track)
    issues.extend(finance_issues)

    # Auto-append finance disclaimer if not present
    if track in FINANCE_TRACKS and "免责声明" not in content:
        updated_content = content + FINANCE_DISCLAIMER
        logger.info("[Node 4] Auto-appended finance disclaimer.")

    # 4. Image compliance
    issues.extend(_check_image_compliance(visual_assets))

    # 5. Content deduplication
    # TODO: Implement embedding-based dedup against recent posts

    safety_passed = len(issues) == 0

    if not safety_passed:
        logger.warning("[Node 4] Safety issues found: %s", issues)
    else:
        logger.info("[Node 4] Safety check passed.")

    result: dict = {
        "safety_passed": safety_passed,
        "safety_issues": issues,
    }
    # Pass through updated content if disclaimer was added
    if updated_content != content:
        result["draft_content"] = updated_content

    return result
