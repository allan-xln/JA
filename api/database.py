from __future__ import annotations

import time
from typing import Any

import requests

from api.config import settings
from api.logger import logger


class SupabaseError(RuntimeError):
    pass


TEMPORARY_SUPABASE_MESSAGE = (
    "Banco operacional temporariamente indisponível. O Supabase retornou instabilidade "
    "ao consultar o schema; tente atualizar em instantes."
)


def is_temporary_supabase_error(exc: Exception) -> bool:
    text = str(exc).lower()
    return (
        "supabase 502" in text
        or "supabase 503" in text
        or "supabase 504" in text
        or "pgrst002" in text
        or "schema cache" in text
        or "could not query the database" in text
        or "read timed out" in text
        or "timed out" in text
        or "timeout" in text
    )


def _is_temporary_response(status_code: int, body: str) -> bool:
    text = body.lower()
    return (
        status_code in {502, 503, 504}
        or "pgrst002" in text
        or "schema cache" in text
        or "could not query the database" in text
    )


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
        self._unavailable_until = 0.0
        self._unavailable_error = ""

    def enabled(self) -> bool:
        return settings.supabase_enabled

    def _request(self, method: str, table: str, **kwargs: Any) -> Any:
        if not self.enabled():
            raise SupabaseError("Supabase não configurado. Preencha SUPABASE_URL e SUPABASE_SERVICE_ROLE_KEY.")
        if time.monotonic() < self._unavailable_until:
            raise SupabaseError(
                self._unavailable_error or f"{TEMPORARY_SUPABASE_MESSAGE} (PGRST002: schema cache indisponível)"
            )

        url = f"{self.base_url}/{table}"
        headers = {**self.headers, **kwargs.pop("headers", {})}
        response: requests.Response | None = None
        timeout_seconds = kwargs.pop("timeout", settings.http_timeout_seconds)
        max_attempts = int(kwargs.pop("attempts", 2))
        for attempt in range(max_attempts):
            try:
                response = requests.request(
                    method,
                    url,
                    headers=headers,
                    timeout=timeout_seconds,
                    **kwargs,
                )
            except requests.RequestException as exc:
                if attempt < max_attempts - 1:
                    logger.warning(
                        "Falha temporária no Supabase %s %s; tentando novamente (%s/%s): %s",
                        method,
                        table,
                        attempt + 1,
                        max_attempts,
                        exc,
                    )
                    time.sleep(0.4 * (attempt + 1))
                    continue
                logger.error("Falha de rede no Supabase %s %s: %s", method, table, exc)
                raise SupabaseError(str(exc)) from exc

            if response.status_code < 400:
                self._unavailable_until = 0.0
                self._unavailable_error = ""
                break

            body = response.text[:800]
            if _is_temporary_response(response.status_code, body) and attempt < max_attempts - 1:
                logger.warning(
                    "Supabase temporariamente indisponível em %s (%s); tentando novamente (%s/%s): %s",
                    table,
                    response.status_code,
                    attempt + 1,
                    max_attempts,
                    response.text[:300],
                )
                time.sleep(0.6 * (attempt + 1))
                continue
            break

        if response is None:
            raise SupabaseError(TEMPORARY_SUPABASE_MESSAGE)

        if response.status_code >= 400:
            body = response.text[:800]
            compact_body = response.text[:300]
            if _is_temporary_response(response.status_code, body):
                self._unavailable_until = time.monotonic() + 12
                self._unavailable_error = f"{TEMPORARY_SUPABASE_MESSAGE} (PGRST002: schema cache indisponível)"
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

    def select(
        self,
        table: str,
        params: dict[str, Any] | None = None,
        timeout: int | float | None = None,
        attempts: int | None = None,
    ) -> list[dict[str, Any]]:
        request_kwargs: dict[str, Any] = {"params": params or {}}
        if timeout is not None:
            request_kwargs["timeout"] = timeout
        if attempts is not None:
            request_kwargs["attempts"] = attempts
        result = self._request("GET", table, **request_kwargs)
        return result if isinstance(result, list) else []

    def insert(
        self,
        table: str,
        rows: list[dict[str, Any]] | dict[str, Any],
        timeout: int | float | None = None,
        attempts: int | None = None,
    ) -> list[dict[str, Any]]:
        payload = rows if isinstance(rows, list) else [rows]
        if not payload:
            return []
        request_kwargs: dict[str, Any] = {"json": payload}
        if timeout is not None:
            request_kwargs["timeout"] = timeout
        if attempts is not None:
            request_kwargs["attempts"] = attempts
        result = self._request("POST", table, **request_kwargs)
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

    def rpc(self, function_name: str, params: dict[str, Any] | None = None) -> Any:
        return self._request("POST", f"rpc/{function_name}", json=params or {})


supabase = SupabaseClient()
