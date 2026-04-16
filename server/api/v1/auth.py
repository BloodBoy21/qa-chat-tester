import os
from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel
from loguru import logger

from lib.auth import (
    create_access_token,
    create_reset_token,
    verify_reset_token,
    send_welcome_email,
    send_reset_email,
)
from db.repositories.user_repository import UserRepository

router = APIRouter(prefix="/auth", tags=["auth"])

MIN_PASSWORD_LEN = 8


# ── Schemas ───────────────────────────────────────────────────────────────────

class LoginRequest(BaseModel):
    email: str
    password: str


class ChangePasswordRequest(BaseModel):
    current_password: str
    new_password: str


class ForgotPasswordRequest(BaseModel):
    email: str


class ResetPasswordRequest(BaseModel):
    token: str
    new_password: str


# ── Helpers ───────────────────────────────────────────────────────────────────

def _token_response(user: dict) -> dict:
    token = create_access_token(user["user_id"], user["email"], user.get("name"))
    return {
        "access_token":        token,
        "token_type":          "bearer",
        "must_change_password": bool(user.get("must_change_password", False)),
        "user": {
            "user_id": user["user_id"],
            "email":   user["email"],
            "name":    user.get("name"),
        },
    }


def _validate_new_password(password: str) -> None:
    if len(password) < MIN_PASSWORD_LEN:
        raise HTTPException(
            status_code=400,
            detail=f"La contraseña debe tener al menos {MIN_PASSWORD_LEN} caracteres",
        )


# ── Endpoints ─────────────────────────────────────────────────────────────────

@router.post("/login")
async def login(body: LoginRequest):
    repo = UserRepository()
    user = repo.validate_login(body.email.strip().lower(), body.password)
    if not user:
        raise HTTPException(status_code=401, detail="Email o contraseña incorrectos")
    logger.info(f"[auth] login ok: {body.email}")
    return _token_response(user)


@router.post("/change-password")
async def change_password(body: ChangePasswordRequest, request: Request):
    """Authenticated endpoint — requires valid JWT."""
    me = request.state.user
    repo = UserRepository()

    user = repo.validate_login(me["email"], body.current_password)
    if not user:
        raise HTTPException(status_code=400, detail="Contraseña actual incorrecta")

    _validate_new_password(body.new_password)
    repo.change_password(user["user_id"], body.new_password)
    repo.clear_must_change_password(user["user_id"])

    # Fetch updated user and return fresh token
    updated = repo.get_by_id(user["user_id"])
    logger.info(f"[auth] password changed: {me['email']}")
    return _token_response(updated)


@router.post("/forgot-password")
async def forgot_password(body: ForgotPasswordRequest):
    """Always returns ok — prevents user enumeration."""
    repo = UserRepository()
    user = repo.get_by_email(body.email.strip().lower())
    if user:
        token = create_reset_token(user["user_id"], user["email"])
        app_url = os.getenv("APP_URL", "http://localhost:8765")
        reset_url = f"{app_url}?reset_token={token}"
        send_reset_email(user["email"], user.get("name", ""), reset_url)
        logger.info(f"[auth] reset email sent: {user['email']}")
    return {"ok": True, "message": "Si el email existe recibirás instrucciones en breve."}


@router.post("/reset-password")
async def reset_password(body: ResetPasswordRequest):
    payload = verify_reset_token(body.token)
    if not payload:
        raise HTTPException(status_code=400, detail="El enlace es inválido o ha expirado")

    _validate_new_password(body.new_password)

    repo = UserRepository()
    user = repo.get_by_id(int(payload["sub"]))
    if not user:
        raise HTTPException(status_code=400, detail="Usuario no encontrado")

    repo.change_password(user["user_id"], body.new_password)
    repo.clear_must_change_password(user["user_id"])
    logger.info(f"[auth] password reset: {user['email']}")
    return {"ok": True}


@router.get("/me")
async def me(request: Request):
    """Returns the authenticated user's profile."""
    u = request.state.user
    return {"user_id": u["sub"], "email": u["email"], "name": u.get("name")}
