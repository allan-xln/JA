from __future__ import annotations

from fastapi import APIRouter, Depends
from fastapi.security import HTTPAuthorizationCredentials
from pydantic import BaseModel

from api.auth import authenticate_user, create_session, current_user, logout_token, security
from fastapi import HTTPException


router = APIRouter(prefix="/api/auth", tags=["auth"])


class LoginPayload(BaseModel):
    username: str
    password: str


@router.post("/login")
def login(payload: LoginPayload):
    user = authenticate_user(payload.username, payload.password)
    if not user:
        raise HTTPException(status_code=401, detail="Usuário ou senha inválidos.")
    token = create_session(user)
    return {"token": token, "user": user.public_dict()}


@router.get("/me")
def me(user=Depends(current_user)):
    return {"user": user.public_dict()}


@router.post("/logout")
def logout(credentials: HTTPAuthorizationCredentials | None = Depends(security)):
    if credentials:
        logout_token(credentials.credentials)
    return {"ok": True}
