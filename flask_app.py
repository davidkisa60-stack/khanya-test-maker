#!/usr/bin/env python3
"""
Flask for Khanya Test Maker - with Login + Admin User Management

User emails are written to data/users.json AND (if GITHUB_TOKEN is set)
committed back to GitHub so they survive Render restarts.
"""

from flask import Flask, request, send_file, jsonify, send_from_directory
from io import BytesIO
from pathlib import Path
import traceback
import sys
import os
import json
import base64
import threading
import secrets
import time
from datetime import datetime
from urllib.request import Request, urlopen
from urllib.error import HTTPError, URLError

sys.path.append(str(Path(__file__).parent))

from generate_paper import load_questions, build_pdf, build_docx, get_question_by_id, HAS_DOCX

app = Flask(__name__, static_folder=".", static_url_path="")

ALLOWED_ORIGINS = os.environ.get("ALLOWED_ORIGINS", "*")

# Local file (wiped on Render restart unless you attach a Persistent Disk)
USERS_FILE = Path(os.environ.get("USERS_FILE", str(Path(__file__).parent / "data" / "users.json")))

# Persist to GitHub so emails survive restarts (set these on Render)
GITHUB_TOKEN = (os.environ.get("GITHUB_TOKEN") or "").strip()
GITHUB_REPO = os.environ.get("GITHUB_REPO", "davidkisa60-stack/khanya-test-maker").strip()
GITHUB_BRANCH = os.environ.get("GITHUB_BRANCH", "main").strip()
GITHUB_USERS_PATH = os.environ.get("GITHUB_USERS_PATH", "data/users.json").strip()

_lock = threading.Lock()
_memory_users = None

# One live session per email. Idle timeout is 5 minutes.
IDLE_SECONDS = int(os.environ.get("SESSION_IDLE_SECONDS", "300"))
_sessions = {}  # email -> {token, last_activity}
_sess_lock = threading.Lock()


def _default_users():
    admin = os.environ.get("KHANYA_ADMIN_EMAIL", "admin@khanya.test").strip().lower()
    return {
        "users": [
            {
                "email": admin,
                "active": True,
                "role": "admin",
                "added_at": datetime.now().strftime("%Y-%m-%d"),
            }
        ]
    }


def _github_headers(with_auth=True):
    headers = {
        "Accept": "application/vnd.github+json",
        "User-Agent": "khanya-test-maker",
        "X-GitHub-Api-Version": "2022-11-28",
    }
    if with_auth and GITHUB_TOKEN:
        headers["Authorization"] = f"Bearer {GITHUB_TOKEN}"
    return headers


def _github_get_file():
    """Return (data_dict, sha) from GitHub, or (None, None)."""
    api = f"https://api.github.com/repos/{GITHUB_REPO}/contents/{GITHUB_USERS_PATH}?ref={GITHUB_BRANCH}"
    req = Request(api, headers=_github_headers(with_auth=bool(GITHUB_TOKEN)))
    try:
        with urlopen(req, timeout=20) as resp:
            payload = json.loads(resp.read().decode("utf-8"))
        sha = payload.get("sha")
        raw = base64.b64decode(payload.get("content") or "").decode("utf-8")
        data = json.loads(raw)
        if isinstance(data, dict) and "users" in data:
            return data, sha
    except Exception as e:
        print("GitHub read failed:", e)
    return None, None


def _github_put_file(data):
    """Commit users.json to GitHub. Returns True on success."""
    if not GITHUB_TOKEN:
        print("GITHUB_TOKEN is not set — emails will be lost on the next Render restart.")
        return False

    _, sha = _github_get_file()
    body = {
        "message": "Update registered emails (admin panel)",
        "content": base64.b64encode(json.dumps(data, indent=2).encode("utf-8")).decode("ascii"),
        "branch": GITHUB_BRANCH,
    }
    if sha:
        body["sha"] = sha

    api = f"https://api.github.com/repos/{GITHUB_REPO}/contents/{GITHUB_USERS_PATH}"
    req = Request(
        api,
        data=json.dumps(body).encode("utf-8"),
        headers={**_github_headers(with_auth=True), "Content-Type": "application/json"},
        method="PUT",
    )
    try:
        with urlopen(req, timeout=20) as resp:
            if 200 <= resp.status < 300:
                print("Saved users.json to GitHub")
                return True
            print("GitHub save status:", resp.status)
    except HTTPError as e:
        err = e.read().decode("utf-8", "replace")
        print("GitHub save HTTP error:", e.code, err)
    except URLError as e:
        print("GitHub save network error:", e)
    return False


def load_users():
    global _memory_users
    with _lock:
        if _memory_users and _memory_users.get("users"):
            return json.loads(json.dumps(_memory_users))

        if USERS_FILE.exists():
            try:
                with open(USERS_FILE, "r", encoding="utf-8") as f:
                    data = json.load(f)
                if data.get("users"):
                    _memory_users = data
                    return json.loads(json.dumps(data))
            except Exception as e:
                print("Local users.json read failed:", e)

        data, _ = _github_get_file()
        if data and data.get("users"):
            _memory_users = data
            try:
                USERS_FILE.parent.mkdir(parents=True, exist_ok=True)
                with open(USERS_FILE, "w", encoding="utf-8") as f:
                    json.dump(data, f, indent=2)
            except Exception:
                pass
            return json.loads(json.dumps(data))

        data = _default_users()
        _memory_users = data
        return json.loads(json.dumps(data))


