import { cn } from "@/lib/utils";
import type { TaskStatus } from "@/lib/types";

const STATUS_CONFIG: Record<TaskStatus, { label: string; className: string }> = {
  created: { label: "已创建", className: "bg-slate-100 text-slate-700" },
  running: { label: "AI 生成中", className: "bg-blue-100 text-blue-700 animate-pulse" },
  reviewing: { label: "待审核", className: "bg-amber-100 text-amber-700" },
  approved: { label: "已批准", className: "bg-green-100 text-green-700" },
  publishing: { label: "发布中", className: "bg-indigo-100 text-indigo-700 animate-pulse" },
  published: { label: "已发布", className: "bg-emerald-100 text-emerald-700" },
  rejected: { label: "已拒绝", className: "bg-red-100 text-red-700" },
  failed: { label: "失败", className: "bg-red-100 text-red-700" },
};

export function StatusBadge({ status }: { status: TaskStatus }) {
  const config = STATUS_CONFIG[status] || STATUS_CONFIG.created;
  return (
    <span
      className={cn(
        "inline-flex items-center px-2.5 py-0.5 rounded-full text-xs font-medium",
        config.className
      )}
    >
      {config.label}
    </span>
  );
}
