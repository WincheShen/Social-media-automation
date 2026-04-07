# 社交媒体自动化系统 — Backlog

> 最后更新: 2026-04-02

---

## 🎯 核心目标

1. **每日自动循环**：系统每天自动收集热点 → 分析前日反馈 → 生成当日内容 → 发布
2. **社交互动引流**：发布后自动搜索同类内容，点赞/评论引流

---

## 🔴 P0 — 必须完成（阻塞核心目标）

### TASK-001: 定时调度器 (Daily Scheduler)

**目标**：实现每日自动执行循环，无需人工触发

**实现方案**：
```
src/scheduler/
├── __init__.py
├── daily_scheduler.py    # APScheduler 主调度器
├── monitor_worker.py     # Monitor 任务消费者
└── social_worker.py      # 社交互动 worker
```

**调度计划**：
| 时间 | 任务 | 说明 |
|------|------|------|
| 08:00 | `run_monitor_worker()` | 回收 T+24h 数据 |
| 09:00 | `create_daily_tasks()` | 为每个账号创建当日任务 |
| 12:00 | `run_social_engagement()` | 搜索同类内容 + 互动 |
| 20:00 | `run_monitor_worker()` | 回收 T+2h 数据 |

**技术选型**：
- 方案 A: APScheduler (Python, 进程内)
- 方案 B: systemd timer + cron (系统级)
- 方案 C: Celery Beat (分布式，重量级)

**推荐**: APScheduler — 轻量、Python 原生、易于调试

**验收标准**：
- [ ] 调度器可后台运行 (`python -m src.scheduler`)
- [ ] 支持从 YAML 配置调度时间
- [ ] 日志记录每次触发
- [ ] 支持手动触发单个 job

**预估工时**: 4h

---

### TASK-002: Monitor 消费者 (Monitor Worker)

**目标**：自动执行 `monitor_tasks.db` 中的待处理任务，回收发布后数据

**现状**：
- `monitor.py` 已将 T+2h/T+24h/T+72h 任务写入 SQLite
- 无消费者进程执行这些任务
- 数据永远停留在 `pending` 状态

**实现**：
```python
# src/scheduler/monitor_worker.py

async def run_monitor_worker():
    """扫描并执行到期的 monitor 任务"""
    pending_tasks = get_pending_tasks_due_now()
    for task in pending_tasks:
        adapter = get_adapter_for_account(task.account_id)
        metrics = await collect_metrics_for_task(adapter, task)
        if metrics:
            # 写入 memory.json 供 Analyst 使用
            append_metrics_to_memory(task.account_id, metrics)
```

**数据流**：
```
monitor_tasks.db (pending) 
    → Worker 执行 get-feed-detail 
    → 更新 monitor_tasks.db (completed)
    → 写入 data/memory/{account}/memory.json
    → Analyst 下次运行时读取
```

**验收标准**：
- [ ] Worker 可独立运行
- [ ] 正确处理 pending → completed 状态转换
- [ ] 回收的数据写入 memory.json
- [ ] 处理 CLI 调用失败的重试逻辑

**预估工时**: 3h

---

## 🟡 P1 — 重要功能

### TASK-003: 社交互动引擎集成 (Social Engagement Integration)

**目标**：发布后自动搜索同类内容，点赞/评论引流

**现状**：
- `social_interaction.py` 已实现核心功能
- 未集成进主循环或调度器

**实现方案**：

**方案 A: 作为 Node 9 集成进 workflow**
```
... → monitor → feedback → social_engagement → END
```
- 优点：与发布流程紧密耦合
- 缺点：增加单次运行时间

**方案 B: 独立 Job 由调度器触发（推荐）**
```python
# src/scheduler/social_worker.py

async def run_social_engagement(account_id: str):
    """基于最近发布内容搜索同类并互动"""
    recent_posts = get_recent_posts(account_id, days=1)
    for post in recent_posts:
        keywords = extract_keywords(post.title, post.tags)
        for kw in keywords[:2]:
            await engage_with_similar_content(account_id, kw)
```

**智能评论生成**：
```python
async def generate_comment(adapter, feed: FeedItem, persona: dict) -> str:
    """LLM 生成拟人化评论"""
    prompt = f"""你是{persona['name']}，正在浏览小红书。
    看到这篇笔记：《{feed.title}》
    请写一条真诚的评论（15-30字），要求：
    1. 符合你的人设和语气
    2. 与内容相关，不要泛泛而谈
    3. 可以提问或分享经验
    """
    return await router.invoke("copywriter", prompt)
```

**防检测策略**：
- 随机延迟：3-8 秒/操作
- 每日上限：点赞 ≤30，评论 ≤10
- 时间分散：不要集中在同一时段
- 行为模式：偶尔只浏览不互动

