#!/usr/bin/env python3
"""
QA Chat Tester — Admin CLI

Manage users (create, list, deactivate, reset password).
All operations run against the configured SQL database.

Usage:
    uv run python cli/admin.py create-user  --email=... [--name=...]
    uv run python cli/admin.py list-users
    uv run python cli/admin.py deactivate-user --email=...
    uv run python cli/admin.py reset-password --email=...

Environment (.env is loaded automatically):
    DATABASE_URL        — MySQL or SQLite connection string
    SENDGRID_API_KEY    — Required to send email; if missing, prints credentials to stdout
    SENDER_EMAIL        — From address (default: it@nerds.ai)
    APP_URL             — Dashboard URL included in emails (default: http://localhost:8765)
    PASSWORD_SALT       — Salt for SHA-256 hashing (must match the API)
"""
import sys
from pathlib import Path

# Allow running from any directory
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from dotenv import load_dotenv
load_dotenv()

import argparse

from lib.sql_db import init_db
from lib.auth import generate_temp_password, send_welcome_email
from db.repositories.user_repository import UserRepository


# ── Helpers ───────────────────────────────────────────────────────────────────

def _repo() -> UserRepository:
    init_db()
    return UserRepository()


def _ok(msg: str):   print(f"  ✓  {msg}")
def _warn(msg: str): print(f"  ⚠  {msg}")
def _err(msg: str):  print(f"  ✗  {msg}"); sys.exit(1)


# ── Commands ──────────────────────────────────────────────────────────────────

def cmd_create_user(args: argparse.Namespace):
    email = args.email.strip().lower()
    name  = (args.name or email.split("@")[0]).strip()

    repo = _repo()
    if repo.get_by_email(email):
        _err(f"Ya existe un usuario con email '{email}'.")

    temp_password = generate_temp_password()
    user_id = repo.create(email=email, password=temp_password, name=name)

    sent = send_welcome_email(email, name, temp_password)

    print()
    _ok(f"Usuario creado — id={user_id}  email={email}  name={name}")
    if sent:
        _ok(f"Email de bienvenida enviado a {email}")
    else:
        _warn("Email no enviado (revisa SENDGRID_API_KEY).")
        print(f"\n  {'Email':<22}: {email}")
        print(f"  {'Contraseña temporal':<22}: {temp_password}")
    print(f"\n  El usuario deberá cambiar su contraseña en el primer login.\n")


def cmd_list_users(_args: argparse.Namespace):
    users = _repo().get_all()
    if not users:
        print("  Sin usuarios registrados.")
        return

    header = f"{'ID':<6} {'Email':<36} {'Nombre':<24} {'Activo':<8} {'Cambiar pwd'}"
    print()
    print("  " + header)
    print("  " + "─" * len(header))
    for u in users:
        print(
            f"  {u['user_id']:<6} "
            f"{u['email']:<36} "
            f"{(u.get('name') or ''):<24} "
            f"{'Sí' if u['is_active'] else 'No':<8} "
            f"{'Sí' if u.get('must_change_password') else 'No'}"
        )
    print()


def cmd_deactivate(args: argparse.Namespace):
    email = args.email.strip().lower()
    repo  = _repo()
    user  = repo.get_by_email(email)
    if not user:
        _err(f"No existe usuario activo con email '{email}'.")

    confirm = input(f"  ¿Desactivar '{email}'? [s/N]: ").strip().lower()
    if confirm != "s":
        print("  Operación cancelada.")
        return

    repo.deactivate(user["user_id"])
    _ok(f"Usuario '{email}' desactivado.")
    print()


def cmd_reset_password(args: argparse.Namespace):
    email = args.email.strip().lower()
    repo  = _repo()
    user  = repo.get_by_email(email)
    if not user:
        _err(f"No existe usuario activo con email '{email}'.")

    temp_password = generate_temp_password()
    repo.change_password(user["user_id"], temp_password)
    repo.set_must_change_password(user["user_id"])

    name = user.get("name", email.split("@")[0])
    sent = send_welcome_email(email, name, temp_password)

    print()
    _ok(f"Contraseña restablecida para {email}")
    if sent:
        _ok(f"Nueva contraseña temporal enviada por email.")
    else:
        _warn("Email no enviado (revisa SENDGRID_API_KEY).")
        print(f"\n  {'Email':<22}: {email}")
        print(f"  {'Nueva contraseña':<22}: {temp_password}")
    print()


# ── CLI parser ────────────────────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser(
        prog="cli/admin.py",
        description="QA Chat Tester — administración de usuarios",
    )
    sub = parser.add_subparsers(dest="command", required=True)

    # create-user
    p_create = sub.add_parser("create-user", help="Crear un nuevo usuario admin")
    p_create.add_argument("--email", required=True, help="Email del usuario")
    p_create.add_argument("--name",  default=None,  help="Nombre (opcional)")
    p_create.set_defaults(func=cmd_create_user)

    # list-users
    p_list = sub.add_parser("list-users", help="Listar todos los usuarios")
    p_list.set_defaults(func=cmd_list_users)

    # deactivate-user
    p_deact = sub.add_parser("deactivate-user", help="Desactivar un usuario")
    p_deact.add_argument("--email", required=True)
    p_deact.set_defaults(func=cmd_deactivate)

    # reset-password
    p_reset = sub.add_parser("reset-password", help="Generar nueva contraseña temporal y enviarla por email")
    p_reset.add_argument("--email", required=True)
    p_reset.set_defaults(func=cmd_reset_password)

    args = parser.parse_args()
    args.func(args)


if __name__ == "__main__":
    main()
