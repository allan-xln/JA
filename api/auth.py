from __future__ import annotations

import base64
import hashlib
import hmac
import json
import os
import secrets
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer

from api.config import ROOT_DIR
from api.database import SupabaseError, supabase
from api.logger import logger


AUTH_SCHEMA_MESSAGE = (
    "Schema multi-cliente ainda não aplicado. Execute sql/005_multi_tenant_auth.sql "
    "no Supabase e rode python -m api.scripts.seed_tenants."
)
DATA_DIR = Path(os.getenv("ELETROFRIO_DATA_DIR", str(ROOT_DIR / "data")))
DEMO_USERS_FILE = DATA_DIR / "demo_users_generated.json"
SESSION_TTL_HOURS = int(os.getenv("ELETROFRIO_SESSION_TTL_HOURS", "12"))
PASSWORD_ITERATIONS = 180_000

security = HTTPBearer(auto_error=False)
_memory_sessions: dict[str, dict[str, Any]] = {}


@dataclass(frozen=True)
class TenantScope:
    role: str = "admin"
    customer_id: str | None = None
    customer_name: str | None = None
    allowed_loja_ids: set[int] = field(default_factory=set)
    allowed_dispositivo_ids: set[int] = field(default_factory=set)

    @property
    def is_admin(self) -> bool:
        return self.role == "admin"

    @property
    def label(self) -> str:
        return "Visão administrativa" if self.is_admin else "Ambiente do cliente"


@dataclass(frozen=True)
class AuthUser:
    id: str
    username: str
    role: str
    customer_id: str | None = None
    customer_name: str | None = None
    scope: TenantScope = field(default_factory=TenantScope)

    def public_dict(self) -> dict[str, Any]:
        return {
            "username": self.username,
            "role": self.role,
            "customer_id": self.customer_id,
            "customer_name": self.customer_name,
            "scope_label": self.scope.label,
            "allowed_loja_ids": sorted(self.scope.allowed_loja_ids) if not self.scope.is_admin else [],
            "allowed_dispositivo_ids": sorted(self.scope.allowed_dispositivo_ids) if not self.scope.is_admin else [],
        }


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


def utc_now_iso() -> str:
    return utc_now().isoformat()


def parse_datetime(value: Any) -> datetime | None:
    if not value:
        return None
    try:
        parsed = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
        if parsed.tzinfo is None:
            parsed = parsed.replace(tzinfo=timezone.utc)
        return parsed.astimezone(timezone.utc)
    except ValueError:
        return None


def hash_password(password: str, salt: str | None = None) -> str:
    raw_salt = base64.urlsafe_b64decode(salt.encode("utf-8")) if salt else secrets.token_bytes(16)
    digest = hashlib.pbkdf2_hmac("sha256", password.encode("utf-8"), raw_salt, PASSWORD_ITERATIONS)
    encoded_salt = base64.urlsafe_b64encode(raw_salt).decode("utf-8")
    encoded_hash = base64.urlsafe_b64encode(digest).decode("utf-8")
    return f"pbkdf2_sha256${PASSWORD_ITERATIONS}${encoded_salt}${encoded_hash}"


def verify_password(password: str, password_hash: str) -> bool:
    try:
        algorithm, iterations, salt, expected = password_hash.split("$", 3)
        if algorithm != "pbkdf2_sha256":
            return False
        raw_salt = base64.urlsafe_b64decode(salt.encode("utf-8"))
        digest = hashlib.pbkdf2_hmac("sha256", password.encode("utf-8"), raw_salt, int(iterations))
        actual = base64.urlsafe_b64encode(digest).decode("utf-8")
        return hmac.compare_digest(actual, expected)
    except Exception:
        return False


def hash_token(token: str) -> str:
    return hashlib.sha256(token.encode("utf-8")).hexdigest()


def _schema_missing(exc: Exception) -> bool:
    text = str(exc).lower()
    return (
        "eletrofrio_users" in text
        or "eletrofrio_customers" in text
        or "eletrofrio_sessions" in text
        or "eletrofrio_customer_units" in text
        or "eletrofrio_customer_devices" in text
        or "pgrst205" in text
        or "schema cache" in text
    )


