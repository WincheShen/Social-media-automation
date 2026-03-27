import { NextResponse } from "next/server";
import { listTasks, createTask } from "@/lib/db";
import { runWorkflowResearch } from "@/lib/workflow";

export async function GET(request: Request) {
  const { searchParams } = new URL(request.url);
  const accountId = searchParams.get("account_id") || undefined;
  const tasks = listTasks(accountId);
  return NextResponse.json(tasks);
}

export async function POST(request: Request) {
  const body = await request.json();
  const { account_id, description } = body;

  if (!account_id || !description) {
    return NextResponse.json(
      { error: "account_id and description are required" },
      { status: 400 }
    );
  }

  const task = createTask(account_id, description);

  // Auto-start the AI workflow (nodes 1-4)
  runWorkflowResearch(task.id, account_id, description);

  return NextResponse.json(task, { status: 201 });
}
