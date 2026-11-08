"""Registration, login, logout and the login_required decorator.

Login returns a random token. Only a SHA-256 hash of the token is stored in
the database, so a leaked database cannot be used to impersonate users.
The website and the Flutter app send it as:  Authorization: Bearer <token>
"""
import hashlib
import re
import secrets
from datetime import datetime, timedelta, timezone
from functools import wraps

from flask import Blueprint, current_app, g, jsonify, request
from werkzeug.security import check_password_hash, generate_password_hash

from database import get_db

auth_bp = Blueprint("auth", __name__, url_prefix="/api/auth")

EMAIL_RE = re.compile(r"^[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}$")
FMT = "%Y-%m-%d %H:%M:%S"


def utcnow():
    """Current UTC time (matches SQLite datetime('now'))."""
    return datetime.now(timezone.utc).replace(tzinfo=None)


class ApiError(Exception):
    def __init__(self, message, status=400, field=None):
        super().__init__(message)
        self.message, self.status, self.field = message, status, field


def get_json():
    data = request.get_json(silent=True)
    if not isinstance(data, dict):
        raise ApiError("Request body must be a JSON object.")
    return data


def clean_name(value):
    name = " ".join(str(value or "").split())
    if not 2 <= len(name) <= 80:
        raise ApiError("Name must be 2 to 80 characters.", field="name")
    return name


def clean_email(value):
    email = str(value or "").strip().lower()
    if len(email) > 254 or not EMAIL_RE.match(email):
        raise ApiError("Enter a valid email address.", field="email")
    return email


def check_password_rules(password):
    if not isinstance(password, str) or not 8 <= len(password) <= 128:
        raise ApiError("Password must be 8 to 128 characters.", field="password")
    if not (re.search(r"[A-Za-z]", password) and re.search(r"\d", password)):
        raise ApiError("Password must contain at least one letter and one number.", field="password")


def hash_token(token):
    return hashlib.sha256(token.encode()).hexdigest()


def user_dict(row):
    return {"id": row["id"], "name": row["name"], "email": row["email"],
            "role": row["role"], "created_at": row["created_at"]}


def create_session(user_id):
    token = secrets.token_urlsafe(32)
    now = utcnow()
    expires = now + timedelta(days=current_app.config["TOKEN_DAYS"])
    db = get_db()
    db.execute("DELETE FROM sessions WHERE expires_at < ?", (now.strftime(FMT),))
    db.execute("INSERT INTO sessions (user_id, token_hash, expires_at) VALUES (?,?,?)",
               (user_id, hash_token(token), expires.strftime(FMT)))
    db.commit()
    return token


def login_required(view):
    @wraps(view)
    def wrapper(*args, **kwargs):
        header = request.headers.get("Authorization", "")
        if not header.startswith("Bearer ") or len(header) < 20:
            raise ApiError("Please log in to continue.", 401)
        token_hash = hash_token(header[7:].strip())
        row = get_db().execute(
            "SELECT u.* FROM sessions s JOIN users u ON u.id = s.user_id "
            "WHERE s.token_hash = ? AND s.expires_at > ?",
            (token_hash, utcnow().strftime(FMT))).fetchone()
        if row is None:
            raise ApiError("Your session has expired. Please log in again.", 401)
        g.user, g.token_hash = row, token_hash
        return view(*args, **kwargs)
    return wrapper


@auth_bp.post("/register")
def register():
    data = get_json()
    name = clean_name(data.get("name"))
    email = clean_email(data.get("email"))
    password = data.get("password")
    check_password_rules(password)

    db = get_db()
    if db.execute("SELECT 1 FROM users WHERE email = ?", (email,)).fetchone():
        raise ApiError("An account with this email already exists.", 409, "email")
    cur = db.execute("INSERT INTO users (name, email, password_hash) VALUES (?,?,?)",
                     (name, email, generate_password_hash(password)))
    db.commit()
    user = db.execute("SELECT * FROM users WHERE id = ?", (cur.lastrowid,)).fetchone()
    return jsonify(message="Registration successful.", user=user_dict(user)), 201


@auth_bp.post("/login")
def login():
    data = get_json()
    email = str(data.get("email") or "").strip().lower()
    password = data.get("password")
    if not email or not isinstance(password, str) or not password:
        raise ApiError("Enter your email and password.")
    user = get_db().execute("SELECT * FROM users WHERE email = ?", (email,)).fetchone()
    # Same message for unknown email and wrong password, so emails cannot be probed.
    if user is None or not check_password_hash(user["password_hash"], password):
        raise ApiError("Incorrect email or password.", 401)
    token = create_session(user["id"])
    return jsonify(message="Login successful.", token=token, user=user_dict(user))


@auth_bp.post("/logout")
@login_required
def logout():
    db = get_db()
    db.execute("DELETE FROM sessions WHERE token_hash = ?", (g.token_hash,))
    db.commit()
    return jsonify(message="Logged out.")
