# 社交媒体自动发布系统 — 架构设计文档

> 版本：v0.1.0 | 更新日期：2026-03-25

---

## 1. 系统全局架构

```
┌─────────────────────────────────────────────────────────────────────┐
│                        Social Media Automation Agent                │
├─────────────────────────────────────────────────────────────────────┤
│                                                                     │
│  ┌───────────┐    ┌──────────────────────────────────────────────┐  │
│  │  CLI /    │    │            LangGraph Orchestrator             │  │
│  │  Scheduler│───▶│                                              │  │
│  └───────────┘    │  ┌─────────┐  ┌──────────┐  ┌───────────┐   │  │
│                   │  │ Node 1  │─▶│ Node 2   │─▶│ Node 3    │   │  │
│                   │  │ Persona │  │ Research  │  │ Creative  │   │  │
│                   │  │ Loader  │  │ Engine    │  │ Engine    │   │  │
│                   │  └─────────┘  └──────────┘  └─────┬─────┘   │  │
│                   │                                    │         │  │
│                   │  ┌─────────┐  ┌──────────┐  ┌─────▼─────┐   │  │
│                   │  │ Node 8  │◀─│ Node 7   │◀─│ Node 4    │   │  │
│                   │  │Feedback │  │ Monitor  │  │ Safety    │   │  │
│                   │  │& Memory │  │          │  │ Check     │   │  │
│                   │  └─────────┘  └──────────┘  └─────┬─────┘   │  │
│                   │                                    │         │  │
│                   │               ┌──────────┐  ┌─────▼─────┐   │  │
│                   │               │ Node 6   │◀─│ Node 5    │   │  │
│                   │               │ Execute  │  │ Review    │   │  │
│                   │               │ (Browser)│  │ Gate      │   │  │
│                   │               └──────────┘  └───────────┘   │  │
│                   └──────────────────────────────────────────────┘  │
│                                                                     │
│  ┌──────────────────────────────────────────────────────────────┐   │
│  │                     Infrastructure Layer                      │   │
│  │  ┌──────────┐  ┌──────────┐  ┌────────┐  ┌──────────────┐   │   │
│  │  │ Identity │  │  Model   │  │ State  │  │  Browser     │   │   │
│  │  │ Registry │  │ Adapter  │  │  Store  │  │  Pool        │   │   │
│  │  │ (YAML)   │  │          │  │(SQLite) │  │ (Playwright) │   │   │
│  │  └──────────┘  └──────────┘  └────────┘  └──────────────┘   │   │
│  └──────────────────────────────────────────────────────────────┘   │
└─────────────────────────────────────────────────────────────────────┘
```

---

## 2. 核心组件设计

### 2.1 LangGraph 工作流 (Graph Workflow)

整个系统以 LangGraph 的 `StateGraph` 为核心编排引擎，所有节点共享一个 `AgentState`。

#### State 定义

```python
from typing import TypedDict, Literal, Optional
from langgraph.graph import MessagesState

class AgentState(TypedDict):
    # 身份与上下文
    account_id: str
    persona: dict                    # 从 Identity Registry 加载的完整配置
    task: str                        # 当前任务描述
    memory: list[dict]               # 该账号的历史经验

    # 研究阶段产物
    research_results: list[dict]     # 检索到的素材与分析结论
    data_sources: list[str]          # 使用的数据源列表

    # 内容生成产物
    draft_title: str                 # 草稿标题
    draft_content: str               # 草稿正文
    draft_tags: list[str]            # 标签列表
    visual_assets: list[str]         # 生成的图片文件路径

    # 安全检查
    safety_passed: bool              # 是否通过合规检查
    safety_issues: list[str]         # 检出的问题列表

    # 审核与发布
    review_mode: Literal["auto", "review", "scheduled"]
    approved: bool                   # 是否通过审核
    publish_result: Optional[dict]   # 发布结果（URL、状态等）

    # 反馈
    post_metrics: Optional[dict]     # 发布后的效果数据
    feedback_summary: Optional[str]  # AI 生成的优化建议
```

#### 节点流转图