def save_users(data):
    global _memory_users
    with _lock:
        _memory_users = json.loads(json.dumps(data))
        try:
            USERS_FILE.parent.mkdir(parents=True, exist_ok=True)
            with open(USERS_FILE, "w", encoding="utf-8") as f:
                json.dump(data, f, indent=2)
        except Exception as e:
            print("Local users.json write failed:", e)
        saved = _github_put_file(data)
        return saved


def _session_now():
    return time.time()


def _session_token_from_request():
    auth = request.headers.get("Authorization") or ""
    if auth.lower().startswith("bearer "):
        return auth.split(" ", 1)[1].strip()
    token = (request.headers.get("X-Session-Token") or "").strip()
    if token:
        return token
    body = request.get_json(silent=True) or {}
    return (body.get("token") or "").strip()


def _find_session(token):
    if not token:
        return None, None
    with _sess_lock:
        for email, sess in list(_sessions.items()):
            if sess.get("token") == token:
                idle = _session_now() - float(sess.get("last_activity") or 0)
                if idle > IDLE_SECONDS:
                    _sessions.pop(email, None)
                    return None, "idle"
                return email, sess
    return None, "replaced"


def create_session(email):
    token = secrets.token_urlsafe(32)
    with _sess_lock:
        _sessions[email] = {"token": token, "last_activity": _session_now()}
    return token


def touch_session(email):
    with _sess_lock:
        if email in _sessions:
            _sessions[email]["last_activity"] = _session_now()


def destroy_session(token):
    with _sess_lock:
        for email, sess in list(_sessions.items()):
            if sess.get("token") == token:
                _sessions.pop(email, None)
                return True
    return False


def require_session(admin_only=False):
    token = _session_token_from_request()
    email, sess = _find_session(token)
    if sess == "idle":
        return None, (
            jsonify(
                {
                    "success": False,
                    "reason": "idle",
                    "message": "Signed out after 5 minutes of inactivity.",
                }
            ),
            401,
        )
    if not email:
        reason = "replaced" if token else "session"
        msg = (
            "This email is signed in somewhere else."
            if token
            else "Please sign in."
        )
        return None, (
            jsonify({"success": False, "reason": reason, "message": msg}),
            401,
        )

    users_data = load_users()
    user = next((u for u in users_data.get("users", []) if u["email"].lower() == email), None)
    if not user or not user.get("active"):
        destroy_session(token)
        return None, (
            jsonify({"success": False, "reason": "session", "message": "Account is not active."}),
            403,
        )
    if admin_only and user.get("role") != "admin":
        return None, (jsonify({"success": False, "message": "Admin access required"}), 403)
    touch_session(email)
    return (email, user), None


@app.after_request
def add_cors_headers(response):
    origin = request.headers.get("Origin", "")
    if (
        ALLOWED_ORIGINS == "*"
        or origin in ALLOWED_ORIGINS.split(",")
        or "localhost" in origin
        or "127.0.0.1" in origin
    ):
        response.headers["Access-Control-Allow-Origin"] = origin if origin else "*"
        response.headers["Access-Control-Allow-Methods"] = "GET, POST, OPTIONS"
        response.headers["Access-Control-Allow-Headers"] = "Content-Type, Authorization, X-User-Email, X-Session-Token"
        response.headers["Access-Control-Allow-Credentials"] = "true"
    if request.method == "OPTIONS":
        response.status_code = 200
    return response


# ==================== AUTH ROUTES ====================

@app.route("/login")
def login_page():
    return send_from_directory(".", "login.html")


@app.route("/admin")
def admin_page():
    return send_from_directory(".", "admin.html")


@app.route("/api/login", methods=["POST"])
def login():
    try:
        data = request.get_json(force=True)
        email = data.get("email", "").strip().lower()

        if not email:
            return jsonify({"success": False, "message": "Email is required"}), 400

        users_data = load_users()
        user = next((u for u in users_data.get("users", []) if u["email"].lower() == email), None)

        if not user:
            return jsonify(
                {"success": False, "message": "Email not registered. Please contact the administrator."}
            ), 403

        if not user.get("active", False):
            return jsonify(
                {
                    "success": False,
                    "message": "This account is currently disabled. Please contact the administrator.",
                }
            ), 403

        token = create_session(user["email"])
        return jsonify(
            {
                "success": True,
                "email": user["email"],
                "active": user["active"],
                "role": user.get("role", "user"),
                "token": token,
                "idle_seconds": IDLE_SECONDS,
            }
        )
    except Exception as e:
        return jsonify({"success": False, "message": str(e)}), 500


@app.route("/api/session", methods=["GET", "POST"])
def api_session():
    pair, err = require_session()
    if err:
        return err
    email, user = pair
    return jsonify({"success": True, "email": email, "role": user.get("role", "user")})


