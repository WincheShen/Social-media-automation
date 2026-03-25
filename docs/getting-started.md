# 启动指南

## 1. 环境要求

| 依赖 | 版本 | 说明 |
|------|------|------|
| Python | ≥ 3.11 | 推荐 3.12 |
| Google Chrome | 最新稳定版 | xiaohongshu-skills 通过 CDP 直连本机 Chrome |
| pip | 最新 | `pip install --upgrade pip` |

## 2. 安装依赖

```bash
# 克隆项目（含 submodule）
git clone --recurse-submodules <repo-url>
cd Social-media-automation

# 创建虚拟环境
python -m venv .venv
source .venv/bin/activate

# 安装项目依赖
pip install -e ".[dev]"

# 安装 xiaohongshu-skills 的依赖
pip install websockets requests
```

> 如果已克隆但没有 `vendor/xiaohongshu-skills` 内容，补拉 submodule：
> ```bash
> git submodule update --init --recursive
> ```

## 3. 配置 API Keys

```bash
cp .env.example .env
```

编辑 `.env`：

```env
GOOGLE_API_KEY=AIzaSy...          # 必填
TAVILY_API_KEY=tvly-...           # 必填
ANTHROPIC_API_KEY=sk-ant-...      # 仅 XHS_02 需要，见下方说明
XHS_SKILLS_DIR=vendor/xiaohongshu-skills
```

### 各 Key 说明

#### GOOGLE_API_KEY（必填）

