import { spawn } from "child_process";
import path from "path";
import { getTask, updateTask } from "./db";

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
import asyncio, json, sys, base64
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
        "traffic_analysis": None,
        "suggested_topic": None,
        "research_results": [],
        "data_sources": [],
        "draft_title": "",
        "draft_content": "",
        "draft_tags": [],
        "visual_assets": [],
        "image_gen_prompt": None,
        "safety_passed": False,
        "safety_issues": [],
        "review_mode": "review",
        "approved": False,
        "publish_result": None,
        "post_metrics": None,
        "feedback_summary": None,
    }

    result = await graph.ainvoke(state)
    
    # Safely extract research summary - create readable text instead of dumping raw dicts
    research_results = result.get("research_results", [])
    research_summary = ""
    if research_results:
        try:
            summaries = []
            for idx, r in enumerate(research_results[:3], 1):
                if isinstance(r, dict):
                    # Extract key information from the research result
                    task_type = r.get("task_type", "unknown")
                    models = r.get("models_used", {})
                    source_count = r.get("raw_search_count", 0)
                    
                    # Get analysis summary if available
                    analysis = r.get("analysis", {})
                    if isinstance(analysis, dict):
                        summary_text = analysis.get("summary", "")
                        if summary_text and len(summary_text) > 300:
                            summary_text = summary_text[:300] + "..."
                    else:
                        summary_text = ""
                    
                    summary_parts = [
                        f"研究 {idx}: {task_type}",
                        f"数据源: {source_count} 条",
                        f"模型: {models.get('logic_analyst', 'N/A')}",
                    ]
                    if summary_text:
                        summary_parts.append(f"摘要: {summary_text}")
                    
                    summaries.append("\\n".join(summary_parts))
                else:
                    # Fallback for non-dict results
                    r_str = str(r)
                    if len(r_str) > 200:
                        r_str = r_str[:200] + "..."
                    summaries.append(r_str)
            
            research_summary = "\\n\\n".join(summaries)
        except Exception as e:
            research_summary = f"研究结果解析失败: {str(e)}"
    
    # Store full research data for retry functionality
    research_data = {
        "research_results": result.get("research_results", []),
        "data_sources": result.get("data_sources", []),
        "traffic_analysis": result.get("traffic_analysis"),
        "suggested_topic": result.get("suggested_topic"),
    }
    
    output = {
        "draft_title": result.get("draft_title", ""),
        "draft_content": result.get("draft_content", ""),
        "draft_tags": result.get("draft_tags", []),
        "research_summary": research_summary,
        "research_data": research_data,
        "safety_passed": result.get("safety_passed", False),
        "safety_issues": result.get("safety_issues", []),
        "image_gen_prompt": result.get("image_gen_prompt") or "",
        "review_mode": result.get("review_mode", "review"),
        "image_gen_model": result.get("persona", {}).get("models", {}).get("image_gen") or "",
    }
    # Encode as base64 to avoid JSON escaping issues in stdout
    output_json = json.dumps(output, ensure_ascii=False)
    output_b64 = base64.b64encode(output_json.encode('utf-8')).decode('ascii')
    print("__JSON_START__")
    print(output_b64)
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
        const b64Str = stdout.split("__JSON_START__")[1].split("__JSON_END__")[0].trim();
        const jsonStr = Buffer.from(b64Str, 'base64').toString('utf-8');
        const result = JSON.parse(jsonStr);
        updateTask(taskId, {
          status: result.safety_passed ? "reviewing" : "reviewing",
          draft_title: result.draft_title || "",
          draft_content: result.draft_content || "",
          draft_tags: result.draft_tags || [],
          research_summary: result.research_summary || "",
          research_data: result.research_data || undefined,
          safety_issues: result.safety_issues || [],
          image_gen_prompt: result.image_gen_prompt || undefined,
        });

        // Auto-generate image when review_mode is "auto" and we have a prompt
        const reviewMode = result.review_mode || "review";
        const imagePrompt = result.image_gen_prompt || "";
        if (reviewMode === "auto" && imagePrompt) {
          const imageModel = result.image_gen_model || null;
          runImageGeneration(taskId, accountId, imagePrompt, imageModel);
        }
      } catch (e) {
        updateTask(taskId, {
          status: "failed",
          error: `Failed to parse workflow output: ${e instanceof Error ? e.message : 'Unknown error'}\n${stdout.slice(-500)}`,
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
 * Run the Python workflow with retry logic - reuses existing research data if available.
 * This is the "Brain" decision: if research data exists, skip Node 2 and go directly to Node 3.
 */
export function runWorkflowResearchWithRetry(
  taskId: string,
  accountId: string,
  description: string,
  existingResearchData?: any
): void {
  updateTask(taskId, { status: "running" });

  const hasResearchData = existingResearchData && 
    existingResearchData.research_results && 
    existingResearchData.research_results.length > 0;

  // Safely encode research data as base64 to avoid JSON escaping issues
  const researchDataJson = existingResearchData ? JSON.stringify(existingResearchData) : null;
  const researchDataB64 = researchDataJson ? Buffer.from(researchDataJson).toString('base64') : '';

  // Python script that conditionally skips research if data exists
  const scriptContent = `
import asyncio, json, sys, base64
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

    # Check if we have existing research data to reuse (decode from base64)
    research_b64 = "${researchDataB64}"
    if research_b64:
        try:
            existing_data = json.loads(base64.b64decode(research_b64).decode('utf-8'))
            has_research = bool(existing_data and existing_data.get("research_results"))
        except Exception as e:
            print(f"[RETRY] Failed to decode research data: {e}", file=sys.stderr)
            existing_data = None
            has_research = False
    else:
        existing_data = None
        has_research = False
    
    if has_research:
        print("[RETRY] Reusing existing research data, skipping Node 2...", file=sys.stderr)
    
    graph = build_graph()
    state: AgentState = {
        "account_id": ${JSON.stringify(accountId)},
        "task": ${JSON.stringify(description)},
        "persona": {},
        "memory": [],
        "traffic_analysis": existing_data.get("traffic_analysis") if has_research else None,
        "suggested_topic": existing_data.get("suggested_topic") if has_research else None,
        "research_results": existing_data.get("research_results", []) if has_research else [],
        "data_sources": existing_data.get("data_sources", []) if has_research else [],
        "draft_title": "",
        "draft_content": "",
        "draft_tags": [],
        "visual_assets": [],
        "image_gen_prompt": None,
        "safety_passed": False,
        "safety_issues": [],
        "review_mode": "review",
        "approved": False,
        "publish_result": None,
        "post_metrics": None,
        "feedback_summary": None,
    }

    result = await graph.ainvoke(state)
    
    # Safely extract research summary
    research_results = result.get("research_results", [])
    research_summary = ""
    if research_results:
        try:
            summaries = []
            for idx, r in enumerate(research_results[:3], 1):
                if isinstance(r, dict):
                    task_type = r.get("task_type", "unknown")
                    models = r.get("models_used", {})
                    source_count = r.get("raw_search_count", 0)
                    
                    analysis = r.get("analysis", {})
                    if isinstance(analysis, dict):
                        summary_text = analysis.get("summary", "")
                        if summary_text and len(summary_text) > 300:
                            summary_text = summary_text[:300] + "..."
                    else:
                        summary_text = ""
                    
                    summary_parts = [
                        f"研究 {idx}: {task_type}",
                        f"数据源: {source_count} 条",
                        f"模型: {models.get('logic_analyst', 'N/A')}",
                    ]
                    if summary_text:
                        summary_parts.append(f"摘要: {summary_text}")
                    
                    summaries.append("\\n".join(summary_parts))
                else:
                    r_str = str(r)
                    if len(r_str) > 200:
                        r_str = r_str[:200] + "..."
                    summaries.append(r_str)
            
            research_summary = "\\n\\n".join(summaries)
        except Exception as e:
            research_summary = f"研究结果解析失败: {str(e)}"
    
    # Store full research data for future retry
    research_data = {
        "research_results": result.get("research_results", []),
        "data_sources": result.get("data_sources", []),
        "traffic_analysis": result.get("traffic_analysis"),
        "suggested_topic": result.get("suggested_topic"),
    }
    
    output = {
        "draft_title": result.get("draft_title", ""),
        "draft_content": result.get("draft_content", ""),
        "draft_tags": result.get("draft_tags", []),
        "research_summary": research_summary,
        "research_data": research_data,
        "safety_passed": result.get("safety_passed", False),
        "safety_issues": result.get("safety_issues", []),
        "image_gen_prompt": result.get("image_gen_prompt") or "",
        "reused_research": has_research,
    }
    # Encode as base64 to avoid JSON escaping issues in stdout
    output_json = json.dumps(output, ensure_ascii=False)
    output_b64 = base64.b64encode(output_json.encode('utf-8')).decode('ascii')
    print("__JSON_START__")
    print(output_b64)
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
        const b64Str = stdout.split("__JSON_START__")[1].split("__JSON_END__")[0].trim();
        const jsonStr = Buffer.from(b64Str, 'base64').toString('utf-8');
        const result = JSON.parse(jsonStr);
        
        const statusMessage = result.reused_research 
          ? "reviewing (复用已有研究数据)" 
          : "reviewing";
        
        updateTask(taskId, {
          status: result.safety_passed ? "reviewing" : "reviewing",
          draft_title: result.draft_title || "",
          draft_content: result.draft_content || "",
          draft_tags: result.draft_tags || [],
          research_summary: result.research_summary || "",
          research_data: result.research_data || undefined,
          safety_issues: result.safety_issues || [],
          image_gen_prompt: result.image_gen_prompt || undefined,
        });
      } catch (e) {
        updateTask(taskId, {
          status: "failed",
          error: `Failed to parse workflow output: ${e instanceof Error ? e.message : 'Unknown error'}\n${stdout.slice(-500)}`,
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
        "traffic_analysis": None,
        "suggested_topic": None,
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

/**
 * Run image generation for a task. Uses the Python ImageGenerator backend.
 * Returns generated image paths via callback. Updates task.generated_images.
 */
export function runImageGeneration(
  taskId: string,
  accountId: string,
  prompt: string,
  model: string | null,
): void {
  const scriptContent = `
import asyncio, json, sys
sys.path.insert(0, "${PROJECT_ROOT}")
from dotenv import load_dotenv
load_dotenv("${PROJECT_ROOT}/.env")
from src.infra.image_gen import ImageGenerator

async def main():
    model = ${model ? JSON.stringify(model) : "None"}
    gen = ImageGenerator(model=model)
    path = await gen.generate(
        prompt=${JSON.stringify(prompt)},
        style="xiaohongshu",
        account_id=${JSON.stringify(accountId)},
    )
    output = {"images": [path], "error": ""}
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
        const images: string[] = result.images || [];
        // Store as relative paths from project root
        const relImages = images.map((p: string) => path.relative(PROJECT_ROOT, p));
        updateTask(taskId, { generated_images: relImages });
      } catch {
        updateTask(taskId, {
          error: `Image generation parse error: ${stdout.slice(-300)}`,
        });
      }
    } else {
      updateTask(taskId, {
        error: `Image generation failed (exit ${code}): ${stderr.slice(-500)}`,
      });
    }
  });
}
