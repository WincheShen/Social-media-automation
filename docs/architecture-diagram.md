# 社交媒体自动化系统架构图

```mermaid
flowchart TD
    subgraph LOOP ["🔄 自动化发文循环（每日执行）"]
        direction TB

        subgraph DC ["① 数据采集层"]
            DC1["🌐 外部数据采集\n(Tavily 热点搜索)"]
            DC2["📊 平台内数据采集\n(小红书 search-feeds CLI)"]
            DC3["📈 历史发文反馈\n(点赞/收藏/评论/阅读量)"]
        end

        subgraph AN ["② 分析师"]
            AN1["🧠 Logic Analyst\n(Claude claude-3.7-opus)"]
            AN2["今日热点 Topic 识别\n流量原因分析\n（有流量/无流量的帖子归因）"]
        end

        subgraph RG ["③ 选题 & 数据补充"]
            RG1["📌 确定今日发文方向"]
            RG2["🔍 Data Collector 定向抓取\n(Gemini 2.5 Flash)"]
        end

        subgraph CR ["④ 创作师"]
            CR1["✍️ Copywriter\n(Claude claude-3.7-sonnet)"]
            CR2["拟人化创作\n结合角色人设 & 平台风格"]
        end

        subgraph SO ["⑤ 策略优化师"]
            SO1["🎯 Strategist\n(GPT-4o)"]
            SO2["内容深度优化\n标题/结构/hashtag"]
            SO3["生成配图 / 封面\n(Image Gen / Pillow)"]
        end

        subgraph SC ["⑥ 安全审核"]
            SC1["🛡️ Safety Check\n敏感词过滤\n合规性检查"]
        end

        subgraph RV ["⑦ 人工审核（可选）"]
            RV1["👤 Review Gate\n仅 review_mode 账号触发\n管理员在 Web Admin 审批"]
        end

        subgraph PB ["⑧ 发布执行"]
            PB1["🤖 XhsCliAdapter\nfill-publish → 预览 → click-publish"]
            PB2["📱 小红书创作平台\n(Chrome CDP 自动化)"]
        end

        subgraph MN ["⑨ 发后监控"]
            MN1["📡 Post Monitor\n(get-feed-detail CLI)"]
            MN2["记录 feed_id / xsec_token\n阅读/点赞/收藏/评论数"]
        end

        subgraph FB ["⑩ 反馈记忆更新"]
            FB1["💾 Feedback Memory\n(SQLite + YAML)"]
            FB2["更新角色记忆库\n优化下次选题策略"]
        end
    end

    subgraph INFRA ["⚙️ 基础设施"]
        CFG["🗂️ 角色配置\nconfig/identities/*.yaml\n(账号/模型/关键词/风格)"]
        WEB["🖥️ Web Admin\nNext.js 管理后台\n任务管理 / 审批 / 数据看板"]
        DB["🗄️ SQLite\nweb_tasks.db\n任务状态 / 发文记录"]
        CHR["🌏 Chrome\n多账号独立实例\nXHS_01:9222 XHS_02:9223"]
    end

    %% 主流程
    DC1 & DC2 & DC3 --> AN1
    AN1 --> AN2
    AN2 --> RG1
    RG1 --> RG2
    RG2 --> CR1
    CR1 --> CR2
    CR2 --> SO1
    SO1 --> SO2 & SO3
    SO2 & SO3 --> SC1
    SC1 -->|"通过"| RV1
    SC1 -->|"auto 模式直接跳过"| PB1
    RV1 -->|"审批通过"| PB1
    RV1 -->|"驳回"| CR1
    PB1 --> PB2
    PB2 --> MN1
    MN1 --> MN2
    MN2 --> FB1
    FB1 --> FB2

    %% 反馈循环（关键！）
    FB2 -->|"📊 下一个发文周期\n携带历史表现数据"| DC3
    MN2 -->|"实时数据"| AN1

    %% 基础设施连接
    CFG -.->|"角色人设 & 模型配置"| AN1 & CR1 & SO1
    WEB -.->|"触发任务 / 审批"| RV1
    WEB -.->|"查看结果"| DB
    DB -.->|"任务状态同步"| WEB
    CHR -.->|"CDP 连接"| PB1

    %% 样式
    classDef collector fill:#e3f2fd,stroke:#1976d2,color:#0d47a1
    classDef analyst fill:#f3e5f5,stroke:#7b1fa2,color:#4a148c
    classDef creator fill:#e8f5e9,stroke:#388e3c,color:#1b5e20
    classDef publish fill:#fff3e0,stroke:#f57c00,color:#e65100
    classDef monitor fill:#fce4ec,stroke:#c62828,color:#b71c1c
    classDef infra fill:#f5f5f5,stroke:#757575,color:#212121

    class DC1,DC2,DC3 collector
    class AN1,AN2,RG1,RG2 analyst
    class CR1,CR2,SO1,SO2,SO3 creator
    class SC1,RV1,PB1,PB2 publish
    class MN1,MN2,FB1,FB2 monitor
    class CFG,WEB,DB,CHR infra
```

## 各角色职责说明

| 角色 | 模型 | 职责 |
|------|------|------|
| **Data Collector** | Gemini 2.5 Flash | 外部热点抓取 + 小红书内搜索 + 读取历史反馈 |
| **Logic Analyst** | Claude claude-3.7-opus | 分析今日 Topic / 流量归因 / 内容策略建议 |
| **Copywriter** | Claude claude-3.7-sonnet | 拟人化创作，结合角色人设写小红书风格文案 |
| **Strategist** | GPT-4o | 二次优化：标题、结构、hashtag、配图方向 |
| **Safety Check** | 规则引擎 | 敏感词过滤 + 合规性检查 |
| **Review Gate** | 人工 | 仅 review 模式账号触发，Web Admin 页面审批 |
| **XhsCliAdapter** | CDP 自动化 | fill-publish → 人工预览 → click-publish |
| **Post Monitor** | CLI | 发布后定时拉取阅读/互动数据 |
| **Feedback Memory** | SQLite | 将本次表现写回记忆库，影响下次选题和创作策略 |

## 当前缺失 / 待实现

- [ ] **自动触发循环**：目前需要手动在 Web Admin 创建任务，缺少定时调度器（cron/scheduler）
- [ ] **分析师介入选题**：Logic Analyst 目前主要做内容安全分析，尚未实现流量归因 → 选题建议的闭环
- [ ] **策略优化师配图**：图片生成逻辑（Image Gen）尚未完整对接，目前仅有 Pillow 生成占位封面
- [ ] **社交互动引擎**：`social_interaction.py` 已实现但未集成进主循环（点赞/评论/互动趋势）