```
                    ┌──────────────┐
                    │    START     │
                    └──────┬───────┘
                           │
                           ▼
               ┌───────────────────────┐
               │  Node 1: Persona &    │
               │  Context Loader       │
               └───────────┬───────────┘
                           │
                           ▼
               ┌───────────────────────┐
               │  Node 2: Multi-VLM    │
               │  Research Engine      │
               └───────────┬───────────┘
                           │
                           ▼
               ┌───────────────────────┐
               │  Node 3: Creative &   │
               │  Optimization Engine  │
               └───────────┬───────────┘
                           │
                           ▼
               ┌───────────────────────┐
               │  Node 4: Content      │
           ┌───│  Safety Check         │
           │   └───────────┬───────────┘
           │               │
           │ (failed)      │ (passed)
           │               ▼
           │   ┌───────────────────────┐
           │   │  Node 5: Review &     │───┐
           │   │  Approval Gate        │   │ (rejected)
           │   └───────────┬───────────┘   │
           │               │               │
           │               │ (approved)    │
           │               ▼               │
           │   ┌───────────────────────┐   │
           │   │  Node 6: Execution &  │   │
           │   │  Browser Publish      │   │
           │   └───────────┬───────────┘   │
           │               │               │
           │               ▼               │
           │   ┌───────────────────────┐   │
           │   │  Node 7: Post-Publish │   │
           │   │  Monitor              │   │
           │   └───────────┬───────────┘   │
           │               │               │
           │               ▼               │
           │   ┌───────────────────────┐   │
           └──▶│  Node 8: Feedback &   │◀──┘
               │  Memory Update        │
               └───────────┬───────────┘
                           │
                           ▼
                    ┌──────────────┐
                    │     END      │
                    └──────────────┘
```

**条件路由规则：**

| 来源节点 | 条件 | 目标节点 |
|---------|------|---------|
| Node 4 (Safety) | `safety_passed == True` | Node 5 (Review) |
| Node 4 (Safety) | `safety_passed == False` | Node 8 (Feedback) — 记录失败原因，终止 |
| Node 5 (Review) | `approved == True` | Node 6 (Execute) |
| Node 5 (Review) | `approved == False` | Node 8 (Feedback) — 记录拒绝原因 |
| Node 6 (Execute) | 发布成功 | Node 7 (Monitor) |
| Node 6 (Execute) | 发布失败 | Node 8 (Feedback) — 记录错误 |

---

### 2.2 各节点详细设计

#### Node 1: Persona & Context Loader

**职责：** 根据 `account_id` 加载身份配置、历史 memory 和近期关注点。

```
输入: account_id, task
输出: persona (完整配置), memory (历史经验列表)
```

**实现要点：**
- 从 `config/identities/` 目录读取对应的 YAML 文件
- 从 `data/memory/{account_id}/` 加载历史 memory
- 注入最近 N 条爆款案例作为 few-shot 参考

---

#### Node 2: Multi-VLM Research Engine

**职责：** 根据任务类型和账号配置，动态选择模型进行素材检索与分析。

```
输入: persona, task
输出: research_results, data_sources
```

**模型选择流程：**

```
task_type = classify_task(task)
         │
         ├── "policy_analysis"  → Gemini 1.5 Pro (长文档)
         ├── "market_analysis"  → Claude 3.7 + yfinance API
         ├── "trend_scan"       → Gemini 1.5 Flash (快速)
         └── "general"          → persona.primary_model
```

**数据源适配器：**

| 数据源 | 实现方式 | 适用场景 |
|--------|---------|---------|
| Web 搜索 | Tavily / SerpAPI | 通用热点、政策新闻 |
| PDF 文档 | PyPDF2 + VLM | 政策文件、研究报告 |
| 金融数据 | yfinance API | K 线、财报数据 |
| 社交平台 | browser-use 抓取 | 竞品分析、热帖采集 |

**容错机制：**

```python
async def call_model_with_fallback(primary, fallback, prompt):
    try:
        return await call_model(primary, prompt)
    except (RateLimitError, APIError) as e:
        logger.warning(f"Primary model failed: {e}, falling back to {fallback}")
        return await call_model(fallback, prompt)
```

---

#### Node 3: Creative & Optimization Engine

**职责：** 根据研究结果和人格设定，生成平台适配的文案与视觉内容。

```
输入: persona, research_results
输出: draft_title, draft_content, draft_tags, visual_assets
```

**文案生成 Prompt 模板结构：**

```
你是 {persona.name}，{persona.description}。
你的语言风格是：{persona.tone}
你的目标受众是：{persona.audience}

基于以下素材，生成一篇小红书笔记：
---
{research_results}
---

要求：
1. 标题：{platform_rules.title_format}
2. 正文：{platform_rules.content_format}
3. 标签：{platform_rules.tag_rules}
```

