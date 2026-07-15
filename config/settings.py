"""Global configuration management."""

import os
from pathlib import Path
from typing import List

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Global settings for TechLead Agent."""

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )

    # LLM Configuration
    openai_api_key: str
    openai_api_base: str = "https://api.openai.com/v1"
    llm_model: str = "gpt-4o"
    llm_temperature: float = 0.1
    llm_max_tokens: int = 4000

    # TAPD Configuration
    tapd_api_user: str = ""
    tapd_api_password: str = ""
    tapd_company_id: str = ""

    # Git Configuration
    gitlab_token: str = ""
    gitlab_url: str = "https://gitlab.example.com"
    default_project_id: int = 12345
    default_branch: str = "main"

    # Database Configuration
    db_path: str = "./storage/memory.db"

    # Notification Configuration
    notification_webhook_url: str = ""
    notification_enabled: bool = False

    # System Configuration
    log_level: str = "INFO"
    trace_enabled: bool = True
    session_timeout_minutes: int = 30

    # Paths
    root_dir: Path = Path(__file__).parent.parent
    rules_dir: Path = root_dir / ".techlead-rules"
    storage_dir: Path = root_dir / "storage"
    logs_dir: Path = storage_dir / "logs"
    state_dir: Path = root_dir / "state"

    # Risk Thresholds
    urgent_risk_days: int = 3  # < 3天且进度<80% 为紧急
    warning_risk_days: int = 5  # < 5天且进度<50% 为警告
    stale_update_days: int = 3  # 状态未更新>3天可能阻塞

    # Efficiency Thresholds
    efficiency_anomaly_threshold: float = 1.3  # > 团队均值 * 1.3 为异常
    quality_anomaly_threshold: float = 1.5  # > 团队均值 * 1.5 为异常

    @property
    def available_llm_providers(self) -> List[str]:
        """Return list of configured LLM providers."""
        providers = []
        if self.openai_api_key:
            providers.append("openai")
        return providers

    def get_rules_file(self, rule_key: str) -> Path:
        """Get the full path for a rules file by key."""
        # Rule mapping will be in rule_loader.py
        from tools.rule_loader import RULE_MAP

        if rule_key not in RULE_MAP:
            raise ValueError(f"Unknown rule key: {rule_key}")
        return self.rules_dir / RULE_MAP[rule_key]


# Global settings instance
settings = Settings()