@app.route("/api/logout", methods=["POST"])
def api_logout():
    token = _session_token_from_request()
    destroy_session(token)
    return jsonify({"success": True})


# ==================== ADMIN ROUTES ====================

@app.route("/api/admin/users", methods=["GET"])
def get_users():
    pair, err = require_session(admin_only=True)
    if err:
        return err
    try:
        users_data = load_users()
        users_data["persist_ok"] = bool(GITHUB_TOKEN)
        return jsonify(users_data)
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@app.route("/api/admin/add-user", methods=["POST"])
def add_user():
    pair, err = require_session(admin_only=True)
    if err:
        return err
    try:
        data = request.get_json(force=True)
        email = data.get("email", "").strip().lower()
        role = (data.get("role") or "user").strip().lower()
        if role not in ("user", "admin"):
            role = "user"

        if not email:
            return jsonify({"success": False, "message": "Email is required"}), 400

        users_data = load_users()
        existing = [u for u in users_data.get("users", []) if u["email"].lower() == email]

        if existing:
            return jsonify({"success": False, "message": "User already exists"}), 409

        new_user = {
            "email": email,
            "active": True,
            "role": role,
            "added_at": datetime.now().strftime("%Y-%m-%d"),
        }
        users_data.setdefault("users", []).append(new_user)
        persisted = save_users(users_data)

        msg = "User added successfully"
        if not persisted:
            msg += ". WARNING: GITHUB_TOKEN is not set on Render, so this email will disappear after the next restart."

        return jsonify({"success": True, "message": msg, "persisted": persisted})
    except Exception as e:
        return jsonify({"success": False, "message": str(e)}), 500


@app.route("/api/admin/toggle-user", methods=["POST"])
def toggle_user():
    pair, err = require_session(admin_only=True)
    if err:
        return err
    try:
        data = request.get_json(force=True)
        email = data.get("email", "").strip().lower()
        active = data.get("active", True)

        users_data = load_users()
        updated = False

        for user in users_data.get("users", []):
            if user["email"].lower() == email:
                user["active"] = bool(active)
                updated = True
                break

        if not updated:
            return jsonify({"success": False, "message": "User not found"}), 404

        persisted = save_users(users_data)
        return jsonify({"success": True, "persisted": persisted})
    except Exception as e:
        return jsonify({"success": False, "message": str(e)}), 500


# ==================== EXISTING ROUTES ====================

@app.route("/")
def index():
    # Site URL always opens the login page (never the last session).
    return send_from_directory(".", "login.html")


@app.route("/app")
@app.route("/index.html")
def app_page():
    return send_from_directory(".", "index.html")


@app.route("/<path:path>")
def static_files(path):
    return send_from_directory(".", path)


@app.route("/api/generate-pdf", methods=["POST"])
def generate_pdf_api():
    pair, err = require_session()
    if err:
        return err
    try:
        data = request.get_json(force=True)
        ids = data.get("ids", [])
        title = data.get("title", "Test Paper")

        if not ids:
            return jsonify({"error": "No question IDs provided"}), 400

        subject = data.get("subject", "Mathematics")
        all_q = load_questions(subject)
        selected = [q for q in all_q if q["id"] in ids]

        if not selected:
            return jsonify({"error": "No valid questions found"}), 400

        pdf_bytes = build_pdf(selected, title=title)

        if not pdf_bytes:
            return jsonify({"error": "PDF generation returned empty"}), 500

        return send_file(
            BytesIO(pdf_bytes),
            mimetype="application/pdf",
            as_attachment=True,
            download_name=f"{title.replace(' ', '_')}.pdf",
        )
    except Exception as e:
        print("=== ERROR ===")
        traceback.print_exc()
        return jsonify({"error": str(e)}), 500


@app.route("/api/generate-docx", methods=["POST"])
def generate_docx_api():
    pair, err = require_session()
    if err:
        return err
    try:
        if not HAS_DOCX:
            return jsonify({"error": "python-docx not installed on server. Run: pip install python-docx"}), 500

        data = request.get_json(force=True)
        ids = data.get("ids", [])
        title = data.get("title", "Test Paper")

        if not ids:
            return jsonify({"error": "No question IDs provided"}), 400

        subject = data.get("subject", "Mathematics")
        all_q = load_questions(subject)
        selected = [q for q in all_q if q["id"] in ids]

        if not selected:
            return jsonify({"error": "No valid questions found"}), 400

        docx_bytes = build_docx(selected, title=title)

        if not docx_bytes:
            return jsonify({"error": "Word generation returned empty"}), 500

        return send_file(
            BytesIO(docx_bytes),
            mimetype="application/vnd.openxmlformats-officedocument.wordprocessingml.document",
            as_attachment=True,
            download_name=f"{title.replace(' ', '_')}.docx",
        )
    except Exception as e:
        print("=== ERROR (DOCX) ===")
        traceback.print_exc()
        return jsonify({"error": str(e)}), 500


if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5001))
    print(f"Khanya Test Maker server running on http://0.0.0.0:{port}")
    print("  - Login: /login")
    print("  - Admin: /admin")
    app.run(host="0.0.0.0", port=port, debug=True)
