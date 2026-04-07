import Link from "next/link";
import { readAllAccounts } from "@/lib/yaml-utils";
import { listTasks, getDashboardStats, getEngagementStats } from "@/lib/db";
import { StatusBadge } from "@/components/status-badge";
import { 
  Users, ListTodo, Sparkles, TrendingUp, 
  Heart, MessageCircle, Calendar, AlertCircle,
  Activity, Clock
} from "lucide-react";

export const dynamic = "force-dynamic";

export default function Dashboard() {
  const accounts = readAllAccounts();
  const tasks = listTasks();
  const recentTasks = tasks.slice(0, 5);
  const dashboardStats = getDashboardStats();
  const engagementStats = getEngagementStats();

  const stats = {
    accounts: accounts.length,
    totalTasks: dashboardStats.totalTasks,
    todayTasks: dashboardStats.todayTasks,
    reviewing: dashboardStats.reviewing,
    published: dashboardStats.published,
    failed: dashboardStats.failed,
    running: dashboardStats.running,
  };

  return (
    <div className="space-y-8">
      <div>
        <h1 className="text-2xl font-bold tracking-tight">仪表盘</h1>
        <p className="text-muted-foreground mt-1">小红书自动化管理总览</p>
      </div>

      {/* Stats cards - Row 1: Tasks */}
      <div className="grid grid-cols-2 md:grid-cols-4 lg:grid-cols-6 gap-4">
        {[
          { label: "账号总数", value: stats.accounts, icon: Users, color: "text-blue-600" },
          { label: "总任务数", value: stats.totalTasks, icon: ListTodo, color: "text-slate-600" },
          { label: "今日任务", value: stats.todayTasks, icon: Calendar, color: "text-purple-600" },
          { label: "待审核", value: stats.reviewing, icon: Sparkles, color: "text-amber-600" },
          { label: "已发布", value: stats.published, icon: TrendingUp, color: "text-emerald-600" },
          { label: "运行中", value: stats.running, icon: Activity, color: "text-cyan-600" },
        ].map((stat) => (
          <div
            key={stat.label}
            className="bg-card rounded-xl border border-border p-4 flex items-start justify-between"
          >
            <div>
              <p className="text-xs text-muted-foreground">{stat.label}</p>
              <p className="text-2xl font-bold mt-1">{stat.value}</p>
            </div>
            <stat.icon className={`h-4 w-4 ${stat.color} mt-1`} />
          </div>
        ))}
      </div>

      {/* Stats cards - Row 2: Engagement */}
      <div className="grid grid-cols-2 md:grid-cols-4 gap-4">
        {[
          { label: "总点赞数", value: engagementStats.totalLikes, icon: Heart, color: "text-red-500" },
          { label: "总评论数", value: engagementStats.totalComments, icon: MessageCircle, color: "text-blue-500" },
          { label: "今日点赞", value: engagementStats.todayLikes, icon: Heart, color: "text-pink-500" },
          { label: "今日评论", value: engagementStats.todayComments, icon: MessageCircle, color: "text-indigo-500" },
        ].map((stat) => (
          <div
            key={stat.label}
            className="bg-card rounded-xl border border-border p-4 flex items-start justify-between"
          >
            <div>
              <p className="text-xs text-muted-foreground">{stat.label}</p>
              <p className="text-2xl font-bold mt-1">{stat.value}</p>
            </div>
            <stat.icon className={`h-4 w-4 ${stat.color} mt-1`} />
          </div>
        ))}
      </div>

      {/* 7-day trend */}
      {dashboardStats.recentTrend.length > 0 && (
        <div className="bg-card rounded-xl border border-border p-6">
          <h2 className="font-semibold mb-4">近7天趋势</h2>
          <div className="flex items-end gap-2 h-32">
            {dashboardStats.recentTrend.slice().reverse().map((day) => {
              const maxCount = Math.max(...dashboardStats.recentTrend.map(d => d.count), 1);
              const height = (day.count / maxCount) * 100;
              const publishedHeight = (day.published / maxCount) * 100;
              return (
                <div key={day.date} className="flex-1 flex flex-col items-center gap-1">
                  <div className="w-full flex flex-col items-center" style={{ height: '100px' }}>
                    <div className="w-full flex flex-col justify-end h-full">
                      <div 
                        className="w-full bg-primary/20 rounded-t relative"
                        style={{ height: `${height}%` }}
                      >
                        <div 
                          className="absolute bottom-0 w-full bg-primary rounded-t"
                          style={{ height: `${publishedHeight}%` }}
                        />
                      </div>
                    </div>
                  </div>
                  <span className="text-xs text-muted-foreground">
                    {new Date(day.date).toLocaleDateString("zh-CN", { month: "numeric", day: "numeric" })}
                  </span>
                  <span className="text-xs font-medium">{day.count}</span>
                </div>
              );
            })}
          </div>
          <div className="flex items-center gap-4 mt-4 text-xs text-muted-foreground">
            <div className="flex items-center gap-1">
              <div className="w-3 h-3 bg-primary/20 rounded" />
              <span>总任务</span>
            </div>
            <div className="flex items-center gap-1">
              <div className="w-3 h-3 bg-primary rounded" />
              <span>已发布</span>
            </div>
          </div>
        </div>
      )}

      {/* Accounts overview with stats */}
      <div className="bg-card rounded-xl border border-border">
        <div className="px-6 py-4 border-b border-border flex items-center justify-between">
          <h2 className="font-semibold">账号概览</h2>
          <Link href="/accounts" className="text-sm text-primary hover:underline">
            管理全部
          </Link>
        </div>
        <div className="divide-y divide-border">
          {accounts.map((acc) => {
            const accountStats = dashboardStats.byAccount[acc.account_id] || { total: 0, published: 0, reviewing: 0 };
            const accountEngagement = engagementStats.byAccount[acc.account_id] || { likes: 0, comments: 0 };
            return (
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
                <div className="flex items-center gap-6">
                  <div className="text-right">
                    <p className="text-xs text-muted-foreground">任务</p>
                    <p className="text-sm font-medium">{accountStats.total} <span className="text-emerald-600">({accountStats.published})</span></p>
                  </div>
                  <div className="text-right">
                    <p className="text-xs text-muted-foreground">互动</p>
                    <p className="text-sm font-medium">
                      <span className="text-red-500">{accountEngagement.likes}</span>
                      {" / "}
                      <span className="text-blue-500">{accountEngagement.comments}</span>
                    </p>
                  </div>
                  <span className="text-xs px-2.5 py-1 rounded-full bg-secondary text-muted-foreground">
                    {acc.schedule?.review_mode || "review"}
                  </span>
                </div>
              </Link>
            );
          })}
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
