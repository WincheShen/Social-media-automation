import { NextResponse } from "next/server";
import { getTask, updateTask } from "@/lib/db";

export async function POST(
  _request: Request,
  { params }: { params: Promise<{ id: string }> }
) {
  const { id } = await params;
  const task = getTask(id);
  if (!task) {
    return NextResponse.json({ error: "Task not found" }, { status: 404 });
  }

  if (task.status !== "reviewing") {
    return NextResponse.json(
      { error: `Cannot reject task in status '${task.status}'` },
      { status: 400 }
    );
  }

  updateTask(id, { status: "rejected" });
  return NextResponse.json({ success: true, status: "rejected" });
}
