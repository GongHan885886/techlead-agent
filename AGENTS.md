# Repository Guidelines

## Project Structure & Module Organization

```
techlead-agent/
├── agents/          # Agent modules (orchestrator, code_reviewer, design_reviewer, etc.)
├── tools/           # Tool layer (TAPD client, git client, cache, memory, notifier, rules)
├── config/          # Settings and tool configuration (YAML + pydantic-settings)
├── state/           # Session management for human-in-the-loop workflows
├── utils/           # Logging utilities
├── storage/         # Persistent data: SQLite databases, cache files, trace logs
├── dashboard/       # FastAPI web dashboard with Jinja2 templates
├── prompts/         # System prompt templates for each agent role
├── tests/           # Test suite (mirrors agents/ and tools/ layout)
├── main.py          # CLI entry point (powered by typer)
└── requirements.txt # Python dependencies
```

Agent modules live in `agents/`, with `orchestrator.py` acting as the main controller that routes requests to specialist agents. All agents inherit from `BaseAgent` in `agents/base_agent.py`. Tool implementations are in `tools/` and are consumed by agents at runtime.

## Build, Test, and Development Commands

Run the project from the virtual environment at `venv/`:

| Command | Purpose |
|---|---|
| `python main.py scan` | Daily scan: review pending designs, MRs, and delivery risks |
| `python main.py review-design --author "Name" --scenario "file-upload"` | Deep design review against loaded rules |
| `python main.py review-mr --mr-id "123"` | Code review on a specific MR diff |
| `python main.py profile --developer "Name"` | Generate learning advice from error history |
| `uvicorn dashboard.app:app --port 7820` | Start the FastAPI dashboard |
| `pytest` | Run all tests |
| `pip install -r requirements.txt` | Install dependencies |

## Coding Style & Naming Conventions

- **Indentation**: 4 spaces, no tabs.
- **Naming**: `snake_case` for modules, functions, and variables; `PascalCase` for classes.
- **Type hints**: Required on all function signatures and class attributes.
- **Docstrings**: Google-style docstrings on public modules and methods.
- **Imports**: Standard library first, then third-party, then local. Grouped by section.
- **Linting**: No automated linter is configured; follow the existing conventions in the codebase.

## Testing Guidelines

- **Framework**: pytest with pytest-asyncio for async tests.
- **Test layout**: `tests/test_agents/` and `tests/test_tools/` mirror the source layout.
- **Naming**: Test classes prefixed with `Test`, test methods prefixed with `test_`.
- **Fixtures**: Class-level fixtures in test classes for reusable setup (e.g., agent instances).
- **Coverage**: No formal coverage threshold; critical agent logic and intent routing should have tests.

Run `pytest` from the project root to execute the full suite.

## Commit & Pull Request Guidelines

Commit messages follow the conventional commit format with Chinese descriptions:

```
feat: add multi-level caching system with exact-match LLM cache
fix: restore requirements.txt (accidental deletion)
```

Use `feat:`, `fix:`, `refactor:`, `docs:`, `test:`, or `chore:` prefixes. Pull requests should include a summary of what changed and why. Link related issues where applicable. No strict template required, but keep the description focused on the functional change.
