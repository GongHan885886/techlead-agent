# TechLead Manager Agent

> 基于多 Agent 架构的技术经理日常工作自动化系统

[![Python 3.10+](https://img.shields.io/badge/python-3.10+-blue.svg)](https://www.python.org/downloads/)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](https://opensource.org/licenses/MIT)

## 📋 目录

- [项目概述](#项目概述)
- [核心功能](#核心功能)
- [系统架构](#系统架构)
- [快速开始](#快速开始)
- [使用示例](#使用示例)
- [人效看板](#人效看板)
- [配置说明](#配置说明)
- [可观测性](#可观测性)
- [开发指南](#开发指南)

## 项目概述

TechLead Manager Agent 是一个基于多 Agent 架构的 AI 系统，帮助技术经理高效完成方案评审、代码审查、交付追踪、个性化学习建议等日常工作。

### 核心目标

- 🤖 **自动化扫描**：每日自动扫描待评审方案、待处理 MR、在途需求风险
- 📊 **专业化评审**：针对不同场景加载对应规则，精准检查
- 🔄 **人机协作**：关键决策点保留人工确认，不替代技术经理判断
- 📈 **持续成长**：建立"错题本"机制，为每位开发者生成个性化学习方案
- 👁️ **全链路可观测**：Token 追踪、延迟监控、缓存效率、人效看板

## 核心功能

### 1. 每日扫描
- 自动扫描待评审技术方案
- 识别待处理的 Merge Request
- 追踪 TAPD 需求进度和风险
- 生成今日工作摘要

### 2. 方案评审
- 识别技术场景（文件上传/表设计/消息队列等）
- 加载对应规则，逐条检查方案覆盖情况
- 生成 Blocker/Warning 两级缺失项清单

### 3. 代码审查
- 分析 MR diff
- 检查事务失效、多线程安全、异常日志三类问题
- 生成评论草稿，支持人工确认后发送

### 4. 交付追踪
- 获取 TAPD 进行中需求
- 识别进度风险
- 计算效率/质量指标，对比团队均值

### 5. 学习建议（LLM 驱动）
- 基于错题本数据生成个性化学习计划
- **根源分析**：读取具体错误描述，由 LLM 识别错误模式而非泛泛分类
- **精准资源推荐**：匹配具体错误模式推荐学习资料（而非通用书单）
- **验证题目**：每种弱点 2-3 道代码题/改错题/场景题，附答案要点
- **可量化目标**：改进目标可验证，如"2 周内将 transaction 类 Blocker 降为 0"

### 6. 人效看板（Web Dashboard）
- 开发者和团队问题雷达
- 交付周期/缺陷率/CR 吞吐量趋势
- 开发者 5 维能力雷达图
- **LLM 成本与效率面板**：Token 消耗趋势、Agent 延迟 P50/P95、缓存命中率

## 系统架构

```
┌──────────────────────────────────────────────────────────────────────────────┐
│                         TechLead Manager Agent System                         │
│                                                                              │
│  ┌────────────────────────────────────────────────────────────────────────┐  │
│  │                         CLI (main.py / Typer)                          │  │
│  │   scan / review-design / review-mr / profile / dashboard / status      │  │
│  └──────────────────────────────────┬─────────────────────────────────────┘  │
│                                     │                                       │
│  ┌──────────────────────────────────▼─────────────────────────────────────┐  │
│  │                         Orchestrator Agent                             │  │
│  │   • 意图识别（关键词匹配）• 任务调度 • 上下文传递（trace_id/span）      │  │
│  └──┬──────────────┬──────────────┬──────────────┬──────────────────────┘  │
│     │              │              │              │                         │
│  ┌──▼─────────┐ ┌──▼─────────┐ ┌──▼──────────┐ ┌──▼───────────────┐      │
│  │DesignReview │ │CodeReview  │ │DeliveryTrack │ │LearningAdvisor    │      │
│  │er Agent     │ │er Agent    │ │er Agent      │ │Agent (LLM驱动)    │      │
│  └─────────────┘ └────────────┘ └──────────────┘ └──────────────────┘      │
│                                                                              │
│  ┌────────────────────────────────────────────────────────────────────────┐  │
│  │                          Tool Layer                                    │  │
│  │  TAPD API / Git API / 规则加载器 / 通知服务 / 缓存管理器 / 记忆读写    │  │
│  └────────────────────────────────────────────────────────────────────────┘  │
│                                                                              │
│  ┌────────────────────────────────────────────────────────────────────────┐  │
│  │                    Memory Layer (SQLite)                               │  │
│  │  developer_issues │ developer_profiles │ review_history               │  │
│  │  team_metrics     │ **spans** (可观测性) │ stories                    │  │
│  └────────────────────────────────────────────────────────────────────────┘  │
│                                                                              │
│  ┌────────────────────────────────────────────────────────────────────────┐  │
│  │                    Web Dashboard (FastAPI)                              │  │
│  │  • 问题雷达 • 交付趋势 • 5 维雷达图 • 开发者详情                       │  │
│  │  • **LLM 成本面板** • **Token 趋势图** • **Agent 延迟 P50/P95**        │  │
│  │  • **个人提升计划页面**（嵌入/独立）                                    │  │
│  └────────────────────────────────────────────────────────────────────────┘  │
└──────────────────────────────────────────────────────────────────────────────┘
```

### Agent 列表

| Agent | 职责 | 是否调用 LLM |
|:---|:---|:---|
| Orchestrator | 主控 Agent，理解意图，调度子 Agent | ❌ 关键词匹配 |
| DesignReviewer | 方案评审专家 | ✅ 每次场景评审一次 |
| CodeReviewer | 代码审查专家 | ✅ 每个 focus area 一次 |
| DeliveryTracker | 交付效能分析师 | ❌ 纯规则计算 |
| LearningAdvisor | 学习顾问（LLM 驱动） | ✅ 含根源分析/验证题目 |

## 快速开始

### 1. 环境要求

- Python 3.10+
- OpenAI API Key（或兼容接口）

### 2. 安装依赖

```bash
# 克隆项目
git clone <repository-url>
cd techlead-agent

# 创建虚拟环境
python -m venv venv
source venv/bin/activate  # Windows: venv\Scripts\activate

# 安装依赖
pip install -r requirements.txt
```

### 3. 配置环境变量

```bash
cp .env.example .env
# 编辑 .env 文件填入配置
# OPENAI_API_KEY=your_openai_api_key_here
```

### 4. 初始化数据库

```bash
python -c "from tools.memory_store import init_db; init_db()"
```

### 5. 启动

```bash
# CLI 模式
python main.py scan

# Web 看板
python main.py dashboard
```

## 使用示例

### 每日全量扫描

```bash
python main.py scan
```

### 深度方案评审

```bash
python main.py review-design --author "张三" --scenario "file-upload"
```

### 代码 CR 审查

```bash
python main.py review-mr --mr-id "123" --focus "transaction,multithread"
```

### 生成周报

```bash
python main.py weekly-report
```

### 个性化学习建议

```bash
python main.py profile --developer "李四" --days 30
```

### 查看系统状态

```bash
python main.py status
```

## 人效看板

Web 看板基于 FastAPI + Chart.js，提供一站式团队效能可视化和个人提升计划。

### 启动

```bash
python main.py dashboard
# 或指定端口
python main.py dashboard --port 7820 --host 127.0.0.1
```

### 页面

| 页面 | 地址 | 说明 |
|:---|:---|:---|
| 主看板 | `http://127.0.0.1:7820/` | 问题雷达、交付趋势、开发者雷达、LLM 效率面板 |
| 提升计划 | `http://127.0.0.1:7820/learning` | 开发者下拉选择 + 时间范围 + 生成按钮 |

### 看板组件

- **今日待办**：自动聚合待审 MR、高风险需求、超期需求、需关注人员
- **问题雷达**：人员负荷、交付效率、代码质量、CR 节奏等异常检测
- **交付趋势**：交付周期、缺陷率、CR 吞吐量、CR 周转时间
- **开发者雷达**：5 维能力（技术方案评审/代码质量/缺陷控制/交付效率/CR 响应）
- **LLM 效率面板**：Token 消耗趋势、Agent 延迟 P50/P95、预估成本、缓存命中率
- **开发者详情**：issues 列表 + **"生成改进计划"按钮**，支持选择时间范围
- **个人提升计划**：嵌入主看板或独立页面，含根源分析、学习资源、验证题目

### Demo 模式

未配置 API Key 时，访问 `http://127.0.0.1:7820/demo` 使用 demo 数据库查看界面布局。

## 配置说明

### 规则配置

所有规则文件位于 `.techlead-rules/` 目录，采用 YAML 格式：

```yaml
# .techlead-rules/scenarios/file-upload.yaml
scenario: file-upload
name: 文件上传场景
checks:
  - id: F001
    name: 文件大小限制
    question: 是否明确限制单文件和总文件大小？
    severity: blocker
```

### 环境变量

| 变量 | 说明 | 默认值 |
|:---|:---|:---|
| `OPENAI_API_KEY` | LLM API 密钥 | 必填 |
| `LLM_MODEL` | 模型名 | `gpt-4o` |
| `TRACE_ENABLED` | 是否启用追踪日志 | `true` |
| `LOG_LEVEL` | 日志级别 | `INFO` |
| `CACHE_ENABLED` | 是否启用缓存 | `true` |
| `NOTIFICATION_ENABLED` | 是否启用通知 | `true` |

## 可观测性

### Span-based Tracing

每次 LLM 调用和 Agent 执行都写入 `spans` 表（SQLite）+ `traces_*.jsonl`（JSON 冷备份）：

| 指标 | 存储位置 | 查询方式 |
|:---|:---|:---|
| Token 消耗 | spans 表 | `SELECT SUM(total_tokens) FROM spans WHERE type='llm_call'` |
| 延迟 P50/P95 | spans 表 | `SELECT AVG(duration_ms), PERCENTILE...` |
| 调用链 | spans 表 | `SELECT * FROM spans WHERE trace_id='xxx'` |
| 缓存命中 | spans 表 | `SELECT cache_hit, COUNT(*) FROM spans GROUP BY cache_hit` |
| 原始日志 | JSONL 文件 | `grep / jq traces_*.jsonl` |

### Dashboard 可观测 API

| 端点 | 说明 |
|:---|:---|
| `GET /api/cost?days=7` | Token 消耗和预估成本汇总 |
| `GET /api/latency?days=7` | 每个 Agent 的 P50/P95/P99 延迟 |
| `GET /api/llm-trends?days=30` | 每日调用量和 Token 趋势 |
| `GET /api/cache-efficiency?days=7` | 缓存命中率和节省的 Token |

## 开发指南

### 添加新的检查规则

1. 在 `.techlead-rules/scenarios/` 或 `.techlead-rules/quality-gates/` 创建新规则文件
2. 在 `tools/rule_loader.py` 的 `RULE_MAP` 中添加映射
3. 重启服务，规则自动生效

### 添加新的 Agent

1. 在 `agents/` 目录创建新的 Agent 类，继承 `BaseAgent`
2. 在 `prompts/` 目录添加对应的 System Prompt
3. 在 `agents/orchestrator.py` 中注册新的 Agent

### 运行测试

```bash
pytest tests/
```

### 项目结构

```
techlead-agent/
├── agents/            # Agent 模块（5 个 Agent）
├── tools/             # 工具层（TAPD/Git/缓存/规则/记忆/通知）
├── config/            # 配置管理（Pydantic Settings + YAML）
├── state/             # Session 管理（人机回环）
├── utils/             # 日志工具（JSON Lines + 彩色输出）
├── storage/           # 数据存储（SQLite + JSONL + 缓存文件）
├── dashboard/         # FastAPI Web 看板 + 模板
├── prompts/           # System Prompt 模板
├── tests/             # 测试套件
├── .techlead-rules/   # YAML 规则文件（场景 + 质量门禁）
└── main.py            # CLI 入口
```

## 演进路线图

- [x] Sprint 1: CLI 交互 + 规则加载 + 每日扫描
- [x] Sprint 2: DesignReviewer + CodeReviewer 完整实现
- [x] Sprint 3: 人机回环（审批挂起 + 确认唤醒）
- [x] Sprint 4: 错题本记录（SQLite + developer_issues 表）
- [x] Sprint 5: 画像查询 + 团队对比
- [x] Sprint 6: LearningAdvisor Agent（LLM 驱动根源分析 + 验证题目）
- [x] Sprint 7: 可观测性（Span-based Tracing + spans 表 + 双写）
- [x] Sprint 8: 人效看板（FastAPI + Chart.js 主看板）
- [x] Sprint 9: 个人提升计划页面（嵌入主看板 + 独立页面）
- [x] Sprint 10: LLM 效率面板（Token 趋势 + 延迟 P50/P95 + 成本估算）
- [x] Sprint 11: Demo 模式（无 API Key 可预览界面）
- [ ] Sprint 12: 生产环境（PostgreSQL 支持 + 多团队隔离）
- [ ] Sprint 13: 规则管理后台（在线编辑 YAML + 版本管理）

## 技术选型

| 组件 | 技术选型 |
|:---|:---|
| LLM | OpenAI GPT-4o / DeepSeek |
| Agent 框架 | 基于 Python 的自定义多 Agent 架构 |
| 数据库 | SQLite（spans 表 + 错题本 + 团队指标） |
| CLI | Typer + Rich |
| Web 看板 | FastAPI + Chart.js |
| 日志 | JSON Lines（冷备）+ SQLite（热查询） |
| 配置 | Pydantic Settings + .env |

## 许可证

MIT License

## 维护者

技术经理 + 开发团队