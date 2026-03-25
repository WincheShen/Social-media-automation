# xiaohongshu-skills CLI 集成设计方案

## 1. 总体架构

```
┌─────────────────────────────────────────────────────────────────┐
│                    LangGraph Agent (Brain)                       │
│  context_loader → research → creative → safety → review → ...   │
└──────────┬──────────────────────────────┬───────────────────────┘
           │ search-feeds / list-feeds    │ fill-publish / click-publish
           │ get-feed-detail              │ like / favorite / comment
           ▼                              ▼
┌─────────────────────────────────────────────────────────────────┐
│                     XhsCliAdapter                                │
│  Python 封装层 — async subprocess 调用 CLI，解析 JSON 输出       │
│                                                                  │
│  ┌──────────────┐  ┌──────────────┐  ┌──────────────────────┐   │
│  │ ChromeManager│  │ AccountRouter│  │ ResultParser          │   │
│  │ 启动/关闭    │  │ --account    │  │ JSON→dataclass        │   │
│  │ 健康检查     │  │ --port       │  │ exit code→exception   │   │
│  └──────────────┘  └──────────────┘  └──────────────────────┘   │
└──────────┬──────────────────────────────────────────────────────┘
           │  subprocess (async)
           ▼
┌─────────────────────────────────────────────────────────────────┐
│              xiaohongshu-skills CLI (scripts/cli.py)             │
│  Python CDP 引擎 → Chrome DevTools Protocol → Chrome → 小红书   │
│  内置: stealth.js 注入 / human.py 行为模拟 / cookies 持久化     │
└─────────────────────────────────────────────────────────────────┘
```

**核心原则：Agent 只做「思考」，所有浏览器操作通过 CLI 子进程完成。**

---

## 2. XhsCliAdapter 类设计

### 2.1 文件位置

```
src/infra/xhs_cli.py          # XhsCliAdapter 主文件
src/infra/xhs_cli_types.py    # 返回值 dataclass 定义
```

### 2.2 核心类

```python
class XhsCliAdapter:
    """封装 xiaohongshu-skills CLI 调用。
    
    所有方法都是 async 的，通过 asyncio.create_subprocess_exec 调用 CLI，
    解析 JSON stdout，根据 exit code 抛出对应异常。
    """

    def __init__(
        self,
        skills_dir: str | Path,       # xiaohongshu-skills 根目录
        account: str | None = None,   # --account 参数
        host: str = "127.0.0.1",      # Chrome CDP host
        port: int = 9222,             # Chrome CDP port
        python_bin: str = "python",   # python 可执行文件路径
        timeout: int = 60,            # 默认命令超时（秒）
    ): ...
```

### 2.3 方法清单

```python
# ─── Chrome 生命周期 ───
async def launch_chrome(self, headless: bool = False) -> None
async def shutdown_chrome(self) -> None
async def is_chrome_running(self) -> bool

# ─── 认证 ───
async def check_login(self) -> LoginStatus        # 返回 {logged_in, nickname, xhs_id}
async def login(self) -> LoginStatus               # 启动扫码登录流程
async def delete_cookies(self) -> None

# ─── 浏览（Research 阶段可用）───
async def list_feeds(self) -> list[FeedItem]       # 首页推荐流
async def search_feeds(                            # 搜索笔记
    self, keyword: str,
    sort_by: str | None = None,      # "最多点赞" / "最新"
    note_type: str | None = None,    # "图文" / "视频"
) -> list[FeedItem]
async def get_feed_detail(                         # 笔记详情 + 评论
    self, feed_id: str, xsec_token: str,
) -> FeedDetail
async def user_profile(self, user_id: str) -> UserProfile

# ─── 发布（Execution 阶段）───
async def fill_publish(                            # 填写发布表单（不提交）
    self,
    title: str,
    content: str,
    images: list[str],               # 绝对路径
    title_file: str | None = None,   # 或通过临时文件传入
    content_file: str | None = None,
) -> None
async def click_publish(self) -> PublishResult     # 确认发布
async def save_draft(self) -> None                 # 保存草稿

# ─── 社交互动 ───
async def like_feed(self, feed_id: str, xsec_token: str) -> None
async def favorite_feed(self, feed_id: str, xsec_token: str) -> None
async def post_comment(
    self, feed_id: str, xsec_token: str, content: str,
) -> None
```