def _load_demo_store() -> dict[str, Any]:
    if not DEMO_USERS_FILE.exists():
        return {"users": [], "customers": [], "customer_units": [], "customer_devices": []}
    try:
        return json.loads(DEMO_USERS_FILE.read_text(encoding="utf-8"))
    except Exception as exc:
        logger.warning("Falha ao carregar usuarios demo multi-cliente: %s", exc)
        return {"users": [], "customers": [], "customer_units": [], "customer_devices": []}


def _demo_user(username: str) -> dict[str, Any] | None:
    store = _load_demo_store()
    for user in store.get("users", []):
        if user.get("username") == username and user.get("is_active", True):
            return user
    return None


def _demo_user_by_id(user_id: str | None, store: dict[str, Any] | None = None) -> dict[str, Any] | None:
    if not user_id:
        return None
    store = store or _load_demo_store()
    for user in store.get("users", []):
        if str(user.get("id")) == str(user_id) and user.get("is_active", True):
            return user
    return None


def _customer_name(customer_id: str | None, store: dict[str, Any] | None = None) -> str | None:
    if not customer_id:
        return None
    store = store or _load_demo_store()
    for customer in store.get("customers", []):
        if str(customer.get("id")) == str(customer_id):
            return customer.get("name")
    try:
        rows = supabase.select("eletrofrio_customers", {"select": "name", "id": f"eq.{customer_id}", "limit": 1})
        return rows[0].get("name") if rows else None
    except Exception:
        return None


def scope_for_user(user: dict[str, Any], store: dict[str, Any] | None = None) -> TenantScope:
    role = str(user.get("role") or "client")
    customer_id = user.get("customer_id")
    customer_name = user.get("customer_name") or _customer_name(customer_id, store)
    if role == "admin":
        return TenantScope(role="admin", customer_id=None, customer_name=None)

    allowed_loja_ids: set[int] = set()
    allowed_dispositivo_ids: set[int] = set()
    try:
        unit_rows = supabase.select(
            "eletrofrio_customer_units",
            {"select": "loja_id", "customer_id": f"eq.{customer_id}", "limit": 5000},
        )
        device_rows = supabase.select(
            "eletrofrio_customer_devices",
            {"select": "dispositivo_id", "customer_id": f"eq.{customer_id}", "limit": 5000},
        )
    except Exception as exc:
        if not _schema_missing(exc):
            logger.warning("Falha ao carregar escopo do cliente no Supabase: %s", exc)
        store = store or _load_demo_store()
        unit_rows = [row for row in store.get("customer_units", []) if str(row.get("customer_id")) == str(customer_id)]
        device_rows = [row for row in store.get("customer_devices", []) if str(row.get("customer_id")) == str(customer_id)]

    for row in unit_rows:
        try:
            allowed_loja_ids.add(int(row["loja_id"]))
        except (KeyError, TypeError, ValueError):
            continue
    for row in device_rows:
        try:
            allowed_dispositivo_ids.add(int(row["dispositivo_id"]))
        except (KeyError, TypeError, ValueError):
            continue

    return TenantScope(
        role="client",
        customer_id=str(customer_id) if customer_id else None,
        customer_name=customer_name,
        allowed_loja_ids=allowed_loja_ids,
        allowed_dispositivo_ids=allowed_dispositivo_ids,
    )


def authenticate_user(username: str, password: str) -> AuthUser | None:
    username = username.strip().casefold()
    user: dict[str, Any] | None = None
    store: dict[str, Any] | None = None
    try:
        rows = supabase.select("eletrofrio_users", {"select": "*", "username": f"eq.{username}", "limit": 1})
        user = rows[0] if rows else None
    except SupabaseError as exc:
        if not _schema_missing(exc):
            logger.warning("Falha ao autenticar usuario no Supabase: %s", exc)
        store = _load_demo_store()
        user = _demo_user(username)
    if user is None:
        store = _load_demo_store()
        user = _demo_user(username)

    if not user or not user.get("is_active", True):
        return None
    if not verify_password(password, str(user.get("password_hash") or "")):
        return None

    scope = scope_for_user(user, store)
    return AuthUser(
        id=str(user.get("id") or username),
        username=str(user.get("username") or username),
        role=str(user.get("role") or "client"),
        customer_id=scope.customer_id,
        customer_name=scope.customer_name,
        scope=scope,
    )


