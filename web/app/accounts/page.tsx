import Link from "next/link";
import { readAllAccounts } from "@/lib/yaml-utils";
import { Settings, ChevronRight } from "lucide-react";

export const dynamic = "force-dynamic";

export default function AccountsPage() {
  const accounts = readAllAccounts();

  return (
    <div className="space-y-6">
      <div>
        <h1 className="text-2xl font-bold tracking-tight">账号管理</h1>
        <p className="text-muted-foreground mt-1">管理 Prompt、模型版本和账号配置</p>
      </div>

      <div className="grid gap-4">
        {accounts.map((acc) => (
          <Link
            key={acc.account_id}
            href={`/accounts/${acc.account_id}`}
            className="bg-card rounded-xl border border-border p-6 hover:border-primary/30 hover:shadow-sm transition-all group"
          >
            <div className="flex items-start justify-between">
              <div className="flex items-start gap-4">
                <div className="h-12 w-12 rounded-full bg-primary/10 text-primary flex items-center justify-center font-bold text-lg flex-shrink-0">
                  {acc.persona?.name?.[0] || "?"}
                </div>
                <div className="space-y-1">
                  <div className="flex items-center gap-3">
                    <h3 className="font-semibold">{acc.persona?.name || acc.account_id}</h3>
                    <span className="text-xs px-2 py-0.5 rounded bg-secondary text-muted-foreground">
                      {acc.account_id}
                    </span>
                  </div>
                  <p className="text-sm text-muted-foreground">{acc.persona?.description}</p>
                  <div className="flex items-center gap-4 mt-2">
                    <span className="text-xs text-muted-foreground">
                      赛道: <span className="text-foreground font-medium">{acc.track}</span>
                    </span>
                    <span className="text-xs text-muted-foreground">
                      主模型: <span className="text-foreground font-medium">{acc.models?.primary}</span>
                    </span>
                    <span className="text-xs text-muted-foreground">
                      Fallback: <span className="text-foreground font-medium">{acc.models?.fallback}</span>
                    </span>
                    <span className="text-xs text-muted-foreground">
                      审核: <span className="text-foreground font-medium">{acc.schedule?.review_mode}</span>
                    </span>
                  </div>
                  <div className="flex flex-wrap gap-1.5 mt-2">
                    {acc.keywords?.slice(0, 6).map((kw) => (
                      <span
                        key={kw}
                        className="text-xs px-2 py-0.5 rounded-full bg-blue-50 text-blue-600"
                      >
                        {kw}
                      </span>
                    ))}
                  </div>
                </div>
              </div>
              <div className="flex items-center gap-1 text-muted-foreground group-hover:text-primary transition-colors">
                <Settings className="h-4 w-4" />
                <ChevronRight className="h-4 w-4" />
              </div>
            </div>
          </Link>
        ))}
      </div>
    </div>
  );
}