### 2.4 底层调用机制

```python
async def _run_cli(self, *args: str, timeout: int | None = None) -> dict:
    """执行 CLI 命令，返回解析后的 JSON 输出。
    
    流程:
    1. 拼接命令: python scripts/cli.py --host H --port P --account A <args>
    2. asyncio.create_subprocess_exec 执行
    3. 等待完成（带超时）
    4. 根据 exit code 处理:
       - 0: 成功，解析 stdout JSON
       - 1: 未登录，抛出 XhsNotLoggedInError
       - 2: 错误，抛出 XhsCliError(stderr)
    5. 记录日志（命令、耗时、结果摘要）
    """
```

### 2.5 异常体系

```python
class XhsCliError(Exception):          # CLI 返回 exit code 2
class XhsNotLoggedInError(XhsCliError): # CLI 返回 exit code 1
class XhsTimeoutError(XhsCliError):     # 命令超时
class XhsChromeNotRunning(XhsCliError): # Chrome 未启动
```

### 2.6 数据类型

```python
@dataclass
class LoginStatus:
    logged_in: bool
    nickname: str | None = None
    xhs_id: str | None = None

@dataclass
class FeedItem:
    feed_id: str
    xsec_token: str
    title: str
    author: str
    likes: int
    url: str | None = None

@dataclass
class FeedDetail:
    feed_id: str
    title: str
    content: str
    author: str
    likes: int
    collects: int
    comments: int
    comment_list: list[dict]
    images: list[str]

@dataclass
class PublishResult:
    success: bool
    post_url: str | None = None
    error: str | None = None
```

---

## 3. 各节点集成方式

### 3.1 Node 2: Research Engine（搜索增强）

**新增能力**：除了 Tavily 网络搜索，还可从小红书站内获取实时数据。

```python
# research_engine.py 新增

async def _xhs_search(adapter: XhsCliAdapter, keyword: str) -> list[dict]:
    """从小红书站内搜索竞品/热点笔记。"""
    feeds = await adapter.search_feeds(
        keyword=keyword,
        sort_by="最多点赞",
        note_type="图文",
    )
    return [
        {
            "title": f.title,
            "url": f.url or f"xhs://feed/{f.feed_id}",
            "content": f"作者: {f.author}, 点赞: {f.likes}",
            "score": f.likes,
            "source": "xiaohongshu_search",
        }
        for f in feeds
    ]
```

**数据流**：
```
task + persona.keywords
  → Tavily 搜索 (外部信息)        ──┐
  → XHS search-feeds (站内竞品)    ──┼──→ 合并去重 → LLM 分析
  → XHS list-feeds (推荐流趋势)    ──┘
```

### 3.2 Node 6: Execution（发布 — 核心改造）

**替换 browser-use，改为 CLI 调用**：

```python
# execution.py 改造后

async def browser_publish(state: AgentState) -> dict:
    adapter = _get_adapter(state)

    # 1. 确认登录态
    login_status = await adapter.check_login()
    if not login_status.logged_in:
        logger.warning("未登录，请先扫码: python scripts/cli.py login")
        return {"publish_result": {"status": "failed", "error": "not_logged_in"}}

    # 2. 写入临时文件（避免命令行参数中文编码问题）
    title_file, content_file = _write_temp_files(state)

    # 3. 填写发布表单（不提交）
    await adapter.fill_publish(
        title=state["draft_title"],
        content=state["draft_content"],
        images=state.get("visual_assets", []),
        title_file=title_file,
        content_file=content_file,
    )

    # 4. 确认发布
    result = await adapter.click_publish()

    return {
        "publish_result": {
            "status": "success" if result.success else "failed",
            "url": result.post_url,
            "platform": "xiaohongshu",
            "account_id": state["account_id"],
            "published_at": datetime.now(timezone.utc).isoformat(),
            "error": result.error,
        }
    }
```

