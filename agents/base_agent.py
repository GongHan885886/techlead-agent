"""Base agent class for TechLead agent system.

All specialist agents inherit from this base class.
"""

import json
import time
import uuid
from abc import ABC, abstractmethod
from typing import Dict, Any, Optional, List
from pathlib import Path
from datetime import datetime

from openai import OpenAI

from config import settings
from utils.logger import get_logger


class BaseAgent(ABC):
    """Base agent with common functionality.

    Provides LLM calls with span-based tracing: every llm_call writes a
    structured trace entry containing token consumption and latency.
    """

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

        # ── Tracing fields ──
        self._trace_id: Optional[str] = None        # one per user interaction
        self._current_span_id: Optional[str] = None  # current span in the tree
        self._parent_span_id: Optional[str] = None   # parent span in the tree
        self._span_stack: List[str] = []             # for nested spans (agent→llm→tool)

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

    # ── Span lifecycle ──────────────────────────────────────────

    def _start_span(self, action: str, span_type: str = "agent_process") -> str:
        """Begin a new span and return its span_id.

        Pushes the current span onto a stack so nested calls
        (agent → llm_call → …) produce a proper parent-child tree.

        Args:
            action: Human-readable action name
            span_type: One of 'agent_process', 'llm_call', 'tool_call'

        Returns:
            str: The new span_id
        """
        span_id = str(uuid.uuid4())
        if self._current_span_id:
            self._span_stack.append(self._current_span_id)
        self._parent_span_id = self._current_span_id
        self._current_span_id = span_id

        self._write_trace({
            "type": span_type,
            "span_id": span_id,
            "parent_span_id": self._parent_span_id,
            "trace_id": self._trace_id,
            "session_id": self.session_id,
            "agent": self.name,
            "action": action,
            "status": "started",
            "timestamp": datetime.now().isoformat(),
        })
        return span_id

    def _end_span(self, **kwargs):
        """End the current span, writing remaining fields.

        Keyword args are merged into the trace entry (duration_ms,
        total_tokens, model, status, error, etc.).
        """
        if not self._current_span_id:
            return

        self._write_trace({
            "type": "agent_process",
            "span_id": self._current_span_id,
            "trace_id": self._trace_id,
            "agent": self.name,
            "status": "ok",
            "timestamp": datetime.now().isoformat(),
            **kwargs,
        })

        # Restore parent span
        self._current_span_id = (
            self._span_stack.pop() if self._span_stack else self._parent_span_id
        )

    # ── LLM call with tracing ───────────────────────────────────

    async def llm_call(
        self,
        messages: List[Dict[str, str]],
        tools: Optional[List[Dict]] = None,
    ) -> str:
        """Make an LLM API call with exact-match caching and full tracing.

        Every call — cache hit or API request — writes a structured
        span entry that includes token consumption, latency, model,
        and status.
        """
        from tools.cache_manager import get_cache_manager
        cache_manager = get_cache_manager()

        prompt = json.dumps(messages, sort_keys=True)
        span_id = self._start_span("llm_call", "llm_call")

        # ── Cache check ──
        cached = cache_manager.get_llm(prompt, self.model)
        if cached is not None:
            self._write_trace({
                "type": "llm_call",
                "span_id": span_id,
                "parent_span_id": self._parent_span_id,
                "trace_id": self._trace_id,
                "session_id": self.session_id,
                "agent": self.name,
                "model": self.model,
                "cache_hit": True,
                "duration_ms": 0,
                "prompt_tokens": 0,
                "completion_tokens": 0,
                "total_tokens": 0,
                "status": "ok",
                "timestamp": datetime.now().isoformat(),
            })
            # Restore parent span (don't use _end_span — already wrote)
            self._current_span_id = (
                self._span_stack.pop() if self._span_stack else self._parent_span_id
            )
            self.logger.debug("LLM cache hit (exact match)")
            return cached

        t0 = time.monotonic()
        try:
            response = self.client.chat.completions.create(
                model=self.model,
                messages=messages,
                temperature=self.temperature,
                max_tokens=self.max_tokens,
                tools=tools,
            )

            duration_ms = round((time.monotonic() - t0) * 1000, 1)
            usage = response.usage
            model_used = getattr(response, "model", None) or self.model

            result = response.choices[0].message.content or ""

            self._write_trace({
                "type": "llm_call",
                "span_id": span_id,
                "parent_span_id": self._parent_span_id,
                "trace_id": self._trace_id,
                "session_id": self.session_id,
                "agent": self.name,
                "model": model_used,
                "cache_hit": False,
                "duration_ms": duration_ms,
                "prompt_tokens": usage.prompt_tokens if usage else 0,
                "completion_tokens": usage.completion_tokens if usage else 0,
                "total_tokens": usage.total_tokens if usage else 0,
                "status": "ok",
                "timestamp": datetime.now().isoformat(),
            })

            cache_manager.set_llm(prompt, result, self.model, ttl_hours=2)

            # Restore parent span
            self._current_span_id = (
                self._span_stack.pop() if self._span_stack else self._parent_span_id
            )
            return result

        except Exception as e:
            self._write_trace({
                "type": "llm_call",
                "span_id": span_id,
                "parent_span_id": self._parent_span_id,
                "trace_id": self._trace_id,
                "session_id": self.session_id,
                "agent": self.name,
                "model": self.model,
                "cache_hit": False,
                "duration_ms": round((time.monotonic() - t0) * 1000, 1),
                "prompt_tokens": 0,
                "completion_tokens": 0,
                "total_tokens": 0,
                "status": "error",
                "error": str(e),
                "timestamp": datetime.now().isoformat(),
            })
            self._current_span_id = (
                self._span_stack.pop() if self._span_stack else self._parent_span_id
            )
            self.logger.error(f"LLM call failed: {e}")
            raise

    # ── Session / context ────────────────────────────────────────

    def set_session(self, session_id: str):
        self.session_id = session_id
        self.context["session_id"] = session_id
        self.context["timestamp"] = datetime.now().isoformat()

    def update_context(self, key: str, value: Any):
        self.context[key] = value

    def get_context(self, key: str, default: Any = None) -> Any:
        return self.context.get(key, default)

    # ── Trace logging ────────────────────────────────────────────

    def _log_execution(self, action: str, input_data: Dict, output_data: Dict):
        """Log execution for observability — legacy format.

        Kept for backward compatibility; new spans use _start_span/_end_span.
        """
        log_entry = {
            "timestamp": datetime.now().isoformat(),
            "session_id": self.session_id,
            "agent": self.name,
            "action": action,
            "input": input_data,
            "output": output_data,
        }

        if settings.trace_enabled:
            self._write_trace(log_entry)

    def _write_trace(self, log_entry: Dict):
        """Write a trace entry to JSONL file + SQLite spans table.

        JSONL = cold backup (grep/jq friendly).
        SQLite = hot query path (dashboard/analytics).

        Args:
            log_entry: Flat dictionary — all keys are written as-is.
        """
        settings.logs_dir.mkdir(parents=True, exist_ok=True)
        trace_file = settings.logs_dir / f"traces_{datetime.now().strftime('%Y-%m-%d')}.jsonl"

        with open(trace_file, "a", encoding="utf-8") as f:
            f.write(json.dumps(log_entry, ensure_ascii=False) + "\n")

        # Dual-write to SQLite for dashboard queries (best-effort)
        try:
            from tools.memory_store import write_span
            write_span(log_entry)
        except Exception:
            pass

    # ── Output formatting ────────────────────────────────────────

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

        lines = [f"【{self.name}】"]
        for key, value in output.items():
            lines.append(f"{key}: {value}")
        return "\n".join(lines)
