"""Git client for fetching MRs and posting comments.

Supports GitLab API (can be extended for GitHub/GitHub Enterprise).
"""

from typing import List, Dict, Any, Optional
from urllib.parse import urlencode

import httpx

from config import settings
from tools.cache_manager import get_cache_manager
from utils.logger import get_logger

_logger = get_logger("git_client")


class GitClient:
    """Client for Git API operations (GitLab-focused)."""

    def __init__(
        self,
        token: Optional[str] = None,
        base_url: Optional[str] = None,
        default_project_id: Optional[int] = None,
        timeout: int = 30,
    ):
        """Initialize Git client.

        Args:
            token: Git access token
            base_url: Git instance base URL
            default_project_id: Default project ID
            timeout: Request timeout in seconds
        """
        self.token = token or settings.gitlab_token
        self.base_url = base_url or settings.gitlab_url
        self.project_id = default_project_id or settings.default_project_id
        self.timeout = timeout
        self._client = None

        self.default_branch = settings.default_branch

    @property
    def client(self) -> httpx.Client:
        """Lazy-loaded HTTP client."""
        if self._client is None:
            self._client = httpx.Client(
                base_url=self.base_url,
                headers={
                    "Authorization": f"Bearer {self.token}",
                    "Content-Type": "application/json",
                },
                timeout=self.timeout,
            )
        return self._client

    def is_configured(self) -> bool:
        """Check if Git credentials are configured."""
        return bool(self.token and self.base_url)

    async def fetch_mrs(
        self,
        state: str = "opened",
        project_id: Optional[int] = None,
        per_page: int = 100,
    ) -> List[Dict[str, Any]]:
        """Fetch merge requests from GitLab with caching.

        Args:
            state: MR state filter (opened, closed, merged)
            project_id: Project ID
            per_page: Number of MRs per page

        Returns:
            List of MR dictionaries
        """
        if not self.is_configured():
            _logger.warning("Git not configured, returning mock data")
            return self._mock_mrs()

        project_id = project_id or self.project_id
        params = {
            "state": state,
            "per_page": per_page,
            "target_branch": self.default_branch,
        }

        # Try to get from cache
        cache_manager = get_cache_manager()
        cache_key = f"mrs:{project_id}:{state}"
        cached = cache_manager.get_http(
            url=f"/api/v4/projects/{project_id}/merge_requests",
            method="GET",
            params=params,
            headers={"Authorization": f"Bearer {self.token}"}
        )
        if cached is not None:
            return cached

        try:
            response = self.client.get(
                f"/api/v4/projects/{project_id}/merge_requests?{urlencode(params)}"
            )
            response.raise_for_status()
            data = response.json()

            mrs = []
            for item in data:
                mrs.append(self._parse_mr(item))

            # Cache the result (30 minutes TTL)
            cache_manager.set_http(
                url=f"/api/v4/projects/{project_id}/merge_requests",
                method="GET",
                params=params,
                headers={"Authorization": f"Bearer {self.token}"},
                data=mrs,
                ttl_minutes=30
            )

            return mrs

        except Exception as e:
            print(f"⚠️  Failed to fetch GitLab MRs: {e}")
            return self._mock_mrs()

    async def fetch_mr_diff(
        self, mr_id: int, project_id: Optional[int] = None
    ) -> str:
        """Fetch diff for a specific merge request with caching.

        Args:
            mr_id: MR ID (internal GitLab ID, not IID)
            project_id: Project ID

        Returns:
            Diff content as string
        """
        if not self.is_configured():
            return self._mock_diff()

        project_id = project_id or self.project_id

        # Try to get from cache
        cache_manager = get_cache_manager()
        cache_key = f"mr_diff:{project_id}:{mr_id}"
        cached = cache_manager.get_http(
            url=f"/api/v4/projects/{project_id}/merge_requests/{mr_id}/diff",
            method="GET",
            headers={"Authorization": f"Bearer {self.token}"}
        )
        if cached is not None:
            return cached

        try:
            response = self.client.get(
                f"/api/v4/projects/{project_id}/merge_requests/{mr_id}/diff"
            )
            response.raise_for_status()
            data = response.json()

            # Combine all diffs into a single string
            diff_parts = []
            for diff_item in data:
                old_path = diff_item.get("old_path", "")
                new_path = diff_item.get("new_path", "")
                diff_content = diff_item.get("diff", "")
                diff_parts.append(
                    f"--- a/{old_path}\n"
                    f"+++ b/{new_path}\n"
                    f"{diff_content}\n"
                )

            result = "\n".join(diff_parts)

            # Cache the result (15 minutes TTL)
            cache_manager.set_http(
                url=f"/api/v4/projects/{project_id}/merge_requests/{mr_id}/diff",
                method="GET",
                headers={"Authorization": f"Bearer {self.token}"},
                data=result,
                ttl_minutes=15
            )

            return result

        except Exception as e:
            print(f"⚠️  Failed to fetch MR diff: {e}")
            return self._mock_diff()

    async def fetch_mr_changes(
        self, mr_iid: int, project_id: Optional[int] = None
    ) -> Dict[str, Any]:
        """Fetch changes for a merge request.

        Args:
            mr_iid: MR IID (the human-readable number)
            project_id: Project ID

        Returns:
            Changes dictionary with files, additions, deletions
        """
        if not self.is_configured():
            return self._mock_changes()

        project_id = project_id or self.project_id

        try:
            response = self.client.get(
                f"/api/v4/projects/{project_id}/merge_requests/{mr_iid}/changes"
            )
            response.raise_for_status()
            data = response.json()

            return {
                "files": data.get("changes", []),
                "additions": data.get("additions", 0),
                "deletions": data.get("deletions", 0),
                "commits": [c["id"] for c in data.get("commits", [])],
            }

        except Exception as e:
            print(f"⚠️  Failed to fetch MR changes: {e}")
            return self._mock_changes()

    async def post_comment(
        self,
        mr_iid: int,
        body: str,
        position: Optional[Dict] = None,
        project_id: Optional[int] = None,
    ) -> bool:
        """Post a comment to a merge request.

        Args:
            mr_iid: MR IID
            body: Comment body
            position: Position for inline comment (line-based)
            project_id: Project ID

        Returns:
            bool: Success status
        """
        if not self.is_configured():
            print(f"✅ Mock: Posted comment to MR !{mr_iid}")
            return True

        project_id = project_id or self.project_id

        try:
            payload = {"body": body}

            # Add position for inline comments
            if position:
                payload["position"] = position

            response = self.client.post(
                f"/api/v4/projects/{project_id}/merge_requests/{mr_iid}/notes",
                json=payload,
            )
            response.raise_for_status()
            print(f"✅ Comment posted to MR !{mr_iid}")
            return True

        except Exception as e:
            print(f"⚠️  Failed to post comment to MR !{mr_iid}: {e}")
            return False

    async def post_comments_batch(
        self,
        mr_iid: int,
        comments: List[Dict[str, str]],
        project_id: Optional[int] = None,
    ) -> Dict[str, bool]:
        """Post multiple comments to a merge request.

        Args:
            mr_iid: MR IID
            comments: List of comment dicts with keys: body, file_path, line
            project_id: Project ID

        Returns:
            dict: Mapping of comment index to success status
        """
        results = {}

        for idx, comment in enumerate(comments):
            body = comment.get("body", "")
            file_path = comment.get("file_path")
            line = comment.get("line")

            # Prepare position for inline comments
            position = None
            if file_path and line:
                position = {
                    "base_sha": "",
                    "head_sha": "",
                    "start_sha": "",
                    "position_type": "text",
                    "new_path": file_path,
                    "new_line": line,
                }

            success = await self.post_comment(mr_iid, body, position, project_id)
            results[idx] = success

            # Rate limiting: small delay between comments
            import asyncio

            await asyncio.sleep(0.2)

        return results

    async def update_mr_state(
        self, mr_iid: int, state_event: str, project_id: Optional[int] = None
    ) -> bool:
        """Update merge request state.

        Args:
            mr_iid: MR IID
            state_event: State event (approve, unapprove, close, reopen)
            project_id: Project ID

        Returns:
            bool: Success status
        """
        if not self.is_configured():
            print(f"✅ Mock: Updated MR !{mr_iid} state to {state_event}")
            return True

        project_id = project_id or self.project_id

        try:
            response = self.client.post(
                f"/api/v4/projects/{project_id}/merge_requests/{mr_iid}/approvals",
                json={f"{state_event}": True},
            )
            response.raise_for_status()
            print(f"✅ MR !{mr_iid} state updated: {state_event}")
            return True

        except Exception as e:
            print(f"⚠️  Failed to update MR !{mr_iid} state: {e}")
            return False

    def _parse_mr(self, item: Dict) -> Dict[str, Any]:
        """Parse GitLab MR API response.

        Args:
            item: Raw MR data from API

        Returns:
            Normalized MR dictionary
        """
        return {
            "id": item.get("id"),
            "iid": item.get("iid"),
            "title": item.get("title", ""),
            "author": item.get("author", {}).get("name", ""),
            "source_branch": item.get("source_branch", ""),
            "target_branch": item.get("target_branch", ""),
            "state": item.get("state", ""),
            "created_at": item.get("created_at", ""),
            "updated_at": item.get("updated_at", ""),
            "web_url": item.get("web_url", ""),
            "changes_count": item.get("changes_count", 0),
            "additions": item.get("additions", 0),
            "deletions": item.get("deletions", 0),
            "draft": item.get("draft", False),
        }

    def _mock_mrs(self) -> List[Dict[str, Any]]:
        """Return mock MRs for testing without Git credentials."""
        return [
            {
                "id": 123,
                "iid": 123,
                "title": "feat: add file upload functionality",
                "author": "张三",
                "source_branch": "feature/file-upload",
                "target_branch": "main",
                "state": "opened",
                "created_at": "2026-07-12T10:00:00Z",
                "updated_at": "2026-07-13T08:00:00Z",
                "web_url": "https://gitlab.example.com/project/-/merge_requests/123",
                "changes_count": 15,
                "additions": 450,
                "deletions": 30,
                "draft": False,
            },
            {
                "id": 124,
                "iid": 124,
                "title": "fix: order query performance issue",
                "author": "李四",
                "source_branch": "fix/order-performance",
                "target_branch": "main",
                "state": "opened",
                "created_at": "2026-07-12T15:00:00Z",
                "updated_at": "2026-07-13T09:00:00Z",
                "web_url": "https://gitlab.example.com/project/-/merge_requests/124",
                "changes_count": 8,
                "additions": 120,
                "deletions": 80,
                "draft": False,
            },
        ]

    def _mock_diff(self) -> str:
        """Return mock diff content for testing."""
        return """--- a/OrderService.java
+++ b/OrderService.java
@@ -42,6 +42,7 @@ public class OrderService {

     @Transactional
     private void updateOrderStatus(Long orderId, String status) {
+        // This @Transactional won't work due to private method
         Order order = orderRepository.findById(orderId).orElseThrow();
         order.setStatus(status);
         orderRepository.save(order);
@@ -78,8 +79,10 @@ public class FileHandler {
     private static final Map<String, UploadResult> uploads = new HashMap<>();

     public UploadResult handleUpload(File file) {
+        // HashMap is not thread-safe in concurrent environment
         UploadResult result = new UploadResult();
         uploads.put(file.getName(), result);
         return result;
     }
@@ -95,6 +95,6 @@ public class PaymentService {
             throw e;
         } catch (Exception e) {
-            log.error("Payment failed: " + e.getMessage());
+            log.error("Payment failed", e);  // Missing business context
         }
     }"""

    def _mock_changes(self) -> Dict[str, Any]:
        """Return mock changes for testing."""
        return {
            "files": [
                {
                    "old_path": "OrderService.java",
                    "new_path": "OrderService.java",
                    "additions": 10,
                    "deletions": 5,
                },
                {
                    "old_path": "FileHandler.java",
                    "new_path": "FileHandler.java",
                    "additions": 5,
                    "deletions": 2,
                },
            ],
            "additions": 15,
            "deletions": 7,
            "commits": ["abc123", "def456"],
        }

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
_git_client: Optional[GitClient] = None


def get_git_client() -> GitClient:
    """Get or create global Git client instance."""
    global _git_client
    if _git_client is None:
        _git_client = GitClient()
    return _git_client