**对比**：
| 方面 | 旧 (browser-use) | 新 (CLI) |
|------|------------------|----------|
| LLM Token 消耗 | 大量（Gemini 解读页面） | 零 |
| 确定性 | LLM 可能误操作 | 固定 CSS 选择器 |
| 反检测 | 基础 | Stealth + CDP isTrusted |
| 可调试 | 难 | CLI 日志 + JSON 输出 |

### 3.3 Node 7: Monitor（指标采集）

```python
# monitor.py 改造后

async def _collect_metrics(adapter: XhsCliAdapter, feed_id: str, xsec_token: str):
    detail = await adapter.get_feed_detail(feed_id, xsec_token)
    return {
        "likes": detail.likes,
        "collects": detail.collects,
        "comments": detail.comments,
        "collected_at": datetime.now(timezone.utc).isoformat(),
    }
```

### 3.4 新增能力：社交互动（可选）

Feedback 节点或独立任务中可调用：
```python
# 给竞品笔记互动（养号）
await adapter.like_feed(feed_id, xsec_token)
await adapter.post_comment(feed_id, xsec_token, "写得好！")
```

---

## 4. 多账号 Chrome 管理

每个账号使用独立的 Chrome 实例和 CDP 端口：

```python
# config/identities/XHS_01.yaml 新增配置
xhs_cli:
  port: 9222
  account: "xhs_01"

# config/identities/XHS_02.yaml
xhs_cli:
  port: 9223
  account: "xhs_02"
```

Adapter 工厂函数：
```python
def get_adapter_for_account(persona: dict) -> XhsCliAdapter:
    cli_cfg = persona.get("xhs_cli", {})
    return XhsCliAdapter(
        skills_dir=os.getenv("XHS_SKILLS_DIR", "vendor/xiaohongshu-skills"),
        account=cli_cfg.get("account"),
        port=cli_cfg.get("port", 9222),
    )
```

---

## 5. 安装方式选项

### 方案 A: Git Submodule（推荐）
```
vendor/xiaohongshu-skills/   # git submodule
```
- 版本锁定，可控
- `XHS_SKILLS_DIR` 默认指向 `vendor/xiaohongshu-skills`

### 方案 B: 环境变量指定路径
```env
XHS_SKILLS_DIR=/path/to/xiaohongshu-skills
```
- 灵活，适合已有独立安装的场景

---

## 6. 配置变更汇总

### .env.example 新增
```env
# xiaohongshu-skills 路径
XHS_SKILLS_DIR=vendor/xiaohongshu-skills
```

### pyproject.toml 变更
- 移除 `browser-use` 依赖（不再需要）
- 移除 `langchain-google-genai`（execution 不再用 LLM 驱动浏览器）
- 保留 `playwright`（xiaohongshu-skills 可能需要 Chrome）

### 各 YAML 新增 xhs_cli 配置块

---

## 7. 风险与缓解

| 风险 | 缓解措施 |
|------|---------|
| xiaohongshu-skills CLI 输出格式变更 | ResultParser 做宽松解析 + 版本锁定 |
| Chrome 实例异常退出 | ChromeManager 健康检查 + 自动重启 |
| 扫码登录需人工介入 | check_login 前置检查 + 登录过期告警 |
| 小红书改版导致选择器失效 | xiaohongshu-skills 的 selectors.py 集中管理，更新一处即可 |
| CLI 调用超时 | 可配置 timeout + 重试机制 |
