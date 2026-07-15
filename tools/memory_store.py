"""Memory store for techlead agent using SQLite.

Provides:
- Short-term memory: in-session conversation context (handled by orchestrator)
- Long-term memory: persistent storage in SQLite
- Error tracking: developer issues and profiles
"""

import sqlite3
import json
from datetime import datetime, timedelta
from pathlib import Path
from typing import Optional, List, Dict, Any

from config import settings


def init_db():
    """Initialize the database schema if it doesn't exist."""
    storage_dir = settings.storage_dir
    storage_dir.mkdir(parents=True, exist_ok=True)

    conn = sqlite3.connect(settings.db_path)
    cursor = conn.cursor()

    # Developer issues table
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS developer_issues (
            id TEXT PRIMARY KEY,
            developer_name TEXT NOT NULL,
            issue_type TEXT NOT NULL,
            severity TEXT NOT NULL,
            scenario TEXT,
            description TEXT NOT NULL,
            suggestion TEXT,
            source TEXT NOT NULL,
            mr_id TEXT,
            story_id TEXT,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            is_confirmed INTEGER DEFAULT 1
        )
    """)

    # Developer profiles summary table
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS developer_profiles (
            developer_name TEXT PRIMARY KEY,
            total_issues INTEGER DEFAULT 0,
            blocker_count INTEGER DEFAULT 0,
            warning_count INTEGER DEFAULT 0,
            top_issue_types TEXT,
            last_updated TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    """)

    # Review history table
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS review_history (
            id TEXT PRIMARY KEY,
            review_type TEXT NOT NULL,
            reviewer TEXT,
            target TEXT NOT NULL,
            result TEXT NOT NULL,
            blocker_count INTEGER DEFAULT 0,
            warning_count INTEGER DEFAULT 0,
            suggestion_count INTEGER DEFAULT 0,
            details TEXT,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    """)

    # Team metrics table
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS team_metrics (
            id TEXT PRIMARY KEY,
            metric_type TEXT NOT NULL,
            metric_value REAL NOT NULL,
            unit TEXT,
            timestamp TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            metadata TEXT
        )
    """)

    # Create indexes
    cursor.execute(
        "CREATE INDEX IF NOT EXISTS idx_issues_developer ON developer_issues(developer_name)"
    )
    cursor.execute("CREATE INDEX IF NOT EXISTS idx_issues_type ON developer_issues(issue_type)")
    cursor.execute("CREATE INDEX IF NOT EXISTS idx_issues_created ON developer_issues(created_at)")
    cursor.execute(
        "CREATE INDEX IF NOT EXISTS idx_review_created ON review_history(created_at)"
    )

    conn.commit()
    conn.close()
    print(f"✅ Database initialized at: {settings.db_path}")


def record_issue(
    developer_name: str,
    issue_type: str,
    severity: str,
    description: str,
    suggestion: Optional[str] = None,
    scenario: Optional[str] = None,
    source: str = "manual",
    mr_id: Optional[str] = None,
    story_id: Optional[str] = None,
) -> str:
    """Record a single issue to the error tracking.

    Args:
        developer_name: Name of the developer
        issue_type: Type of issue (e.g., "transaction", "logging")
        severity: Severity level (blocker, warning, info)
        description: Detailed description of the issue
        suggestion: Suggested fix or improvement
        scenario: Scenario where issue was found
        source: Source of the issue (code_review, design_review, manual)
        mr_id: Related merge request ID
        story_id: Related TAPD story ID

    Returns:
        str: The ID of the created issue record
    """
    import uuid

    issue_id = f"issue_{uuid.uuid4().hex[:8]}"

    conn = sqlite3.connect(settings.db_path)
    cursor = conn.cursor()

    cursor.execute(
        """
        INSERT INTO developer_issues
        (id, developer_name, issue_type, severity, scenario, description,
         suggestion, source, mr_id, story_id)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
    """,
        (
            issue_id,
            developer_name,
            issue_type,
            severity,
            scenario,
            description,
            suggestion,
            source,
            mr_id,
            story_id,
        ),
    )

    conn.commit()
    conn.close()

    # Update profile asynchronously
    _update_profile(developer_name)

    return issue_id


