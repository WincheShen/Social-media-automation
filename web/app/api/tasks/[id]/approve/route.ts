import { NextResponse } from "next/server";
import { getTask, updateTask } from "@/lib/db";
import { runWorkflowPublish } from "@/lib/workflow";

export async function POST(
  request: Request,
  { params }: { params: Promise<{ id: string }> }
) {
  const { id } = await params;
  const task = getTask(id);
  if (!task) {
    return NextResponse.json({ error: "Task not found" }, { status: 404 });
  }

  if (task.status !== "reviewing" && task.status !== "failed") {
    return NextResponse.json(
      { error: `Cannot approve task in status '${task.status}'` },
      { status: 400 }
    );
  }

  // Allow optional content overrides from the review form
  const body = await request.json().catch(() => ({}));
  const title = body.draft_title || task.draft_title || "";
  const content = body.draft_content || task.draft_content || "";
  const tags = body.draft_tags || task.draft_tags || [];

  // Update task with any edits
  updateTask(id, {
    status: "approved",
    draft_title: title,
    draft_content: content,
    draft_tags: tags,
  });

  // Trigger publish workflow (nodes 6-8)
  runWorkflowPublish(id, task.account_id, title, content, tags);

  return NextResponse.json({ success: true, status: "publishing" });
}
