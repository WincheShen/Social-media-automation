"use client";

import { useState, useEffect, useCallback } from "react";
import { useRouter } from "next/navigation";
import type { Task } from "@/lib/types";
import { StatusBadge } from "@/components/status-badge";
import {
  ArrowLeft,
  Check,
  X,
  Pencil,
  Loader2,
  ExternalLink,
  AlertTriangle,
  Trash2,
  Sparkles,
  Copy,
  CheckCheck,
} from "lucide-react";
import Link from "next/link";

export function TaskDetail({ task: initialTask }: { task: Task }) {
  const router = useRouter();
  const [task, setTask] = useState(initialTask);
  const [editing, setEditing] = useState(false);
  const [approving, setApproving] = useState(false);
  const [rejecting, setRejecting] = useState(false);
  const [deleting, setDeleting] = useState(false);
  const [retrying, setRetrying] = useState(false);
  const [promptCopied, setPromptCopied] = useState(false);

  // Editable fields
  const [title, setTitle] = useState(task.draft_title || "");
  const [content, setContent] = useState(task.draft_content || "");
  const [tagsStr, setTagsStr] = useState(
    (task.draft_tags || []).join(", ")
  );

  // Auto-refresh for running/publishing tasks
  const refresh = useCallback(async () => {
    const res = await fetch(`/api/tasks/${task.id}`);
    if (res.ok) {
      const updated = await res.json();
      setTask(updated);
      if (!editing) {
        setTitle(updated.draft_title || "");
        setContent(updated.draft_content || "");
        setTagsStr((updated.draft_tags || []).join(", "));
      }
    }
  }, [task.id, editing]);

  useEffect(() => {
    if (task.status === "running" || task.status === "publishing") {
      const interval = setInterval(refresh, 3000);
      return () => clearInterval(interval);
    }
  }, [task.status, refresh]);

  async function handleApprove() {
    setApproving(true);
    try {
      const tags = tagsStr
        .split(",")
        .map((t) => t.trim())
        .filter(Boolean);
      const res = await fetch(`/api/tasks/${task.id}/approve`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          draft_title: title,
          draft_content: content,
          draft_tags: tags,
        }),
      });
      if (res.ok) {
        setEditing(false);
        refresh();
      }
    } finally {
      setApproving(false);
    }
  }

  async function handleReject() {
    setRejecting(true);
    try {
      const res = await fetch(`/api/tasks/${task.id}/reject`, {
        method: "POST",
      });
      if (res.ok) refresh();
    } finally {
      setRejecting(false);
    }
  }

  async function handleSaveEdits() {
    const tags = tagsStr
      .split(",")
      .map((t) => t.trim())
      .filter(Boolean);
    await fetch(`/api/tasks/${task.id}`, {
      method: "PUT",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        draft_title: title,
        draft_content: content,
        draft_tags: tags,
      }),
    });
    setEditing(false);
    refresh();
  }

  async function handleCopyPrompt() {
    if (!task.image_gen_prompt) return;
    await navigator.clipboard.writeText(task.image_gen_prompt);
    setPromptCopied(true);
    setTimeout(() => setPromptCopied(false), 2000);
  }

  async function handleDelete() {
    if (!confirm("确定要删除这个任务吗？")) return;
    setDeleting(true);
    const res = await fetch(`/api/tasks/${task.id}`, { method: "DELETE" });
    if (res.ok) router.push("/tasks");
  }

  async function handleRetry() {
    setRetrying(true);
    try {
      const res = await fetch(`/api/tasks/${task.id}/retry`, {
        method: "POST",
      });
      if (res.ok) {
        refresh();
      }
    } finally {
      setRetrying(false);
    }
  }

  const isReviewing = task.status === "reviewing";
  const isRunning = task.status === "running" || task.status === "publishing";
  const hasContent = !!task.draft_title || !!task.draft_content;
  const hasResearchData = !!task.research_data && task.research_data.research_results?.length > 0;

  return (
    <div className="space-y-6">
      <Link
        href="/tasks"
        className="inline-flex items-center gap-1.5 text-sm text-muted-foreground hover:text-foreground transition-colors"
      >
        <ArrowLeft className="h-4 w-4" />
        返回任务列表
      </Link>

      {/* Header */}
      <div className="flex items-start justify-between">
        <div>
          <div className="flex items-center gap-3">
            <h1 className="text-2xl font-bold tracking-tight">
              {task.draft_title || task.description}
            </h1>
            <StatusBadge status={task.status} />
          </div>
          <p className="text-muted-foreground mt-1 text-sm">
            {task.account_id} · 创建于{" "}
            {new Date(task.created_at).toLocaleString("zh-CN")}
          </p>
        </div>
        <button
          onClick={handleDelete}
          disabled={deleting || isRunning}
          className="inline-flex items-center gap-1.5 px-3 py-2 rounded-lg text-sm text-red-600 hover:bg-red-50 transition-colors disabled:opacity-50"
        >
          <Trash2 className="h-4 w-4" />
          删除
        </button>
      </div>

      {/* Running indicator */}
      {isRunning && (
        <div className="bg-blue-50 border border-blue-200 rounded-xl px-5 py-4 flex items-center gap-3">
          <Loader2 className="h-5 w-5 text-blue-600 animate-spin" />
          <div>
            <p className="text-sm font-medium text-blue-800">
              {task.status === "running"
                ? "AI 正在研究和创作内容..."
                : "正在发布到小红书..."}
            </p>
            <p className="text-xs text-blue-600 mt-0.5">
              页面会自动刷新，请稍候
            </p>
          </div>
        </div>
      )}

      {/* Error */}
      {task.error && (
        <div className="bg-red-50 border border-red-200 rounded-xl px-5 py-4">
          <div className="flex items-start gap-3">
            <AlertTriangle className="h-5 w-5 text-red-600 flex-shrink-0 mt-0.5" />
            <div className="flex-1">
              <p className="text-sm font-medium text-red-800">任务失败</p>
              <p className="text-xs text-red-600 mt-1 font-mono whitespace-pre-wrap">
                {task.error}
              </p>
              {hasResearchData && (
                <p className="text-xs text-amber-700 mt-2 flex items-center gap-1">
                  <Sparkles className="h-3 w-3" />
                  检测到已有研究数据，重试时将自动复用（节省时间和 API 成本）
                </p>
              )}
            </div>
            <button
              onClick={handleRetry}
              disabled={retrying}
              className="inline-flex items-center gap-1.5 px-4 py-2 rounded-lg bg-blue-600 text-white text-sm font-medium hover:bg-blue-700 transition-colors disabled:opacity-50 flex-shrink-0"
            >
              {retrying ? (
                <><Loader2 className="h-4 w-4 animate-spin" />重试中...</>
              ) : (
                <><Check className="h-4 w-4" />智能重试</>
              )}
            </button>
          </div>
        </div>
      )}

      {/* Published URL */}
      {task.post_url && (
        <div className="bg-emerald-50 border border-emerald-200 rounded-xl px-5 py-4 flex items-center justify-between">
          <div>
            <p className="text-sm font-medium text-emerald-800">已成功发布</p>
            <p className="text-xs text-emerald-600 mt-0.5">内容已发布到小红书</p>
          </div>
          <a
            href={task.post_url}
            target="_blank"
            rel="noopener noreferrer"
            className="inline-flex items-center gap-1.5 px-3 py-2 rounded-lg bg-emerald-600 text-white text-sm hover:bg-emerald-700 transition-colors"
          >
            <ExternalLink className="h-4 w-4" />
            查看笔记
          </a>
        </div>
      )}

      {/* Safety issues */}
      {task.safety_issues && task.safety_issues.length > 0 && (
        <div className="bg-amber-50 border border-amber-200 rounded-xl px-5 py-4">
          <p className="text-sm font-medium text-amber-800 mb-2">
            安全检查提示
          </p>
          <ul className="space-y-1">
            {task.safety_issues.map((issue, i) => (
              <li key={i} className="text-xs text-amber-700 flex items-start gap-1.5">
                <AlertTriangle className="h-3.5 w-3.5 flex-shrink-0 mt-0.5" />
                {issue}
              </li>
            ))}
          </ul>
        </div>
      )}

      {/* Content preview / editor */}
      {hasContent && (
        <div className="bg-card rounded-xl border border-border overflow-hidden">
          <div className="px-6 py-4 border-b border-border flex items-center justify-between">
            <h2 className="font-semibold">
              {editing ? "编辑内容" : "内容预览"}
            </h2>
            {(isReviewing || task.status === "failed") && !editing && (
              <button
                onClick={() => setEditing(true)}
                className="inline-flex items-center gap-1.5 text-sm text-primary hover:underline"
              >
                <Pencil className="h-3.5 w-3.5" />
                编辑
              </button>
            )}
          </div>

          <div className="p-6 space-y-4">
            {/* Title */}
            <div>
              <label className="block text-xs font-medium text-muted-foreground mb-1.5 uppercase tracking-wider">
                标题
              </label>
              {editing ? (
                <input
                  type="text"
                  value={title}
                  onChange={(e) => setTitle(e.target.value)}
                  className="w-full px-3 py-2 rounded-lg border border-border bg-background text-sm font-medium focus:outline-none focus:ring-2 focus:ring-ring"
                />
              ) : (
                <p className="text-lg font-bold">{title || "(无标题)"}</p>
              )}
            </div>

            {/* Body */}
            <div>
              <label className="block text-xs font-medium text-muted-foreground mb-1.5 uppercase tracking-wider">
                正文
              </label>
              {editing ? (
                <textarea
                  value={content}
                  onChange={(e) => setContent(e.target.value)}
                  rows={12}
                  className="w-full px-4 py-3 rounded-lg border border-border bg-background text-sm leading-relaxed focus:outline-none focus:ring-2 focus:ring-ring resize-y"
                />
              ) : (
                <div className="text-sm leading-relaxed whitespace-pre-wrap bg-secondary/30 rounded-lg p-4">
                  {content || "(无内容)"}
                </div>
              )}
            </div>

            {/* Tags */}
            <div>
              <label className="block text-xs font-medium text-muted-foreground mb-1.5 uppercase tracking-wider">
                标签
              </label>
              {editing ? (
                <input
                  type="text"
                  value={tagsStr}
                  onChange={(e) => setTagsStr(e.target.value)}
                  placeholder="标签1, 标签2, 标签3"
                  className="w-full px-3 py-2 rounded-lg border border-border bg-background text-sm focus:outline-none focus:ring-2 focus:ring-ring"
                />
              ) : (
                <div className="flex flex-wrap gap-2">
                  {(task.draft_tags || []).map((tag) => (
                    <span
                      key={tag}
                      className="text-xs px-2.5 py-1 rounded-full bg-blue-50 text-blue-600"
                    >
                      #{tag}
                    </span>
                  ))}
                  {(!task.draft_tags || task.draft_tags.length === 0) && (
                    <span className="text-xs text-muted-foreground">(无标签)</span>
                  )}
                </div>
              )}
            </div>

            {/* Edit actions */}
            {editing && (
              <div className="flex gap-2 pt-2">
                <button
                  onClick={handleSaveEdits}
                  className="px-4 py-2 rounded-lg bg-primary text-primary-foreground text-sm font-medium hover:bg-primary/90 transition-colors"
                >
                  保存修改
                </button>
                <button
                  onClick={() => {
                    setEditing(false);
                    setTitle(task.draft_title || "");
                    setContent(task.draft_content || "");
                    setTagsStr((task.draft_tags || []).join(", "));
                  }}
                  className="px-4 py-2 rounded-lg border border-border text-sm text-muted-foreground hover:text-foreground transition-colors"
                >
                  取消
                </button>
              </div>
            )}
          </div>
        </div>
      )}

      {/* Research summary */}
      {task.research_summary && (
        <div className="bg-card rounded-xl border border-border p-6">
          <h2 className="font-semibold mb-3">研究摘要</h2>
          <p className="text-sm text-muted-foreground whitespace-pre-wrap leading-relaxed">
            {task.research_summary}
          </p>
        </div>
      )}

      {/* Image generation prompt */}
      {task.image_gen_prompt && (
        <div className="bg-card rounded-xl border border-violet-200 overflow-hidden">
          <div className="px-6 py-4 border-b border-violet-100 bg-violet-50 flex items-center justify-between">
            <div className="flex items-center gap-2">
              <Sparkles className="h-4 w-4 text-violet-600" />
              <h2 className="font-semibold text-violet-900">策略优化师推荐配图 Prompt</h2>
            </div>
            <button
              onClick={handleCopyPrompt}
              className="inline-flex items-center gap-1.5 px-3 py-1.5 rounded-lg text-sm font-medium text-violet-700 hover:bg-violet-100 transition-colors"
            >
              {promptCopied ? (
                <><CheckCheck className="h-3.5 w-3.5" />已复制</>
              ) : (
                <><Copy className="h-3.5 w-3.5" />复制 Prompt</>
              )}
            </button>
          </div>
          <div className="p-5">
            <p className="text-xs text-violet-500 mb-2">可直接粘贴到 DALL-E 3 / Midjourney / 其他图片生成工具</p>
            <div className="font-mono text-sm bg-violet-50 border border-violet-100 rounded-lg px-4 py-3 leading-relaxed text-violet-900 whitespace-pre-wrap">
              {task.image_gen_prompt}
            </div>
          </div>
        </div>
      )}

      {/* Approve / Reject actions */}
      {isReviewing && !editing && (
        <div className="flex items-center gap-3 p-5 bg-amber-50 border border-amber-200 rounded-xl">
          <div className="flex-1">
            <p className="text-sm font-medium text-amber-800">等待审核</p>
            <p className="text-xs text-amber-600 mt-0.5">
              审核通过后将发布到小红书。你可以先编辑内容再审核。
            </p>
          </div>
          <button
            onClick={handleReject}
            disabled={rejecting}
            className="inline-flex items-center gap-1.5 px-4 py-2.5 rounded-lg border border-red-300 text-sm font-medium text-red-700 hover:bg-red-50 transition-colors disabled:opacity-50"
          >
            <X className="h-4 w-4" />
            {rejecting ? "处理中..." : "拒绝"}
          </button>
          <button
            onClick={handleApprove}
            disabled={approving}
            className="inline-flex items-center gap-1.5 px-5 py-2.5 rounded-lg bg-emerald-600 text-sm font-medium text-white hover:bg-emerald-700 transition-colors disabled:opacity-50"
          >
            <Check className="h-4 w-4" />
            {approving ? "发布中..." : "审核通过并发布"}
          </button>
        </div>
      )}

      {/* Retry for failed tasks */}
      {task.status === "failed" && hasContent && !editing && (
        <div className="flex items-center gap-3 p-5 bg-red-50 border border-red-200 rounded-xl">
          <div className="flex-1">
            <p className="text-sm font-medium text-red-800">发布失败</p>
            <p className="text-xs text-red-600 mt-0.5">
              你可以编辑内容后重新发布，或删除此任务。
            </p>
          </div>
          <button
            onClick={handleApprove}
            disabled={approving}
            className="inline-flex items-center gap-1.5 px-5 py-2.5 rounded-lg bg-emerald-600 text-sm font-medium text-white hover:bg-emerald-700 transition-colors disabled:opacity-50"
          >
            <Check className="h-4 w-4" />
            {approving ? "发布中..." : "重新发布"}
          </button>
        </div>
      )}

      {/* Task metadata */}
      <div className="bg-secondary/50 rounded-xl p-4 text-xs text-muted-foreground space-y-1">
        <p>任务 ID: {task.id}</p>
        <p>描述: {task.description}</p>
        <p>最后更新: {new Date(task.updated_at).toLocaleString("zh-CN")}</p>
      </div>
    </div>
  );
}