**视觉内容生成策略：**

| 内容类型 | 生成工具 | 输出格式 |
|---------|---------|---------|
| 思维导图 | graphviz / mermaid | PNG |
| 数据图表 | matplotlib / plotly | PNG |
| 对比表格 | Pillow + 模板 | PNG |
| AI 配图 | Nano Banana 2 | PNG |
| 知识卡片 | HTML → screenshot | PNG |

---

#### Node 4: Content Safety Check

**职责：** 对生成的内容进行合规性和安全性检查。

```
输入: draft_title, draft_content, visual_assets, persona
输出: safety_passed, safety_issues
```

**检查清单：**

1. **敏感词过滤**
   - 通用词库（`config/sensitive_words/common.yaml`）
   - 赛道专用词库（`config/sensitive_words/{track}.yaml`）
   - 平台限流词库

2. **金融合规**（仅 `track == "finance"`）
   - 禁止断言性收益预测（"一定涨"、"稳赚"等）
   - 自动追加免责声明
   - 标注"以上内容仅供参考，不构成投资建议"

3. **内容去重**
   - 计算当前内容的 embedding
   - 与近 30 天已发布内容做余弦相似度比较
   - 相似度 > 0.85 则标记为重复

4. **图片合规**
   - 水印检测（避免侵权）
   - 尺寸/比例校验（符合平台规范）

---

#### Node 5: Review & Approval Gate

**职责：** 根据审核模式决定内容的发布路径。

```
输入: review_mode, draft_*, safety_passed
输出: approved
```

**三种模式：**

| 模式 | 行为 |
|------|------|
| `auto` | 安全检查通过后直接发布，**金融类账号禁用此模式** |
| `review` | 在终端/Web UI 展示内容预览，等待人工输入 `approve` / `reject` |
| `scheduled` | 内容写入发布队列（SQLite），由独立的 Scheduler 按时间窗口消费 |

---

#### Node 6: Execution & Browser Publish

**职责：** 通过浏览器自动化完成实际的社交平台发布操作。

```
输入: approved content, persona.browser_config
输出: publish_result (url, status, timestamp)
```

**浏览器隔离架构：**

```
Browser Pool Manager
    │
    ├── Profile: XHS_01 ──→ Chrome Instance 1
    │   ├── user-data-dir: /data/profiles/XHS_01/
    │   ├── proxy: socks5://proxy1:1080
    │   └── fingerprint: {ua: "...", resolution: "1920x1080"}
    │
    ├── Profile: XHS_02 ──→ Chrome Instance 2
    │   ├── user-data-dir: /data/profiles/XHS_02/
    │   ├── proxy: socks5://proxy2:1080
    │   └── fingerprint: {ua: "...", resolution: "1440x900"}
    │
    └── Profile: XHS_03 ──→ Chrome Instance 3
        ├── user-data-dir: /data/profiles/XHS_03/
        ├── proxy: socks5://proxy3:1080
        └── fingerprint: {ua: "...", resolution: "1366x768"}
```

**反检测措施：**

| 维度 | 措施 |
|------|------|
| IP | 每账号绑定独立住宅代理 |
| 指纹 | UA、Canvas、WebGL、屏幕分辨率差异化 |
| 行为 | 随机操作间隔 (1-5s)、模拟滚动、点击偏移 |
| 时间 | 发布时间加随机抖动 (±15min) |

---

#### Node 7: Post-Publish Monitor

**职责：** 在发布后的关键时间节点自动抓取内容效果数据。

```
输入: publish_result
输出: post_metrics
```

**数据回收时间线：**

| 时间点 | 抓取内容 | 用途 |
|--------|---------|------|
| T+2h | 初始曝光、互动数 | 判断是否被限流 |
| T+24h | 全维度数据 | 核心效果评估 |
| T+72h | 最终数据 | 长尾效果 + 入库 |

**指标维度：**

```python
PostMetrics = {
    "impressions": int,      # 曝光量
    "likes": int,            # 点赞
    "favorites": int,        # 收藏
    "comments": int,         # 评论
    "shares": int,           # 分享
    "new_followers": int,    # 涨粉
    "engagement_rate": float # 互动率
}
```

---

#### Node 8: Feedback & Memory Update

