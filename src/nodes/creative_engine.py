"""Node 3: Creative & Optimization Engine

Generates platform-adapted copy (title, body, tags) and visual assets
based on research results and persona settings.

Visual generation strategies:
- Education:  knowledge-card images via matplotlib / Pillow
- Finance:    data charts via matplotlib
- Lifestyle:  AI image generation (future: Nano Banana 2)
"""

from __future__ import annotations

import json
import logging
from datetime import datetime, timezone
from pathlib import Path

from src.graph.state import AgentState
from src.infra.model_adapter import ModelAdapter

logger = logging.getLogger(__name__)

ASSETS_DIR = Path("data/assets")

# ---------------------------------------------------------------------------
# Copy generation prompt
# ---------------------------------------------------------------------------

COPY_PROMPT_TEMPLATE = """你是 {persona_name}，{persona_desc}。

## 你的语言风格
{persona_tone}

## 目标受众
{audience}

## 研究素材
{research_summary}

## 核心观点
{content_angles}

## 任务
基于以上研究素材，为小红书平台撰写一篇笔记。

## 输出格式要求（JSON）
```json
{{
  "title": "标题（15-20字，包含emoji，吸引点击）",
  "content": "正文（300-800字，分段清晰，重点加粗用**标记**）",
  "tags": ["标签1", "标签2", "标签3", "标签4", "标签5"]
}}
```

## 小红书内容规范
1. 标题：简洁有力，善用数字和emoji，制造信息差
2. 正文：开头抛痛点/悬念，中间给干货，结尾引互动
3. 标签：5个左右，混合热门标签和精准长尾标签
4. 避免：过度营销、绝对化用语、虚假承诺"""


def _format_research_for_creative(research_results: list[dict]) -> tuple[str, str]:
    """Extract summary and content angles from research results."""
    if not research_results:
        return "(无研究素材)", "(无)"

    analysis = research_results[0].get("analysis", {})
    summary = analysis.get("summary", "(无总结)")

    angles = analysis.get("content_angles", [])
    if angles:
        angles_text = "\n".join(
            f"- {a.get('angle', '')}: {a.get('supporting_data', '')}"
            for a in angles
        )
    else:
        angles_text = "(无)"

    return summary, angles_text


def _parse_copy_response(text: str) -> dict:
    """Extract JSON from the LLM copy generation response."""
    if "```json" in text:
        start = text.index("```json") + 7
        end = text.index("```", start)
        text = text[start:end].strip()
    elif "```" in text:
        start = text.index("```") + 3
        end = text.index("```", start)
        text = text[start:end].strip()

    try:
        return json.loads(text)
    except json.JSONDecodeError:
        logger.warning("[Node 3] Failed to parse copy JSON, extracting manually.")
        return {"title": "", "content": text[:1000], "tags": []}


# ---------------------------------------------------------------------------
# Visual asset generation
# ---------------------------------------------------------------------------

async def _generate_knowledge_card(
    title: str,
    key_facts: list[str],
    account_id: str,
    visual_style: dict,
) -> str | None:
    """Generate a knowledge card image using Pillow."""
    try:
        from PIL import Image, ImageDraw, ImageFont
    except ImportError:
        logger.warning("Pillow not available, skipping knowledge card generation.")
        return None

    # Prepare output path
    date_str = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    out_dir = ASSETS_DIR / account_id / date_str
    out_dir.mkdir(parents=True, exist_ok=True)
    out_path = out_dir / "knowledge_card.png"

    # Card dimensions
    width, height = 1080, 1440
    colors = visual_style.get("color_scheme", ["#1a73e8", "#ffffff", "#f0f4f9"])
    primary_color = colors[0] if len(colors) > 0 else "#1a73e8"
    bg_color = colors[2] if len(colors) > 2 else "#f0f4f9"
    text_color = "#333333"

    img = Image.new("RGB", (width, height), bg_color)
    draw = ImageDraw.Draw(img)

    # Try to use a system font, fall back to default
    try:
        title_font = ImageFont.truetype("/System/Library/Fonts/PingFang.ttc", 48)
        body_font = ImageFont.truetype("/System/Library/Fonts/PingFang.ttc", 32)
    except (OSError, IOError):
        title_font = ImageFont.load_default()
        body_font = ImageFont.load_default()

    # Header bar
    draw.rectangle([0, 0, width, 160], fill=primary_color)
    draw.text((60, 50), title[:20], fill="#ffffff", font=title_font)

    # Key facts
    y_offset = 200
    for i, fact in enumerate(key_facts[:8]):
        marker = f"📌 " if i < 3 else f"• "
        text = f"{marker}{fact}"
        # Wrap long text
        if len(text) > 25:
            draw.text((60, y_offset), text[:25], fill=text_color, font=body_font)
            y_offset += 50
            draw.text((100, y_offset), text[25:50], fill=text_color, font=body_font)
        else:
            draw.text((60, y_offset), text, fill=text_color, font=body_font)
        y_offset += 70

    # Footer
    draw.rectangle([0, height - 80, width, height], fill=primary_color)
    draw.text((60, height - 60), "关注我获取更多干货 👆", fill="#ffffff", font=body_font)

    img.save(str(out_path), "PNG")
    logger.info("[Node 3] Knowledge card saved: %s", out_path)
    return str(out_path)


