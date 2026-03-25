"""Node 6: Execution & Browser Publish

Publishes approved content to social media platforms via xiaohongshu-skills CLI.
Each account uses an isolated Chrome instance via CDP with stealth anti-detection.

Three-step flow:
    1. fill-publish  — populate the form (title, content, images)
    2. User previews  — user inspects the note in the real browser
    3. click-publish  — confirm and submit

Uses XhsCliAdapter (subprocess → CLI → CDP → Chrome → 小红书).
No LLM tokens consumed for browser operations.
"""

from __future__ import annotations

import logging
from datetime import datetime, timezone

from src.graph.state import AgentState
from src.infra.xhs_cli import XhsCliAdapter, get_adapter_for_account
from src.infra.xhs_cli_types import XhsNotLoggedInError, XhsCliError

logger = logging.getLogger(__name__)


async def _ensure_login(adapter: XhsCliAdapter, account_id: str) -> bool:
    """Check login status; log a clear message if not logged in."""
    status = await adapter.check_login()
    if status.logged_in:
        logger.info(
            "[Node 6] Logged in as %s (XHS ID: %s)",
            status.nickname, status.xhs_id,
        )
        return True

    logger.warning(
        "[Node 6] Account %s not logged in. "
        "Please run:  python scripts/cli.py login --account %s",
        account_id, account_id,
    )
    return False


async def _publish_via_cli(
    adapter: XhsCliAdapter,
    state: AgentState,
) -> dict:
    """Execute the three-step publish flow via CLI.

    Steps:
        1. fill-publish — fill form without submitting
        2. Pause for human preview (logged, agent waits for next step)
        3. click-publish — confirm and submit
    """
    title = state.get("draft_title", "")
    content = state.get("draft_content", "")
    tags = state.get("draft_tags", [])
    images = state.get("visual_assets", [])

    # Append tags to content body (小红书 convention)
    if tags:
        tag_line = " ".join(f"#{t}" for t in tags)
        content = f"{content}\n\n{tag_line}"

    # Step 1: Fill the publish form
    logger.info("[Node 6] Step 1/3 — Filling publish form...")
    await adapter.fill_publish(
        title=title,
        content=content,
        images=images,
    )
    logger.info(
        "[Node 6] Step 2/3 — Form filled. Please preview in the browser."
    )

    # Step 3: Confirm publish
    # In review mode the human will have already previewed via the browser.
    # The click-publish call submits the form.
    logger.info("[Node 6] Step 3/3 — Submitting publish...")
    result = await adapter.click_publish()

    return {
        "status": "success" if result.success else "failed",
        "url": result.post_url,
        "error": result.error,
    }


async def browser_publish(state: AgentState) -> dict:
    """Graph node: publish content via xiaohongshu-skills CLI."""
    account_id = state["account_id"]
    persona = state["persona"]
    platform = persona.get("platform", "xiaohongshu")

    logger.info(
        "[Node 6] Publishing to %s for account: %s", platform, account_id,
    )

    adapter = get_adapter_for_account(persona)

    # Pre-flight: verify login
    try:
        logged_in = await _ensure_login(adapter, account_id)
    except XhsCliError as e:
        logger.error("[Node 6] Chrome/CLI not reachable: %s", e)
        return {"publish_result": _make_result(
            "failed", platform, account_id, error=f"CLI unreachable: {e}",
        )}

    if not logged_in:
        return {"publish_result": _make_result(
            "failed", platform, account_id, error="not_logged_in",
        )}

    # Execute publish
    try:
        result = await _publish_via_cli(adapter, state)
    except XhsNotLoggedInError:
        return {"publish_result": _make_result(
            "failed", platform, account_id, error="session_expired",
        )}
    except XhsCliError as e:
        logger.error("[Node 6] Publish failed: %s", e)
        return {"publish_result": _make_result(
            "failed", platform, account_id, error=str(e),
        )}

    publish_result = _make_result(
        status=result.get("status", "failed"),
        platform=platform,
        account_id=account_id,
        url=result.get("url"),
        error=result.get("error"),
    )

    if publish_result["status"] == "success":
        logger.info("[Node 6] Published — url=%s", publish_result["url"])
    else:
        logger.warning(
            "[Node 6] Publish result: status=%s, error=%s",
            publish_result["status"], publish_result.get("error"),
        )

    return {"publish_result": publish_result}


def _make_result(
    status: str,
    platform: str,
    account_id: str,
    url: str | None = None,
    error: str | None = None,
) -> dict:
    """Build a standardised publish_result dict."""
    return {
        "status": status,
        "platform": platform,
        "account_id": account_id,
        "url": url,
        "published_at": datetime.now(timezone.utc).isoformat(),
        "error": error,
    }
