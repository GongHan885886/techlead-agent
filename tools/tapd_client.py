"""TAPD client for fetching stories and bugs.

TAPD (Tencent Agile Product Development) API integration.
"""

import base64
import json
from typing import List, Dict, Any, Optional
from urllib.parse import urlencode

import httpx

from config import settings
from tools.cache_manager import get_cache_manager


class TAPDClient:
    """Client for TAPD API operations."""

    def __init__(
        self,
        api_user: Optional[str] = None,
        api_password: Optional[str] = None,
        company_id: Optional[str] = None,
        timeout: int = 30,
    ):
        """Initialize TAPD client.

        Args:
            api_user: TAPD username
            api_password: TAPD password or API token
            company_id: TAPD company ID
            timeout: Request timeout in seconds
        """
        self.api_user = api_user or settings.tapd_api_user
        self.api_password = api_password or settings.tapd_api_password
        self.company_id = company_id or settings.tapd_company_id
        self.api_base = "https://api.tapd.cn"
        self.timeout = timeout
        self._client = None

        # Basic auth header
        if self.api_user and self.api_password:
            credentials = f"{self.api_user}:{self.api_password}"
            self.auth_header = {
                "Authorization": f"Basic {base64.b64encode(credentials.encode()).decode()}"
            }
        else:
            self.auth_header = {}

    @property
    def client(self) -> httpx.Client:
        """Lazy-loaded HTTP client."""
        if self._client is None:
            self._client = httpx.Client(
                base_url=self.api_base,
                headers=self.auth_header,
                timeout=self.timeout,
            )
        return self._client

    def is_configured(self) -> bool:
        """Check if TAPD credentials are configured."""
        return bool(self.api_user and self.api_password and self.company_id)

    async def fetch_stories(
        self,
        status: str = "进行中",
        workspace_id: Optional[str] = None,
        limit: int = 100,
    ) -> List[Dict[str, Any]]:
        """Fetch stories from TAPD with caching.

        Args:
            status: Story status filter
            workspace_id: Workspace ID (defaults to company_id)
            limit: Maximum number of stories to fetch

        Returns:
            List of story dictionaries
        """
        if not self.is_configured():
            print("⚠️  TAPD not configured, returning mock data")
            return self._mock_stories()

        workspace_id = workspace_id or self.company_id
        params = {
            "workspace_id": workspace_id,
            "status": status,
            "limit": limit,
            "fields": "id,name,owner,status,progress,begin_date,due_date,modified,priority",
        }

        # Try to get from cache
        cache_manager = get_cache_manager()
        cache_key = f"tapd_stories:{workspace_id}:{status}"
        cached = cache_manager.get_http(
            url=f"/stories",
            method="GET",
            params=params,
            headers=self.auth_header
        )
        if cached is not None:
            return cached

        try:
            response = self.client.get(f"/stories?{urlencode(params)}")
            response.raise_for_status()
            data = response.json()

            stories = []
            for item in data.get("data", {}).get("Story", []):
                stories.append(self._parse_story(item))

            # Cache the result (10 minutes TTL for TAPD data)
            cache_manager.set_http(
                url=f"/stories",
                method="GET",
                params=params,
                headers=self.auth_header,
                data=stories,
                ttl_minutes=10
            )

            return stories

        except Exception as e:
            print(f"⚠️  Failed to fetch TAPD stories: {e}")
            return self._mock_stories()

    async def fetch_bugs(
        self,
        story_id: Optional[str] = None,
        owner: Optional[str] = None,
        days: int = 30,
        workspace_id: Optional[str] = None,
    ) -> List[Dict[str, Any]]:
        """Fetch bugs from TAPD.

        Args:
            story_id: Filter by story ID
            owner: Filter by owner name
            days: Number of days to look back
            workspace_id: Workspace ID

        Returns:
            List of bug dictionaries
        """
        if not self.is_configured():
            return self._mock_bugs()

        workspace_id = workspace_id or self.company_id
        params = {
            "workspace_id": workspace_id,
            "limit": 200,
            "fields": "id,title,severity,owner,created,story_id,workspace_id",
        }

        if story_id:
            params["story_id"] = story_id
        if owner:
            params["owner"] = owner

        try:
            response = self.client.get(f"/bugs?{urlencode(params)}")
            response.raise_for_status()
            data = response.json()

            bugs = []
            for item in data.get("data", {}).get("Bug", []):
                bug = self._parse_bug(item)
                # Filter by days if specified
                if days and bug["days_ago"] <= days:
                    bugs.append(bug)

            return bugs

        except Exception as e:
            print(f"⚠️  Failed to fetch TAPD bugs: {e}")
            return self._mock_bugs()

    def _parse_story(self, item: Dict) -> Dict[str, Any]:
        """Parse TAPD story API response.

        Args:
            item: Raw story data from API

        Returns:
            Normalized story dictionary
        """
        return {
            "id": item.get("id"),
            "title": item.get("name", ""),
            "owner": item.get("Owner", ""),
            "status": item.get("status", ""),
            "progress": int(item.get("progress", 0)),
            "begin_date": item.get("begin", ""),
            "due_date": item.get("due", ""),
            "modified": item.get("modified", ""),
            "priority": item.get("priority", ""),
        }

    def _parse_bug(self, item: Dict) -> Dict[str, Any]:
        """Parse TAPD bug API response.

        Args:
            item: Raw bug data from API

        Returns:
            Normalized bug dictionary
        """
        created = item.get("created", "")
        days_ago = self._calculate_days_ago(created) if created else 0

        return {
            "id": item.get("id"),
            "title": item.get("title", ""),
            "severity": item.get("severity", ""),
            "owner": item.get("Owner", ""),
            "created": created,
            "story_id": item.get("story_id", ""),
            "days_ago": days_ago,
        }

    def _calculate_days_ago(self, date_str: str) -> int:
        """Calculate days ago from a date string.

        Args:
            date_str: Date string in TAPD format

        Returns:
            Number of days ago
        """
        from datetime import datetime, timedelta

        try:
            # TAPD date format: 2026-07-13
            dt = datetime.strptime(date_str, "%Y-%m-%d")
            return (datetime.now() - dt).days
        except (ValueError, TypeError):
            return 999  # Very old or invalid date

    def _mock_stories(self) -> List[Dict[str, Any]]:
        """Return mock stories for testing without TAPD credentials."""
        return [
            {
                "id": "1234567890001",
                "title": "文件上传功能优化",
                "owner": "张三",
                "status": "进行中",
                "progress": 60,
                "begin_date": "2026-07-01",
                "due_date": "2026-07-15",
                "modified": "2026-07-13",
                "priority": "P0",
            },
            {
                "id": "1234567890002",
                "title": "订单列表查询性能优化",
                "owner": "李四",
                "status": "进行中",
                "progress": 90,
                "begin_date": "2026-07-05",
                "due_date": "2026-07-14",
                "modified": "2026-07-13",
                "priority": "P1",
            },
            {
                "id": "1234567890003",
                "title": "支付链路优化",
                "owner": "王五",
                "status": "进行中",
                "progress": 50,
                "begin_date": "2026-07-08",
                "due_date": "2026-07-15",
                "modified": "2026-07-10",
                "priority": "P0",
            },
        ]

    def _mock_bugs(self) -> List[Dict[str, Any]]:
        """Return mock bugs for testing without TAPD credentials."""
        return [
            {
                "id": "9876543210001",
                "title": "事务回滚失败导致脏数据",
                "severity": "严重",
                "owner": "张三",
                "created": "2026-07-12",
                "story_id": "1234567890001",
                "days_ago": 1,
            },
            {
                "id": "9876543210002",
                "title": "日志缺少业务标识",
                "severity": "一般",
                "owner": "李四",
                "created": "2026-07-11",
                "story_id": "1234567890002",
                "days_ago": 2,
            },
        ]

    def close(self):
        """Close HTTP client."""
        if self._client:
            self._client.close()
            self._client = None

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        self.close()


# Global client instance
_tapd_client: Optional[TAPDClient] = None


def get_tapd_client() -> TAPDClient:
    """Get or create global TAPD client instance."""
    global _tapd_client
    if _tapd_client is None:
        _tapd_client = TAPDClient()
    return _tapd_client