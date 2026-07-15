"""Deterministic rule loader for techlead agent.

This module provides file-based rule loading, not vector-based RAG.
Rules are small, structured YAML files with exact mapping by scenario.
"""

import os
from pathlib import Path
from typing import Optional

import yaml

from config import settings

# Scenario to file path mapping
RULE_MAP = {
    # Design review scenarios
    "file-upload": "scenarios/file-upload.yaml",
    "table-design": "scenarios/table-design.yaml",
    "message-queue": "scenarios/message-queue.yaml",
    "monitoring": "scenarios/monitoring.yaml",
    "crud": "scenarios/crud.yaml",
    "cache": "scenarios/cache.yaml",
    "search": "scenarios/search.yaml",
    "notification": "scenarios/notification.yaml",
    "security": "scenarios/security.yaml",
    # Code quality gates
    "transaction": "quality-gates/transaction.yaml",
    "multithread": "quality-gates/multithread.yaml",
    "logging": "quality-gates/logging.yaml",
    "api": "quality-gates/api.yaml",
    "sql": "quality-gates/sql.yaml",
}


def load_rules(scenario: str) -> dict:
    """Load rules for a given scenario from YAML file.

    Args:
        scenario: The scenario identifier (e.g., "file-upload", "transaction")

    Returns:
        dict: Parsed YAML content as dictionary

    Raises:
        ValueError: If scenario is not found in RULE_MAP
        FileNotFoundError: If the rule file doesn't exist
        yaml.YAMLError: If the YAML file is malformed
    """
    if scenario not in RULE_MAP:
        raise ValueError(f"Unknown scenario: {scenario}. Available: {list(RULE_MAP.keys())}")

    file_path = settings.rules_dir / RULE_MAP[scenario]
    if not file_path.exists():
        raise FileNotFoundError(f"Rule file not found: {file_path}")

    with open(file_path, "r", encoding="utf-8") as f:
        content = yaml.safe_load(f)

    return content


def load_rules_text(scenario: str) -> str:
    """Load rules as plain text for injection into prompts.

    Args:
        scenario: The scenario identifier

    Returns:
        str: Rules formatted as plain text
    """
    rules = load_rules(scenario)
    lines = [f"【场景】{rules.get('scenario', scenario)}"]
    lines.append(f"【名称】{rules.get('name', scenario)}")
    lines.append("\n【检查项】")

    for idx, check in enumerate(rules.get("checks", []), 1):
        severity = check.get("severity", "info")
        emoji = {"blocker": "🔴", "warning": "🟡", "info": "🟢"}.get(severity, "⚪")
        lines.append(
            f"{idx}. [{check.get('id', f'C{idx:03d}')}] {check.get('name', 'Unknown')} "
            f"{emoji} {severity.upper()}"
        )
        lines.append(f"   问题：{check.get('question', 'N/A')}")

    return "\n".join(lines)


def get_available_scenarios() -> list[str]:
    """Get list of all available scenarios.

    Returns:
        list: List of scenario identifiers
    """
    return list(RULE_MAP.keys())


def validate_rules_dir() -> bool:
    """Validate that all rule files exist.

    Returns:
        bool: True if all files exist, False otherwise
    """
    missing = []
    for scenario, relative_path in RULE_MAP.items():
        file_path = settings.rules_dir / relative_path
        if not file_path.exists():
            missing.append((scenario, str(file_path)))

    if missing:
        print("⚠️  Missing rule files:")
        for scenario, path in missing:
            print(f"  - {scenario}: {path}")
        return False
    return True