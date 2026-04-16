"""
Authentication utilities: JWT creation/verification + SendGrid email sending.
"""
import os
import secrets
import string
from datetime import datetime, timedelta, timezone
from typing import Optional

import jwt
from loguru import logger

# ── Secrets ───────────────────────────────────────────────────────────────────

JWT_SECRET    = os.getenv("JWT_SECRET",   "CHANGE_ME_JWT_SECRET_IN_PRODUCTION")
RESET_SECRET  = os.getenv("RESET_SECRET", "CHANGE_ME_RESET_SECRET_IN_PRODUCTION")
JWT_ALGORITHM = "HS256"
JWT_EXPIRE_HOURS = int(os.getenv("JWT_EXPIRE_HOURS", 24))

# ── Token creation ────────────────────────────────────────────────────────────

def create_access_token(user_id: int, email: str, name: str = None) -> str:
    payload = {
        "sub":   str(user_id),
        "email": email,
        "name":  name or "",
        "type":  "access",
        "iat":   datetime.now(timezone.utc),
        "exp":   datetime.now(timezone.utc) + timedelta(hours=JWT_EXPIRE_HOURS),
    }
    return jwt.encode(payload, JWT_SECRET, algorithm=JWT_ALGORITHM)


def verify_access_token(token: str) -> Optional[dict]:
    try:
        payload = jwt.decode(token, JWT_SECRET, algorithms=[JWT_ALGORITHM])
        if payload.get("type") != "access":
            return None
        return payload
    except jwt.ExpiredSignatureError:
        return None
    except jwt.InvalidTokenError:
        return None


def create_reset_token(user_id: int, email: str) -> str:
    payload = {
        "sub":   str(user_id),
        "email": email,
        "type":  "reset",
        "iat":   datetime.now(timezone.utc),
        "exp":   datetime.now(timezone.utc) + timedelta(hours=1),
    }
    return jwt.encode(payload, RESET_SECRET, algorithm=JWT_ALGORITHM)


def verify_reset_token(token: str) -> Optional[dict]:
    try:
        payload = jwt.decode(token, RESET_SECRET, algorithms=[JWT_ALGORITHM])
        if payload.get("type") != "reset":
            return None
        return payload
    except jwt.ExpiredSignatureError:
        return None
    except jwt.InvalidTokenError:
        return None


# ── Password utilities ────────────────────────────────────────────────────────

def generate_temp_password(length: int = 12) -> str:
    """Generate a cryptographically secure temporary password."""
    alphabet = string.ascii_letters + string.digits + "!@#$%&"
    while True:
        pwd = "".join(secrets.choice(alphabet) for _ in range(length))
        # Ensure at least one of each required type
        if (any(c.islower() for c in pwd) and
                any(c.isupper() for c in pwd) and
                any(c.isdigit() for c in pwd)):
            return pwd


# ── Email via SendGrid ────────────────────────────────────────────────────────

SENDGRID_API_KEY = os.getenv("SENDGRID_API_KEY")
SENDER_EMAIL     = os.getenv("SENDER_EMAIL", "it@nerds.ai")
SENDER_NAME      = os.getenv("SENDER_NAME",  "QA Chat Tester")
APP_URL          = os.getenv("APP_URL", "http://localhost:8765")


def _send(to_email: str, subject: str, html: str) -> bool:
    if not SENDGRID_API_KEY:
        logger.warning("SENDGRID_API_KEY not set — email not sent.")
        return False
    try:
        import sendgrid as sg_module
        from sendgrid.helpers.mail import Mail, Email, To, Content

        sg = sg_module.SendGridAPIClient(api_key=SENDGRID_API_KEY)
        message = Mail(
            from_email=Email(SENDER_EMAIL, SENDER_NAME),
            to_emails=To(to_email),
            subject=subject,
            html_content=Content("text/html", html),
        )
        response = sg.send(message)
        ok = response.status_code in (200, 202)
        if ok:
            logger.info(f"[email] Sent '{subject}' to {to_email}")
        else:
            logger.error(f"[email] SendGrid status {response.status_code}")
        return ok
    except Exception as e:
        logger.error(f"[email] SendGrid error: {e}")
        return False


