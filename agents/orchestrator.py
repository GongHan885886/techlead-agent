"""Orchestrator agent - main controller for TechLead system.

Routes user requests to specialist agents and aggregates results.
"""

import asyncio
import uuid
from typing import Dict, Any, Optional, List
from datetime import datetime

from agents.base_agent import BaseAgent
from state.session_manager import SessionManager, PendingTask


class OrchestratorAgent(BaseAgent):
    """Main orchestrator that routes requests to specialist agents."""

    # Intent mappings — more specific keywords first to avoid false matches
    INTENTS = {
        # Code review intent (check before "review" in scan)
        ("cr", "代码审查", "code review", "review-mr", "review code"): "code_review",

        # Design review intent (check before "review" in scan)
        ("评审", "方案", "design review", "深度评审", "design"): "deep_review",

        # Scan intent
        ("扫描", "scan", "今天", "daily", "检查", "关注"): "scan",

        # Weekly report intent
        ("周报", "weekly", "weekly-report", "report"): "weekly_report",

        # Learning advice intent
        ("学习", "建议", "profile", "learning", "advice", "错题"): "learning_advice",

        # Confirm intent
        ("确认", "发送", "放行", "confirm", "approve"): "confirm",

        # Cancel intent
        ("取消", "cancel", "放弃"): "cancel",

        # Help intent
        ("帮助", "help", "用法", "usage"): "help",
    }

    def __init__(self):
        """Initialize orchestrator agent."""
        super().__init__(name="orchestrator")
        self.session_manager = SessionManager()

        # Specialist agents will be initialized lazily
        self._specialists = {}

    async def process(self, input_data: Dict[str, Any]) -> Dict[str, Any]:
        """Process user request and route to specialist agents.

        Args:
            input_data: User input with 'message' key

        Returns:
            dict: Processing result
        """
        message = input_data.get("message", "")
        session_id = input_data.get("session_id") or str(uuid.uuid4())

        self.set_session(session_id)
        self._log_execution("orchestrate", input_data, {})

        # Clean up expired sessions
        self.session_manager.cleanup_expired_sessions()

        # Check for pending confirmations first
        pending = self.session_manager.get_pending_task(session_id)
        if pending:
            return await self._handle_confirmation(message, pending)

        # Identify user intent
        intent = self._identify_intent(message)
        self.logger.info(f"Intent identified: {intent}")

        # Route to appropriate handler
        result = None
        if intent == "scan":
            result = await self._handle_scan(input_data)
        elif intent == "deep_review":
            result = await self._handle_design_review(input_data)
        elif intent == "code_review":
            result = await self._handle_code_review(input_data)
        elif intent == "weekly_report":
            result = await self._handle_weekly_report(input_data)
        elif intent == "learning_advice":
            result = await self._handle_learning_advice(input_data)
        elif intent == "help":
            result = self._generate_help()
        else:
            result = {
                "intent": "unknown",
                "response": "❓ 没有理解您的意图。请使用 'help' 查看可用命令。",
            }

        # Send notification for high-risk results
        if result:
            await self._send_notification(intent, result)

        return result

    def _identify_intent(self, message: str) -> str:
        """Identify user intent from message.

        Args:
            message: User message

        Returns:
            str: Intent identifier
        """
        message_lower = message.lower()

        for keywords, intent in self.INTENTS.items():
            if any(keyword in message_lower for keyword in keywords):
                return intent

        return "unknown"

    async def _handle_scan(self, input_data: Dict[str, Any]) -> Dict[str, Any]:
        """Handle daily scan request.

        Args:
            input_data: Input data

        Returns:
            dict: Scan results
        """
        from tools.tapd_client import get_tapd_client
        from tools.git_client import get_git_client

        results = {
            "intent": "scan",
            "timestamp": datetime.now().isoformat(),
            "sections": [],
        }

        # Scan TAPD stories
        tapd_client = get_tapd_client()
        stories = await tapd_client.fetch_stories(status="进行中")
        self._analyze_story_risks(stories, results)

        # Scan GitLab MRs
        git_client = get_git_client()
        mrs = await git_client.fetch_mrs(state="opened")
        results["mrs"] = mrs
        results["mr_count"] = len(mrs)

        return results

    def _analyze_story_risks(self, stories: List[Dict], results: Dict):
        """Analyze TAPD stories for risks.

        Args:
            stories: List of stories
            results: Results dict to update
        """
        from datetime import datetime, timedelta

        high_risk = []
        warning = []

        for story in stories:
            due_date_str = story.get("due_date", "")
            progress = story.get("progress", 0)

            if not due_date_str:
                continue

            try:
                due_date = datetime.strptime(due_date_str, "%Y-%m-%d")
                days_left = (due_date - datetime.now()).days

                if days_left < 3 and progress < 80:
                    high_risk.append(story)
                elif days_left < 5 and progress < 50:
                    warning.append(story)

            except (ValueError, TypeError):
                continue

        results["stories"] = stories
        results["high_risk_stories"] = high_risk
        results["warning_stories"] = warning

    async def _handle_design_review(self, input_data: Dict[str, Any]) -> Dict[str, Any]:
        """Handle design review request by delegating to DesignReviewerAgent.

        Fetches relevant stories from TAPD and passes them as context,
        so output can be organized by story/requirement.

        Args:
            input_data: Input data with author, scenario, message, and optional content

        Returns:
            dict: Review results
        """
        from agents.design_reviewer import DesignReviewerAgent
        from tools.tapd_client import get_tapd_client

        reviewer = DesignReviewerAgent()
        author = input_data.get("author")
        scenario = input_data.get("scenario")
        message = input_data.get("message", "")

        # Try to extract author from message if not explicitly provided
        if not author:
            author = self._extract_name_from_message(message)

        # Try to fetch stories from TAPD for context
        tapd_client = get_tapd_client()
        stories = await tapd_client.fetch_stories(status="进行中")

        # Filter stories based on input context
        matched_stories = self._filter_stories(stories, author, message)

        # If we have matched stories, pass them to the reviewer
        if matched_stories:
            result = await reviewer.process({
                "content": input_data.get("content", ""),
                "scenarios": [scenario] if scenario else [],
                "stories": matched_stories,
            })
        else:
            # Fallback: no matching stories found, do legacy review
            result = await reviewer.process({
                "content": input_data.get("content", ""),
                "scenarios": [scenario] if scenario else [],
                "developer": author or "Unknown",
            })

        return result

    def _extract_name_from_message(self, message: str) -> Optional[str]:
        """Extract a person's name from a natural language message.

        Args:
            message: User message

        Returns:
            str or None: Extracted name if found
        """
        # Common Chinese surnames that appear in the system
        common_names = ["张三", "李四", "王五", "赵六", "陈七", "周八"]
        for name in common_names:
            if name in message:
                return name
        return None

    def _filter_stories(
        self, stories: list, author: Optional[str], message: str
    ) -> list:
        """Filter TAPD stories based on author, message keywords.

        Args:
            stories: List of TAPD story dicts
            author: Optional author name filter
            message: User message for keyword matching

        Returns:
            list: Filtered stories with scenarios
        """
        if not stories:
            return []

        message_lower = message.lower()

        # Extract potential author name from message if not explicitly provided
        if not author:
            # Try to match any owner name in the message
            for story in stories:
                owner = story.get("owner", "")
                if owner and owner in message:
                    author = owner
                    break

        filtered = []
        for story in stories:
            title = story.get("title", "").lower()
            owner = story.get("owner", "").lower()

            # Filter by author
            if author and author.lower() != owner:
                continue

            # Filter by message keywords (match story title)
            # Remove common intent words
            keywords = message_lower
            for word in ["评审", "方案", "设计", "review", "design", "deep_review"]:
                keywords = keywords.replace(word, "")
            keywords = keywords.strip()

            if keywords and keywords not in ("review design", "deep_review", "review", "design"):
                # Check if any keyword matches story title
                story_title_lower = story.get("title", "").lower()
                if keywords not in story_title_lower and not any(
                    kw.strip() for kw in keywords.split() if kw.strip() in story_title_lower
                ):
                    # If no title match, still include if author matched
                    if not author:
                        continue

            # Attach all scenarios (will be auto-detected from content later)
            story["scenarios"] = []
            filtered.append(story)

        return filtered

    async def _handle_code_review(self, input_data: Dict[str, Any]) -> Dict[str, Any]:
        """Handle code review request by delegating to CodeReviewerAgent.

        Args:
            input_data: Input data with mr_id and optional focus_areas

        Returns:
            dict: Review results
        """
        from agents.code_reviewer import CodeReviewerAgent
        from tools.tapd_client import get_tapd_client

        mr_id = input_data.get("mr_id")

        # If MR ID provided, fetch and review
        if mr_id:
            # Try to find associated story
            story = None
            try:
                tapd_client = get_tapd_client()
                stories = await tapd_client.fetch_stories()
                # Match by MR ID in story title or description
                for s in stories:
                    title = s.get("title", "")
                    if str(mr_id) in title:
                        story = {"id": s.get("id"), "title": s.get("title")}
                        break
            except Exception:
                pass

            reviewer = CodeReviewerAgent()
            result = await reviewer.process({
                "mr_id": mr_id,
                "focus_areas": input_data.get("focus_areas", []),
                "story": story,
            })

            return result

        # Otherwise, list available MRs
        from tools.git_client import get_git_client

        git_client = get_git_client()
        mrs = await git_client.fetch_mrs(state="opened")

        return {
            "intent": "code_review",
            "available_mrs": mrs,
            "message": f"Found {len(mrs)} open MRs. Specify MR ID to review.",
        }

    async def _handle_weekly_report(self, input_data: Dict[str, Any]) -> Dict[str, Any]:
        """Handle weekly report request.

        Args:
            input_data: Input data

        Returns:
            dict: Weekly report data
        """
        from agents.delivery_tracker import DeliveryTrackerAgent
        from agents.learning_advisor import LearningAdvisorAgent
        from tools.talent_developer import get_team_overview

        # Get delivery analysis
        delivery_agent = DeliveryTrackerAgent()
        delivery_result = await delivery_agent.process({"days": 7})

        # Get team overview
        team = get_team_overview(days=7)

        # Generate formatted report
        return {
            "intent": "weekly_report",
            "delivery": delivery_result,
            "team": team,
            "message": "🔧 Weekly report generator - See delivery section for details",
        }

    async def _handle_learning_advice(self, input_data: Dict[str, Any]) -> Dict[str, Any]:
        """Handle learning advice request.

        Args:
            input_data: Input data

        Returns:
            dict: Learning advice
        """
        from agents.learning_advisor import LearningAdvisorAgent

        developer = input_data.get("developer")

        if not developer:
            return {
                "intent": "learning_advice",
                "message": "Please specify developer name. Usage: learning_advice --developer <name>",
            }

        # Route to LearningAdvisor agent
        learning_agent = LearningAdvisorAgent()
        result = await learning_agent.process({
            "developer": developer,
            "days": input_data.get("days", 30),
        })

        # Format report
        if result.get("intent") == "learning_advice" and "error" not in result:
            formatted_report = learning_agent.format_report(result)
            return {
                "intent": "learning_advice",
                "developer": developer,
                "raw_result": result,
                "formatted_report": formatted_report,
            }

        return result

    async def _handle_confirmation(self, message: str, pending: PendingTask) -> Dict[str, Any]:
        """Handle user confirmation for pending task.

        Args:
            message: User's confirmation message
            pending: Pending task

        Returns:
            dict: Confirmation result
        """
        message_lower = message.lower()

        if "确认" in message_lower or "发送" in message_lower or "放行" in message_lower:
            # Execute pending task
            result = await pending.execute()
            self.session_manager.clear_pending(self.session_id)

            return {
                "intent": "confirm",
                "task_type": pending.task_type,
                "result": result,
                "message": "✅ 操作已执行",
            }

        elif "取消" in message_lower or "放弃" in message_lower:
            # Cancel pending task
            self.session_manager.clear_pending(self.session_id)

            return {
                "intent": "cancel",
                "task_type": pending.task_type,
                "message": "❌ 操作已取消",
            }

        else:
            return {
                "intent": "unknown",
                "message": "请确认：输入 '确认' 执行，'取消' 放弃",
            }

    def _generate_help(self) -> Dict[str, Any]:
        """Generate help message.

        Returns:
            dict: Help information
        """
        return {
            "intent": "help",
            "message": """🤖 TechLead Agent 可用命令：

【扫描】
  scan / 扫描今天的事情

【方案评审】
  review-design --author <name> --scenario <type>
  深度评审张三的文件上传方案

【代码审查】
  review-mr --mr-id <123>
  CR MR !123

【周报】
  weekly-report / 生成周报

【学习建议】
  profile --developer <name>
  查询李四的错题情况

【其他】
  help - 显示此帮助信息
  confirm - 确认执行待处理任务
  cancel - 取消待处理任务
""",
        }

    def set_pending_task(
        self,
        task_type: str,
        task_data: Dict[str, Any],
        execute_callback,
    ):
        """Set a pending task requiring user confirmation.

        Args:
            task_type: Type of pending task
            task_data: Task data
            execute_callback: Async callback to execute on confirmation
        """
        task = PendingTask(
            task_type=task_type,
            task_data=task_data,
            execute_callback=execute_callback,
            created_at=datetime.now(),
        )

        self.session_manager.set_pending_task(self.session_id, task)

    async def _send_notification(self, intent: str, result: Dict[str, Any]):
        """Send notification for important events.

        Args:
            intent: Intent type
            result: Processing result
        """
        from tools.notifier import get_notifier

        notifier = get_notifier()

        if not notifier.enabled:
            return

        try:
            if intent == "scan":
                high_risk = result.get("high_risk_stories", [])
                if high_risk:
                    titles = ", ".join(s["title"] for s in high_risk[:3])
                    notifier.notify_user(
                        recipient="techlead",
                        title="🚨 高风险需求提醒",
                        content=f"以下需求存在高风险：{titles}",
                    )

            elif intent == "deep_review":
                blockers = result.get("blockers", [])
                if blockers:
                    notifier.send_review_request(
                        target="design",
                        target_type="方案",
                        reviewer="techlead",
                        description=f"方案评审发现 {len(blockers)} 个 Blocker 项",
                    )

            elif intent == "code_review":
                blockers = result.get("blockers", [])
                if blockers:
                    mr_id = result.get("mr_id", "Unknown")
                    notifier.send_cr_feedback(
                        mr_id=mr_id,
                        author="Unknown",
                        issues=blockers + result.get("warnings", []),
                    )

            elif intent == "learning_advice":
                developer = result.get("developer", "Unknown")
                notifier.send_learning_advice(
                    developer=developer,
                    advice_summary=f"已生成 {developer} 的学习提升计划",
                    focus_areas=[w["type"] for w in result.get("weaknesses", [])],
                )

        except Exception as e:
            self.logger.warning(f"Failed to send notification: {e}")