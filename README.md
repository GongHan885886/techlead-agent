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
- [配置说明](#配置说明)
- [开发指南](#开发指南)

## 项目概述

TechLead Manager Agent 是一个基于 AI Harness 架构的多 Agent 系统，帮助技术经理高效完成方案评审、代码审查、交付追踪等日常工作。

### 核心目标

- 🤖 **自动化扫描**：每日自动扫描待评审方案、待处理 MR、在途需求风险
- 📊 **专业化评审**：针对不同场景加载对应规则，精准检查
- 🔄 **人机协作**：关键决策点保留人工确认，不替代技术经理判断
- 📈 **持续成长**：建立"错题本"机制，为每位开发者生成个性化学习建议

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

### 5. 学习建议
- 基于错题本数据生成个性化学习计划
- 输出弱点定位 + 根源分析 + 学习推荐 + 改进目标

## 系统架构

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                         TechLead Manager Agent System                       │
│                                                                             │
│  ┌───────────────────────────────────────────────────────────────────────┐  │
│  │                        Orchestrator Agent                             │  │
│  │   • 意图识别与任务调度                                                │  │
│  └─────────┬─────────────────────┬─────────────────────┬──────────────┘  │
│            │                     │                     │                  │
│  ┌───────────────────┐ ┌───────────────────┐ ┌──────────────────────────┐ │
│  │  DesignReviewer   │ │   CodeReviewer    │ │   DeliveryTracker        │ │
│  │  Agent            │ │   Agent           │ │   Agent                  │ │
│  └───────────────────┘ └───────────────────┘ └──────────────────────────┘ │
│                                                                             │
│  ┌───────────────────────────────────────────────────────────────────────┐│
│  │                          Tool Layer                                   ││
│  │  TAPD API / Git API / 规则加载器 / 通知服务 / 记忆读写                 ││
│  └───────────────────────────────────────────────────────────────────────┘│
│                                                                             │
│  ┌───────────────────────────────────────────────────────────────────────┐│
│  │                    Memory Layer (SQLite)                              ││
│  │  短期记忆 + 长期记忆 + 错题本                                          ││
│  └───────────────────────────────────────────────────────────────────────┘│
└─────────────────────────────────────────────────────────────────────────────┘
```

### Agent 列表

| Agent | 职责 |
|:---|:---|
| Orchestrator | 主控 Agent，理解意图，调度子 Agent |
| DesignReviewer | 方案评审专家 |
| CodeReviewer | 代码审查专家 |
| DeliveryTracker | 交付效能分析师 |
| LearningAdvisor | 学习顾问（基于错题本生成成长计划） |

## 快速开始

### 1. 环境要求

- Python 3.10+
- OpenAI API Key

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
# 复制环境变量模板
cp .env.example .env

# 编辑 .env 文件，填入你的配置
# OPENAI_API_KEY=your_openai_api_key_here
# TAPD_API_USER=your_tapd_username
# ...
```

### 4. 初始化数据库

```bash
python -c "from storage.memory_store import init_db; init_db()"
```

### 5. 启动 CLI

```bash
python main.py scan
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

### 查询错题本

```bash
python main.py profile --developer "李四"
```

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

### 阈值配置

```yaml
# .techlead-rules/thresholds.yaml
risk:
  urgent_days: 3  # 紧急关注：距提测<3天且进度<80%
  warning_days: 5 # 警告：距提测<5天且进度<50%

efficiency:
  anomaly_threshold: 1.3  # 个人效率 > 团队均值 * 1.3 为异常
```

## 开发指南

### 添加新的检查规则

1. 在 `.techlead-rules/scenarios/` 或 `.techlead-rules/quality-gates/` 创建新规则文件
2. 在 `tools/rule_loader.py` 的 `RULE_MAP` 中添加映射
3. 重启服务，规则自动生效

### 添加新的 Agent

1. 在 `agents/` 目录创建新的 Agent 类
2. 在 `prompts/` 目录添加对应的 System Prompt
3. 在 `agents/orchestrator.py` 中注册新的 Agent

### 运行测试

```bash
pytest tests/
```

## 演进路线图

- [x] Sprint 1: CLI 交互 + 规则加载 + 三个工作池扫描
- [x] Sprint 2: DesignReviewer + CodeReviewer 完整实现
- [x] Sprint 3: 人机回环（审批挂起 + 确认唤醒）
- [x] Sprint 4: 错题本记录
- [x] Sprint 5: 画像查询
- [x] Sprint 6: LearningAdvisor Agent
- [ ] Sprint 7: 可观测性（Trace 日志 + Token 统计 + 看板）

## 技术选型

| 组件 | 技术选型 |
|:---|:---|
| LLM | GPT-4o / Claude 3.5 Sonnet |
| Agent 框架 | LangChain |
| 数据库 | SQLite（起步）→ PostgreSQL（生产） |
| API 服务 | FastAPI |
| 日志 | JSON Lines |
| 部署 | Docker + Kubernetes |

## 许可证

MIT License

## 维护者

技术经理 + 开发团队