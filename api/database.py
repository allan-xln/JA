from __future__ import annotations

from typing import Any

import requests

from api.config import settings
from api.logger import logger


class SupabaseError(RuntimeError):
    pass


class SupabaseClient:
    def __init__(self) -> None:
        self.base_url = f"{settings.supabase_url}/rest/v1" if settings.supabase_url else ""
        self.headers = {
            "apikey": settings.supabase_service_role_key,
            "Authorization": f"Bearer {settings.supabase_service_role_key}",
            "Content-Type": "application/json",
            "Prefer": "return=representation",
        }
        self._logged_schema_errors: set[str] = set()

    def enabled(self) -> bool:
        return settings.supabase_enabled

    def _request(self, method: str, table: str, **kwargs: Any) -> Any:
        if not self.enabled():
            raise SupabaseError("Supabase não configurado. Preencha SUPABASE_URL e SUPABASE_SERVICE_ROLE_KEY.")

        url = f"{self.base_url}/{table}"
        try:
            response = requests.request(
                method,
                url,
                headers={**self.headers, **kwargs.pop("headers", {})},
                timeout=settings.http_timeout_seconds,
                **kwargs,
            )
        except requests.RequestException as exc:
            logger.error("Falha de rede no Supabase %s %s: %s", method, table, exc)
            raise SupabaseError(str(exc)) from exc

        if response.status_code >= 400:
            body = response.text[:800]
            compact_body = response.text[:300]
            schema_cache_error = "schema cache" in body.lower() or "PGRST205" in body
            if schema_cache_error:
                log_key = f"{response.status_code}:{table}:{compact_body}"
                if log_key not in self._logged_schema_errors:
                    logger.warning(
                        "Supabase schema pendente em %s (%s). Aplique as migrations SQL: %s",
                        table,
                        response.status_code,
                        compact_body,
                    )
                    self._logged_schema_errors.add(log_key)
            else:
                logger.error("Supabase retornou erro %s em %s: %s", response.status_code, table, body)
            raise SupabaseError(f"Supabase {response.status_code}: {compact_body}")

        if not response.text:
            return None
        return response.json()

    def select(self, table: str, params: dict[str, Any] | None = None) -> list[dict[str, Any]]:
        result = self._request("GET", table, params=params or {})
        return result if isinstance(result, list) else []

    def insert(self, table: str, rows: list[dict[str, Any]] | dict[str, Any]) -> list[dict[str, Any]]:
        payload = rows if isinstance(rows, list) else [rows]
        if not payload:
            return []
        result = self._request("POST", table, json=payload)
        return result if isinstance(result, list) else []

    def upsert(
        self,
        table: str,
        rows: list[dict[str, Any]] | dict[str, Any],
        on_conflict: str,
        return_representation: bool = True,
    ) -> list[dict[str, Any]]:
        payload = rows if isinstance(rows, list) else [rows]
        if not payload:
            return []
        return_mode = "return=representation" if return_representation else "return=minimal"
        headers = {"Prefer": f"resolution=merge-duplicates,{return_mode}"}
        result = self._request(
            "POST",
            table,
            params={"on_conflict": on_conflict},
            headers=headers,
            json=payload,
        )
        return result if isinstance(result, list) else []

    def patch(self, table: str, filters: dict[str, Any], data: dict[str, Any]) -> list[dict[str, Any]]:
        params = {key: f"eq.{value}" for key, value in filters.items()}
        result = self._request("PATCH", table, params=params, json=data)
        return result if isinstance(result, list) else []

    def delete(self, table: str, filters: dict[str, Any]) -> list[dict[str, Any]]:
        params = {key: f"eq.{value}" for key, value in filters.items()}
        result = self._request("DELETE", table, params=params)
        return result if isinstance(result, list) else []


supabase = SupabaseClient()
