"""
AutoSRE — Centralized Configuration
Loads settings from environment variables with sensible defaults.
"""

import os
from pathlib import Path
from dotenv import load_dotenv

# Load .env from project root (one level up from autosre/)
_env_path = Path(__file__).resolve().parent.parent / ".env"
load_dotenv(_env_path)


class Settings:
    """Application-wide settings loaded from environment."""

    # --- Ollama LLM ---
    OLLAMA_BASE_URL: str = os.getenv("OLLAMA_BASE_URL", "http://localhost:11434")
    OLLAMA_MODEL: str = os.getenv("OLLAMA_MODEL", "qwen2.5-coder:3b")
    OLLAMA_FALLBACK_MODEL: str = os.getenv("OLLAMA_FALLBACK_MODEL", "deepseek-coder:1.3b")

    # --- Redis ---
    REDIS_URL: str = os.getenv("REDIS_URL", "redis://localhost:6379/0")

    # --- PostgreSQL ---
    POSTGRES_HOST: str = os.getenv("POSTGRES_HOST", "localhost")
    POSTGRES_PORT: int = int(os.getenv("POSTGRES_PORT", "5432"))
    POSTGRES_DB: str = os.getenv("POSTGRES_DB", "autosre")
    POSTGRES_USER: str = os.getenv("POSTGRES_USER", "autosre")
    POSTGRES_PASSWORD: str = os.getenv("POSTGRES_PASSWORD", "autosre_secret_2026")

    @property
    def POSTGRES_DSN(self) -> str:
        return (
            f"host={self.POSTGRES_HOST} port={self.POSTGRES_PORT} "
            f"dbname={self.POSTGRES_DB} user={self.POSTGRES_USER} "
            f"password={self.POSTGRES_PASSWORD}"
        )

    # --- Slack ---
    SLACK_BOT_TOKEN: str = os.getenv("SLACK_BOT_TOKEN", "")
    SLACK_INCIDENT_CHANNEL: str = os.getenv("SLACK_INCIDENT_CHANNEL", "#incidents")

    # --- GitHub ---
    GITHUB_TOKEN: str = os.getenv("GITHUB_TOKEN", "")
    GITHUB_REPO_OWNER: str = os.getenv("GITHUB_REPO_OWNER", "")
    GITHUB_REPO_NAME: str = os.getenv("GITHUB_REPO_NAME", "")

    # --- Jira ---
    JIRA_API_TOKEN: str = os.getenv("JIRA_API_TOKEN", "")
    JIRA_EMAIL: str = os.getenv("JIRA_EMAIL", "")
    JIRA_URL: str = os.getenv("JIRA_URL", "")
    JIRA_PROJECT_KEY: str = os.getenv("JIRA_PROJECT_KEY", "SRE")

    # --- Langfuse ---
    LANGFUSE_SECRET_KEY: str = os.getenv("LANGFUSE_SECRET_KEY", "")
    LANGFUSE_PUBLIC_KEY: str = os.getenv("LANGFUSE_PUBLIC_KEY", "")
    LANGFUSE_BASE_URL: str = os.getenv("LANGFUSE_BASE_URL", "https://cloud.langfuse.com")

    # --- Email ---
    SMTP_HOST: str = os.getenv("SMTP_HOST", "smtp.gmail.com")
    SMTP_PORT: int = int(os.getenv("SMTP_PORT", "587"))
    SMTP_EMAIL: str = os.getenv("SMTP_EMAIL", "")
    SMTP_PASSWORD: str = os.getenv("SMTP_PASSWORD", "")

    # --- Gateway ---
    GATEWAY_HOST: str = os.getenv("GATEWAY_HOST", "0.0.0.0")
    GATEWAY_PORT: int = int(os.getenv("GATEWAY_PORT", "8000"))
    PAGERDUTY_WEBHOOK_SECRET: str = os.getenv("PAGERDUTY_WEBHOOK_SECRET", "")
    GITHUB_WEBHOOK_SECRET: str = os.getenv("GITHUB_WEBHOOK_SECRET", "")
    SLACK_SIGNING_SECRET: str = os.getenv("SLACK_SIGNING_SECRET", "")

    def has_slack(self) -> bool:
        return bool(self.SLACK_BOT_TOKEN and self.SLACK_BOT_TOKEN != "xoxb-your-token-here")

    def has_github(self) -> bool:
        return bool(self.GITHUB_TOKEN and self.GITHUB_TOKEN != "ghp_your_token_here")

    def has_jira(self) -> bool:
        return bool(self.JIRA_API_TOKEN and self.JIRA_EMAIL and self.JIRA_URL)

    def has_langfuse(self) -> bool:
        return bool(self.LANGFUSE_SECRET_KEY and self.LANGFUSE_PUBLIC_KEY)

    def has_email(self) -> bool:
        return bool(self.SMTP_EMAIL and self.SMTP_PASSWORD)


settings = Settings()