def record_issues_batch(developer: str, issues: list, source: str, mr_id: str = None):
    """Record multiple issues at once (batch operation).

    Args:
        developer: Name of the developer
        issues: List of issue dicts with keys: type, severity, description, suggestion, scenario
        source: Source of the issues
        mr_id: Related merge request ID
    """
    import uuid

    conn = sqlite3.connect(settings.db_path)
    cursor = conn.cursor()

    for issue in issues:
        issue_id = f"issue_{uuid.uuid4().hex[:8]}"
        cursor.execute(
            """
            INSERT INTO developer_issues
            (id, developer_name, issue_type, severity, scenario, description,
             suggestion, source, mr_id)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
            (
                issue_id,
                developer,
                issue["type"],
                issue["severity"],
                issue.get("scenario"),
                issue["description"],
                issue.get("suggestion"),
                source,
                mr_id,
            ),
        )

    conn.commit()
    conn.close()

    # Update profile
    _update_profile(developer)


def _update_profile(developer_name: str):
    """Update developer profile summary."""
    conn = sqlite3.connect(settings.db_path)
    cursor = conn.cursor()

    # Get total counts
    cursor.execute(
        """
        SELECT severity, COUNT(*) as count
        FROM developer_issues
        WHERE developer_name = ? AND created_at > datetime('now', '-90 days')
        GROUP BY severity
    """,
        (developer_name,),
    )
    severity_counts = dict(cursor.fetchall())

    # Get top issue types
    cursor.execute(
        """
        SELECT issue_type, COUNT(*) as count
        FROM developer_issues
        WHERE developer_name = ? AND created_at > datetime('now', '-90 days')
        GROUP BY issue_type
        ORDER BY count DESC
        LIMIT 5
    """,
        (developer_name,),
    )
    top_types = cursor.fetchall()

    total_issues = sum(severity_counts.values())
    blocker_count = severity_counts.get("blocker", 0)
    warning_count = severity_counts.get("warning", 0)

    # Format top types as JSON
    top_types_json = json.dumps(
        [{"type": t, "count": c} for t, c in top_types] if top_types else []
    )

    cursor.execute(
        """
        INSERT OR REPLACE INTO developer_profiles
        (developer_name, total_issues, blocker_count, warning_count,
         top_issue_types, last_updated)
        VALUES (?, ?, ?, ?, ?, CURRENT_TIMESTAMP)
    """,
        (developer_name, total_issues, blocker_count, warning_count, top_types_json),
    )

    conn.commit()
    conn.close()


def get_developer_profile(developer: str, days: int = 30) -> Dict[str, Any]:
    """Get developer's issue profile and statistics.

    Args:
        developer: Name of the developer
        days: Number of days to look back

    Returns:
        dict: Developer profile with statistics and recent issues
    """
    conn = sqlite3.connect(settings.db_path)
    cursor = conn.cursor()

    # Get profile summary
    cursor.execute(
        "SELECT * FROM developer_profiles WHERE developer_name = ?", (developer,)
    )
    profile_row = cursor.fetchone()

    # Get recent issues
    cursor.execute(
        """
        SELECT issue_type, severity, description, scenario, source,
               mr_id, story_id, created_at
        FROM developer_issues
        WHERE developer_name = ? AND created_at > datetime('now', '-{} days')
        ORDER BY created_at DESC
        LIMIT 50
    """.format(days),
        (developer,),
    )
    recent_issues = cursor.fetchall()

    # Get issue type breakdown
    cursor.execute(
        """
        SELECT issue_type, severity, COUNT(*) as count
        FROM developer_issues
        WHERE developer_name = ? AND created_at > datetime('now', '-{} days')
        GROUP BY issue_type, severity
        ORDER BY count DESC
    """.format(days),
        (developer,),
    )
    type_breakdown = cursor.fetchall()

    conn.close()

    # Build profile
    profile = {
        "developer": developer,
        "total_issues": 0,
        "blocker_count": 0,
        "warning_count": 0,
        "top_issue_types": [],
        "recent_issues": [],
        "type_breakdown": [],
        "last_updated": None,
    }

    if profile_row:
        profile.update(
            {
                "total_issues": profile_row[1],
                "blocker_count": profile_row[2],
                "warning_count": profile_row[3],
                "top_issue_types": json.loads(profile_row[4]) if profile_row[4] else [],
                "last_updated": profile_row[5],
            }
        )

    # Add detailed issue breakdown
    profile["recent_issues"] = [
        {
            "type": row[0],
            "severity": row[1],
            "description": row[2],
            "scenario": row[3],
            "source": row[4],
            "mr_id": row[5],
            "story_id": row[6],
            "created_at": row[7],
        }
        for row in recent_issues
    ]

    profile["type_breakdown"] = [
        {"type": row[0], "severity": row[1], "count": row[2]} for row in type_breakdown
    ]

    return profile


def get_team_common_issues(days: int = 30) -> Dict[str, Any]:
    """Get aggregate issue statistics across the team.

    Args:
        days: Number of days to look back

    Returns:
        dict: Team-level statistics
    """
    conn = sqlite3.connect(settings.db_path)
    cursor = conn.cursor()

    # Get total issues by type
    cursor.execute(
        """
        SELECT issue_type, severity, COUNT(*) as count
        FROM developer_issues
        WHERE created_at > datetime('now', '-{} days')
        GROUP BY issue_type, severity
        ORDER BY count DESC
        LIMIT 20
    """.format(days),
    )
    common_issues = cursor.fetchall()

    # Get developer-level summary
    cursor.execute(
        """
        SELECT developer_name, total_issues, blocker_count, warning_count
        FROM developer_profiles
        ORDER BY total_issues DESC
    """,
    )
    developer_summaries = cursor.fetchall()

    conn.close()

    return {
        "common_issues": [
            {"type": row[0], "severity": row[1], "count": row[2]} for row in common_issues
        ],
        "developer_summaries": [
            {
                "developer": row[0],
                "total": row[1],
                "blockers": row[2],
                "warnings": row[3],
            }
            for row in developer_summaries
        ],
    }


def record_review(
    review_type: str,
    target: str,
    result: str,
    blocker_count: int = 0,
    warning_count: int = 0,
    suggestion_count: int = 0,
    details: Optional[Dict] = None,
    reviewer: Optional[str] = None,
) -> str:
    """Record a review (design review, code review) to history.

    Args:
        review_type: Type of review (design_review, code_review)
        target: Target identifier (story_id, mr_id)
        result: Review result (pass, fail, pending)
        blocker_count: Number of blocker issues found
        warning_count: Number of warning issues found
        suggestion_count: Number of suggestions
        details: Additional details as dict
        reviewer: Name of the reviewer

    Returns:
        str: The ID of the created review record
    """
    import uuid

    review_id = f"review_{uuid.uuid4().hex[:8]}"

    conn = sqlite3.connect(settings.db_path)
    cursor = conn.cursor()

    cursor.execute(
        """
        INSERT INTO review_history
        (id, review_type, target, result, blocker_count, warning_count,
         suggestion_count, details, reviewer)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
    """,
        (
            review_id,
            review_type,
            target,
            result,
            blocker_count,
            warning_count,
            suggestion_count,
            json.dumps(details) if details else None,
            reviewer,
        ),
    )

    conn.commit()
    conn.close()

    return review_id


def record_team_metric(
    metric_type: str, metric_value: float, unit: str = "", metadata: Optional[Dict] = None
):
    """Record a team-level metric.

    Args:
        metric_type: Type of metric (avg_delivery_days, defect_rate, etc.)
        metric_value: The metric value
        unit: Unit of measurement (days, %, etc.)
        metadata: Additional context
    """
    import uuid

    metric_id = f"metric_{uuid.uuid4().hex[:8]}"

    conn = sqlite3.connect(settings.db_path)
    cursor = conn.cursor()

    cursor.execute(
        """
        INSERT INTO team_metrics
        (id, metric_type, metric_value, unit, metadata)
        VALUES (?, ?, ?, ?, ?)
    """,
        (metric_id, metric_type, metric_value, unit, json.dumps(metadata) if metadata else None),
    )

    conn.commit()
    conn.close()