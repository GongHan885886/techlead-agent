# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

TechLead Manager Agent is a multi-agent AI system for technical managers. It automates daily workflows including design reviews, code reviews, delivery tracking, and generates personalized learning recommendations based on error patterns.

**Key Principles:**
- Multi-agent architecture: Orchestrator routes to specialist agents
- YAML-based rule system for reviews and quality gates
- SQLite memory store for context and error tracking
- Human-in-the-loop: critical decisions require confirmation
- Integration with external systems (TAPD, GitLab)

## Commands

```bash
# Initialize and setup
python main.py scan                    # Daily scan: pending designs, MRs, TAPD risks
python main.py review-design --author "张三" --scenario "file-upload"
python main.py review-mr --mr-id "123" --focus "transaction,logging"
python main.py profile --developer "李四" --days 30
python main.py weekly-report
python main.py status                  # Check system configuration and database status
python main.py help                    # Show all available commands

# Development
pytest tests/                          # Run all tests
pytest tests/test_agents/              # Test agents
pytest tests/test_tools/               # Test tools
python -m venv venv                    # Create virtual environment (if needed)
pip install -r requirements.txt       # Install dependencies
```

## Architecture

### Multi-Agent System

```
┌─────────────────────────────────────────────┐
│        OrchestratorAgent (main.py)          │
│  • Intent recognition via INTENTS dict       │
│  • Session management via SessionManager     │
│  • Routes to specialist agents              │
└───────────────┬─────────────────────────────┘
                │
    ┌───────────┼───────────┬──────────────┐
    ▼           ▼           ▼              ▼
┌─────────┐ ┌─────────┐ ┌──────────┐ ┌────────────┐
│Design   │ │Code     │ │Delivery  │ │Learning    │
│Reviewer │ │Reviewer │ │Tracker   │ │Advisor     │
└─────────┘ └─────────┘ └──────────┘ └────────────┘
```

**Agents:**
- `OrchestratorAgent`: Routes requests, manages sessions, handles confirmations
- `DesignReviewerAgent`: Loads scenario-specific rules, reviews technical designs
- `CodeReviewerAgent`: Analyzes MR diffs, checks transaction safety, multithreading, logging
- `DeliveryTrackerAgent`: Fetches TAPD stories, calculates efficiency metrics
- `LearningAdvisorAgent`: Generates personalized learning plans from error profiles

### Tool Layer

- `TAPDClient`: Integrates with TAPD for story fetching and progress tracking
- `GitClient`: GitLab API integration for MR fetching and comment posting
- `MemoryStore`: SQLite-based storage for short/long term memory and error book
- `RuleLoader`: Loads YAML rules from `.techlead-rules/`
- `Notifier`: Sends notifications via webhook/email
- `TalentDeveloper`: Analyzes developer error patterns

### Rule System

**Scenarios** (`.techlead-rules/scenarios/`): Business scenario-specific rules (file-upload, table-design, search, etc.)

**Quality Gates** (`.techlead-rules/quality-gates/`): Code quality rules (transaction, multithread, logging)

Each rule file contains:
```yaml
scenario: file-upload
name: 文件上传场景
checks:
  - id: F001
    name: 文件大小限制
    question: 是否明确限制单文件和总文件大小？
    severity: blocker
```

**Rule Loader** (`tools/rule_loader.py`): Maps scenario names to rule files via `RULE_MAP`.

## Memory System

**SQLite Database** (`storage/memory.db`):
- **Short-term memory**: Current session context
- **Long-term memory**: Persistent developer profiles
- **Error book**: `error_book` table with fields: `id`, `developer`, `type`, `severity`, `description`, `timestamp`

**Key Functions:**
- `MemoryStore`: CRUD operations for memory and error book
- `init_db()`: Initialize database schema

## Workflow Patterns

### Design Review Flow

1. User calls `review-design` with author and optional scenario
2. Orchestrator routes to `DesignReviewerAgent`
3. Agent loads scenario rules from YAML
4. Agent prompts LLM with design document and rules
5. Returns blocker/warning/suggestion findings
6. If blockers found, agent posts to session pending task queue

