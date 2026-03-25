# 🤖 Social Media Automation Agent

基于 LangGraph 的多人格社交媒体自动化发布系统。

## 功能特性

- **多人格路由** — 每个账号拥有独立的人格设定、模型配置和浏览器环境
- **智能内容生成** — 根据赛道自动检索素材、生成文案和视觉内容
- **动态模型适配** — 根据任务类型自动选择最优 VLM（Gemini / Claude）
- **内容安全合规** — 敏感词过滤、金融合规检查、内容去重
- **浏览器隔离发布** — 独立 Profile + 代理 IP + 指纹差异化
- **数据驱动优化** — 发布效果回收 → AI 分析 → Memory 自动更新

## 项目结构

```
Social-media-automation/
├── config/
│   ├── identities/           # 账号身份配置 (YAML)
│   │   ├── XHS_01.yaml       # 上海中考博主
│   │   ├── XHS_02.yaml       # 股票分析师
│   │   └── XHS_03.yaml       # 老年生活家
│   └── sensitive_words/      # 敏感词库
│       ├── common.yaml       # 通用敏感词
│       └── finance.yaml      # 金融赛道敏感词
├── src/
│   ├── graph/                # LangGraph 工作流
│   │   ├── state.py          # AgentState 定义
│   │   └── workflow.py       # Graph 构建与路由
│   ├── nodes/                # 工作流节点实现
│   │   ├── context_loader.py # Node 1: 身份与上下文加载
│   │   ├── research_engine.py# Node 2: 多模型研究引擎
│   │   ├── creative_engine.py# Node 3: 内容生成引擎
│   │   ├── safety_check.py   # Node 4: 内容安全检查
│   │   ├── review_gate.py    # Node 5: 审核网关 (HITL)
│   │   ├── execution.py      # Node 6: 浏览器发布
│   │   ├── monitor.py        # Node 7: 发布后监控
│   │   └── feedback.py       # Node 8: 反馈与记忆更新
│   ├── publishers/           # 平台发布器
│   │   ├── base.py           # Publisher 协议接口
│   │   └── xiaohongshu.py    # 小红书发布器
│   ├── infra/                # 基础设施层
│   │   ├── model_adapter.py  # 动态模型适配器
│   │   ├── browser_pool.py   # 浏览器实例池
│   │   ├── identity_registry.py # 身份注册表
│   │   └── logger.py         # 结构化日志
│   └── main.py               # 程序入口
├── tests/                    # 测试
├── data/                     # 运行时数据 (gitignored)
│   ├── profiles/             # 浏览器 Profile
│   ├── memory/               # 账号记忆
│   ├── assets/               # 生成的素材
│   ├── state/                # LangGraph checkpoint
│   ├── queue/                # 定时发布队列
│   └── logs/                 # 结构化日志
├── docs/
│   ├── requirements.md       # 需求文档
│   └── architecture.md       # 架构设计文档
├── pyproject.toml            # 项目配置与依赖
├── .env.example              # 环境变量模板
└── .gitignore
```

## 快速开始

### 1. 环境准备

```bash
# 克隆项目
git clone <repo-url>
cd Social-media-automation

# 创建虚拟环境并安装依赖
python -m venv .venv
source .venv/bin/activate
pip install -e ".[dev]"

# 安装 Playwright 浏览器
playwright install chromium
```

### 2. 配置

```bash
# 复制环境变量模板并填入 API Key
cp .env.example .env

# 编辑账号身份配置
# config/identities/XHS_01.yaml
```

### 3. 运行

```bash
# 单次任务执行
python -m src.main --account XHS_01 --task "分析 2026 上海体育中考新规"
```

## 工作流节点

```
[Context Loader] → [Research] → [Creative] → [Safety Check]
                                                    │
                                              ┌─────┴─────┐
                                              ▼           ▼
                                         [Review]    [Feedback]
                                              │
                                              ▼
                                         [Execute] → [Monitor] → [Feedback]
```

## 文档

- [需求文档](docs/requirements.md) — 完整功能需求与非功能需求
- [架构设计](docs/architecture.md) — 系统架构、节点设计、数据流

## 技术栈

| 组件 | 技术 |
|------|------|
| 编排框架 | LangGraph |
| LLM | Google Gemini, Anthropic Claude |
| 浏览器自动化 | Playwright (browser-use) |
| 图像生成 | matplotlib, Pillow, Nano Banana 2 |
| 存储 | SQLite, JSON |
| 语言 | Python 3.11+ |
