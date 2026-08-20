"""
Khanya Test Maker — Flask server for Render.

Serves the HTML/JS files and the email allow-list APIs:
  POST /api/login
  GET  /api/admin/users
  POST /api/admin/add-user
  POST /api/admin/toggle-user

Keep any existing PDF/DOCX routes you already have; copy them into this
file (placeholders are at the bottom) so you do not lose test generation.
"""
from __future__ import annotations

import hashlib
import json
import os
import threading
from datetime import datetime, timezone
from functools import wraps

from flask import Flask, jsonify, request, send_from_directory
from flask_cors import CORS

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
USERS_FILE = os.path.join(BASE_DIR, "users.json")
SECRET = os.environ.get("KHANYA_SECRET", "khanya-change-this-secret")
ADMIN_EMAIL = os.environ.get("KHANYA_ADMIN_EMAIL", "admin@khanya.test").strip().lower()

app = Flask(__name__, static_folder=None)
CORS(app)
_lock = threading.Lock()


def _now() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%d")


def _default_users() -> dict:
    return {
        "users": [
            {
                "email": ADMIN_EMAIL,
                "active": True,
                "role": "admin",
                "added_at": _now(),
            }
        ]
    }


def load_users() -> list[dict]:
    with _lock:
        if not os.path.exists(USERS_FILE):
            data = _default_users()
            with open(USERS_FILE, "w", encoding="utf-8") as f:
                json.dump(data, f, indent=2)
            return data["users"]
        with open(USERS_FILE, "r", encoding="utf-8") as f:
            data = json.load(f)
        users = data.get("users") or []
        if not any(u.get("email") == ADMIN_EMAIL for u in users):
            users.insert(
                0,
                {
                    "email": ADMIN_EMAIL,
                    "active": True,
                    "role": "admin",
                    "added_at": _now(),
                },
            )
            _write_users_unlocked(users)
        return users


def _write_users_unlocked(users: list[dict]) -> None:
    with open(USERS_FILE, "w", encoding="utf-8") as f:
        json.dump({"users": users}, f, indent=2)


def save_users(users: list[dict]) -> None:
    with _lock:
        _write_users_unlocked(users)


def find_user(email: str) -> dict | None:
    email = (email or "").strip().lower()
    for u in load_users():
        if u.get("email") == email:
            return u
    return None


def make_token(email: str) -> str:
    return hashlib.sha256(f"{email.strip().lower()}:{SECRET}".encode()).hexdigest()


def public_user(u: dict) -> dict:
    return {
        "email": u.get("email"),
        "active": bool(u.get("active")),
        "role": u.get("role") or "user",
        "added_at": u.get("added_at") or "—",
    }


def current_user_from_request() -> dict | None:
    auth = request.headers.get("Authorization") or ""
    token = ""
    if auth.lower().startswith("bearer "):
        token = auth.split(" ", 1)[1].strip()
    email = (request.headers.get("X-User-Email") or "").strip().lower()
    if not email and request.is_json and request.json:
        email = (request.json.get("actor_email") or "").strip().lower()
    if not email:
        return None
    user = find_user(email)
    if not user or not user.get("active"):
        return None
    if token and token != make_token(email):
        return None
    return user


def require_admin(fn):
    @wraps(fn)
    def wrapper(*args, **kwargs):
        user = current_user_from_request()
        if not user or user.get("role") != "admin":
            return jsonify({"success": False, "message": "Admin access required"}), 403
        return fn(*args, **kwargs)

    return wrapper


# ---------- Pages (site opens on the login page) ----------

@app.route("/")
@app.route("/login")
@app.route("/login.html")
def login_page():
    return send_from_directory(BASE_DIR, "login.html")


@app.route("/admin")
@app.route("/admin.html")
def admin_page():
    return send_from_directory(BASE_DIR, "admin.html")


@app.route("/app")
@app.route("/index.html")
def app_page():
    return send_from_directory(BASE_DIR, "index.html")


@app.route("/js/<path:filename>")
def js_files(filename):
    return send_from_directory(os.path.join(BASE_DIR, "js"), filename)


# ---------- Auth APIs ----------

@app.post("/api/login")
def api_login():
    body = request.get_json(silent=True) or {}
    email = (body.get("email") or "").strip().lower()
    if not email or "@" not in email:
        return jsonify({"success": False, "message": "Enter a valid email address."}), 400

    user = find_user(email)
    if not user:
        return jsonify(
            {
                "success": False,
                "message": "This email is not registered. Ask an admin to add it.",
            }
        ), 403
    if not user.get("active"):
        return jsonify(
            {
                "success": False,
                "message": "This email is deactivated. Contact an admin.",
            }
        ), 403

    return jsonify(
        {
            "success": True,
            "email": user["email"],
            "active": True,
            "role": user.get("role") or "user",
            "token": make_token(user["email"]),
        }
    )


@app.get("/api/admin/users")
@require_admin
def api_users():
    users = [public_user(u) for u in load_users()]
    users.sort(key=lambda u: (u["role"] != "admin", u["email"]))
    return jsonify({"success": True, "users": users})


@app.post("/api/admin/add-user")
@require_admin
def api_add_user():
    body = request.get_json(silent=True) or {}
    email = (body.get("email") or "").strip().lower()
    role = (body.get("role") or "user").strip().lower()
    if role not in ("user", "admin"):
        role = "user"
    if not email or "@" not in email:
        return jsonify({"success": False, "message": "Enter a valid email address."}), 400

    users = load_users()
    if any(u.get("email") == email for u in users):
        return jsonify({"success": False, "message": "That email is already registered."}), 409

    # New emails start inactive so you activate them from the admin panel.
    users.append(
        {
            "email": email,
            "active": False,
            "role": role,
            "added_at": _now(),
        }
    )
    save_users(users)
    return jsonify({"success": True, "message": "User added. Activate them to allow login."})


@app.post("/api/admin/toggle-user")
@require_admin
def api_toggle_user():
    body = request.get_json(silent=True) or {}
    email = (body.get("email") or "").strip().lower()
    if "active" not in body:
        return jsonify({"success": False, "message": "Missing active flag."}), 400
    active = bool(body.get("active"))

    users = load_users()
    target = next((u for u in users if u.get("email") == email), None)
    if not target:
        return jsonify({"success": False, "message": "User not found."}), 404

    if target.get("role") == "admin" and not active:
        admins_left = [
            u for u in users if u.get("role") == "admin" and u.get("active") and u.get("email") != email
        ]
        if not admins_left:
            return jsonify(
                {"success": False, "message": "You cannot deactivate the last admin."}
            ), 400

    target["active"] = active
    save_users(users)
    return jsonify({"success": True, "user": public_user(target)})


# Serve existing project files (questions.json, images, etc.)
@app.route("/<path:path>")
def other_files(path):
    if path.startswith("api/"):
        return jsonify({"message": "Not found"}), 404
    full = os.path.join(BASE_DIR, path)
    if os.path.isfile(full):
        return send_from_directory(BASE_DIR, path)
    return jsonify({"message": "Not found"}), 404


# ---------- Keep / paste your existing generators here ----------
# @app.post("/api/generate-pdf")
# def generate_pdf():
#     ...
#
# @app.post("/api/generate-docx")
# def generate_docx():
#     ...


if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5000))
    app.run(host="0.0.0.0", port=port, debug=False)