### Code Review Flow

1. User calls `review-mr` with MR ID and optional focus areas
2. Orchestrator routes to `CodeReviewerAgent`
3. Agent fetches MR diff via `GitClient`
4. Agent applies LLM prompt with focus areas
5. Returns structured findings: blockers, warnings, suggestions
6. Findings can be confirmed by user before posting comments

### Learning Advisor Flow

1. User calls `profile` with developer name and days range
2. Agent queries `error_book` for developer's errors
3. Agent calculates statistics (type breakdown, severity counts)
4. Agent generates learning recommendations with root cause analysis
5. Returns formatted report with weak points and improvement goals

## Configuration

**Environment Variables** (`.env`):
- `OPENAI_API_KEY`: Required for LLM calls
- `LLM_MODEL`: Model to use (default: gpt-4o)
- `TAPD_API_USER/PASSWORD/COMPANY_ID`: TAPD integration
- `GITLAB_TOKEN/URL/DEFAULT_PROJECT_ID`: GitLab integration
- `DB_PATH`: Database file location
- `TRACE_ENABLED`: Enable detailed execution logging
- `LOG_LEVEL`: Logging verbosity

**System Settings** (`config/settings.py`):
- `rules_dir`: Path to `.techlead-rules/`
- `logs_dir`: Path to log files
- `llm_temperature`: 0.1 for deterministic responses
- `session_timeout_minutes`: Inactivity cleanup

## Important Notes

### Rule Loading
- All rules must be defined in `.techlead-rules/` and loaded via `RuleLoader`
- Adding a new scenario requires creating the YAML file AND registering it in `RULE_MAP`
- `validate_rules_dir()` checks if rule files exist at startup

### Agent Architecture
- All agents inherit from `BaseAgent` (`agents/base_agent.py`)
- Each agent has `_load_system_prompt()` method that reads from `prompts/agent_name_system.txt`
- LLM calls use `llm_call()` with temperature=0.1 (low for consistency)
- Trace logging is optional but enabled by default for observability

### Session Management
- Sessions are managed by `SessionManager` in `state/session_manager.py`
- Pending tasks are stored in the session context
- Human-in-the-loop: confirmations must be manually triggered via CLI
- Sessions timeout after `SESSION_TIMEOUT_MINUTES` of inactivity

### Integration Points
- **TAPD**: Disabled by default (`tapd.enabled: false`), requires credentials to enable
- **GitLab**: Disabled by default (`gitlab.enabled: false`), requires token to enable
- **Notifications**: Disabled by default (`notification.enabled: false`)

### Testing
- Tests are organized by component: `tests/test_agents/` and `tests/test_tools/`
- Rule loader tests verify YAML parsing
- Agent tests verify intent recognition and routing
- No integration tests (mock external APIs)

### Error Handling
- All LLM calls are wrapped in try-except with logging
- Failed tool calls return structured error responses
- Missing rule files fall back to mock data with warning
- Database operations are wrapped in transaction checks

## Adding New Features

### Adding a New Agent

1. Create agent class in `agents/` inheriting from `BaseAgent`
2. Implement `async def process(self, input_data: Dict) -> Dict`
3. Add system prompt in `prompts/agent_name_system.txt`
4. Register agent in `OrchestratorAgent._get_specialist()`
5. Add intent mapping in `OrchestratorAgent.INTENTS`
6. Add CLI command in `main.py`

### Adding a New Review Rule

1. Create YAML file in `.techlead-rules/scenarios/` or `.techlead-rules/quality-gates/`
2. Register in `tools/rule_loader.py RULE_MAP`
3. Update system prompts to reference new rules
4. Test with `review-design` or `review-mr` commands

### Adding a New CLI Command

1. Add `@app.command()` function in `main.py`
2. Call `OrchestratorAgent().process()` with appropriate parameters
3. Display results using Rich table/panel formatting
4. Update `help_command()` with usage description
