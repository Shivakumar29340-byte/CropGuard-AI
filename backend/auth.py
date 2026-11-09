
"""Registration, login, logout and password reset."""

import hashlib
import logging
import os
import re
import secrets
import smtplib

from datetime import datetime, timedelta, timezone
from email.message import EmailMessage
from functools import wraps
from urllib.parse import urlencode, urlsplit, urlunsplit, parse_qsl

from flask import Blueprint, current_app, g, jsonify, request
from werkzeug.security import check_password_hash, generate_password_hash

from database import get_db


auth_bp = Blueprint("auth", __name__, url_prefix="/api/auth")

EMAIL_RE = re.compile(
    r"^[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}$"
)

FMT = "%Y-%m-%d %H:%M:%S"
RESET_TOKEN_MINUTES = 30


def utcnow():
    """Current UTC time, compatible with SQLite datetime('now')."""
    return datetime.now(timezone.utc).replace(tzinfo=None)


class ApiError(Exception):
    def __init__(self, message, status=400, field=None):
        super().__init__(message)
        self.message = message
        self.status = status
        self.field = field


def get_json():
    data = request.get_json(silent=True)

    if not isinstance(data, dict):
        raise ApiError("Request body must be a JSON object.")

    return data


def clean_name(value):
    name = " ".join(str(value or "").split())

    if not 2 <= len(name) <= 80:
        raise ApiError(
            "Name must be 2 to 80 characters.",
            field="name"
        )

    return name


def clean_email(value):
    email = str(value or "").strip().lower()

    if len(email) > 254 or not EMAIL_RE.match(email):
        raise ApiError(
            "Enter a valid email address.",
            field="email"
        )

    return email


def check_password_rules(password):
    if not isinstance(password, str) or not 8 <= len(password) <= 128:
        raise ApiError(
            "Password must be 8 to 128 characters.",
            field="password"
        )

    if not (
        re.search(r"[A-Za-z]", password)
        and re.search(r"\d", password)
    ):
        raise ApiError(
            "Password must contain at least one letter and one number.",
            field="password"
        )


def hash_token(token):
    return hashlib.sha256(token.encode("utf-8")).hexdigest()


def user_dict(row):
    return {
        "id": row["id"],
        "name": row["name"],
        "email": row["email"],
        "role": row["role"],
        "created_at": row["created_at"]
    }


def create_session(user_id):
    token = secrets.token_urlsafe(32)

    now = utcnow()
    expires = now + timedelta(
        days=current_app.config["TOKEN_DAYS"]
    )

    db = get_db()

    db.execute(
        "DELETE FROM sessions WHERE expires_at < ?",
        (now.strftime(FMT),)
    )

    db.execute(
        """
        INSERT INTO sessions (user_id, token_hash, expires_at)
        VALUES (?, ?, ?)
        """,
        (
            user_id,
            hash_token(token),
            expires.strftime(FMT)
        )
    )

    db.commit()

    return token


def send_reset_email(email, reset_link):
    """Send a password-reset email using SMTP environment variables."""

    mail_host = os.environ.get("MAIL_HOST", "smtp.gmail.com")
    mail_port = int(os.environ.get("MAIL_PORT", "587"))
    mail_username = os.environ.get("MAIL_USERNAME")
    mail_password = os.environ.get("MAIL_APP_PASSWORD")
    mail_from = os.environ.get("MAIL_FROM") or mail_username

    if not all([mail_username, mail_password, mail_from]):
        raise RuntimeError("Email configuration is missing.")

    message = EmailMessage()
    message["Subject"] = "CropGuard AI - Password Reset"
    message["From"] = mail_from
    message["To"] = email

    message.set_content(
        f"""
Hello,

We received a request to reset your CropGuard AI account password.

Click the link below to create a new password:

{reset_link}

This link expires in {RESET_TOKEN_MINUTES} minutes
and can only be used once.

If you did not request this password reset, you can ignore this email.

CropGuard AI Team
"""
    )

    with smtplib.SMTP(mail_host, mail_port, timeout=20) as server:
        server.ehlo()
        server.starttls()
        server.ehlo()
        server.login(mail_username, mail_password)
        server.send_message(message)


def build_reset_link(token):
    """Build the frontend reset URL with the token query parameter."""

    base_url = os.environ.get("FRONTEND_RESET_URL")

    if not base_url:
        raise RuntimeError("FRONTEND_RESET_URL is not configured.")

    parts = urlsplit(base_url)

    if parts.scheme != "https" and parts.hostname not in (
        "localhost",
        "127.0.0.1"
    ):
        raise RuntimeError("Reset URL must use HTTPS.")

    query = dict(parse_qsl(parts.query))
    query["token"] = token

    return urlunsplit((
        parts.scheme,
        parts.netloc,
        parts.path,
        urlencode(query),
        parts.fragment
    ))


def login_required(view):
    @wraps(view)
    def wrapper(*args, **kwargs):
        header = request.headers.get("Authorization", "")

        if not header.startswith("Bearer ") or len(header) < 20:
            raise ApiError("Please log in to continue.", 401)

        token_hash = hash_token(header[7:].strip())

        row = get_db().execute(
            """
            SELECT u.*
            FROM sessions s
            JOIN users u ON u.id = s.user_id
            WHERE s.token_hash = ? AND s.expires_at > ?
            """,
            (token_hash, utcnow().strftime(FMT))
        ).fetchone()

        if row is None:
            raise ApiError(
                "Your session has expired. Please log in again.",
                401
            )

        g.user = row
        g.token_hash = token_hash

        return view(*args, **kwargs)

    return wrapper