def send_welcome_email(email: str, name: str, temp_password: str) -> bool:
    html = f"""
    <!DOCTYPE html>
    <html lang="es">
    <body style="font-family:'Segoe UI',sans-serif;background:#f4f4f5;padding:32px;color:#111">
      <div style="max-width:500px;margin:0 auto;background:#fff;border-radius:12px;padding:32px;box-shadow:0 2px 8px rgba(0,0,0,.08)">
        <h2 style="color:#6c63ff;margin-top:0">Bienvenido a QA Chat Tester</h2>
        <p>Hola <b>{name}</b>,</p>
        <p>Tu cuenta ha sido creada. Usa las siguientes credenciales para ingresar:</p>
        <table style="width:100%;border-collapse:collapse;margin:16px 0">
          <tr>
            <td style="padding:8px 12px;background:#f4f4f5;border-radius:6px 0 0 6px;color:#555;width:40%"><b>Email</b></td>
            <td style="padding:8px 12px;background:#f4f4f5;border-radius:0 6px 6px 0;font-family:monospace">{email}</td>
          </tr>
          <tr><td colspan="2" style="height:6px"></td></tr>
          <tr>
            <td style="padding:8px 12px;background:#f4f4f5;border-radius:6px 0 0 6px;color:#555;width:40%"><b>Contraseña temporal</b></td>
            <td style="padding:8px 12px;background:#f4f4f5;border-radius:0 6px 6px 0;font-family:monospace;letter-spacing:2px">{temp_password}</td>
          </tr>
        </table>
        <p style="color:#e85d04;font-size:13px">⚠ Deberás cambiar tu contraseña al iniciar sesión por primera vez.</p>
        <a href="{APP_URL}" style="display:inline-block;padding:11px 24px;background:#6c63ff;color:#fff;border-radius:8px;text-decoration:none;font-weight:600;margin-top:8px">
          Ingresar al dashboard →
        </a>
        <hr style="border:none;border-top:1px solid #eee;margin:28px 0 16px">
        <p style="font-size:12px;color:#999">Si no esperabas este email, ignóralo.</p>
      </div>
    </body>
    </html>
    """
    return _send(email, "Bienvenido a QA Chat Tester — credenciales de acceso", html)


def send_reset_email(email: str, name: str, reset_url: str) -> bool:
    html = f"""
    <!DOCTYPE html>
    <html lang="es">
    <body style="font-family:'Segoe UI',sans-serif;background:#f4f4f5;padding:32px;color:#111">
      <div style="max-width:500px;margin:0 auto;background:#fff;border-radius:12px;padding:32px;box-shadow:0 2px 8px rgba(0,0,0,.08)">
        <h2 style="color:#6c63ff;margin-top:0">Restablecer contraseña</h2>
        <p>Hola <b>{name}</b>,</p>
        <p>Recibimos una solicitud para restablecer tu contraseña. El enlace expira en <b>1 hora</b>.</p>
        <a href="{reset_url}" style="display:inline-block;padding:11px 24px;background:#6c63ff;color:#fff;border-radius:8px;text-decoration:none;font-weight:600;margin:16px 0">
          Restablecer contraseña →
        </a>
        <p style="font-size:13px;color:#555">O copia este enlace en tu navegador:</p>
        <p style="font-size:12px;font-family:monospace;word-break:break-all;background:#f4f4f5;padding:10px;border-radius:6px">{reset_url}</p>
        <hr style="border:none;border-top:1px solid #eee;margin:24px 0 16px">
        <p style="font-size:12px;color:#999">Si no solicitaste esto, ignora este email. Tu contraseña no cambiará.</p>
      </div>
    </body>
    </html>
    """
    return _send(email, "QA Chat Tester — restablece tu contraseña", html)
