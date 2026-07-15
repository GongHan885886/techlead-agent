"""Learning advisor agent for generating personalized learning recommendations."""

import asyncio
from typing import Dict, Any, List, Optional
from datetime import datetime

from agents.base_agent import BaseAgent
from tools.talent_developer import get_profile, generate_learning_context, get_team_overview


class LearningAdvisorAgent(BaseAgent):
    """Agent specialized in generating personalized learning recommendations based on error tracking."""

    def __init__(self):
        """Initialize learning advisor agent."""
        super().__init__(name="learning_advisor")

    async def process(self, input_data: Dict[str, Any]) -> Dict[str, Any]:
        """Generate learning advice for a developer.

        Args:
            input_data: Must contain 'developer' and optionally 'days'

        Returns:
            dict: Learning advice result
        """
        developer = input_data.get("developer")
        days = input_data.get("days", 30)

        if not developer:
            return {
                "intent": "learning_advice",
                "error": "Developer name is required",
                "message": "Please specify developer name",
            }

        self._log_execution("generate_learning_advice", input_data, {})

        # Get developer profile and team context
        profile = get_profile(developer, days)
        team = get_team_overview(days)

        # Generate learning advice
        result = await self._generate_advice(profile, team, days)

        self._log_execution("generate_learning_advice_complete", input_data, result)
        return result

    async def _generate_advice(
        self, profile: Dict[str, Any], team: Dict[str, Any], days: int
    ) -> Dict[str, Any]:
        """Generate structured learning advice.

        Args:
            profile: Developer profile
            team: Team overview data
            days: Number of days data covers

        Returns:
            dict: Structured learning advice
        """
        now = datetime.now()

        # Identify weaknesses
        weaknesses = self._identify_weaknesses(profile)

        # Analyze root causes
        root_causes = self._analyze_root_causes(weaknesses)

        # Generate recommendations
        recommendations = self._generate_recommendations(weaknesses, root_causes)

        # Suggest team collaboration
        collaboration = self._suggest_collaboration(profile, team)

        # Calculate team comparison metrics
        team_metrics = self._calculate_team_metrics(profile, team)

        # Build result
        result = {
            "intent": "learning_advice",
            "developer": profile.get("developer", "Unknown"),
            "timestamp": now.isoformat(),
            "days": days,
            "profile": profile,
            "weaknesses": weaknesses,
            "root_causes": root_causes,
            "recommendations": recommendations,
            "collaboration": collaboration,
            "team_metrics": team_metrics,
        }

        return result

    def _identify_weaknesses(self, profile: Dict[str, Any]) -> List[Dict[str, Any]]:
        """Identify top 2-3 weaknesses from profile.

        Args:
            profile: Developer profile

        Returns:
            list: List of weakness dictionaries
        """
        type_breakdown = profile.get("type_breakdown", [])

        # Aggregate by type
        type_totals = {}
        for item in type_breakdown:
            issue_type = item["type"]
            count = item["count"]
            severity = item["severity"]

            if issue_type not in type_totals:
                type_totals[issue_type] = {"count": 0, "blocker": 0, "warning": 0}
            type_totals[issue_type]["count"] += count
            if severity == "blocker":
                type_totals[issue_type]["blocker"] += count
            elif severity == "warning":
                type_totals[issue_type]["warning"] += count

        # Sort by total count (prioritize blockers)
        sorted_types = sorted(
            type_totals.items(),
            key=lambda x: (x[1]["blocker"], x[1]["count"]),
            reverse=True,
        )

        # Take top 3
        weaknesses = []
        for idx, (issue_type, data) in enumerate(sorted_types[:3], 1):
            # Find most recent occurrence
            recent_issues = [
                i for i in profile.get("recent_issues", [])
                if i["type"] == issue_type
            ]
            last_occurrence = recent_issues[0]["created_at"] if recent_issues else "N/A"

            weaknesses.append({
                "rank": idx,
                "type": issue_type,
                "total_count": data["count"],
                "blocker_count": data["blocker"],
                "warning_count": data["warning"],
                "last_occurrence": last_occurrence,
            })

        return weaknesses

    def _analyze_root_causes(self, weaknesses: List[Dict[str, Any]]) -> Dict[str, str]:
        """Analyze root causes for weaknesses.

        Args:
            weaknesses: List of weaknesses

        Returns:
            dict: Mapping of weakness type to root cause
        """
        # Root cause patterns
        cause_patterns = {
            "transaction": "基础知识薄弱：对 Spring 事务传播机制、代理模式理解不足",
            "multithread": "技术盲区：对并发编程、线程安全、锁机制掌握不够",
            "logging": "编码习惯问题：缺乏对日志规范的重视和可观测性意识",
            "api": "经验不足：对 API 设计最佳实践理解不够深入",
            "sql": "编码习惯问题：SQL 编写不够规范，缺少性能优化意识",
            "security": "安全意识薄弱：对常见安全漏洞认识不足",
        }

        root_causes = {}
        for weakness in weaknesses:
            issue_type = weakness["type"]
            root_causes[issue_type] = cause_patterns.get(
                issue_type,
                "需要进一步分析：可能涉及知识盲区或习惯问题",
            )

        return root_causes

    def _generate_recommendations(
        self, weaknesses: List[Dict[str, Any]], root_causes: Dict[str, str]
    ) -> List[Dict[str, Any]]:
        """Generate learning recommendations for weaknesses.

        Args:
            weaknesses: List of weaknesses
            root_causes: Root cause analysis

        Returns:
            list: List of recommendation dictionaries
        """
        # Learning resource database
        resources = {
            "transaction": [
                {"type": "官方文档", "name": "Spring 事务官方文档", "priority": "high"},
                {"type": "书籍", "name": "《Spring 实战》第 4、5 章", "priority": "high"},
                {"type": "视频", "name": "B站：Spring 事务深度解析", "priority": "medium"},
            ],
            "multithread": [
                {"type": "书籍", "name": "《Java 并发编程实战》", "priority": "high"},
                {"type": "官方文档", "name": "JDK Concurrency 官方文档", "priority": "high"},
                {"type": "实践", "name": "Review 团队内多线程代码", "priority": "medium"},
            ],
            "logging": [
                {"type": "规范", "name": "团队日志规范文档", "priority": "high"},
                {"type": "工具", "name": "Logback 官方文档", "priority": "medium"},
                {"type": "最佳实践", "name": "可观测性最佳实践分享", "priority": "medium"},
            ],
            "api": [
                {"type": "规范", "name": "RESTful API 设计规范", "priority": "high"},
                {"type": "书籍", "name": "《RESTful Web APIs》", "priority": "medium"},
                {"type": "实践", "name": "Review 优秀 API 设计案例", "priority": "medium"},
            ],
            "sql": [
                {"type": "书籍", "name": "《高性能 MySQL》", "priority": "high"},
                {"type": "规范", "name": "SQL 编写规范", "priority": "high"},
                {"type": "工具", "name": "Explain 执行计划分析", "priority": "medium"},
            ],
            "security": [
                {"type": "课程", "name": "OWASP Top 10 安全漏洞", "priority": "high"},
                {"type": "书籍", "name": "《Web 安全深度剖析》", "priority": "medium"},
                {"type": "实践", "name": "安全代码审查 check list", "priority": "high"},
            ],
        }

        recommendations = []
        for i, weakness in enumerate(weaknesses):
            issue_type = weakness["type"]

            # Determine urgency
            urgency = "【紧急】" if weakness["blocker_count"] > 0 else "【长期】"

            # Get resources
            issue_resources = resources.get(issue_type, [])

            # Generate improvement goal
            goal = self._generate_improvement_goal(weakness, issue_type)

            recommendations.append({
                "rank": i + 1,
                "issue_type": issue_type,
                "root_cause": root_causes.get(issue_type, ""),
                "resources": issue_resources,
                "actions": self._generate_actions(issue_type, issue_resources),
                "goal": goal,
            })

        return recommendations

    def _generate_actions(self, issue_type: str, resources: List[Dict]) -> List[str]:
        """Generate specific action items.

        Args:
            issue_type: Issue type
            resources: Available learning resources

        Returns:
            list: List of action items
        """
        actions = []

        # Get high priority resource
        high_priority = [r for r in resources if r.get("priority") == "high"]
        if high_priority:
            main_resource = high_priority[0]
            actions.append(f"本周完成《{main_resource['name']}》精读")

        # Add practice actions based on issue type
        if issue_type == "transaction":
            actions.append("后续 CR 重点检查事务注解使用是否正确")
            actions.append("与架构师确认现有 Service 层代理模式")
        elif issue_type == "multithread":
            actions.append("Review 团队内现有的多线程代码实现")
            actions.append("后续 CR 重点检查共享变量线程安全性")
        elif issue_type == "logging":
            actions.append("后续 CR 重点检查日志是否包含业务标识")
            actions.append("学习团队日志规范并应用到日常开发")
        elif issue_type == "api":
            actions.append("Review 优秀 API 设计案例并总结经验")
            actions.append("参与 API 评审会，了解设计考量")
        elif issue_type == "sql":
            actions.append("学习 Explain 执行计划分析方法")
            actions.append("后续 CR 重点关注 SQL 性能和索引设计")
        elif issue_type == "security":
            actions.append("完成 OWASP Top 10 课程学习")
            actions.append("使用安全代码审查 check list 自查")

        return actions

    def _generate_improvement_goal(self, weakness: Dict, issue_type: str) -> str:
        """Generate improvement goal for a weakness.

        Args:
            weakness: Weakness data
            issue_type: Issue type

        Returns:
            str: Improvement goal
        """
        blocker_count = weakness.get("blocker_count", 0)

        if blocker_count > 0:
            timeframe = "2 周"
            target = "将此类 Blocker 降为 0"
        elif weakness.get("warning_count", 0) > 3:
            timeframe = "1 个月"
            target = "将此类 Warning 降低 50%"
        else:
            timeframe = "持续"
            target = "保持当前水平，定期复盘"

        return f"未来 {timeframe} 内，{target}"

    def _suggest_collaboration(
        self, profile: Dict[str, Any], team: Dict[str, Any]
    ) -> List[str]:
        """Suggest team collaboration activities.

        Args:
            profile: Developer profile
            team: Team overview

        Returns:
            list: List of collaboration suggestions
        """
        suggestions = []
        developer = profile.get("developer", "Unknown")
        weaknesses = self._identify_weaknesses(profile)

        if not weaknesses:
            return ["继续保持良好的编码习惯"]

        top_weakness = weaknesses[0]["type"]

        # Find developers strong in this area (mock logic)
        suggestions.append(f"建议安排 {developer} 在下周需求评审会上分享'{top_weakness} 踩坑经验'")

        # Suggest pair programming if there are blockers
        if weaknesses[0].get("blocker_count", 0) > 0:
            suggestions.append("建议安排一次 Pair Programming，与经验丰富的同事共同开发")

        # Suggest 1on1 if issues are high
        if profile.get("total_issues", 0) > 10:
            suggestions.append("建议安排 1on1 沟通，了解是否有需要支持的困难")

        return suggestions

    def _calculate_team_metrics(self, profile: Dict[str, Any], team: Dict[str, Any]) -> Dict[str, Any]:
        """Calculate team comparison metrics.

        Args:
            profile: Developer profile
            team: Team overview

        Returns:
            dict: Team metrics
        """
        # Calculate team averages
        summaries = team.get("developer_summaries", [])
        if not summaries:
            return {}

        total_team_issues = sum(s.get("total", 0) for s in summaries)
        total_team_blockers = sum(s.get("blockers", 0) for s in summaries)
        avg_team_blocker_pct = (
            (total_team_blockers / total_team_issues * 100) if total_team_issues > 0 else 0
        )

        # Calculate developer metrics
        dev_total = profile.get("total_issues", 0)
        dev_blockers = profile.get("blocker_count", 0)
        dev_blocker_pct = (dev_blockers / dev_total * 100) if dev_total > 0 else 0

        return {
            "team_avg_blocker_pct": round(avg_team_blocker_pct, 1),
            "dev_blocker_pct": round(dev_blocker_pct, 1),
            "vs_team": round(dev_blocker_pct - avg_team_blocker_pct, 1),
        }

    def format_report(self, result: Dict[str, Any]) -> str:
        """Format learning advice result as a readable report.

        Args:
            result: Learning advice result dictionary

        Returns:
            str: Formatted report
        """
        lines = [
            f"📚 【{result.get('developer', 'Unknown')}】的个性化提升计划（基于近{result.get('days', 30)}天数据）",
            f"生成时间：{result.get('timestamp', '')}",
            "",
        ]

        profile = result.get("profile", {})
        team_metrics = result.get("team_metrics", {})

        # Error profile
        lines.append("📊 错题画像")
        lines.append(f"- 总问题数：{profile.get('total_issues', 0)} 个")
        lines.append(f"- Blocker 占比：{profile.get('blocker_count', 0)} 个")

        if team_metrics:
            team_avg = team_metrics.get("team_avg_blocker_pct", 0)
            dev_pct = team_metrics.get("dev_blocker_pct", 0)
            lines.append(f"（团队平均：{team_avg}%，个人：{dev_pct}%）")

        lines.append("")

        # High frequency weaknesses
        weaknesses = result.get("weaknesses", [])
        if weaknesses:
            lines.append("🎯 高频弱点")
            for weakness in weaknesses:
                lines.append(f"{weakness['rank']}. [{weakness['type']}] - {weakness['total_count']} 次")
                lines.append(f"   严重程度：{weakness['blocker_count']} Blocker / {weakness['warning_count']} Warning")
                lines.append(f"   最近一次：{weakness['last_occurrence']}")
            lines.append("")

        # Recommendations
        recommendations = result.get("recommendations", [])
        if recommendations:
            for rec in recommendations:
                urgency = "【紧急】" if rec["rank"] == 1 else "【长期】"
                lines.append(f"{urgency}{rec['issue_type']} - {rec['root_cause']}")

                # Learning resources
                lines.append("📚 学习资源：")
                for resource in rec["resources"][:3]:
                    priority = "★" if resource.get("priority") == "high" else ""
                    lines.append(f"  - {resource['name']}（{resource['type']}）{priority}")

                # Actions
                lines.append("🔧 实践行动：")
                for action in rec["actions"][:3]:
                    lines.append(f"  - {action}")

                # Goal
                lines.append(f"⏰ 改进目标：{rec['goal']}")
                lines.append("")

        # Team collaboration
        collaboration = result.get("collaboration", [])
        if collaboration:
            lines.append("👥 团队协同建议")
            for suggestion in collaboration:
                lines.append(f"- {suggestion}")
            lines.append("")

        # Next steps
        lines.append("📝 后续行动")
        lines.append("1. 本周内完成紧急项学习")
        lines.append("2. 两周后复盘，评估改进效果")

        return "\n".join(lines)