**职责：** 汇总执行结果（成功/失败/拒绝），生成优化建议并写入 memory。

```
输入: publish_result | safety_issues | rejection_reason, post_metrics
输出: feedback_summary → 写入 memory 文件
```

**Memory 结构：**

```json
{
    "account_id": "XHS_01",
    "entries": [
        {
            "timestamp": "2026-03-25T10:00:00Z",
            "type": "success",
            "task": "2026上海体育中考新规解读",
            "metrics": {"likes": 1200, "favorites": 890},
            "insight": "家长对耐力跑标准的焦虑是核心痛点，配图使用对比表格效果最佳"
        },
        {
            "timestamp": "2026-03-20T15:00:00Z",
            "type": "low_performance",
            "task": "中考数学备考建议",
            "metrics": {"likes": 45, "favorites": 30},
            "insight": "纯文字攻略缺乏吸引力，下次应增加思维导图或错题分析图"
        }
    ]
}
```

---

## 3. 基础设施层设计

### 3.1 Identity Registry

```
config/
└── identities/
    ├── XHS_01.yaml      # 上海中考博主
    ├── XHS_02.yaml      # 股票分析师
    └── XHS_03.yaml      # 老年生活家
```

**单个 Identity 配置结构：**

```yaml
account_id: XHS_01
platform: xiaohongshu

persona:
  name: "学霸学长"
  description: "上海本地教育博主，专注中考政策解读和备考攻略"
  tone: "专业但亲切，像一个耐心的学长在给学弟学妹讲重点"
  audience: "上海初中生家长，25-45岁"
  system_prompt: |
    你是一位上海本地的教育博主，擅长将复杂的中考政策用通俗易懂的方式讲解。
    你的风格是：专业、有条理、善用数据和对比表格。
    ...

track: "上海中考"
keywords: ["中考", "择校", "体育考", "自招", "名额分配"]

models:
  primary: "gemini-1.5-pro"
  fallback: "gemini-1.5-flash"
  image_gen: null  # 使用代码生成图表

visual_style:
  color_scheme: ["#1a73e8", "#ffffff", "#f0f4f9"]
  font: "思源黑体"
  template: "knowledge_card"

browser:
  profile_dir: "/data/profiles/XHS_01"
  proxy: "socks5://user:pass@proxy1.example.com:1080"
  fingerprint:
    user_agent: "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7)..."
    resolution: "1920x1080"

schedule:
  post_windows: ["19:00-21:00", "07:00-08:00"]
  max_daily_posts: 2
  review_mode: "review"

sensitive_words_extra: ["包过", "保分", "押题"]
```

### 3.2 Model Adapter

动态模型适配器，统一不同 LLM Provider 的调用接口。

```python
class ModelAdapter:
    """统一的模型调用接口"""

    _registry: dict[str, BaseModelClient] = {}

    @classmethod
    def register(cls, model_name: str, client: BaseModelClient):
        cls._registry[model_name] = client

    @classmethod
    async def invoke(cls, model_name: str, prompt: str, **kwargs) -> str:
        client = cls._registry[model_name]
        return await client.invoke(prompt, **kwargs)

    @classmethod
    async def invoke_with_fallback(
        cls, primary: str, fallback: str, prompt: str, **kwargs
    ) -> str:
        try:
            return await cls.invoke(primary, prompt, **kwargs)
        except Exception as e:
            logger.warning(f"Fallback from {primary} to {fallback}: {e}")
            return await cls.invoke(fallback, prompt, **kwargs)
```

### 3.3 State Store

使用 LangGraph 原生的 Checkpointer 机制 + SQLite 持久化。

```python
from langgraph.checkpoint.sqlite.aio import AsyncSqliteSaver

# 状态持久化配置
checkpointer = AsyncSqliteSaver.from_conn_string("data/state/checkpoints.db")

# 发布队列（scheduled 模式）
# data/queue/publish_queue.db

# Memory 存储
# data/memory/{account_id}/memory.json
```

### 3.4 Browser Pool Manager

管理多个独立的浏览器实例，确保账号隔离。