- **用途：** 调用 Google Gemini 大模型，负责内容研究、文案生成、反馈分析
- **哪些账号用：** XHS_01（gemini-1.5-pro）、XHS_03（gemini-1.5-flash），以及作为 XHS_02 的 fallback
- **获取：** [Google AI Studio](https://aistudio.google.com/apikey) → 创建 API Key
- **免费额度：** 每分钟 15 次请求（足够单账号运营）

#### TAVILY_API_KEY（必填）

- **用途：** AI 搜索引擎 API。Research 节点用它做**外部网络搜索**——输入关键词，返回结构化的搜索结果（标题、摘要、URL、相关度评分），比直接调 Google Search 更适合 AI Agent 消费
- **工作原理：** 你给 Agent 一个任务（如"分析上海中考体育新规"），Research 节点会：
  1. 用 Tavily 搜外部网页（政策文件、新闻、论坛）
  2. 用 xiaohongshu-skills 搜小红书站内竞品笔记
  3. 合并去重后交给 LLM 分析
- **获取：** [app.tavily.com](https://app.tavily.com/) → 注册 → Dashboard 直接拿 Key（`tvly-` 开头）
- **免费额度：** 每月 1,000 次搜索（每次 workflow 消耗 2-3 次，足够日常运营）

#### ANTHROPIC_API_KEY（可选）

- **用途：** 调用 Anthropic Claude 大模型
- **哪些账号用：** **仅 XHS_02**（老K侃股 / 股票分析师）。选 Claude 是因为它在金融数据的严谨推理上表现更好
- **如果不配：** XHS_02 会自动 fallback 到 `gemini-1.5-pro`，也能用，只是金融分析质量略有下降
- **获取：** [console.anthropic.com](https://console.anthropic.com/) → API Keys
- **结论：** 如果你只跑 XHS_01 或 XHS_03，**完全不需要这个 Key**

### 各账号模型配置一览

| 账号 | 人设 | 主模型 | Fallback | 需要的 Key |
|------|------|--------|----------|-----------|
| XHS_01 | 学霸学长（上海中考） | gemini-1.5-pro | gemini-1.5-flash | GOOGLE_API_KEY |
| XHS_02 | 老K侃股（股票分析） | claude-3.7-sonnet | gemini-1.5-pro | ANTHROPIC_API_KEY + GOOGLE_API_KEY |
| XHS_03 | 暖心小棉袄（老年生活） | gemini-1.5-flash | gemini-1.5-flash | GOOGLE_API_KEY |

## 4. 启动 Chrome 实例

每个小红书账号需要一个**独立的 Chrome 实例**（独立 CDP 端口 + 独立 Profile），登录态互相隔离。

```bash
cd vendor/xiaohongshu-skills

# 终端 1 — XHS_01（端口 9222）
python scripts/chrome_launcher.py --port 9222

# 终端 2 — XHS_02（端口 9223）
python scripts/chrome_launcher.py --port 9223

# 终端 3 — XHS_03（端口 9224）
python scripts/chrome_launcher.py --port 9224
```

- 首次启动会弹出 Chrome 窗口
- Chrome 实例需要**保持运行**，不要关闭终端
- 如果只跑一个账号，启动对应端口的那一个就行

## 5. 扫码登录

**每个账号首次使用必须用小红书 App 扫码登录一次**，之后 cookie 自动持久化。

```bash
cd vendor/xiaohongshu-skills

# 登录 XHS_01
python scripts/cli.py --port 9222 login

# 登录 XHS_02
python scripts/cli.py --port 9223 login

# 登录 XHS_03
python scripts/cli.py --port 9224 login
```

浏览器自动打开小红书登录页，用对应手机上的小红书 App 扫码。

**验证登录是否成功：**

```bash
python scripts/cli.py --port 9222 check-login
# ✅ 成功输出: {"nickname": "学霸学长", "xhs_id": "..."}
# ❌ 失败输出: exit code 1
```

## 6. 运行 Agent

回到项目根目录：

```bash
cd /path/to/Social-media-automation
```

**查看所有账号：**

```bash
python -m src.main accounts
```

```
ID           Platform        Persona              Track                Review Mode
────────────────────────────────────────────────────────────────────────────────────
XHS_01       xiaohongshu     学霸学长              上海中考              review
XHS_02       xiaohongshu     老K侃股              finance              review
XHS_03       xiaohongshu     暖心小棉袄            老年生活              review
```

**运行一次完整 workflow：**

```bash
# XHS_01 — 教育博主
python -m src.main run --account XHS_01 --task "分析 2026 上海体育中考新规的变化和备考建议"

# XHS_02 — 股票分析师
python -m src.main run --account XHS_02 --task "解读本周A股三大指数走势及下周展望"

# XHS_03 — 老年生活
python -m src.main run --account XHS_03 --task "夏季老年人防中暑的5个实用小妙招"
```

## 7. 工作流执行过程

运行 `run` 命令后，Agent 依次执行 8 个节点：

```
Node 1  Context Loader   加载账号人设 + 历史记忆
Node 2  Research Engine   Tavily 外部搜索 + 小红书站内搜索竞品
Node 3  Creative Engine   LLM 生成标题/正文/标签 + 知识卡片图片
Node 4  Safety Check      敏感词/金融合规/内容长度检查
Node 5  Review Gate       终端展示内容 → 你输入 y 确认或 n 拒绝
Node 6  Execution         fill-publish 填表 → 浏览器预览 → click-publish 发布
Node 7  Monitor           注册 T+2h / T+24h / T+72h 指标采集任务
Node 8  Feedback          LLM 生成洞察 + 更新记忆
```

**Node 5 人工审核：** 终端会打印生成的标题、正文、标签，等待你输入 `y`（通过）或 `n`（拒绝）。

**Node 6 发布预览：** fill-publish 填完表单后，你可以在 Chrome 窗口中直接看到笔记预览。确认无误后 Agent 自动 click-publish 提交。

## 8. 配置文件说明

| 文件 | 用途 |
|------|------|
| `.env` | API Keys 和环境变量 |
| `config/identities/XHS_01.yaml` | 账号人设、LLM 模型、排版风格、发布时间窗口、敏感词 |
| `config/identities/XHS_02.yaml` | 同上（金融类，强制 review 模式） |
| `config/identities/XHS_03.yaml` | 同上（老年生活类） |
| `config/sensitive_words/common.yaml` | 全账号通用敏感词 |
| `config/sensitive_words/finance.yaml` | 金融类额外敏感词 |
| `data/state/` | SQLite 数据库（发布队列、监控任务）—— 自动创建 |
| `data/memory/` | 账号历史记忆 JSON —— 自动创建 |

## 9. 常见问题

| 问题 | 解决方案 |
|------|---------|
| `Chrome not found` | 确认 Google Chrome 已安装在系统默认路径 |
| `not logged in` | 重新 `cli.py login` 扫码 |
| Tavily 搜索 403 | 检查 `TAVILY_API_KEY` 是否正确，或免费额度已用完 |
| XHS 站内搜索失败 | 正常降级，仅用 Tavily 外部搜索，不影响 workflow |
| 金融账号无法设为 auto | 设计如此，`finance` track 强制 review 模式，保护合规 |
| `XhsTimeoutError` | Chrome 实例可能未启动，检查对应端口的终端 |

## 10. 建议的首次运行

**推荐先用 XHS_01 测试**——它只需要 `GOOGLE_API_KEY`（免费额度高），风险最低：

```bash
# 1. 确认 .env 中 GOOGLE_API_KEY 和 TAVILY_API_KEY 已填
# 2. 启动 Chrome
cd vendor/xiaohongshu-skills && python scripts/chrome_launcher.py --port 9222

# 3. 扫码登录（另开终端）
python scripts/cli.py --port 9222 login

# 4. 运行
cd /path/to/Social-media-automation
python -m src.main run --account XHS_01 --task "2026上海中考体育评分标准变化解读"
```
