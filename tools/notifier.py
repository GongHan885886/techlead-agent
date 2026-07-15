"""Notification service for sending alerts and reports.

Supports multiple channels: webhook, email (mock).
"""

import json
from typing import Optional, Dict, Any
from datetime import datetime

import httpx

from config import settings


class Notifier:
    """Notification service for sending alerts and reports."""

    def __init__(self, webhook_url: Optional[str] = None, enabled: bool = False):
        """Initialize notifier.

        Args:
            webhook_url: Webhook URL for notifications
            enabled: Whether notifications are enabled
        """
        self.webhook_url = webhook_url or settings.notification_webhook_url
        self.enabled = enabled or settings.notification_enabled
        self._client = None

    @property
    def client(self) -> httpx.Client:
        """Lazy-loaded HTTP client."""
        if self._client is None:
            self._client = httpx.Client(timeout=30)
        return self._client

    def send(
        self,
        title: str,
        content: str,
        channel: str = "webhook",
        priority: str = "info",
        metadata: Optional[Dict[str, Any]] = None,
    ) -> bool:
        """Send a notification.

        Args:
            title: Notification title
            content: Notification body
            channel: Channel to use (webhook, email)
            priority: Priority level (info, warning, urgent)
            metadata: Additional metadata

        Returns:
            bool: Success status
        """
        if not self.enabled:
            print(f"🔕 Notifications disabled: {title}")
            return False

        try:
            if channel == "webhook":
                return self._send_webhook(title, content, priority, metadata)
            elif channel == "email":
                return self._send_email(title, content, metadata)
            else:
                print(f"⚠️  Unknown notification channel: {channel}")
                return False

        except Exception as e:
            print(f"⚠️  Failed to send notification: {e}")
            return False

    def _send_webhook(
        self,
        title: str,
        content: str,
        priority: str,
        metadata: Optional[Dict[str, Any]],
    ) -> bool:
        """Send notification via webhook.

        Args:
            title: Notification title
            content: Notification body
            priority: Priority level
            metadata: Additional metadata

        Returns:
            bool: Success status
        """
        if not self.webhook_url:
            print(f"📧 [Webhook] {title}\n{content[:200]}...")
            return True  # Mock success if no webhook URL

        payload = {
            "title": title,
            "content": content,
            "priority": priority,
            "timestamp": datetime.now().isoformat(),
            "source": "techlead-agent",
            **(metadata or {}),
        }

        response = self.client.post(
            self.webhook_url,
            json=payload,
            headers={"Content-Type": "application/json"},
        )
        response.raise_for_status()

        print(f"✅ Webhook sent: {title}")
        return True

    def _send_email(
        self, title: str, content: str, metadata: Optional[Dict[str, Any]]
    ) -> bool:
        """Send notification via email (mock).

        Args:
            title: Email subject
            content: Email body
            metadata: Additional metadata (e.g., recipients)

        Returns:
            bool: Success status
        """
        # Email sending is mocked for now
        recipients = metadata.get("recipients", ["default@example.com"])
        print(f"📧 [Email] To: {', '.join(recipients)}")
        print(f"   Subject: {title}")
        print(f"   Content: {content[:200]}...")

        return True

    def notify_user(
        self,
        recipient: str,
        title: str,
        content: str,
        urgency: str = "normal",
    ) -> bool:
        """Send notification to a specific user.

        Args:
            recipient: User identifier (name, email, etc.)
            title: Notification title
            content: Notification body
            urgency: Urgency level (normal, high, urgent)

        Returns:
            bool: Success status
        """
        metadata = {
            "recipient": recipient,
            "urgency": urgency,
        }

        priority = {"normal": "info", "high": "warning", "urgent": "urgent"}.get(
            urgency, "info"
        )

        return self.send(title, content, "webhook", priority, metadata)

    def send_review_request(
        self,
        target: str,
        target_type: str,
        reviewer: str,
        description: str,
        urgency: str = "normal",
    ) -> bool:
        """Send a review request notification.

        Args:
            target: Target identifier (MR ID, story ID, etc.)
            target_type: Type of target (MR, story, design)
            reviewer: Name of the reviewer
            description: Description of what needs review
            urgency: Urgency level

        Returns:
            bool: Success status
        """
        title = f"Review Request: {target_type} {target}"
        content = (
            f"Reviewer: {reviewer}\n"
            f"Target: {target_type} {target}\n"
            f"Description: {description}\n"
            f"Urgency: {urgency}"
        )

        metadata = {
            "reviewer": reviewer,
            "target": target,
            "target_type": target_type,
            "urgency": urgency,
            "notification_type": "review_request",
        }

        return self.send(title, content, "webhook", urgency, metadata)

    def send_cr_feedback(
        self,
        mr_id: int,
        author: str,
        issues: list,
        status: str = "completed",
    ) -> bool:
        """Send CR review feedback notification.

        Args:
            mr_id: Merge request ID
            author: Author of the MR
            issues: List of issues found
            status: Review status

        Returns:
            bool: Success status
        """
        blocker_count = sum(1 for i in issues if i.get("severity") == "blocker")
        warning_count = sum(1 for i in issues if i.get("severity") == "warning")
        total = len(issues)

        emoji = "✅" if status == "approved" else "⚠️"
        title = f"CR Review: MR !{mr_id} {emoji}"

        content = (
            f"Author: {author}\n"
            f"Status: {status}\n"
            f"Blockers: {blocker_count}\n"
            f"Warnings: {warning_count}\n"
            f"Total issues: {total}"
        )

        metadata = {
            "mr_id": mr_id,
            "author": author,
            "status": status,
            "blocker_count": blocker_count,
            "warning_count": warning_count,
            "notification_type": "cr_feedback",
        }

        return self.send(title, content, "webhook", "info", metadata)

    def send_learning_advice(
        self,
        developer: str,
        advice_summary: str,
        focus_areas: list,
    ) -> bool:
        """Send learning advice notification.

        Args:
            developer: Developer's name
            advice_summary: Summary of the learning advice
            focus_areas: List of focus areas

        Returns:
            bool: Success status
        """
        title = f"Learning Advice: {developer}"
        content = (
            f"Developer: {developer}\n"
            f"Focus Areas: {', '.join(focus_areas)}\n"
            f"Advice:\n{advice_summary}"
        )

        metadata = {
            "developer": developer,
            "focus_areas": focus_areas,
            "notification_type": "learning_advice",
        }

        return self.send(title, content, "webhook", "info", metadata)

    def close(self):
        """Close HTTP client."""
        if self._client:
            self._client.close()
            self._client = None

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        self.close()


# Global notifier instance
_notifier: Optional[Notifier] = None


def get_notifier() -> Notifier:
    """Get or create global notifier instance."""
    global _notifier
    if _notifier is None:
        _notifier = Notifier()
    return _notifier