async def _generate_visual_assets(
    state: AgentState,
    title: str,
    research_results: list[dict],
) -> list[str]:
    """Generate visual assets based on account type and visual style."""
    persona = state["persona"]
    account_id = state["account_id"]
    visual_style = persona.get("visual_style", {})
    template = visual_style.get("template", "")

    assets: list[str] = []
    analysis = research_results[0].get("analysis", {}) if research_results else {}
    key_facts = analysis.get("key_facts", [])

    if template == "knowledge_card" and key_facts:
        path = await _generate_knowledge_card(
            title, key_facts, account_id, visual_style
        )
        if path:
            assets.append(path)

    # TODO: Add data_dashboard template for finance accounts (matplotlib K-line)
    # TODO: Add warm_card template for lifestyle accounts (AI image gen)

    return assets


# ---------------------------------------------------------------------------
# Node entry point
# ---------------------------------------------------------------------------

async def creative_engine(state: AgentState) -> dict:
    """Graph node: generate content drafts and visual assets."""
    persona = state["persona"]
    research_results = state["research_results"]
    task = state["task"]
    account_id = state["account_id"]

    logger.info("[Node 3] Creative generation for account: %s", account_id)

    # 1. Build copy generation prompt
    persona_cfg = persona.get("persona", {})
    research_summary, content_angles = _format_research_for_creative(research_results)

    prompt = COPY_PROMPT_TEMPLATE.format(
        persona_name=persona_cfg.get("name", "内容创作者"),
        persona_desc=persona_cfg.get("description", ""),
        persona_tone=persona_cfg.get("tone", "专业友好"),
        audience=persona_cfg.get("audience", "通用读者"),
        research_summary=research_summary,
        content_angles=content_angles,
    )

    system_prompt = persona_cfg.get("system_prompt", "")
    models_cfg = persona.get("models", {})
    primary = models_cfg.get("primary", "gemini-1.5-pro")
    fallback = models_cfg.get("fallback", "gemini-1.5-flash")

    # 2. Generate copy via LLM
    raw_response = await ModelAdapter.invoke_with_fallback(
        primary, fallback, prompt,
        system_prompt=system_prompt,
        temperature=0.8,
        max_tokens=4096,
    )

    copy = _parse_copy_response(raw_response)
    draft_title = copy.get("title", "")
    draft_content = copy.get("content", "")
    draft_tags = copy.get("tags", [])

    logger.info(
        "[Node 3] Copy generated — title='%s', content_len=%d, tags=%d",
        draft_title[:30], len(draft_content), len(draft_tags),
    )

    # 3. Generate visual assets
    visual_assets = await _generate_visual_assets(state, draft_title, research_results)

    logger.info("[Node 3] Visual assets generated: %d files", len(visual_assets))

    return {
        "draft_title": draft_title,
        "draft_content": draft_content,
        "draft_tags": draft_tags,
        "visual_assets": visual_assets,
    }