def create_session(user: AuthUser) -> str:
    token = secrets.token_urlsafe(32)
    token_hash = hash_token(token)
    expires_at = utc_now() + timedelta(hours=SESSION_TTL_HOURS)
    payload = {
        "token_hash": token_hash,
        "user_id": user.id,
        "expires_at": expires_at.isoformat(),
        "created_at": utc_now_iso(),
    }
    try:
        supabase.insert("eletrofrio_sessions", payload)
    except SupabaseError as exc:
        if not _schema_missing(exc):
            logger.warning("Falha ao persistir sessao no Supabase; usando sessao local: %s", exc)
        _memory_sessions[token_hash] = {**payload, "user": user.public_dict(), "id": user.id}
    return token


def _user_from_session_hash(token_hash: str) -> AuthUser | None:
    session = None
    store = None
    try:
        rows = supabase.select("eletrofrio_sessions", {"select": "*", "token_hash": f"eq.{token_hash}", "limit": 1})
        session = rows[0] if rows else None
    except SupabaseError as exc:
        if not _schema_missing(exc):
            logger.warning("Falha ao carregar sessao no Supabase: %s", exc)
    if not session:
        session = _memory_sessions.get(token_hash)
        if session:
            store = _load_demo_store()

    if not session:
        return None
    expires_at = parse_datetime(session.get("expires_at"))
    if not expires_at or expires_at <= utc_now():
        _memory_sessions.pop(token_hash, None)
        return None

    if session.get("user"):
        public_user = session["user"]
        user_row = {
            "id": session.get("id") or public_user.get("username"),
            "username": public_user.get("username"),
            "role": public_user.get("role"),
            "customer_id": public_user.get("customer_id"),
            "customer_name": public_user.get("customer_name"),
        }
    else:
        try:
            rows = supabase.select("eletrofrio_users", {"select": "*", "id": f"eq.{session.get('user_id')}", "limit": 1})
            user_row = rows[0] if rows else None
        except SupabaseError as exc:
            if not _schema_missing(exc):
                logger.warning("Falha ao carregar usuario da sessao: %s", exc)
            user_row = None
        if not user_row:
            store = store or _load_demo_store()
            user_row = _demo_user_by_id(str(session.get("user_id") or ""), store)
    if not user_row:
        return None

    scope = scope_for_user(user_row, store)
    return AuthUser(
        id=str(user_row.get("id") or user_row.get("username")),
        username=str(user_row.get("username")),
        role=str(user_row.get("role") or "client"),
        customer_id=scope.customer_id,
        customer_name=scope.customer_name,
        scope=scope,
    )


def current_user(credentials: HTTPAuthorizationCredentials | None = Depends(security)) -> AuthUser:
    if credentials is None or credentials.scheme.casefold() != "bearer":
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Login necessário.")
    user = _user_from_session_hash(hash_token(credentials.credentials))
    if not user:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Sessão expirada. Faça login novamente.")
    return user


def optional_user(credentials: HTTPAuthorizationCredentials | None = Depends(security)) -> AuthUser | None:
    if credentials is None:
        return None
    return current_user(credentials)


def require_admin(user: AuthUser = Depends(current_user)) -> AuthUser:
    if user.role != "admin":
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Acesso restrito ao administrador.")
    return user


def logout_token(token: str) -> None:
    token_hash = hash_token(token)
    _memory_sessions.pop(token_hash, None)
    try:
        supabase.delete("eletrofrio_sessions", {"token_hash": token_hash})
    except Exception:
        pass
