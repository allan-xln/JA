from __future__ import annotations

import time
from typing import Any

import requests

from api.config import settings
from api.logger import logger


class EletrofrioApiError(RuntimeError):
    pass


class EletrofrioClient:
    def __init__(self) -> None:
        self.base_url = settings.eletrofrio_api_base_url
        self.timeout = settings.eletrofrio_timeout_seconds
        self.retry_attempts = max(1, settings.eletrofrio_retry_attempts)

    def _request_once(
        self,
        route: str,
        params: dict[str, Any] | None,
        payload: dict[str, Any] | None,
        method: str,
        timeout: int | None = None,
    ) -> requests.Response:
        query = {"route": route, **(params or {})}
        request_timeout = timeout or self.timeout
        if method == "POST":
            return requests.post(self.base_url, params=query, json=payload, timeout=request_timeout)
        return requests.get(self.base_url, params=query, timeout=request_timeout)

    def _request(
        self,
        route: str,
        params: dict[str, Any] | None = None,
        payload: dict[str, Any] | None = None,
        method: str = "GET",
        timeout: int | None = None,
    ) -> Any:
        method = method.upper()
        last_timeout: requests.Timeout | None = None

        for attempt in range(1, self.retry_attempts + 1):
            try:
                response = self._request_once(route, params, payload, method, timeout)
                break
            except requests.Timeout as exc:
                last_timeout = exc
                if attempt < self.retry_attempts:
                    logger.warning(
                        "Timeout consultando Eletrofrio route=%s tentativa=%s/%s; tentando novamente.",
                        route,
                        attempt,
                        self.retry_attempts,
                    )
                    time.sleep(min(2, attempt))
                    continue
                logger.error("Timeout consultando Eletrofrio route=%s params=%s", route, params)
                raise EletrofrioApiError(f"Timeout na API Eletrofrio: {route}") from last_timeout
            except requests.RequestException as exc:
                logger.error("Falha de rede consultando Eletrofrio route=%s: %s", route, exc)
                raise EletrofrioApiError(str(exc)) from exc
        else:
            raise EletrofrioApiError(f"Timeout na API Eletrofrio: {route}")

        if response.status_code >= 400:
            logger.error("Eletrofrio retornou HTTP %s em route=%s: %s", response.status_code, route, response.text[:800])
            raise EletrofrioApiError(f"Eletrofrio HTTP {response.status_code}: {response.text[:300]}")

        try:
            return response.json()
        except ValueError as exc:
            logger.error("Eletrofrio respondeu corpo não JSON em route=%s: %s", route, response.text[:800])
            raise EletrofrioApiError("Resposta não JSON da API Eletrofrio") from exc

    def _get_or_post(
        self,
        route: str,
        params: dict[str, Any] | None = None,
        payload: dict[str, Any] | None = None,
        timeout: int | None = None,
    ) -> Any:
        try:
            return self._request(route, params=params, payload=payload, method="GET", timeout=timeout)
        except EletrofrioApiError as first_error:
            if "Timeout na API Eletrofrio" in str(first_error):
                raise
            logger.warning("GET falhou para route=%s; tentando POST. Erro: %s", route, first_error)
            return self._request(route, params=params, payload=payload, method="POST", timeout=timeout)

    def fetch_alarms(self) -> Any:
        return self._get_or_post("alarmes")

    def fetch_units(self) -> Any:
        return self._get_or_post("unidades")

    def fetch_telemetry(self, dispositivo_id: int | str, timeout: int | None = None) -> Any:
        return self._get_or_post("telemetria", params={"dispositivoId": dispositivo_id}, timeout=timeout)

    def open_ticket(self, payload: dict[str, Any]) -> Any:
        return self._request("abrir-chamado", payload=payload, method="POST")


eletrofrio_client = EletrofrioClient()
