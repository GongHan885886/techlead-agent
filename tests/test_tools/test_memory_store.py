"""Tests for memory store module."""

import pytest
import tempfile
import os

from tools.memory_store import init_db, record_issue, get_developer_profile, get_team_common_issues


class TestMemoryStore:
    """Test cases for memory store functionality."""

    @pytest.fixture
    def temp_db(self):
        """Create a temporary database for testing."""
        fd, path = tempfile.mkstemp(suffix=".db")
        os.close(fd)

        # Override db_path
        from config import settings
        original_path = settings.db_path
        settings.db_path = path

        yield path

        # Cleanup
        if os.path.exists(path):
            os.unlink(path)
        settings.db_path = original_path

    def test_init_db(self, temp_db):
        """Test database initialization."""
        init_db()

        # Check that database file exists
        assert os.path.exists(temp_db)

    def test_record_issue(self, temp_db):
        """Test recording a single issue."""
        init_db()

        issue_id = record_issue(
            developer_name="张三",
            issue_type="transaction",
            severity="blocker",
            description="事务失效",
            suggestion="改为 public 方法",
        )

        assert issue_id is not None
        assert issue_id.startswith("issue_")

    def test_record_issue_with_metadata(self, temp_db):
        """Test recording issue with additional metadata."""
        init_db()

        issue_id = record_issue(
            developer_name="李四",
            issue_type="logging",
            severity="warning",
            description="日志缺少业务标识",
            suggestion="添加 orderId",
            scenario="logging",
            source="code_review",
            mr_id="123",
        )

        assert issue_id is not None

    def test_get_developer_profile(self, temp_db):
        """Test getting developer profile."""
        init_db()

        # Add some issues
        record_issue("张三", "transaction", "blocker", "事务失效")
        record_issue("张三", "transaction", "blocker", "内部调用")
        record_issue("张三", "logging", "warning", "日志不规范")

        profile = get_developer_profile("张三", days=30)

        assert profile["developer"] == "张三"
        assert profile["total_issues"] >= 3
        assert profile["blocker_count"] >= 2
        assert profile["warning_count"] >= 1
        assert isinstance(profile["recent_issues"], list)

    def test_get_team_common_issues(self, temp_db):
        """Test getting team common issues."""
        init_db()

        # Add issues for multiple developers
        record_issue("张三", "transaction", "blocker", "事务失效")
        record_issue("李四", "transaction", "blocker", "事务失效")
        record_issue("王五", "logging", "warning", "日志问题")

        team = get_team_common_issues(days=30)

        assert "common_issues" in team
        assert "developer_summaries" in team
        assert len(team["common_issues"]) > 0

    def test_profile_type_breakdown(self, temp_db):
        """Test profile issue type breakdown."""
        init_db()

        # Add varied issues
        record_issue("张三", "transaction", "blocker", "问题1")
        record_issue("张三", "transaction", "warning", "问题2")
        record_issue("张三", "logging", "blocker", "问题3")
        record_issue("张三", "multithread", "warning", "问题4")

        profile = get_developer_profile("张三", days=30)

        assert "type_breakdown" in profile
        assert isinstance(profile["type_breakdown"], list)
        assert len(profile["type_breakdown"]) > 0

        # Check breakdown structure
        for item in profile["type_breakdown"]:
            assert "type" in item
            assert "severity" in item
            assert "count" in item