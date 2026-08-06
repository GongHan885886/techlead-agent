"""Learning advisor agent for generating personalized learning recommendations.

Uses LLM to analyze developer error patterns from SQLite error book,
generating personalized root cause analysis, learning resources, and
verification quizzes — replacing the previous hardcoded template approach.
"""

import json
from typing import Dict, Any, List, Optional
from datetime import datetime

from agents.base_agent import BaseAgent
from tools.talent_developer import get_profile, get_team_overview


class LearningAdvisorAgent(BaseAgent):
    """Agent specialized in generating personalized learning recommendations
    based on error tracking data, powered by LLM analysis.

    The LLM receives detailed error descriptions (not just category counts)
    so it can identify specific error patterns and recommend targeted resources
    rather than generic textbook titles.
    """

    def __init__(self):
        super().__init__(name="learning_advisor")

    # ── Public API ──────────────────────────────────────────────

    async def process(self, input_data: Dict[str, Any]) -> Dict[str, Any]:
        """Generate learning advice for a developer.

        Args:
            input_data: Must contain 'developer'; optionally 'days' (default 30).

        Returns:
            dict with keys: intent, developer, timestamp, days,
            profile, weaknesses, root_causes, recommendations,
            collaboration, team_metrics.
            On error the dict contains 'error' and 'message'.
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

        # ── unchanged: fetch data from SQLite ──
        profile = get_profile(developer, days)
        team = get_team_overview(days)

        # ── unchanged: identify weaknesses (deterministic aggregation) ──
        weaknesses = self._identify_weaknesses(profile)

        # ── unchanged: compute team comparison metrics ──
        team_metrics = self._calculate_team_metrics(profile, team)

        if not weaknesses:
            # No issues — no LLM call needed
            result = self._build_no_issues_result(profile, team_metrics, days)
        else:
            # ── NEW: LLM-powered analysis ──
            try:
                llm_output = await self._call_llm_for_advice(
                    profile, weaknesses, team_metrics, days
                )
                result = self._build_result(
                    profile, weaknesses, team_metrics, llm_output, days
                )
            except Exception as e:
                self.logger.error(f"LLM learning advice failed: {e}")
                # Fall back to structured error
                result = self._build_fallback_result(
                    profile, weaknesses, team_metrics, days, str(e)
                )

        self._log_execution("generate_learning_advice_complete", input_data, result)
        return result

    # ── LLM call ────────────────────────────────────────────────

    async def _call_llm_for_advice(
        self,
        profile: Dict[str, Any],
        weaknesses: List[Dict[str, Any]],
        team_metrics: Dict[str, Any],
        days: int,
    ) -> Dict[str, Any]:
        """Build the prompt and call the LLM for personalized analysis.

        The prompt includes detailed error descriptions so the LLM can
        identify specific error patterns rather than just category labels.
        """
        prompt_text = self._build_analysis_prompt(
            profile, weaknesses, team_metrics, days
        )

        messages = [
            {"role": "system", "content": self.system_prompt},
            {"role": "user", "content": prompt_text},
        ]

        response = await self.llm_call(messages)
        return self._parse_llm_response(response)

    def _build_analysis_prompt(
        self,
        profile: Dict[str, Any],
        weaknesses: List[Dict[str, Any]],
        team_metrics: Dict[str, Any],
        days: int,
    ) -> str:
        """Build a detailed prompt with raw error descriptions.

        The key difference from the old approach: we include the actual
        error descriptions from each issue so the LLM can see patterns
        like "repeated private-method @Transactional" vs just "6 transaction issues".
        """
        developer = profile.get("developer", "Unknown")
        total = profile.get("total_issues", 0)
        blocker_count = profile.get("blocker_count", 0)
        warning_count = profile.get("warning_count", 0)

        dev_blocker_pct = team_metrics.get("dev_blocker_pct", 0)
        team_avg_pct = team_metrics.get("team_avg_blocker_pct", 0)

        parts = [
            f"开发者：{developer}",
            f"数据范围：最近 {days} 天",
            "",
            "━━━ 错题画像 ━━━",
            f"总问题数：{total} 个",
            f"Blocker：{blocker_count} 个 | Warning：{warning_count} 个",
            (
                f"个人 Blocker 占比：{dev_blocker_pct}%"
                f"（团队均值：{team_avg_pct}%）"
            ),
            "",
            "━━━ 高频弱点 ━━━",
        ]

        for w in weaknesses:
            parts.append(
                f"\n{w['rank']}. {w['type']}（{w['total_count']} 次，"
                f"Blocker {w['blocker_count']} / Warning {w['warning_count']}）"
            )

            # Include specific error descriptions — this is what lets the LLM
            # identify patterns beyond just category labels
            recent = [
                i for i in profile.get("recent_issues", [])
                if i["type"] == w["type"]
            ]
            if recent:
                parts.append("   具体错误记录：")
                for issue in recent[:8]:  # cap at 8 per weakness
                    source_tag = (
                        f"MR!{issue.get('mr_id')}"
                        if issue.get("mr_id")
                        else issue.get("source", "")
                    )
                    parts.append(
                        f"   - [{issue['severity']}] {issue['description']}"
                        f"  ← 来源：{source_tag}"
                    )
                if len(recent) > 8:
                    parts.append(f"   ... 还有 {len(recent) - 8} 条早期记录")

        parts.extend([
            "",
            "━━━ 团队对比 ━━━",
            f"团队平均 Blocker 占比：{team_avg_pct}%",
            f"该开发者 Blocker 占比：{dev_blocker_pct}%",
            f"差值：{dev_blocker_pct - team_avg_pct:+.1f}%",
            "",
            "请基于以上数据，按照系统提示词中的 JSON 格式生成个性化学习方案。",
        ])

        return "\n".join(parts)

    def _parse_llm_response(self, response: str) -> Dict[str, Any]:
        """Parse LLM JSON output with resilience.

        Handles common LLM formatting quirks: markdown code fences,
        leading/trailing text, and truncated JSON.
        """
        text = response.strip()

        # Strip markdown code fences if present
        if text.startswith("```"):
            # Remove opening fence line
            text = text.split("\n", 1)[1] if "\n" in text else text[3:]
            # Remove closing fence
            if text.rstrip().endswith("```"):
                text = text.rsplit("```", 1)[0]

        # Find the outermost JSON object
        start = text.find("{")
        end = text.rfind("}")
        if start != -1 and end != -1 and end > start:
            text = text[start:end + 1]

        parsed = json.loads(text)
        return {
            "root_causes": parsed.get("root_causes", {}),
            "recommendations": parsed.get("recommendations", []),
            "collaboration": parsed.get("collaboration", []),
        }

    # ── Result builders ─────────────────────────────────────────

    def _build_result(
        self,
        profile: Dict[str, Any],
        weaknesses: List[Dict[str, Any]],
        team_metrics: Dict[str, Any],
        llm_output: Dict[str, Any],
        days: int,
    ) -> Dict[str, Any]:
        """Assemble the final result from profile data + LLM analysis."""
        return {
            "intent": "learning_advice",
            "developer": profile.get("developer", "Unknown"),
            "timestamp": datetime.now().isoformat(),
            "days": days,
            "profile": profile,
            "weaknesses": weaknesses,
            "team_metrics": team_metrics,
            "root_causes": llm_output.get("root_causes", {}),
            "recommendations": llm_output.get("recommendations", []),
            "collaboration": llm_output.get("collaboration", []),
        }

    def _build_no_issues_result(
        self, profile: Dict[str, Any], team_metrics: Dict[str, Any], days: int
    ) -> Dict[str, Any]:
        """Result when the developer has no recent issues."""
        developer = profile.get("developer", "Unknown")
        return {
            "intent": "learning_advice",
            "developer": developer,
            "timestamp": datetime.now().isoformat(),
            "days": days,
            "profile": profile,
            "weaknesses": [],
            "team_metrics": team_metrics,
            "root_causes": {},
            "recommendations": [],
            "collaboration": [
                f"{developer} 近期表现良好，继续保持当前的编码习惯",
            ],
        }

    def _build_fallback_result(
        self,
        profile: Dict[str, Any],
        weaknesses: List[Dict[str, Any]],
        team_metrics: Dict[str, Any],
        days: int,
        error_msg: str,
    ) -> Dict[str, Any]:
        """Fallback result when LLM call fails.

        Still returns weaknesses from deterministic analysis so the
        caller gets something useful even during LLM outages.
        """
        return {
            "intent": "learning_advice",
            "developer": profile.get("developer", "Unknown"),
            "timestamp": datetime.now().isoformat(),
            "days": days,
            "profile": profile,
            "weaknesses": weaknesses,
            "team_metrics": team_metrics,
            "root_causes": {
                w["type"]: f"LLM 分析暂时不可用（{error_msg[:80]}），请稍后重试"
                for w in weaknesses
            },
            "recommendations": [],
            "collaboration": [
                "⚠️ 个性化学习方案生成失败，建议稍后重新运行 profile 命令"
            ],
            "error": error_msg,
        }

    # ── Weakness identification (unchanged, deterministic) ──────

    def _identify_weaknesses(self, profile: Dict[str, Any]) -> List[Dict[str, Any]]:
        """Identify top 2-3 weaknesses from profile by aggregating issue types.

        Deterministic — this does not use LLM. It simply counts and sorts
        issues by type×severity so the LLM gets an accurate starting point.
        """
        type_breakdown = profile.get("type_breakdown", [])

        # Aggregate by type
        type_totals: Dict[str, Dict[str, int]] = {}
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

        # Sort by blocker count desc, then total count desc
        sorted_types = sorted(
            type_totals.items(),
            key=lambda x: (x[1]["blocker"], x[1]["count"]),
            reverse=True,
        )

        weaknesses = []
        for idx, (issue_type, data) in enumerate(sorted_types[:3], 1):
            recent_issues = [
                i for i in profile.get("recent_issues", [])
                if i["type"] == issue_type
            ]
            last_occurrence = (
                recent_issues[0]["created_at"] if recent_issues else "N/A"
            )

            weaknesses.append({
                "rank": idx,
                "type": issue_type,
                "total_count": data["count"],
                "blocker_count": data["blocker"],
                "warning_count": data["warning"],
                "last_occurrence": last_occurrence,
            })

        return weaknesses

    # ── Team metrics (unchanged, deterministic) ─────────────────

    def _calculate_team_metrics(
        self, profile: Dict[str, Any], team: Dict[str, Any]
    ) -> Dict[str, Any]:
        """Calculate developer vs team comparison metrics."""
        summaries = team.get("developer_summaries", [])
        if not summaries:
            return {"team_avg_blocker_pct": 0, "dev_blocker_pct": 0, "vs_team": 0}

        total_team_issues = sum(s.get("total", 0) for s in summaries)
        total_team_blockers = sum(s.get("blockers", 0) for s in summaries)
        avg_team_blocker_pct = (
            (total_team_blockers / total_team_issues * 100)
            if total_team_issues > 0
            else 0
        )

        dev_total = profile.get("total_issues", 0)
        dev_blockers = profile.get("blocker_count", 0)
        dev_blocker_pct = (dev_blockers / dev_total * 100) if dev_total > 0 else 0

        return {
            "team_avg_blocker_pct": round(avg_team_blocker_pct, 1),
            "dev_blocker_pct": round(dev_blocker_pct, 1),
            "vs_team": round(dev_blocker_pct - avg_team_blocker_pct, 1),
        }

    # ── Report formatting ───────────────────────────────────────

    def format_report(self, result: Dict[str, Any]) -> str:
        """Format learning advice result as a readable markdown report.

        Renders both LLM-generated analysis (root causes, quizzes,
        targeted resources) and deterministic data (profile stats).
        """
        lines = [
            f"📚 【{result.get('developer', 'Unknown')}】的个性化提升计划"
            f"（基于近{result.get('days', 30)}天数据）",
            f"生成时间：{result.get('timestamp', '')}",
            "",
        ]

        profile = result.get("profile", {})
        team_metrics = result.get("team_metrics", {})

        # Error profile
        lines.append("📊 错题画像")
        lines.append(f"- 总问题数：{profile.get('total_issues', 0)} 个")
        lines.append(f"- Blocker：{profile.get('blocker_count', 0)} 个")

        if team_metrics:
            team_avg = team_metrics.get("team_avg_blocker_pct", 0)
            dev_pct = team_metrics.get("dev_blocker_pct", 0)
            vs = team_metrics.get("vs_team", 0)
            direction = "↑ 高于" if vs > 0 else ("↓ 低于" if vs < 0 else "≈ 等于")
            lines.append(
                f"  个人 Blocker 占比：{dev_pct}%（团队均值 {team_avg}%，"
                f"{direction}团队均值）"
            )
        lines.append("")

        # High frequency weaknesses
        weaknesses = result.get("weaknesses", [])
        if weaknesses:
            lines.append("🎯 高频弱点")
            for weakness in weaknesses:
                lines.append(
                    f"{weakness['rank']}. [{weakness['type']}] "
                    f"- {weakness['total_count']} 次"
                )
                lines.append(
                    f"   严重程度：{weakness['blocker_count']} Blocker "
                    f"/ {weakness['warning_count']} Warning"
                )
                lines.append(f"   最近一次：{weakness['last_occurrence']}")
            lines.append("")

        # LLM-generated recommendations (with quizzes)
        recommendations = result.get("recommendations", [])
        root_causes = result.get("root_causes", {})
        if recommendations:
            for rec in recommendations:
                issue_type = rec.get("issue_type", "")
                urgency = rec.get("urgency", "")

                # Root cause
                root_cause = rec.get("root_cause") or root_causes.get(issue_type, "")
                lines.append(f"{urgency}{issue_type}")
                lines.append(f"根源分析：{root_cause}")
                lines.append("")

                # Learning resources
                resources = rec.get("resources", [])
                if resources:
                    lines.append("📚 学习资源：")
                    for r in resources:
                        priority_mark = "★" if r.get("priority") == "high" else "☆"
                        lines.append(f"  {priority_mark} {r['name']}（{r['type']}）")
                        focus = r.get("focus", "")
                        if focus:
                            lines.append(f"    → {focus}")
                    lines.append("")

                # Actions
                actions = rec.get("actions", [])
                if actions:
                    lines.append("🔧 实践行动：")
                    for a in actions:
                        lines.append(f"  - {a}")
                    lines.append("")

                # Verification quizzes — the key new section
                quizzes = rec.get("verification_quizzes", [])
                if quizzes:
                    lines.append("✏️ 验证题目：")
                    for qi, q in enumerate(quizzes, 1):
                        qtype = q.get("type", "题目")
                        lines.append(f"  {qi}. 【{qtype}】{q['question']}")
                        hints = q.get("answer_hints", [])
                        if hints:
                            lines.append(f"     答案要点：{'；'.join(hints)}")
                    lines.append("")

                # Goal
                goal = rec.get("goal", "")
                if goal:
                    lines.append(f"⏰ 改进目标：{goal}")
                    lines.append("")
        else:
            # Fallback: use root_causes directly when LLM recommendations
            # are empty (e.g., during fallback scenario)
            if root_causes:
                for issue_type, cause in root_causes.items():
                    lines.append(f"【{issue_type}】")
                    lines.append(f"根源分析：{cause}")
                    lines.append("")

        # Collaboration suggestions
        collaboration = result.get("collaboration", [])
        if collaboration:
            lines.append("👥 团队协同建议")
            for suggestion in collaboration:
                lines.append(f"- {suggestion}")
            lines.append("")

        # Error hint
        if "error" in result:
            lines.append(f"⚠️ 注意：方案生成过程中出现异常（{result['error'][:100]}）")
            lines.append("   请稍后重试以获取完整的学习方案。")
            lines.append("")

        # Next steps
        lines.append("📝 后续行动")
        lines.append("1. 本周内完成紧急项学习")
        lines.append("2. 完成验证题目，检验学习效果")
        lines.append("3. 两周后运行 `python main.py profile` 复盘改进效果")

        return "\n".join(lines)
