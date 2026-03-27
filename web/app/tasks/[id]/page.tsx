import { getTask } from "@/lib/db";
import { notFound } from "next/navigation";
import { TaskDetail } from "./task-detail";

export const dynamic = "force-dynamic";

export default async function TaskDetailPage({
  params,
}: {
  params: Promise<{ id: string }>;
}) {
  const { id } = await params;
  const task = getTask(id);
  if (!task) notFound();

  return <TaskDetail task={task} />;
}
