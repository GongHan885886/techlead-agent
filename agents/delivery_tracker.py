"""Delivery tracker agent for TAPD delivery analysis and risk identification."""

import asyncio
from typing import Dict, Any, List, Optional
from datetime import datetime, timedelta

from agents.base_agent import BaseAgent
from tools.tapd_client import get_tapd_client
from tools.memory_store import record_team_metric


class DeliveryTrackerAgent(BaseAgent):
    """Agent specialized in tracking delivery progress and identifying risks."""

    def __init__(self):
        """Initialize delivery tracker agent."""
        super().__init__(name="delivery_tracker")

    async def process(self, input_data: Dict[str, Any]) -> Dict[str, Any]:
        """Process delivery tracking request.

        Args:
            input_data: May contain 'days' to look back, 'project_id' for filtering

        Returns:
            dict: Delivery analysis results
        """
        days = input_data.get("days", 7)
        project_id = input_data.get("project_id")

        self._log_execution("track_delivery", input_data, {})

        # Get TAPD stories
        tapd_client = get_tapd_client()
        stories = await tapd_client.fetch_stories(status="进行中", workspace_id=project_id)

        # Analyze delivery
        result = await self._analyze_delivery(stories, days)

        self._log_execution("track_delivery_complete", input_data, result)
        return result

    async def _analyze_delivery(self, stories: List[Dict], days: int) -> Dict[str, Any]:
        """Analyze stories for risks, efficiency, and quality metrics.

        Args:
            stories: List of TAPD stories
            days: Number of days to look back for metrics

        Returns:
            dict: Analysis results
        """
        now = datetime.now()

        # Identify risks
        high_risk, warning, possible_blockage = self._identify_risks(stories, now)

        # Calculate efficiency metrics
        efficiency_anomalies = await self._calculate_efficiency_metrics(stories, days)

        # Calculate quality metrics
        quality_anomalies = await self._calculate_quality_metrics(stories, days)

        # Build result
        result = {
            "intent": "delivery_tracking",
            "timestamp": now.isoformat(),
            "days": days,
            "total_stories": len(stories),
            "high_risk_stories": high_risk,
            "warning_stories": warning,
            "blockage_stories": possible_blockage,
            "efficiency_anomalies": efficiency_anomalies,
            "quality_anomalies": quality_anomalies,
            "summary": {
                "high_risk_count": len(high_risk),
                "warning_count": len(warning),
                "blockage_count": len(possible_blockage),
                "efficiency_anomaly_count": len(efficiency_anomalies),
                "quality_anomaly_count": len(quality_anomalies),
            },
        }

        return result

    def _identify_risks(
        self, stories: List[Dict], now: datetime
    ) -> tuple[List[Dict], List[Dict], List[Dict]]:
        """Identify stories with delivery risks.

        Args:
            stories: List of stories
            now: Current datetime

        Returns:
            tuple: (high_risk, warning, blockage) lists
        """
        high_risk = []
        warning = []
        possible_blockage = []

        for story in stories:
            due_date_str = story.get("due_date", "")
            progress = story.get("progress", 0)
            modified_str = story.get("modified", "")
            priority = story.get("priority", "")

            if not due_date_str:
                continue

            try:
                due_date = datetime.strptime(due_date_str, "%Y-%m-%d")
                days_left = (due_date - now).days

                # Check for blockage (no updates in 3+ days)
                if modified_str:
                    try:
                        modified = datetime.strptime(modified_str.split()[0], "%Y-%m-%d")
                        days_since_update = (now - modified).days
                        if days_since_update > 3:
                            possible_blockage.append(story)
                            continue
                    except (ValueError, TypeError):
                        pass

                # High risk: < 3 days and < 80% progress
                if days_left < 3 and progress < 80:
                    high_risk.append(story)

                # Warning: < 5 days and < 50% progress
                elif days_left < 5 and progress < 50:
                    warning.append(story)

            except (ValueError, TypeError):
                continue

        return high_risk, warning, possible_blockage

    async def _calculate_efficiency_metrics(
        self, stories: List[Dict], days: int
    ) -> List[Dict[str, Any]]:
        """Calculate efficiency metrics per developer.

        Args:
            stories: List of stories
            days: Number of days to look back

        Returns:
            list: List of developer efficiency anomalies
        """
        # Group by owner
        owner_stories: Dict[str, List[Dict]] = {}
        for story in stories:
            owner = story.get("owner", "Unknown")
            if owner not in owner_stories:
                owner_stories[owner] = []
            owner_stories[owner].append(story)

        # Calculate metrics per owner
        owner_metrics = []
        for owner, owner_story_list in owner_stories.items():
            # Calculate average delivery cycle (mock)
            avg_days = self._calculate_avg_delivery_cycle(owner_story_list)
            owner_metrics.append({
                "developer": owner,
                "avg_delivery_days": avg_days,
                "story_count": len(owner_story_list),
            })

        # Calculate team average
        team_avg = sum(m["avg_delivery_days"] for m in owner_metrics) / len(owner_metrics) if owner_metrics else 0

        # Identify anomalies (> 1.3x team average)
        anomalies = []
        for metric in owner_metrics:
            if metric["avg_delivery_days"] > team_avg * 1.3:
                percentage = ((metric["avg_delivery_days"] - team_avg) / team_avg) * 100
                anomalies.append({
                    **metric,
                    "team_avg": team_avg,
                    "percentage": round(percentage, 1),
                })

                # Record metric
                record_team_metric(
                    metric_type="avg_delivery_days",
                    metric_value=metric["avg_delivery_days"],
                    unit="days",
                    metadata={"developer": owner},
                )

        return anomalies

    def _calculate_avg_delivery_cycle(self, stories: List[Dict]) -> float:
        """Calculate average delivery cycle for a developer's stories.

        Args:
            stories: List of stories

        Returns:
            float: Average delivery days
        """
        if not stories:
            return 0.0

        total_days = 0
        count = 0

        for story in stories:
            begin_date_str = story.get("begin_date", "")
            due_date_str = story.get("due_date", "")

            if begin_date_str and due_date_str:
                try:
                    begin = datetime.strptime(begin_date_str, "%Y-%m-%d")
                    due = datetime.strptime(due_date_str, "%Y-%m-%d")
                    days = (due - begin).days
                    if days > 0:
                        total_days += days
                        count += 1
                except (ValueError, TypeError):
                    pass

        return total_days / count if count > 0 else 0.0

    async def _calculate_quality_metrics(
        self, stories: List[Dict], days: int
    ) -> List[Dict[str, Any]]:
        """Calculate quality metrics per developer.

        Args:
            stories: List of stories
            days: Number of days to look back

        Returns:
            list: List of developer quality anomalies
        """
        tapd_client = get_tapd_client()

        # Group by owner
        owner_stories: Dict[str, List[str]] = {}
        for story in stories:
            owner = story.get("owner", "Unknown")
            story_id = story.get("id")
            if owner not in owner_stories:
                owner_stories[owner] = []
            owner_stories[owner].append(story_id)

        # Fetch bugs for each story
        owner_bug_scores = {}
        for owner, story_ids in owner_stories.items():
            total_score = 0

            for story_id in story_ids:
                bugs = await tapd_client.fetch_bugs(story_id=story_id, days=days)

                # Calculate defect score with weights
                # 致命(4) / 严重(3) / 一般(2) / 轻微(1)
                weights = {"致命": 4, "严重": 3, "一般": 2, "轻微": 1}
                score = sum(weights.get(bug.get("severity", ""), 1) for bug in bugs)
                total_score += score

            # Calculate defect rate per day
            owner_bug_scores[owner] = total_score / days if days > 0 else 0

        # Calculate team average
        team_avg = sum(owner_bug_scores.values()) / len(owner_bug_scores) if owner_bug_scores else 0

        # Identify anomalies (> 1.5x team average)
        anomalies = []
        for developer, defect_rate in owner_bug_scores.items():
            if defect_rate > team_avg * 1.5:
                percentage = ((defect_rate - team_avg) / team_avg) * 100 if team_avg > 0 else 100
                anomalies.append({
                    "developer": developer,
                    "defect_rate": round(defect_rate, 2),
                    "team_avg": round(team_avg, 2),
                    "percentage": round(percentage, 1),
                })

                # Record metric
                record_team_metric(
                    metric_type="defect_rate",
                    metric_value=defect_rate,
                    unit="score/day",
                    metadata={"developer": developer},
                )

        return anomalies

    def format_report(self, result: Dict[str, Any]) -> str:
        """Format delivery tracking result as a readable report.

        Args:
            result: Delivery tracking result dictionary

        Returns:
            str: Formatted report
        """
        lines = [
            f"📊 交付追踪报告",
            f"数据时间范围：最近 {result.get('days', 7)} 天",
            f"生成时间：{result.get('timestamp', '')}",
            "",
        ]

        summary = result.get("summary", {})
        high_risk = result.get("high_risk_stories", [])
        warning = result.get("warning_stories", [])
        blockage = result.get("blockage_stories", [])
        efficiency = result.get("efficiency_anomalies", [])
        quality = result.get("quality_anomalies", [])

        # Progress risks
        if high_risk or warning or blockage:
            lines.append("【进度风险】")

            if high_risk:
                lines.append("🔴 紧急关注：")
                for story in high_risk:
                    lines.append(
                        f"1. [{story.get('priority', '')}] {story.get('title', '')}（{story.get('owner', '')}）"
                    )
                    lines.append(f"   - 距提测：{self._days_left_text(story)} 天")
                    lines.append(f"   - 当前进度：{story.get('progress', 0)}%")
                    lines.append(f"   - 建议行动：每日站会同步，必要时调配资源")

            if warning:
                lines.append("\n🟡 警告：")
                for story in warning:
                    lines.append(
                        f"1. [{story.get('priority', '')}] {story.get('title', '')}（{story.get('owner', '')}）"
                    )
                    lines.append(f"   - 距提测：{self._days_left_text(story)} 天")
                    lines.append(f"   - 当前进度：{story.get('progress', 0)}%")

            if blockage:
                lines.append("\n⚪ 可能阻塞：")
                for story in blockage:
                    lines.append(
                        f"1. {story.get('title', '')}（{story.get('owner', '')}）"
                    )
                    lines.append(f"   - 最后更新：{story.get('modified', '')}")
                    lines.append(f"   - 建议行动：立即联系确认阻塞原因")

            lines.append("")

        # Efficiency anomalies
        if efficiency:
            lines.append("【效率异常】📈")
            for item in efficiency:
                lines.append(
                    f"- {item['developer']}：{item['avg_delivery_days']:.1f} 天 vs 团队平均 {item['team_avg']:.1f} 天 ↑ {item['percentage']}%"
                )
            lines.append("")

        # Quality anomalies
        if quality:
            lines.append("【质量异常】📉")
            for item in quality:
                lines.append(
                    f"- {item['developer']}：{item['defect_rate']:.2f} 分/天 vs 团队平均 {item['team_avg']:.2f} 分/天 ↑ {item['percentage']}%"
                )
            lines.append("")

        # Summary
        lines.append("【统计摘要】")
        lines.append(f"- 进行中需求：{result.get('total_stories', 0)} 个")
        lines.append(f"- 高风险需求：{summary.get('high_risk_count', 0)} 个")
        lines.append(f"- 效率异常人员：{summary.get('efficiency_anomaly_count', 0)} 人")
        lines.append(f"- 质量异常人员：{summary.get('quality_anomaly_count', 0)} 人")

        return "\n".join(lines)

    def _days_left_text(self, story: Dict) -> str:
        """Get days left text for a story.

        Args:
            story: Story dictionary

        Returns:
            str: Days left text
        """
        due_date_str = story.get("due_date", "")
        if not due_date_str:
            return "N/A"

        try:
            due_date = datetime.strptime(due_date_str, "%Y-%m-%d")
            days_left = (due_date - datetime.now()).days
            return str(max(0, days_left))
        except (ValueError, TypeError):
            return "N/A"