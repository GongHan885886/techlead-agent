"""Base agent class for TechLead agent system.

All specialist agents inherit from this base class.
"""

from abc import ABC, abstractmethod
from typing import Dict, Any, Optional, List
from pathlib import Path
from datetime import datetime

from openai import OpenAI

from config import settings
from utils.logger import get_logger


class BaseAgent(ABC):
    """Base agent with common functionality."""

    def __init__(
        self,
        name: str,
        system_prompt: Optional[str] = None,
        model: Optional[str] = None,
        temperature: float = 0.1,
        max_tokens: int = 4000,
    ):
        """Initialize base agent.

        Args:
            name: Agent name
            system_prompt: System prompt (loaded from file if not provided)
            model: LLM model to use
            temperature: Temperature for LLM
            max_tokens: Max tokens for LLM response
        """
        self.name = name
        self.model = model or settings.llm_model
        self.temperature = temperature
        self.max_tokens = max_tokens
        self.logger = get_logger(self.name)

        # Load system prompt
        self.system_prompt = system_prompt or self._load_system_prompt()

        # Initialize LLM client
        self.client = OpenAI(
            api_key=settings.openai_api_key,
            base_url=settings.openai_api_base,
        )

        # Execution context
        self.session_id: Optional[str] = None
        self.context: Dict[str, Any] = {}

    def _load_system_prompt(self) -> str:
        """Load system prompt from prompts directory.

        Returns:
            str: System prompt content
        """
        prompt_file = settings.root_dir / "prompts" / f"{self.name}_system.txt"

        if prompt_file.exists():
            with open(prompt_file, "r", encoding="utf-8") as f:
                return f.read()

        # Default prompt if file doesn't exist
        return f"You are {self.name}, an AI assistant for technical management tasks."

    @abstractmethod
    async def process(self, input_data: Dict[str, Any]) -> Dict[str, Any]:
        """Process input and return result.

        Args:
            input_data: Input data for the agent

        Returns:
            dict: Processing result
        """
        pass

    async def llm_call(
        self,
        messages: List[Dict[str, str]],
        tools: Optional[List[Dict]] = None,
    ) -> str:
        """Make an LLM API call.

        Args:
            messages: List of message dicts (role, content)
            tools: Optional list of tools for function calling

        Returns:
            str: LLM response text
        """
        try:
            response = self.client.chat.completions.create(
                model=self.model,
                messages=messages,
                temperature=self.temperature,
                max_tokens=self.max_tokens,
                tools=tools,
            )

            return response.choices[0].message.content or ""

        except Exception as e:
            self.logger.error(f"LLM call failed: {e}")
            raise

    def set_session(self, session_id: str):
        """Set session ID for context tracking.

        Args:
            session_id: Unique session identifier
        """
        self.session_id = session_id
        self.context["session_id"] = session_id
        self.context["timestamp"] = datetime.now().isoformat()

    def update_context(self, key: str, value: Any):
        """Update execution context.

        Args:
            key: Context key
            value: Context value
        """
        self.context[key] = value

    def get_context(self, key: str, default: Any = None) -> Any:
        """Get value from context.

        Args:
            key: Context key
            default: Default value if key not found

        Returns:
            Context value or default
        """
        return self.context.get(key, default)

    def _log_execution(self, action: str, input_data: Dict, output_data: Dict):
        """Log execution for observability.

        Args:
            action: Action name
            input_data: Input data
            output_data: Output data
        """
        log_entry = {
            "timestamp": datetime.now().isoformat(),
            "session_id": self.session_id,
            "agent": self.name,
            "action": action,
            "input": input_data,
            "output": output_data,
        }

        # Write to trace log if enabled
        if settings.trace_enabled:
            self._write_trace(log_entry)

    def _write_trace(self, log_entry: Dict):
        """Write log entry to trace file.

        Args:
            log_entry: Log entry dictionary
        """
        import json

        settings.logs_dir.mkdir(parents=True, exist_ok=True)
        trace_file = settings.logs_dir / f"traces_{datetime.now().strftime('%Y-%m-%d')}.jsonl"

        with open(trace_file, "a", encoding="utf-8") as f:
            f.write(json.dumps(log_entry, ensure_ascii=False) + "\n")

    def format_output(self, output: Dict, template: Optional[str] = None) -> str:
        """Format output for presentation.

        Args:
            output: Output dictionary
            template: Optional format template

        Returns:
            str: Formatted output
        """
        if template:
            return template.format(**output)

        # Default formatting
        lines = [f"【{self.name}】"]
        for key, value in output.items():
            lines.append(f"{key}: {value}")
        return "\n".join(lines)