"""Code reviewer agent for MR code review."""

from typing import Dict, Any, List, Optional
from datetime import datetime

from agents.base_agent import BaseAgent
from tools.git_client import get_git_client


class CodeReviewerAgent(BaseAgent):
    """Agent specialized in reviewing code changes (MRs)."""

    # Review focus areas
    FOCUS_AREAS = {
        "transaction": ["transaction", "事务"],
        "multithread": ["multithread", "多线程", "concurrent", "并发"],
        "logging": ["logging", "日志", "log"],
        "api": ["api", "接口"],
        "sql": ["sql", "query", "查询"],
    }

    def __init__(self):
        """Initialize code reviewer agent."""
        super().__init__(name="code_reviewer")

    async def process(self, input_data: Dict[str, Any]) -> Dict[str, Any]:
        """Review MR code changes.

        Args:
            input_data: Must contain 'mr_id' or 'diff'

        Returns:
            dict: Review results with comments
        """
        mr_id = input_data.get("mr_id")
        diff = input_data.get("diff")
        focus_areas = input_data.get("focus_areas", [])
        story = input_data.get("story")  # Optional: {"id": "...", "title": "..."}

        self._log_execution("review_code", input_data, {})

        # Get MR diff if not provided
        if not diff and mr_id:
            git_client = get_git_client()
            mr_data = await git_client.fetch_mrs()
            mr = next((m for m in mr_data if m["iid"] == mr_id), None)

            if mr:
                diff = await git_client.fetch_mr_diff(mr["id"])
            else:
                return {"error": f"MR !{mr_id} not found"}

        if not diff:
            return {"error": "No diff provided and MR not found"}

        # Detect focus areas
        if not focus_areas:
            focus_areas = self._detect_focus_areas(diff)

        # Perform review
        findings = await self._review_diff(diff, focus_areas)

        # Categorize findings
        blockers = [f for f in findings if f["severity"] == "blocker"]
        warnings = [f for f in findings if f["severity"] == "warning"]
        suggestions = [f for f in findings if f["severity"] == "suggestion"]

        # Determine overall status
        passed = len(blockers) == 0

        result = {
            "intent": "code_review",
            "mr_id": mr_id,
            "story": story,
            "focus_areas": focus_areas,
            "passed": passed,
            "blockers": blockers,
            "warnings": warnings,
            "suggestions": suggestions,
            "total_findings": len(findings),
            "timestamp": datetime.now().isoformat(),
        }

        self._log_execution("review_code_complete", input_data, result)
        return result

    def _detect_focus_areas(self, diff: str) -> List[str]:
        """Detect review focus areas from diff.

        Args:
            diff: Code diff

        Returns:
            List of focus area identifiers
        """
        diff_lower = diff.lower()
        detected = []

        for area, patterns in self.FOCUS_AREAS.items():
            if any(pattern in diff_lower for pattern in patterns):
                detected.append(area)

        return list(set(detected))

    async def _review_diff(self, diff: str, focus_areas: List[str]) -> List[Dict[str, Any]]:
        """Review diff against focus area rules.

        Args:
            diff: Code diff
            focus_areas: List of focus areas

        Returns:
            List of findings
        """
        findings = []

        for area in focus_areas:
            area_findings = await self._review_focus_area(area, diff)
            findings.extend(area_findings)

        return findings

    async def _review_focus_area(self, focus_area: str, diff: str) -> List[Dict[str, Any]]:
        """Review diff against a specific focus area.

        Args:
            focus_area: Focus area identifier
            diff: Code diff

        Returns:
            List of findings
        """
        from tools.rule_loader import load_rules_text

        try:
            # Load rules for focus area
            rules_text = load_rules_text(focus_area)

            # Build prompt
            messages = [
                {"role": "system", "content": self.system_prompt},
                {"role": "user", "content": f"{rules_text}\n\n请审查以下代码变更：\n\n{diff}"},
            ]

            # Call LLM
            response = await self.llm_call(messages)

            # Parse structured response
            findings = self._parse_review_response(response, focus_area)

            return findings

        except Exception as e:
            self.logger.error(f"Failed to review focus area {focus_area}: {e}")
            return []

    def _parse_review_response(self, response: str, focus_area: str) -> List[Dict[str, Any]]:
        """Parse LLM response into structured findings.

        Args:
            response: LLM response text
            focus_area: Focus area identifier

        Returns:
            List of finding dictionaries
        """
        findings = []

        # Parse by severity sections
        current_section = None
        current_file = None
        current_line = None

        for line in response.split("\n"):
            line = line.strip()

            if "Blocking 评论" in line:
                current_section = "blocker"
            elif "Warning 评论" in line:
                current_section = "warning"
            elif "Suggestion" in line:
                current_section = "suggestion"

            # Extract file and line info
            if ".java:" in line or ".py:" in line:
                parts = line.split(":")
                if len(parts) >= 2:
                    current_file = parts[0]
                    current_line = parts[1].split()[0]

            # Extract finding description
            if current_section and line and not line.startswith(("Blocking", "Warning", "Suggestion")):
                finding = {
                    "focus_area": focus_area,
                    "severity": current_section,
                    "file": current_file,
                    "line": current_line,
                    "description": line,
                }
                findings.append(finding)

        return findings

    def format_report(self, result: Dict[str, Any]) -> str:
        """Format review result as a readable report.

        Args:
            result: Review result dictionary

        Returns:
            str: Formatted report
        """
        story = result.get("story")
        lines = [
            f"🔍 CR 审查报告 - MR !{result.get('mr_id', 'Unknown')}",
        ]

        if story:
            lines.insert(1, f"需求：{story.get('title', '')}")

        lines.extend([
            f"关注领域：{', '.join(result.get('focus_areas', []))}",
            f"评审时间：{result.get('timestamp', '')}",
            "",
            f"【自检结果】{'✅ 通过' if result.get('passed') else '❌ 不通过'}",
            "",
        ])

        blockers = result.get("blockers", [])
        warnings = result.get("warnings", [])
        suggestions = result.get("suggestions", [])

        if blockers:
            lines.append("【Blocking 评论】（必须修复）：")
            for i, blocker in enumerate(blockers, 1):
                file_line = f"{blocker.get('file', '')}:{blocker.get('line', '')}" if blocker.get('file') else "Unknown"
                lines.append(f"{i}. `{file_line}` - {blocker['description']}")
            lines.append("")

        if warnings:
            lines.append("【Warning 评论】（建议修复）：")
            for i, warning in enumerate(warnings, 1):
                file_line = f"{warning.get('file', '')}:{warning.get('line', '')}" if warning.get('file') else "Unknown"
                lines.append(f"{i}. `{file_line}` - {warning['description']}")
            lines.append("")

        if suggestions:
            lines.append("【Suggestion】（最佳实践）：")
            for i, suggestion in enumerate(suggestions, 1):
                file_line = f"{suggestion.get('file', '')}:{suggestion.get('line', '')}" if suggestion.get('file') else "Unknown"
                lines.append(f"{i}. `{file_line}` - {suggestion['description']}")
            lines.append("")

        lines.append(f"【统计】")
        lines.append(f"- Blocker: {len(blockers)} 个")
        lines.append(f"- Warning: {len(warnings)} 个")
        lines.append(f"- Suggestion: {len(suggestions)} 个")
        lines.append("")
        lines.append("等待技术经理确认...")
        lines.append("输入 '确认' 提交评论，'取消' 放弃")

        return "\n".join(lines)