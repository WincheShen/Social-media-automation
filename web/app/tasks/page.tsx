"use client";

import { useState, useEffect, useCallback } from "react";
import Link from "next/link";
import { StatusBadge } from "@/components/status-badge";
import type { Task, AccountConfig } from "@/lib/types";
import { Plus, RefreshCw } from "lucide-react";

export default function TasksPage() {
  const [tasks, setTasks] = useState<Task[]>([]);
  const [accounts, setAccounts] = useState<AccountConfig[]>([]);
  const [loading, setLoading] = useState(true);
  const [creating, setCreating] = useState(false);
  const [selectedAccount, setSelectedAccount] = useState("");
  const [description, setDescription] = useState("");

  const fetchData = useCallback(async () => {
    const [tasksRes, accountsRes] = await Promise.all([
      fetch("/api/tasks"),
      fetch("/api/accounts"),
    ]);
    setTasks(await tasksRes.json());
    setAccounts(await accountsRes.json());
    setLoading(false);
  }, []);

  useEffect(() => {
    fetchData();
    // Auto-refresh every 5s for running tasks
    const interval = setInterval(fetchData, 5000);
    return () => clearInterval(interval);
  }, [fetchData]);

  async function handleCreate(e: React.FormEvent) {
    e.preventDefault();
    if (!selectedAccount || !description.trim()) return;

    setCreating(true);
    try {
      const res = await fetch("/api/tasks", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          account_id: selectedAccount,
          description: description.trim(),
        }),
      });
      if (res.ok) {
        setDescription("");
        fetchData();
      }
    } finally {
      setCreating(false);
    }
  }

  return (
    <div className="space-y-6">
      <div>
        <h1 className="text-2xl font-bold tracking-tight">任务管理</h1>
        <p className="text-muted-foreground mt-1">
          创建内容任务、审核 AI 生成的内容、发布到小红书
        </p>
      </div>

      {/* Create Task Form */}
      <form
        onSubmit={handleCreate}
        className="bg-card rounded-xl border border-border p-6 space-y-4"
      >
        <h2 className="font-semibold">创建新任务</h2>
        <div className="flex gap-3">
          <select
            value={selectedAccount}
            onChange={(e) => setSelectedAccount(e.target.value)}
            className="w-48 px-3 py-2 rounded-lg border border-border bg-background text-sm focus:outline-none focus:ring-2 focus:ring-ring"
          >
            <option value="">选择账号...</option>
            {accounts.map((acc) => (
              <option key={acc.account_id} value={acc.account_id}>
                {acc.persona?.name || acc.account_id}
              </option>
            ))}
          </select>
          <input
            type="text"
            value={description}
            onChange={(e) => setDescription(e.target.value)}
            placeholder="输入任务描述，如：分析 2026 上海体育中考新规的变化和备考建议"
            className="flex-1 px-3 py-2 rounded-lg border border-border bg-background text-sm focus:outline-none focus:ring-2 focus:ring-ring"
          />
          <button
            type="submit"
            disabled={creating || !selectedAccount || !description.trim()}
            className="inline-flex items-center gap-2 px-4 py-2 rounded-lg bg-primary text-primary-foreground text-sm font-medium hover:bg-primary/90 transition-colors disabled:opacity-50"
          >
            <Plus className="h-4 w-4" />
            {creating ? "创建中..." : "创建"}
          </button>
        </div>
        <p className="text-xs text-muted-foreground">
          创建后 AI 会自动执行研究 → 创作 → 安全检查，完成后进入「待审核」状态
        </p>
      </form>

      {/* Task List */}
      <div className="bg-card rounded-xl border border-border">
        <div className="px-6 py-4 border-b border-border flex items-center justify-between">
          <h2 className="font-semibold">
            全部任务 ({tasks.length})
          </h2>
          <button
            onClick={fetchData}
            className="inline-flex items-center gap-1.5 text-sm text-muted-foreground hover:text-foreground transition-colors"
          >
            <RefreshCw className="h-3.5 w-3.5" />
            刷新
          </button>
        </div>

        {loading ? (
          <div className="px-6 py-12 text-center text-muted-foreground text-sm">
            加载中...
          </div>
        ) : tasks.length === 0 ? (
          <div className="px-6 py-12 text-center text-muted-foreground text-sm">
            暂无任务，使用上方表单创建第一个任务
          </div>
        ) : (
          <div className="divide-y divide-border">
            {tasks.map((task) => (
              <Link
                key={task.id}
                href={`/tasks/${task.id}`}
                className="flex items-center justify-between px-6 py-4 hover:bg-secondary/50 transition-colors"
              >
                <div className="flex-1 min-w-0">
                  <div className="flex items-center gap-3">
                    <p className="font-medium text-sm truncate">
                      {task.draft_title || task.description}
                    </p>
                  </div>
                  <p className="text-xs text-muted-foreground mt-0.5">
                    {task.account_id} ·{" "}
                    {new Date(task.created_at).toLocaleString("zh-CN")}
                  </p>
                </div>
                <div className="flex-shrink-0 ml-4">
                  <StatusBadge status={task.status} />
                </div>
              </Link>
            ))}
          </div>
        )}
      </div>
    </div>
  );
}