**验收标准**：
- [ ] 可独立运行 `python -m src.scheduler.social_worker --account XHS_01`
- [ ] 评论由 LLM 生成，符合人设
- [ ] 有防检测机制（延迟、上限）
- [ ] 互动记录写入日志

**预估工时**: 5h

---

### TASK-004: 自动任务创建 (Auto Task Creation)

**目标**：调度器自动为每个账号创建当日任务

**实现**：
```python
# src/scheduler/daily_scheduler.py

async def create_daily_tasks():
    """为每个活跃账号创建当日任务"""
    for account_id in registry.list_accounts():
        config = registry.get(account_id)
        if not config.get("schedule", {}).get("auto_post", False):
            continue
        
        # 任务描述由 Analyst 自动生成（基于热点 + 历史）
        task_desc = "自动选题：基于今日热点和历史表现"
        
        task = create_task(account_id, task_desc)
        run_workflow_research(task.id, account_id, task_desc)
```

**配置扩展**：
```yaml
# config/identities/XHS_01.yaml
schedule:
  review_mode: review
  auto_post: true          # 新增：是否参与自动发文
  post_windows: ["09:00-11:00", "19:00-21:00"]
  max_daily_posts: 1
```

**验收标准**：
- [ ] 调度器按时创建任务
- [ ] 尊重 `auto_post` 配置
- [ ] 任务自动进入 workflow
- [ ] review 模式账号停在审批环节

**预估工时**: 2h

---

## 🟢 P2 — 增强功能

### TASK-005: 图片生成对接 (Image Generation)

**目标**：根据 `image_gen_prompt` 生成配图

**方案**：
- DALL-E 3 (OpenAI) — 质量高，成本高
- Flux (Replicate) — 性价比好
- 本地 ComfyUI — 零成本，需要 GPU

**实现**：
```python
# src/infra/image_gen.py

async def generate_image(prompt: str, style: str = "xiaohongshu") -> str:
    """生成图片并返回本地路径"""
    # 风格增强
    enhanced_prompt = f"{prompt}, {STYLE_SUFFIXES[style]}"
    
    # 调用 API
    image_url = await dalle3_generate(enhanced_prompt)
    
    # 下载到本地
    local_path = download_image(image_url)
    return local_path
```

**验收标准**：
- [ ] 支持至少一种图片生成 API
- [ ] 图片自动下载到 `data/images/`
- [ ] 发布时自动附带图片

**预估工时**: 4h

---

### TASK-006: Web Admin 数据看板 (Dashboard Enhancement)

**目标**：在 Web Admin 展示历史数据和趋势

**功能**：
- 账号级别：发文数、平均互动、增长趋势
- 任务级别：每篇内容的 T+2h/T+24h/T+72h 数据曲线
- 全局：今日任务状态、待审批数、失败数

**验收标准**：
- [ ] Dashboard 展示关键指标
- [ ] 支持按账号筛选
- [ ] 图表展示趋势

**预估工时**: 6h

---

### TASK-007: 多平台支持 (Multi-Platform)

**目标**：支持微信公众号、抖音等平台

**现状**：仅支持小红书

**实现**：
- 抽象 `Publisher` 协议
- 每个平台实现自己的 Adapter
- 配置中指定 `platform: xiaohongshu | wechat | douyin`

**预估工时**: 8h/平台

---

## 📋 实施路线图

### Phase 1: 自动化基础 (1 周)

```
Week 1:
├── Day 1-2: TASK-001 定时调度器
├── Day 3:   TASK-002 Monitor 消费者
├── Day 4:   TASK-004 自动任务创建
└── Day 5:   集成测试 + 修复
```

**里程碑**: 系统可每日自动运行完整循环

### Phase 2: 社交引流 (3 天)

```
Week 2:
├── Day 1-2: TASK-003 社交互动集成
└── Day 3:   防检测优化 + 测试
```

**里程碑**: 发布后自动互动引流

### Phase 3: 增强功能 (按需)

- TASK-005 图片生成
- TASK-006 数据看板
- TASK-007 多平台

---

## 🔧 技术债务

| 项目 | 优先级 | 说明 |
|------|--------|------|
| 测试覆盖率 | 中 | 核心节点缺少单元测试 |
| 错误处理 | 中 | CLI 调用失败时的重试逻辑不完善 |
| 日志规范 | 低 | 部分模块日志格式不统一 |
| 配置校验 | 低 | YAML 配置缺少 schema 校验 |

---

## 📝 决策记录

### 2026-04-02: 调度器技术选型

**决策**: 使用 APScheduler

**理由**:
1. Python 原生，与现有代码无缝集成
2. 支持 cron 表达式，灵活配置
3. 支持持久化（SQLite/Redis），重启不丢失
4. 轻量级，无需额外基础设施

**备选方案**:
- Celery Beat: 太重，需要 Redis/RabbitMQ
- systemd timer: 不跨平台，调试不便
