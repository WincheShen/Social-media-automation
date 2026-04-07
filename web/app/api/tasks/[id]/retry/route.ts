import { NextRequest, NextResponse } from "next/server";
import { getTask, updateTask } from "@/lib/db";
import { runWorkflowResearchWithRetry } from "@/lib/workflow";

export async function POST(
  request: NextRequest,
  { params }: { params: Promise<{ id: string }> }
) {
  const { id } = await params;
  const task = getTask(id);

  if (!task) {
    return NextResponse.json({ error: "Task not found" }, { status: 404 });
  }

  if (task.status !== "failed") {
    return NextResponse.json(
      { error: "Only failed tasks can be retried" },
      { status: 400 }
    );
  }

  // Clear error and retry
  updateTask(id, { error: undefined });
  runWorkflowResearchWithRetry(id, task.account_id, task.description, task.research_data);

  return NextResponse.json({ success: true });
}
