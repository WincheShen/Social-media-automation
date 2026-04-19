import { NextResponse } from "next/server";
import { getTask, updateTask } from "@/lib/db";
import { runImageGeneration } from "@/lib/workflow";

export async function POST(
  request: Request,
  { params }: { params: Promise<{ id: string }> }
) {
  const { id } = await params;
  const task = getTask(id);
  if (!task) {
    return NextResponse.json({ error: "Task not found" }, { status: 404 });
  }

  const body = await request.json().catch(() => ({}));
  const prompt: string = body.prompt || task.image_gen_prompt || "";
  const model: string | null = body.model || null;

  if (!prompt) {
    return NextResponse.json(
      { error: "No image prompt available. Generate content first." },
      { status: 400 }
    );
  }

  // Clear previous images and mark as generating
  updateTask(id, { generated_images: [] });

  runImageGeneration(id, task.account_id, prompt, model);

  return NextResponse.json({ success: true, status: "generating" });
}
