"""Talent development and error tracking tools.

This module provides functions for managing developer "error books"
and generating learning recommendations.
"""

from datetime import datetime
from typing import List, Dict, Any, Optional
from config import settings
from tools.memory_store import (
    record_issue,
    record_issues_batch,
    get_developer_profile,
    get_team_common_issues,
)


class TalentDeveloper:
    """Manages developer talent tracking and learning recommendations."""

    @staticmethod
    def add_error_entry(
        developer: str,
        issue_type: str,
        severity: str,
        description: str,
        suggestion: Optional[str] = None,
        scenario: Optional[str] = None,
        source: str = "manual",
        mr_id: Optional[str] = None,
        story_id: Optional[str] = None,
    ) -> str:
        """Add a single error entry to developer's error book.

        Args:
            developer: Developer's name
            issue_type: Type of issue (transaction, logging, etc.)
            severity: Severity level (blocker, warning, info)
            description: Detailed description
            suggestion: Suggested fix
            scenario: Scenario where issue occurred
            source: Source of the error
            mr_id: Related MR ID
            story_id: Related story ID

        Returns:
            str: Error entry ID
        """
        return record_issue(
            developer_name=developer,
            issue_type=issue_type,
            severity=severity,
            description=description,
            suggestion=suggestion,
            scenario=scenario,
            source=source,
            mr_id=mr_id,
            story_id=story_id,
        )

    @staticmethod
    def batch_add_errors(
        developer: str,
        errors: List[Dict[str, Any]],
        source: str = "code_review",
        mr_id: Optional[str] = None,
    ):
        """Add multiple errors at once (e.g., after CR confirmation).

        Args:
            developer: Developer's name
            errors: List of error dicts with keys: type, severity, description, suggestion, scenario
            source: Source of errors
            mr_id: Related MR ID
        """
        issues = [
            {
                "type": e.get("type", "unknown"),
                "severity": e.get("severity", "info"),
                "description": e.get("description", ""),
                "suggestion": e.get("suggestion"),
                "scenario": e.get("scenario"),
            }
            for e in errors
        ]
        record_issues_batch(developer, issues, source, mr_id)

    @staticmethod
    def get_profile(developer: str, days: int = 30) -> Dict[str, Any]:
        """Get developer's error profile.

        Args:
            developer: Developer's name
            days: Number of days to look back

        Returns:
            dict: Profile with statistics and recent errors
        """
        return get_developer_profile(developer, days)

    @staticmethod
    def get_team_overview(days: int = 30) -> Dict[str, Any]:
        """Get team-level error overview.

        Args:
            days: Number of days to look back

        Returns:
            dict: Team statistics and common issues
        """
        return get_team_common_issues(days)

    @staticmethod
    def generate_learning_context(developer: str, days: int = 30) -> str:
        """Generate formatted context for learning advisor agent.

        Args:
            developer: Developer's name
            days: Number of days to look back

        Returns:
            str: Formatted context string
        """
        profile = get_developer_profile(developer, days)
        team = get_team_common_issues(days)

        # Calculate team averages
        total_blockers = sum(
            d["blockers"] for d in team["developer_summaries"] if d["blockers"]
        )
        avg_blockers = total_blockers / len(team["developer_summaries"]) if team else 0

        total_issues = sum(d["total"] for d in team["developer_summaries"] if d["total"])
        avg_issues = total_issues / len(team["developer_summaries"]) if team else 0

        # Build context
        lines = [
            f"【开发者】{developer}",
            f"【数据时间范围】最近 {days} 天",
            "",
            "【错题统计】",
            f"- 总问题数：{profile['total_issues']} 个",
            f"- Blocker：{profile['blocker_count']} 个",
            f"- Warning：{profile['warning_count']} 个",
            "",
            "【高频问题类型】",
        ]

        for item in profile["type_breakdown"][:5]:
            emoji = {"blocker": "🔴", "warning": "🟡", "info": "🟢"}.get(item["severity"], "⚪")
            lines.append(
                f"- {item['type']}：{item['count']} 次 {emoji} {item['severity'].upper()}"
            )

        lines.append("")
        lines.append("【团队对比】")
        lines.append(f"- 个人 Blocker 占比：{avg_blockers:.1f}%（团队平均：{avg_issues:.1f}%）")

        lines.append("")
        lines.append("【最近 5 次问题】")
        for issue in profile["recent_issues"][:5]:
            lines.append(f"- {issue['type']}：{issue['description'][:50]}...")
            lines.append(f"  严重程度：{issue['severity']} | 来源：{issue['source']}")

        return "\n".join(lines)


# Convenience functions for backward compatibility
add_error_entry = TalentDeveloper.add_error_entry
batch_add_errors = TalentDeveloper.batch_add_errors
get_profile = TalentDeveloper.get_profile
get_team_overview = TalentDeveloper.get_team_overview
generate_learning_context = TalentDeveloper.generate_learning_context