import Link from "next/link";
import { readAllAccounts } from "@/lib/yaml-utils";
import { listTasks } from "@/lib/db";
import { StatusBadge } from "@/components/status-badge";
import { Users, ListTodo, Sparkles, TrendingUp } from "lucide-react";

export const dynamic = "force-dynamic";

export default function Dashboard() {
  const accounts = readAllAccounts();
  const tasks = listTasks();
  const recentTasks = tasks.slice(0, 5);

  const stats = {
    accounts: accounts.length,
    totalTasks: tasks.length,
    reviewing: tasks.filter((t) => t.status === "reviewing").length,
    published: tasks.filter((t) => t.status === "published").length,
  };

  return (
    <div className="space-y-8">
      <div>
        <h1 className="text-2xl font-bold tracking-tight">仪表盘</h1>
        <p className="text-muted-foreground mt-1">小红书自动化管理总览</p>
      </div>

      {/* Stats cards */}
      <div className="grid grid-cols-4 gap-4">
        {[
          { label: "账号总数", value: stats.accounts, icon: Users, color: "text-blue-600" },
          { label: "总任务数", value: stats.totalTasks, icon: ListTodo, color: "text-slate-600" },
          { label: "待审核", value: stats.reviewing, icon: Sparkles, color: "text-amber-600" },
          { label: "已发布", value: stats.published, icon: TrendingUp, color: "text-emerald-600" },
        ].map((stat) => (
          <div
            key={stat.label}
            className="bg-card rounded-xl border border-border p-5 flex items-start justify-between"
          >
            <div>
              <p className="text-sm text-muted-foreground">{stat.label}</p>
              <p className="text-3xl font-bold mt-1">{stat.value}</p>
            </div>
            <stat.icon className={`h-5 w-5 ${stat.color} mt-1`} />
          </div>
        ))}
      </div>

      {/* Accounts overview */}
      <div className="bg-card rounded-xl border border-border">
        <div className="px-6 py-4 border-b border-border flex items-center justify-between">
          <h2 className="font-semibold">账号概览</h2>
          <Link href="/accounts" className="text-sm text-primary hover:underline">
            管理全部
          </Link>
        </div>
        <div className="divide-y divide-border">
          {accounts.map((acc) => (
            <Link
              key={acc.account_id}
              href={`/accounts/${acc.account_id}`}
              className="flex items-center justify-between px-6 py-4 hover:bg-secondary/50 transition-colors"
            >
              <div className="flex items-center gap-4">
                <div className="h-10 w-10 rounded-full bg-primary/10 text-primary flex items-center justify-center font-bold text-sm">
                  {acc.persona?.name?.[0] || "?"}
                </div>
                <div>
                  <p className="font-medium text-sm">{acc.persona?.name || acc.account_id}</p>
                  <p className="text-xs text-muted-foreground">{acc.track} · {acc.models?.primary}</p>
                </div>
              </div>
              <span className="text-xs px-2.5 py-1 rounded-full bg-secondary text-muted-foreground">
                {acc.schedule?.review_mode || "review"}
              </span>
            </Link>
          ))}
        </div>
      </div>

      {/* Recent tasks */}
      <div className="bg-card rounded-xl border border-border">
        <div className="px-6 py-4 border-b border-border flex items-center justify-between">
          <h2 className="font-semibold">最近任务</h2>
          <Link href="/tasks" className="text-sm text-primary hover:underline">
            查看全部
          </Link>
        </div>
        {recentTasks.length === 0 ? (
          <div className="px-6 py-12 text-center text-muted-foreground text-sm">
            还没有任务。
            <Link href="/tasks" className="text-primary hover:underline ml-1">
              创建第一个任务
            </Link>
          </div>
        ) : (
          <div className="divide-y divide-border">
            {recentTasks.map((task) => (
              <Link
                key={task.id}
                href={`/tasks/${task.id}`}
                className="flex items-center justify-between px-6 py-4 hover:bg-secondary/50 transition-colors"
              >
                <div>
                  <p className="font-medium text-sm">{task.draft_title || task.description}</p>
                  <p className="text-xs text-muted-foreground mt-0.5">
                    {task.account_id} · {new Date(task.created_at).toLocaleDateString("zh-CN")}
                  </p>
                </div>
                <StatusBadge status={task.status} />
              </Link>
            ))}
          </div>
        )}
      </div>
    </div>
  );
}
