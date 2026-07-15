"""Design reviewer agent for technical方案评审."""

from typing import Dict, Any, List, Optional
from datetime import datetime

from agents.base_agent import BaseAgent
from tools.rule_loader import load_rules_text, get_available_scenarios


class DesignReviewerAgent(BaseAgent):
    """Agent specialized in reviewing technical design documents."""

    # Scenario detection patterns
    SCENARIO_PATTERNS = {
        "file-upload": ["文件上传", "上传", "upload", "文件"],
        "table-design": ["表设计", "数据表", "数据库", "table"],
        "message-queue": ["消息队列", "mq", "kafka", "rabbitmq", "queue"],
        "monitoring": ["监控", "告警", "日志", "monitoring", "alert"],
        "crud": ["增删改查", "查询", "接口"],
        "cache": ["缓存", "redis", "cache", "caching"],
        "search": ["搜索", "搜索", "elasticsearch", "search"],
        "notification": ["通知", "消息推送", "notification"],
        "security": ["安全", "权限", "认证", "鉴权", "security", "auth"],
    }

    def __init__(self):
        """Initialize design reviewer agent."""
        super().__init__(name="design_reviewer")

    async def process(self, input_data: Dict[str, Any]) -> Dict[str, Any]:
        """Review technical design document.

        Args:
            input_data: Must contain 'content' (design doc) and optionally 'scenarios'

        Returns:
            dict: Review results with findings
        """
        content = input_data.get("content", "")
        provided_scenarios = input_data.get("scenarios", [])
        developer = input_data.get("developer", "Unknown")

        self._log_execution("review_design", input_data, {})

        # Detect scenarios if not provided
        if not provided_scenarios:
            detected_scenarios = self._detect_scenarios(content)
        else:
            detected_scenarios = provided_scenarios

        # Load rules for each scenario
        findings = []
        for scenario in detected_scenarios:
            scenario_findings = await self._review_scenario(scenario, content)
            findings.extend(scenario_findings)

        # Categorize findings
        blockers = [f for f in findings if f["severity"] == "blocker"]
        warnings = [f for f in findings if f["severity"] == "warning"]
        infos = [f for f in findings if f["severity"] == "info"]

        # Determine overall status
        passed = len(blockers) == 0

        result = {
            "intent": "deep_review",
            "developer": developer,
            "scenarios": detected_scenarios,
            "passed": passed,
            "blockers": blockers,
            "warnings": warnings,
            "infos": infos,
            "total_findings": len(findings),
            "timestamp": datetime.now().isoformat(),
        }

        self._log_execution("review_design_complete", input_data, result)
        return result

    def _detect_scenarios(self, content: str) -> List[str]:
        """Detect technical scenarios from content.

        Args:
            content: Design document content

        Returns:
            List of detected scenarios
        """
        content_lower = content.lower()
        detected = []

        for scenario, patterns in self.SCENARIO_PATTERNS.items():
            if any(pattern in content_lower for pattern in patterns):
                detected.append(scenario)

        # Default to "crud" if no scenarios detected
        if not detected:
            detected.append("crud")

        return list(set(detected))

    async def _review_scenario(self, scenario: str, content: str) -> List[Dict[str, Any]]:
        """Review content against scenario-specific rules.

        Args:
            scenario: Scenario identifier
            content: Content to review

        Returns:
            List of findings
        """
        try:
            # Load rules as text
            rules_text = load_rules_text(scenario)

            # Build prompt
            messages = [
                {"role": "system", "content": self.system_prompt},
                {"role": "user", "content": f"{rules_text}\n\n请审查以下技术方案：\n\n{content}"},
            ]

            # Call LLM
            response = await self.llm_call(messages)

            # Parse structured response
            findings = self._parse_review_response(response, scenario)

            return findings

        except Exception as e:
            self.logger.error(f"Failed to review scenario {scenario}: {e}")
            return []

    def _parse_review_response(self, response: str, scenario: str) -> List[Dict[str, Any]]:
        """Parse LLM response into structured findings.

        Args:
            response: LLM response text
            scenario: Scenario identifier

        Returns:
            List of finding dictionaries
        """
        findings = []

        # Parse by severity sections
        current_section = None

        for line in response.split("\n"):
            line = line.strip()

            if "🔴 Blocker" in line or "Blocker" in line:
                current_section = "blocker"
            elif "🟡 Warning" in line or "Warning" in line:
                current_section = "warning"
            elif "🟢 Info" in line or "Info" in line:
                current_section = "info"
            elif line and current_section:
                # Extract finding details
                finding = {
                    "scenario": scenario,
                    "severity": current_section,
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
        lines = [
            f"📄 技术方案评审报告",
            f"负责人：{result.get('developer', 'Unknown')}",
            f"评审时间：{result.get('timestamp', '')}",
            "",
            f"【识别场景】{', '.join(result.get('scenarios', []))}",
            "",
            f"【自检结果】{'✅ 通过' if result.get('passed') else '❌ 不通过'}",
            "",
        ]

        blockers = result.get("blockers", [])
        warnings = result.get("warnings", [])
        infos = result.get("infos", [])

        if blockers:
            lines.append("【缺失项清单】")
            lines.append("🔴 Blocker（必须补充）：")
            for i, blocker in enumerate(blockers, 1):
                lines.append(f"{i}. {blocker['description']}")
            lines.append("")

        if warnings:
            lines.append("🟡 Warning（建议补充）：")
            for i, warning in enumerate(warnings, 1):
                lines.append(f"{i}. {warning['description']}")
            lines.append("")

        if infos:
            lines.append("🟢 Info（已覆盖）：")
            for i, info in enumerate(infos, 1):
                lines.append(f"{i}. {info['description']}")
            lines.append("")

        lines.append(f"【统计】")
        lines.append(f"- Blocker: {len(blockers)} 个")
        lines.append(f"- Warning: {len(warnings)} 个")
        lines.append(f"- Info: {len(infos)} 个")

        return "\n".join(lines)