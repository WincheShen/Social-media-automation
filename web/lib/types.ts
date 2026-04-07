// Shared TypeScript types for the admin dashboard

export interface AccountConfig {
  account_id: string;
  platform: string;
  persona: {
    name: string;
    description: string;
    tone: string;
    audience: string;
    system_prompt: string;
  };
  track: string;
  keywords: string[];
  models: {
    data_collector?: string;
    logic_analyst?: string;
    copywriter?: string;
    strategist?: string;
    fallback: string;
    image_gen?: string | null;
    // Legacy fields (backward compat)
    primary?: string;
  };
  visual_style: {
    color_scheme: string[];
    font: string;
    template: string;
    font_size?: string;
    contrast?: string;
  };
  xhs_cli?: {
    account: string;
    port: number;
  };
  schedule: {
    post_windows: string[];
    max_daily_posts: number;
    review_mode: string;
  };
  sensitive_words_extra?: string[];
}

export type TaskStatus =
  | "created"
  | "running"
  | "reviewing"
  | "approved"
  | "publishing"
  | "published"
  | "rejected"
  | "failed";

export interface Task {
  id: string;
  account_id: string;
  description: string;
  status: TaskStatus;
  created_at: string;
  updated_at: string;
  // Generated content (populated after AI runs nodes 1-4)
  draft_title?: string;
  draft_content?: string;
  draft_tags?: string[];
  research_summary?: string;
  research_data?: any;  // Full research results for retry (research_results, data_sources, etc.)
  safety_issues?: string[];
  image_gen_prompt?: string;  // Strategist's recommended image generation prompt
  // Publish result (populated after nodes 6-8)
  post_url?: string;
  error?: string;
}

export interface ModelInfo {
  id: string;
  display_name: string;
  provider: "google" | "anthropic" | "openai";
}

export const AVAILABLE_MODELS: ModelInfo[] = [
  { id: "gemini-2.5-pro", display_name: "Gemini 2.5 Pro", provider: "google" },
  { id: "gemini-2.5-flash", display_name: "Gemini 2.5 Flash", provider: "google" },
  { id: "gemini-2.0-flash", display_name: "Gemini 2.0 Flash", provider: "google" },
  { id: "claude-3.7-opus", display_name: "Claude 3.7 Opus", provider: "anthropic" },
  { id: "claude-3.7-sonnet", display_name: "Claude 3.7 Sonnet", provider: "anthropic" },
  { id: "gpt-4o", display_name: "GPT-4o", provider: "openai" },
  { id: "gpt-4o-mini", display_name: "GPT-4o Mini", provider: "openai" },
  { id: "gpt-5.3-chat", display_name: "GPT-5.3 Chat (Azure)", provider: "openai" },
];

export const MODEL_ROLES = [
  { key: "data_collector", label: "Data Collector", desc: "数据采集", hint: "搜索强、窗口大" },
  { key: "logic_analyst", label: "Logic Analyst", desc: "深度分析", hint: "逻辑严密、分析准" },
  { key: "copywriter", label: "Copywriter", desc: "拟人创作", hint: "拒绝AI腔、文笔细腻" },
  { key: "strategist", label: "Strategist", desc: "策略优化", hint: "数据处理强、工具稳定" },
] as const;