```python
class BrowserPoolManager:
    """浏览器实例池管理器"""

    def __init__(self, max_concurrent: int = 3):
        self._semaphore = asyncio.Semaphore(max_concurrent)
        self._instances: dict[str, BrowserContext] = {}

    async def get_browser(self, account_id: str) -> BrowserContext:
        """获取或创建指定账号的浏览器实例"""
        async with self._semaphore:
            if account_id not in self._instances:
                config = identity_registry.get(account_id).browser
                self._instances[account_id] = await self._launch(config)
            return self._instances[account_id]

    async def _launch(self, config: BrowserConfig) -> BrowserContext:
        """启动带隔离配置的浏览器"""
        # Playwright launch with:
        # - user_data_dir
        # - proxy
        # - custom fingerprint
        ...
```

---

## 4. 数据流与存储结构

```
data/
├── profiles/                    # 浏览器 Profile 数据
│   ├── XHS_01/
│   ├── XHS_02/
│   └── XHS_03/
├── memory/                      # 账号记忆存储
│   ├── XHS_01/
│   │   └── memory.json
│   ├── XHS_02/
│   │   └── memory.json
│   └── XHS_03/
│       └── memory.json
├── assets/                      # 生成的视觉素材
│   ├── XHS_01/
│   │   └── 2026-03-25/
│   │       ├── cover.png
│   │       └── chart.png
│   └── ...
├── state/                       # LangGraph 状态持久化
│   └── checkpoints.db
├── queue/                       # 定时发布队列
│   └── publish_queue.db
└── logs/                        # 结构化日志
    ├── XHS_01.jsonl
    ├── XHS_02.jsonl
    └── system.jsonl
```

---

## 5. 错误处理策略

| 错误类型 | 处理方式 | 重试策略 |
|---------|---------|---------|
| LLM API Rate Limit | 切换 fallback model | 指数退避, 最多 3 次 |
| LLM API 超时 | 重试后降级 | 固定间隔 5s, 最多 2 次 |
| 浏览器崩溃 | 重启实例, 从 checkpoint 恢复 | 立即重试 1 次 |
| 登录态失效 | 暂停账号, 发送告警 | 不自动重试, 需人工介入 |
| 内容被平台拦截 | 记录原因, 更新敏感词库 | 不重试 |
| 网络/代理故障 | 切换备用代理 | 3 次后暂停 |

---

## 6. 日志与可观测性

### 结构化日志格式

```json
{
    "timestamp": "2026-03-25T10:30:00Z",
    "level": "INFO",
    "account_id": "XHS_01",
    "node": "research_engine",
    "event": "model_invoked",
    "model": "gemini-1.5-pro",
    "tokens_in": 1200,
    "tokens_out": 800,
    "latency_ms": 3200,
    "cost_usd": 0.012
}
```

### 告警规则

| 事件 | 告警级别 | 通知渠道 |
|------|---------|---------|
| 账号登录态失效 | 🔴 Critical | 微信 + Telegram |
| 发布失败 | 🟡 Warning | Telegram |
| 内容被平台删除 | 🔴 Critical | 微信 + Telegram |
| API 连续失败 > 5 次 | 🟡 Warning | Telegram |
| Token 日消耗超预算 | 🟡 Warning | Telegram |

---

## 7. 扩展性设计

### 7.1 新增平台

实现 `Publisher` 接口即可接入新平台：

```python
class Publisher(Protocol):
    async def login_check(self) -> bool: ...
    async def publish(self, content: PublishContent) -> PublishResult: ...
    async def fetch_metrics(self, post_id: str) -> PostMetrics: ...

class XiaohongshuPublisher(Publisher): ...
class DouyinPublisher(Publisher): ...  # 未来扩展
class WeiboPublisher(Publisher): ...   # 未来扩展
```

### 7.2 新增内容类型

注册 `CreativeHandler` 即可支持新的内容生成方式：

```python
class CreativeHandler(Protocol):
    def can_handle(self, content_type: str) -> bool: ...
    async def generate(self, context: CreativeContext) -> CreativeOutput: ...

# 注册
creative_registry.register(MindMapHandler())
creative_registry.register(KLineChartHandler())
creative_registry.register(AIImageHandler())
```

---

## 8. 安全考量

| 风险 | 缓解措施 |
|------|---------|
| API Key 泄露 | `.env` 管理, `.gitignore` 排除 |
| 账号关联 | Profile + IP + 指纹三重隔离 |
| 内容违规 | Safety Check 节点 + 敏感词库 |
| 金融合规 | 强制审核模式 + 免责声明 |
| 数据安全 | Cookie/Token 日志脱敏 |
| 运行环境 | 定期轮换代理 IP |
