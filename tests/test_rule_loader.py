"""Tests for rule loader module."""

import pytest
from pathlib import Path

from tools.rule_loader import load_rules, load_rules_text, get_available_scenarios


class TestRuleLoader:
    """Test cases for rule loading functionality."""

    def test_get_available_scenarios(self):
        """Test getting list of available scenarios."""
        scenarios = get_available_scenarios()
        assert isinstance(scenarios, list)
        assert len(scenarios) > 0
        assert "file-upload" in scenarios
        assert "transaction" in scenarios

    def test_load_rules_valid_scenario(self):
        """Test loading rules for a valid scenario."""
        rules = load_rules("file-upload")
        assert isinstance(rules, dict)
        assert rules.get("scenario") == "file-upload"
        assert rules.get("name") == "文件上传场景"
        assert "checks" in rules
        assert len(rules["checks"]) > 0

    def test_load_rules_invalid_scenario(self):
        """Test loading rules for an invalid scenario."""
        with pytest.raises(ValueError):
            load_rules("invalid-scenario")

    def test_load_rules_text_format(self):
        """Test loading rules as formatted text."""
        rules_text = load_rules_text("file-upload")
        assert isinstance(rules_text, str)
        assert "文件上传场景" in rules_text
        assert "检查项" in rules_text

    def test_load_rules_text_contains_severity(self):
        """Test that rules text contains severity indicators."""
        rules_text = load_rules_text("transaction")
        assert "BLOCKER" in rules_text
        assert "WARNING" in rules_text

    def test_transaction_rules(self):
        """Test transaction quality gate rules."""
        rules = load_rules("transaction")
        checks = rules.get("checks", [])

        # Check for known transaction issues
        check_descriptions = [c["question"] for c in checks]
        assert any("private" in d.lower() for d in check_descriptions)
        assert any("内部调用" in d for d in check_descriptions)

    def test_multithread_rules(self):
        """Test multithread quality gate rules."""
        rules = load_rules("multithread")
        checks = rules.get("checks", [])

        # Check for known multithread issues
        check_descriptions = [c["question"] for c in checks]
        assert any("HashMap" in d for d in check_descriptions)
        assert any("无界队列" in d for d in check_descriptions)

    def test_logging_rules(self):
        """Test logging quality gate rules."""
        rules = load_rules("logging")
        checks = rules.get("checks", [])

        # Check for known logging issues
        check_descriptions = [c["question"] for c in checks]
        assert any("printStackTrace" in d for d in check_descriptions)
        assert any("业务标识" in d for d in check_descriptions)

    def test_scenario_rules_have_ids(self):
        """Test that all checks have unique IDs."""
        for scenario in ["file-upload", "table-design", "transaction"]:
            rules = load_rules(scenario)
            checks = rules.get("checks", [])

            ids = [c["id"] for c in checks]
            assert len(ids) == len(set(ids)), f"Duplicate IDs in {scenario}"

    def test_scenario_rules_have_severity(self):
        """Test that all checks have valid severity levels."""
        valid_severities = {"blocker", "warning", "info", "suggestion"}

        for scenario in get_available_scenarios()[:3]:  # Test first 3
            rules = load_rules(scenario)
            checks = rules.get("checks", [])

            for check in checks:
                assert check.get("severity") in valid_severities, (
                    f"Invalid severity in {scenario}: {check.get('severity')}"
                )