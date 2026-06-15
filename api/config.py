from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path


ROOT_DIR = Path(__file__).resolve().parents[1]
ENV_PATH = ROOT_DIR / ".env"


def _load_dotenv() -> None:
    if not ENV_PATH.exists():
        return

    for raw_line in ENV_PATH.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        key = key.strip()
        value = value.strip().strip('"').strip("'")
        os.environ.setdefault(key, value)


_load_dotenv()


def _bool_env(name: str, default: bool = False) -> bool:
    value = os.getenv(name)
    if value is None:
        return default
    return value.strip().lower() in {"1", "true", "yes", "y", "on"}


@dataclass(frozen=True)
class Settings:
    eletrofrio_api_base_url: str = os.getenv(
        "ELETROFRIO_API_BASE_URL",
        "https://credenciamento.eletrofrio.com.br:5900/galileo/api/api_hackathon",
    ).rstrip("/")
    eletrofrio_team_name: str = os.getenv("ELETROFRIO_TEAM_NAME", "")
    supabase_url: str = os.getenv("SUPABASE_URL", "").rstrip("/")
    supabase_service_role_key: str = os.getenv("SUPABASE_SERVICE_ROLE_KEY", "")
    internal_service_token: str = os.getenv("ELETROFRIO_INTERNAL_SERVICE_TOKEN", os.getenv("SUPABASE_SERVICE_ROLE_KEY", ""))
    openai_api_key: str = os.getenv("OPENAI_API_KEY", "")
    openai_model: str = os.getenv("OPENAI_MODEL", "gpt-4o-mini")
    collector_interval_minutes: int = int(os.getenv("COLLECTOR_INTERVAL_MINUTES", "5"))
    start_internal_scheduler: bool = _bool_env("ELETROFRIO_START_INTERNAL_SCHEDULER", True)
    whatsapp_enabled: bool = _bool_env("WHATSAPP_ENABLED", False)
    whatsapp_alert_enabled: bool = _bool_env("WHATSAPP_ALERT_ENABLED", False)
    whatsapp_alert_to: str = os.getenv("WHATSAPP_ALERT_TO", os.getenv("WHATSAPP_ALLOWED_RECIPIENTS", ""))
    whatsapp_alert_cooldown_minutes: int = int(os.getenv("WHATSAPP_ALERT_COOLDOWN_MINUTES", "60"))
    whatsapp_dry_run: bool = _bool_env("WHATSAPP_DRY_RUN", True)
    app_public_url: str = os.getenv("APP_PUBLIC_URL", "https://eletrofrio.147.15.56.49.nip.io").rstrip("/")
    auto_open_tickets: bool = _bool_env("AUTO_OPEN_TICKETS", False)
    http_timeout_seconds: int = int(os.getenv("HTTP_TIMEOUT_SECONDS", "30"))
    eletrofrio_timeout_seconds: int = int(os.getenv("ELETROFRIO_TIMEOUT_SECONDS", "20"))
    eletrofrio_retry_attempts: int = int(os.getenv("ELETROFRIO_RETRY_ATTEMPTS", "1"))
    supabase_upsert_batch_size: int = int(os.getenv("SUPABASE_BATCH_SIZE", os.getenv("SUPABASE_UPSERT_BATCH_SIZE", "300")))
    whatsapp_service_url: str = os.getenv("WHATSAPP_SERVICE_URL", "http://127.0.0.1:8091").rstrip("/")
    ai_enrich_notifications: bool = _bool_env("AI_ENRICH_NOTIFICATIONS", False)
    ai_notification_max_per_run: int = int(os.getenv("AI_NOTIFICATION_MAX_PER_RUN", "3"))
    telemetry_fetch_mode: str = os.getenv("TELEMETRY_FETCH_MODE", "priority").strip().lower()
    telemetry_max_devices_per_run: int = int(os.getenv("TELEMETRY_MAX_DEVICES_PER_RUN", "80"))
    telemetry_request_timeout_seconds: int = int(os.getenv("TELEMETRY_REQUEST_TIMEOUT_SECONDS", "15"))
    telemetry_concurrency: int = int(os.getenv("TELEMETRY_CONCURRENCY", "8"))
    telemetry_cache_minutes: int = int(os.getenv("TELEMETRY_CACHE_MINUTES", "10"))
    overview_cache_seconds: int = int(os.getenv("OVERVIEW_CACHE_SECONDS", "30"))
    admin_cache_seconds: int = int(os.getenv("ADMIN_CACHE_SECONDS", "30"))

    @property
    def supabase_enabled(self) -> bool:
        return bool(self.supabase_url and self.supabase_service_role_key)

    @property
    def openai_enabled(self) -> bool:
        return bool(self.openai_api_key)


settings = Settings()
