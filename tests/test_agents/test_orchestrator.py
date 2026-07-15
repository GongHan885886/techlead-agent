"""Tests for orchestrator agent."""

import pytest
import asyncio

from agents.orchestrator import OrchestratorAgent


class TestOrchestratorAgent:
    """Test cases for orchestrator agent."""

    @pytest.fixture
    def orchestrator(self):
        """Create orchestrator agent instance."""
        return OrchestratorAgent()

    def test_identify_intent_scan(self, orchestrator):
        """Test intent identification for scan command."""
        assert orchestrator._identify_intent("扫描今天的事情") == "scan"
        assert orchestrator._identify_intent("scan") == "scan"
        assert orchestrator._identify_intent("有什么需要关注的") == "scan"

    def test_identify_intent_review_design(self, orchestrator):
        """Test intent identification for design review."""
        assert orchestrator._identify_intent("评审张三的方案") == "deep_review"
        assert orchestrator._identify_intent("review design") == "deep_review"
        assert orchestrator._identify_intent("深度评审") == "deep_review"

    def test_identify_intent_code_review(self, orchestrator):
        """Test intent identification for code review."""
        assert orchestrator._identify_intent("cr mr 123") == "code_review"
        assert orchestrator._identify_intent("review-mr 123") == "code_review"
        assert orchestrator._identify_intent("代码审查") == "code_review"

    def test_identify_intent_learning_advice(self, orchestrator):
        """Test intent identification for learning advice."""
        assert orchestrator._identify_intent("给张三出学习建议") == "learning_advice"
        assert orchestrator._identify_intent("profile 张三") == "learning_advice"
        assert orchestrator._identify_intent("错题") == "learning_advice"

    def test_identify_intent_confirm(self, orchestrator):
        """Test intent identification for confirm."""
        assert orchestrator._identify_intent("确认发送") == "confirm"
        assert orchestrator._identify_intent("放行") == "confirm"
        assert orchestrator._identify_intent("confirm") == "confirm"

    def test_identify_intent_cancel(self, orchestrator):
        """Test intent identification for cancel."""
        assert orchestrator._identify_intent("取消") == "cancel"
        assert orchestrator._identify_intent("放弃") == "cancel"

    def test_identify_intent_unknown(self, orchestrator):
        """Test intent identification for unknown messages."""
        assert orchestrator._identify_intent("随机消息") == "unknown"
        assert orchestrator._identify_intent("hello world") == "unknown"

    @pytest.mark.asyncio
    async def test_process_scan(self, orchestrator):
        """Test processing scan intent."""
        result = await orchestrator.process({"message": "scan"})

        assert result["intent"] == "scan"
        assert "stories" in result
        assert "mrs" in result
        assert "timestamp" in result

    @pytest.mark.asyncio
    async def test_process_help(self, orchestrator):
        """Test processing help intent."""
        result = await orchestrator.process({"message": "help"})

        assert result["intent"] == "help"
        assert "message" in result
        assert "可用命令" in result["message"]

    @pytest.mark.asyncio
    async def test_process_code_review_without_mr_id(self, orchestrator):
        """Test code review without MR ID lists available MRs."""
        result = await orchestrator.process({"message": "review-mr"})

        assert result["intent"] == "code_review"
        assert "available_mrs" in result
        assert "message" in result

    def test_generate_help(self, orchestrator):
        """Test help message generation."""
        result = orchestrator._generate_help()

        assert result["intent"] == "help"
        assert "可用命令" in result["message"]
        assert "scan" in result["message"]
        assert "review-design" in result["message"]

    def test_analyze_story_risks(self, orchestrator):
        """Test story risk analysis."""
        stories = [
            {"title": "Story 1", "progress": 60, "due_date": "2026-07-15"},
            {"title": "Story 2", "progress": 90, "due_date": "2026-07-14"},
            {"title": "Story 3", "progress": 50, "due_date": "2026-07-15"},
        ]

        results = {"stories": []}
        orchestrator._analyze_story_risks(stories, results)

        assert "high_risk_stories" in results
        assert "warning_stories" in results
        assert len(results["stories"]) == 3