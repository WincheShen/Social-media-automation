"use client";

import { useState } from "react";
import { useRouter } from "next/navigation";
import type { AccountConfig } from "@/lib/types";
import { AVAILABLE_MODELS, MODEL_ROLES, IMAGE_GEN_MODELS } from "@/lib/types";
import { Save, RotateCcw, ArrowLeft } from "lucide-react";
import Link from "next/link";

export function AccountEditor({ account }: { account: AccountConfig }) {
  const router = useRouter();
  const [saving, setSaving] = useState(false);
  const [saved, setSaved] = useState(false);

  const [systemPrompt, setSystemPrompt] = useState(
    account.persona?.system_prompt || ""
  );
  const [roleModels, setRoleModels] = useState<Record<string, string>>({
    data_collector: account.models?.data_collector || account.models?.primary || "gemini-2.5-pro",
    logic_analyst: account.models?.logic_analyst || account.models?.primary || "claude-3.7-opus",
    copywriter: account.models?.copywriter || account.models?.primary || "claude-3.7-sonnet",
    strategist: account.models?.strategist || account.models?.primary || "gpt-4o",
  });
  const [fallbackModel, setFallbackModel] = useState(
    account.models?.fallback || "gemini-2.5-flash"
  );
  const [imageGenModel, setImageGenModel] = useState(
    account.models?.image_gen || ""
  );
  const [keywords, setKeywords] = useState(
    (account.keywords || []).join(", ")
  );
  const [personaName, setPersonaName] = useState(
    account.persona?.name || ""
  );
  const [personaDesc, setPersonaDesc] = useState(
    account.persona?.description || ""
  );
  const [tone, setTone] = useState(account.persona?.tone || "");
  const [audience, setAudience] = useState(account.persona?.audience || "");
  const [reviewMode, setReviewMode] = useState(
    account.schedule?.review_mode || "review"
  );

  const isFinance = account.track === "finance";

  async function handleSave() {
    setSaving(true);
    setSaved(false);
    try {
      const body = {
        persona: {
          ...account.persona,
          name: personaName,
          description: personaDesc,
          tone,
          audience,
          system_prompt: systemPrompt,
        },
        models: {
          ...account.models,
          data_collector: roleModels.data_collector,
          logic_analyst: roleModels.logic_analyst,
          copywriter: roleModels.copywriter,
          strategist: roleModels.strategist,
          fallback: fallbackModel,
          image_gen: imageGenModel || null,
        },
        keywords: keywords
          .split(",")
          .map((k) => k.trim())
          .filter(Boolean),
        schedule: {
          ...account.schedule,
          review_mode: isFinance ? "review" : reviewMode,
        },
      };

      const res = await fetch(`/api/accounts/${account.account_id}`, {
        method: "PUT",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(body),
      });

      if (res.ok) {
        setSaved(true);
        setTimeout(() => setSaved(false), 3000);
        router.refresh();
      }
    } finally {
      setSaving(false);
    }
  }

  return (
    <div className="space-y-6">
      <Link
        href="/accounts"
        className="inline-flex items-center gap-1.5 text-sm text-muted-foreground hover:text-foreground transition-colors"
      >
        <ArrowLeft className="h-4 w-4" />
        返回账号列表
      </Link>

      {/* Basic Info */}
      <section className="bg-card rounded-xl border border-border p-6 space-y-4">
        <h2 className="font-semibold text-lg">基本信息</h2>
        <div className="grid grid-cols-2 gap-4">
          <div>
            <label className="block text-sm font-medium mb-1.5">人设名称</label>
            <input
              type="text"
              value={personaName}
              onChange={(e) => setPersonaName(e.target.value)}
              className="w-full px-3 py-2 rounded-lg border border-border bg-background text-sm focus:outline-none focus:ring-2 focus:ring-ring"
            />
          </div>
          <div>
            <label className="block text-sm font-medium mb-1.5">目标受众</label>
            <input
              type="text"
              value={audience}
              onChange={(e) => setAudience(e.target.value)}
              className="w-full px-3 py-2 rounded-lg border border-border bg-background text-sm focus:outline-none focus:ring-2 focus:ring-ring"
            />
          </div>
          <div className="col-span-2">
            <label className="block text-sm font-medium mb-1.5">简介</label>
            <input
              type="text"
              value={personaDesc}
              onChange={(e) => setPersonaDesc(e.target.value)}
              className="w-full px-3 py-2 rounded-lg border border-border bg-background text-sm focus:outline-none focus:ring-2 focus:ring-ring"
            />
          </div>
          <div>
            <label className="block text-sm font-medium mb-1.5">语气风格</label>
            <input
              type="text"
              value={tone}
              onChange={(e) => setTone(e.target.value)}
              className="w-full px-3 py-2 rounded-lg border border-border bg-background text-sm focus:outline-none focus:ring-2 focus:ring-ring"
            />
          </div>
          <div>
            <label className="block text-sm font-medium mb-1.5">关键词（逗号分隔）</label>
            <input
              type="text"
              value={keywords}
              onChange={(e) => setKeywords(e.target.value)}
              className="w-full px-3 py-2 rounded-lg border border-border bg-background text-sm focus:outline-none focus:ring-2 focus:ring-ring"
            />
          </div>
        </div>
      </section>

      {/* System Prompt */}
      <section className="bg-card rounded-xl border border-border p-6 space-y-4">
        <div className="flex items-center justify-between">
          <h2 className="font-semibold text-lg">System Prompt</h2>
          <span className="text-xs text-muted-foreground">
            {systemPrompt.length} 字符
          </span>
        </div>
        <textarea
          value={systemPrompt}
          onChange={(e) => setSystemPrompt(e.target.value)}
          rows={10}
          className="w-full px-4 py-3 rounded-lg border border-border bg-background text-sm font-mono leading-relaxed focus:outline-none focus:ring-2 focus:ring-ring resize-y"
          placeholder="输入此账号的 System Prompt..."
        />
      </section>

      {/* Model Selection — Per-role routing */}
      <section className="bg-card rounded-xl border border-border p-6 space-y-4">
        <div>
          <h2 className="font-semibold text-lg">模型路由配置</h2>
          <p className="text-xs text-muted-foreground mt-1">
            不同工作流节点使用不同模型，发挥各模型优势，减少 AI 味
          </p>
        </div>
        <div className="grid grid-cols-2 gap-4">
          {MODEL_ROLES.map((role) => (
            <div key={role.key}>
              <label className="block text-sm font-medium mb-1">
                {role.desc}
                <span className="ml-1.5 text-xs font-normal text-muted-foreground">
                  {role.label}
                </span>
              </label>
              <select
                value={roleModels[role.key] || ""}
                onChange={(e) =>
                  setRoleModels((prev) => ({ ...prev, [role.key]: e.target.value }))
                }
                className="w-full px-3 py-2 rounded-lg border border-border bg-background text-sm focus:outline-none focus:ring-2 focus:ring-ring"
              >
                {AVAILABLE_MODELS.map((m) => (
                  <option key={m.id} value={m.id}>
                    {m.display_name} ({m.provider})
                  </option>
                ))}
              </select>
              <p className="text-xs text-muted-foreground mt-1">{role.hint}</p>
            </div>
          ))}
        </div>
        <div className="pt-2 border-t border-border">
          <label className="block text-sm font-medium mb-1.5">Fallback 模型</label>
          <select
            value={fallbackModel}
            onChange={(e) => setFallbackModel(e.target.value)}
            className="w-64 px-3 py-2 rounded-lg border border-border bg-background text-sm focus:outline-none focus:ring-2 focus:ring-ring"
          >
            {AVAILABLE_MODELS.map((m) => (
              <option key={m.id} value={m.id}>
                {m.display_name} ({m.provider})
              </option>
            ))}
          </select>
          <p className="text-xs text-muted-foreground mt-1">任何节点失败时的备选模型</p>
        </div>
        <div className="pt-2 border-t border-border">
          <label className="block text-sm font-medium mb-1.5">配图生成模型</label>
          <select
            value={imageGenModel}
            onChange={(e) => setImageGenModel(e.target.value)}
            className="w-64 px-3 py-2 rounded-lg border border-border bg-background text-sm focus:outline-none focus:ring-2 focus:ring-ring"
          >
            <option value="">不自动生成</option>
            {IMAGE_GEN_MODELS.map((m) => (
              <option key={m.id} value={m.id}>
                {m.display_name} ({m.provider})
              </option>
            ))}
          </select>
          <p className="text-xs text-muted-foreground mt-1">
            auto 模式下自动生成配图；review 模式可在审核页手动选择
          </p>
        </div>
      </section>

      {/* Review Mode */}
      <section className="bg-card rounded-xl border border-border p-6 space-y-4">
        <h2 className="font-semibold text-lg">审核模式</h2>
        {isFinance && (
          <p className="text-sm text-amber-600 bg-amber-50 px-3 py-2 rounded-lg">
            金融账号强制 review 模式，无法切换为 auto
          </p>
        )}
        <div className="flex gap-3">
          {["review", "auto"].map((mode) => (
            <button
              key={mode}
              onClick={() => !isFinance && setReviewMode(mode)}
              disabled={isFinance && mode === "auto"}
              className={`px-4 py-2 rounded-lg text-sm font-medium border transition-colors ${
                reviewMode === mode
                  ? "bg-primary text-primary-foreground border-primary"
                  : "bg-background border-border text-muted-foreground hover:border-primary/30"
              } ${isFinance && mode === "auto" ? "opacity-40 cursor-not-allowed" : ""}`}
            >
              {mode === "review" ? "人工审核" : "自动发布"}
            </button>
          ))}
        </div>
      </section>

      {/* Actions */}
      <div className="flex items-center gap-3 pt-2">
        <button
          onClick={handleSave}
          disabled={saving}
          className="inline-flex items-center gap-2 px-5 py-2.5 rounded-lg bg-primary text-primary-foreground text-sm font-medium hover:bg-primary/90 transition-colors disabled:opacity-50"
        >
          <Save className="h-4 w-4" />
          {saving ? "保存中..." : "保存配置"}
        </button>
        <button
          onClick={() => router.refresh()}
          className="inline-flex items-center gap-2 px-4 py-2.5 rounded-lg border border-border text-sm text-muted-foreground hover:text-foreground hover:border-foreground/20 transition-colors"
        >
          <RotateCcw className="h-4 w-4" />
          重置
        </button>
        {saved && (
          <span className="text-sm text-emerald-600 font-medium">
            已保存
          </span>
        )}
      </div>

      {/* Metadata */}
      <section className="bg-secondary/50 rounded-xl p-4 text-xs text-muted-foreground space-y-1">
        <p>账号 ID: {account.account_id}</p>
        <p>平台: {account.platform}</p>
        <p>赛道: {account.track}</p>
        <p>CDP 端口: {account.xhs_cli?.port || "未配置"}</p>
      </section>
    </div>
  );
}