# --------------------------------------------------
# REGISTER
# --------------------------------------------------

@auth_bp.post("/register")
def register():
    data = get_json()

    name = clean_name(data.get("name"))
    email = clean_email(data.get("email"))
    password = data.get("password")

    check_password_rules(password)

    db = get_db()

    existing_user = db.execute(
        "SELECT 1 FROM users WHERE email = ?",
        (email,)
    ).fetchone()

    if existing_user:
        raise ApiError(
            "An account with this email already exists.",
            409,
            "email"
        )

    cur = db.execute(
        """
        INSERT INTO users (name, email, password_hash)
        VALUES (?, ?, ?)
        """,
        (
            name,
            email,
            generate_password_hash(password)
        )
    )

    db.commit()

    user = db.execute(
        "SELECT * FROM users WHERE id = ?",
        (cur.lastrowid,)
    ).fetchone()

    return jsonify(
        message="Registration successful.",
        user=user_dict(user)
    ), 201


# --------------------------------------------------
# LOGIN
# --------------------------------------------------

@auth_bp.post("/login")
def login():
    data = get_json()

    email = str(data.get("email") or "").strip().lower()
    password = data.get("password")

    if not email or not isinstance(password, str) or not password:
        raise ApiError("Enter your email and password.")

    user = get_db().execute(
        "SELECT * FROM users WHERE email = ?",
        (email,)
    ).fetchone()

    if user is None or not check_password_hash(
        user["password_hash"],
        password
    ):
        raise ApiError("Incorrect email or password.", 401)

    token = create_session(user["id"])

    return jsonify(
        message="Login successful.",
        token=token,
        user=user_dict(user)
    )


# --------------------------------------------------
# FORGOT PASSWORD
# --------------------------------------------------

@auth_bp.post("/forgot-password")
def forgot_password():
    data = get_json()
    email = clean_email(data.get("email"))

    db = get_db()

    user = db.execute(
        "SELECT id, email FROM users WHERE email = ?",
        (email,)
    ).fetchone()

    # Always return the same response to avoid revealing
    # whether an email address has an account.
    response = jsonify(
        message=(
            "If an account exists for this email, "
            "a password-reset link will be sent."
        )
    )

    if user is None:
        return response, 200

    now = utcnow()
    expires = now + timedelta(minutes=RESET_TOKEN_MINUTES)

    # Remove previous unused tokens for this account.
    db.execute(
        """
        DELETE FROM password_reset_tokens
        WHERE user_id = ? AND used_at IS NULL
        """,
        (user["id"],)
    )

    # Remove expired tokens.
    db.execute(
        """
        DELETE FROM password_reset_tokens
        WHERE expires_at < ?
        """,
        (now.strftime(FMT),)
    )

    token = secrets.token_urlsafe(32)
    token_hash = hash_token(token)

    db.execute(
        """
        INSERT INTO password_reset_tokens
        (user_id, token_hash, expires_at)
        VALUES (?, ?, ?)
        """,
        (
            user["id"],
            token_hash,
            expires.strftime(FMT)
        )
    )

    db.commit()

    try:
        reset_link = build_reset_link(token)
        send_reset_email(user["email"], reset_link)

    except Exception:
        logging.exception("CropGuard password-reset email failed.")

        # Invalidate the token if email delivery failed.
        db.execute(
            """
            DELETE FROM password_reset_tokens
            WHERE token_hash = ?
            """,
            (token_hash,)
        )
        db.commit()

    return response, 200


# --------------------------------------------------
# RESET PASSWORD
# --------------------------------------------------

@auth_bp.post("/reset-password")
def reset_password():
    data = get_json()

    token = str(data.get("token") or "").strip()
    new_password = data.get("password")

    if not token or len(token) > 200:
        raise ApiError("Invalid or expired reset link.")

    check_password_rules(new_password)

    db = get_db()
    now = utcnow().strftime(FMT)

    token_hash = hash_token(token)

    reset_record = db.execute(
        """
        SELECT id, user_id
        FROM password_reset_tokens
        WHERE token_hash = ?
          AND expires_at > ?
          AND used_at IS NULL
        """,
        (token_hash, now)
    ).fetchone()

    if reset_record is None:
        raise ApiError(
            "Invalid or expired reset link.",
            400
        )

    # Change the password.
    db.execute(
        """
        UPDATE users
        SET password_hash = ?
        WHERE id = ?
        """,
        (
            generate_password_hash(new_password),
            reset_record["user_id"]
        )
    )

    # Mark this token as used.
    db.execute(
        """
        UPDATE password_reset_tokens
        SET used_at = ?
        WHERE id = ? AND used_at IS NULL
        """,
        (now, reset_record["id"])
    )

    # Log out all existing sessions for security.
    db.execute(
        "DELETE FROM sessions WHERE user_id = ?",
        (reset_record["user_id"],)
    )

    db.commit()

    return jsonify(
        message="Password reset successful. Please log in with your new password."
    )


# --------------------------------------------------
# LOGOUT
# --------------------------------------------------

@auth_bp.post("/logout")
@login_required
def logout():
    db = get_db()

    db.execute(
        "DELETE FROM sessions WHERE token_hash = ?",
        (g.token_hash,)
    )

    db.commit()

    return jsonify(message="Logged out.")
