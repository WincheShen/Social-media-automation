import { spawn } from "child_process";
import path from "path";
import { updateTask } from "./db";

const PROJECT_ROOT = path.resolve(process.cwd(), "..");
const PYTHON = path.join(PROJECT_ROOT, ".venv", "bin", "python3");

/**
 * Run the Python workflow for a task (nodes 1-4: research + creative + safety).
 * Stores results in the task DB. Runs as a background subprocess.
 */
export function runWorkflowResearch(taskId: string, accountId: string, description: string): void {
  updateTask(taskId, { status: "running" });

  // Python script that runs nodes 1-4 and outputs JSON result
  const scriptContent = `
import asyncio, json, sys
sys.path.insert(0, "${PROJECT_ROOT}")
from dotenv import load_dotenv
load_dotenv("${PROJECT_ROOT}/.env")
from src.graph.state import AgentState
from src.graph.workflow import build_graph
from src.infra.identity_registry import registry
from src.infra.model_adapter import init_models
from src.infra.logger import setup_logging

async def main():
    setup_logging()
    init_models()
    registry.load_all()

    graph = build_graph()
    state: AgentState = {
        "account_id": ${JSON.stringify(accountId)},
        "task": ${JSON.stringify(description)},
        "persona": {},
        "memory": [],
        "research_results": [],
        "data_sources": [],
        "draft_title": "",
        "draft_content": "",
        "draft_tags": [],
        "visual_assets": [],
        "safety_passed": False,
        "safety_issues": [],
        "review_mode": "review",
        "approved": False,
        "publish_result": None,
        "post_metrics": None,
        "feedback_summary": None,
    }

    result = await graph.ainvoke(state)
    output = {
        "draft_title": result.get("draft_title", ""),
        "draft_content": result.get("draft_content", ""),
        "draft_tags": result.get("draft_tags", []),
        "research_summary": "\\n".join(str(r) for r in result.get("research_results", [])[:3]),
        "safety_passed": result.get("safety_passed", False),
        "safety_issues": result.get("safety_issues", []),
    }
    print("__JSON_START__")
    print(json.dumps(output, ensure_ascii=False))
    print("__JSON_END__")

asyncio.run(main())
`;

  const proc = spawn(PYTHON, ["-c", scriptContent], {
    cwd: PROJECT_ROOT,
    env: { ...process.env, PYTHONPATH: PROJECT_ROOT },
    stdio: ["ignore", "pipe", "pipe"],
  });

  let stdout = "";
  let stderr = "";

  proc.stdout.on("data", (data: Buffer) => {
    stdout += data.toString();
  });
  proc.stderr.on("data", (data: Buffer) => {
    stderr += data.toString();
  });

  proc.on("close", (code: number | null) => {
    if (code === 0 && stdout.includes("__JSON_START__")) {
      try {
        const jsonStr = stdout.split("__JSON_START__")[1].split("__JSON_END__")[0].trim();
        const result = JSON.parse(jsonStr);
        updateTask(taskId, {
          status: result.safety_passed ? "reviewing" : "reviewing",
          draft_title: result.draft_title || "",
          draft_content: result.draft_content || "",
          draft_tags: result.draft_tags || [],
          research_summary: result.research_summary || "",
          safety_issues: result.safety_issues || [],
        });
      } catch {
        updateTask(taskId, {
          status: "failed",
          error: `Failed to parse workflow output: ${stdout.slice(-500)}`,
        });
      }
    } else {
      updateTask(taskId, {
        status: "failed",
        error: `Workflow failed (exit ${code}): ${stderr.slice(-500)}`,
      });
    }
  });
}

/**
 * Run the publish step (nodes 6-8) for an approved task.
 */
export function runWorkflowPublish(
  taskId: string,
  accountId: string,
  title: string,
  content: string,
  tags: string[],
): void {
  updateTask(taskId, { status: "publishing" });

  const scriptContent = `
import asyncio, json, sys
sys.path.insert(0, "${PROJECT_ROOT}")
from dotenv import load_dotenv
load_dotenv("${PROJECT_ROOT}/.env")
from src.infra.identity_registry import registry
from src.infra.model_adapter import init_models
from src.infra.logger import setup_logging
from src.nodes.execution import browser_publish
from src.nodes.monitor import post_publish_monitor
from src.nodes.feedback import feedback_memory_update

async def main():
    setup_logging()
    init_models()
    registry.load_all()

    state = {
        "account_id": ${JSON.stringify(accountId)},
        "task": "publish",
        "persona": dict(registry.get(${JSON.stringify(accountId)})),
        "memory": [],
        "research_results": [],
        "data_sources": [],
        "draft_title": ${JSON.stringify(title)},
        "draft_content": ${JSON.stringify(content)},
        "draft_tags": ${JSON.stringify(tags)},
        "visual_assets": [],
        "safety_passed": True,
        "safety_issues": [],
        "review_mode": "review",
        "approved": True,
        "publish_result": None,
        "post_metrics": None,
        "feedback_summary": None,
    }

    result = await browser_publish(state)
    state.update(result)
    mon = await post_publish_monitor(state)
    state.update(mon)
    fb = await feedback_memory_update(state)
    state.update(fb)

    pr = state.get("publish_result") or {}
    output = {
        "post_url": pr.get("url", ""),
        "success": pr.get("status") == "success",
        "error": pr.get("error", ""),
    }
    print("__JSON_START__")
    print(json.dumps(output, ensure_ascii=False))
    print("__JSON_END__")

asyncio.run(main())
`;

  const proc = spawn(PYTHON, ["-c", scriptContent], {
    cwd: PROJECT_ROOT,
    env: { ...process.env, PYTHONPATH: PROJECT_ROOT },
    stdio: ["ignore", "pipe", "pipe"],
  });

  let stdout = "";
  let stderr = "";

  proc.stdout.on("data", (data: Buffer) => {
    stdout += data.toString();
  });
  proc.stderr.on("data", (data: Buffer) => {
    stderr += data.toString();
  });

  proc.on("close", (code: number | null) => {
    if (code === 0 && stdout.includes("__JSON_START__")) {
      try {
        const jsonStr = stdout.split("__JSON_START__")[1].split("__JSON_END__")[0].trim();
        const result = JSON.parse(jsonStr);
        updateTask(taskId, {
          status: result.success ? "published" : "failed",
          post_url: result.post_url || undefined,
          error: result.success ? undefined : (result.error || "Publish failed"),
        });
      } catch {
        updateTask(taskId, {
          status: "failed",
          error: `Failed to parse publish output`,
        });
      }
    } else {
      updateTask(taskId, {
        status: "failed",
        error: `Publish failed (exit ${code}): ${stderr.slice(-500)}`,
      });
    }
  });
}
