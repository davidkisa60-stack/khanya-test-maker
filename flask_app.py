#!/usr/bin/env python3
"""
Flask for Khanya Test Maker - with Login + Admin User Management
"""

from flask import Flask, request, send_file, jsonify, send_from_directory, make_response, redirect
from io import BytesIO
from pathlib import Path
import traceback
import sys
import os
import json
from datetime import datetime

sys.path.append(str(Path(__file__).parent))

from generate_paper import load_questions, build_pdf, build_docx, get_question_by_id, HAS_DOCX

app = Flask(__name__, static_folder='.', static_url_path='')

# === CORS for Netlify frontend (important for split deployment) ===
ALLOWED_ORIGINS = os.environ.get("ALLOWED_ORIGINS", "*")

# User store:
# - Local JSON file for development
# - PostgreSQL when DATABASE_URL is set (survives Render sleep/redeploys)
USERS_FILE = Path(os.environ.get("USERS_FILE", Path(__file__).parent / "data" / "users.json"))
DATABASE_URL = (os.environ.get("DATABASE_URL") or "").strip()

try:
    import psycopg2
    from psycopg2.extras import Json as PgJson
    HAS_PSYCOPG = True
except ImportError:
    HAS_PSYCOPG = False

_pg_ready = False


def _using_postgres():
    return bool(DATABASE_URL) and HAS_PSYCOPG


def _pg_connect():
    dsn = DATABASE_URL
    if dsn.startswith("postgres://"):
        dsn = "postgresql://" + dsn[len("postgres://"):]
    if "sslmode=" not in dsn and "localhost" not in dsn and "127.0.0.1" not in dsn:
        dsn += ("&" if "?" in dsn else "?") + "sslmode=require"
    return psycopg2.connect(dsn)


def _load_users_file():
    if not USERS_FILE.exists():
        USERS_FILE.parent.mkdir(parents=True, exist_ok=True)
        return {"users": []}
    with open(USERS_FILE, "r") as f:
        return json.load(f)


def _save_users_file(data):
    USERS_FILE.parent.mkdir(parents=True, exist_ok=True)
    with open(USERS_FILE, "w") as f:
        json.dump(data, f, indent=2)


def _ensure_pg():
    global _pg_ready
    if _pg_ready:
        return
    conn = _pg_connect()
    try:
        with conn.cursor() as cur:
            cur.execute(
                """
                CREATE TABLE IF NOT EXISTS khanya_kv (
                    key TEXT PRIMARY KEY,
                    value JSONB NOT NULL,
                    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
                )
                """
            )
            cur.execute("SELECT value FROM khanya_kv WHERE key = %s", ("users",))
            row = cur.fetchone()
            if not row:
                seed = _load_users_file()
                cur.execute(
                    "INSERT INTO khanya_kv (key, value) VALUES (%s, %s)",
                    ("users", PgJson(seed)),
                )
        conn.commit()
        _pg_ready = True
        print("Khanya user store: PostgreSQL (persistent)")
    finally:
        conn.close()

ALL_SUBJECTS = [
    "Mathematics",
    "Biology",
    "Physical Science",
    "Economics",
    "Development Studies",
    "Accounting",
    "English",
]


def load_users():
    if _using_postgres():
        try:
            _ensure_pg()
            conn = _pg_connect()
            try:
                with conn.cursor() as cur:
                    cur.execute("SELECT value FROM khanya_kv WHERE key = %s", ("users",))
                    row = cur.fetchone()
                    if row and row[0]:
                        val = row[0]
                        if isinstance(val, str):
                            val = json.loads(val)
                        if isinstance(val, dict) and "users" in val:
                            return val
            finally:
                conn.close()
        except Exception as e:
            print("Postgres load failed, falling back to file:", e)
            traceback.print_exc()
    return _load_users_file()


def save_users(data):
    # Always keep a local copy for development / cache
    try:
        _save_users_file(data)
    except Exception as e:
        print("Local users.json save failed:", e)

    if _using_postgres():
        _ensure_pg()
        conn = _pg_connect()
        try:
            with conn.cursor() as cur:
                cur.execute(
                    """
                    INSERT INTO khanya_kv (key, value, updated_at)
                    VALUES (%s, %s, NOW())
                    ON CONFLICT (key) DO UPDATE
                    SET value = EXCLUDED.value, updated_at = NOW()
                    """,
                    ("users", PgJson(data)),
                )
            conn.commit()
        finally:
            conn.close()
        return

    # Without DATABASE_URL, Render's disk is wiped when the service sleeps.
    print("WARNING: users saved to ephemeral disk only. Set DATABASE_URL to keep admin changes.")


def normalize_subjects(raw, default_all=True):
    """Keep only known subject names, preserving the canonical order."""
    if not isinstance(raw, list):
        return list(ALL_SUBJECTS) if default_all else []
    selected = {s for s in raw if s in ALL_SUBJECTS}
    return [s for s in ALL_SUBJECTS if s in selected]


def subjects_for_user(user):
    """Admins always see every subject. Legacy users without a subjects list keep full access."""
    if not user:
        return []
    if user.get("role") == "admin":
        return list(ALL_SUBJECTS)
    if "subjects" not in user:
        return list(ALL_SUBJECTS)
    return normalize_subjects(user.get("subjects"), default_all=False)

@app.after_request
def add_cors_headers(response):
    origin = request.headers.get("Origin", "")
    if ALLOWED_ORIGINS == "*" or origin in ALLOWED_ORIGINS.split(",") or "localhost" in origin or "127.0.0.1" in origin:
        response.headers["Access-Control-Allow-Origin"] = origin if origin else "*"
        response.headers["Access-Control-Allow-Methods"] = "GET, POST, OPTIONS"
        response.headers["Access-Control-Allow-Headers"] = "Content-Type, Authorization"
        response.headers["Access-Control-Allow-Credentials"] = "true"
    if request.method == "OPTIONS":
        return response, 200
    return response

# ==================== AUTH ROUTES ====================

@app.route('/login')
def login_page():
    return send_from_directory('.', 'login.html')

@app.route('/admin')
def admin_page():
    return send_from_directory('.', 'admin.html')

@app.route('/api/login', methods=['POST'])
def login():
    try:
        data = request.get_json(force=True)
        email = data.get('email', '').strip().lower()

        if not email:
            return jsonify({"success": False, "message": "Email is required"}), 400

        users_data = load_users()
        user = next((u for u in users_data.get("users", []) if u["email"].lower() == email), None)

        if not user:
            return jsonify({"success": False, "message": "Email not registered. Please contact the administrator."}), 403

        if not user.get("active", False):
            return jsonify({"success": False, "message": "This account is currently disabled. Please contact the administrator."}), 403

        return jsonify({
            "success": True,
            "email": user["email"],
            "active": user["active"],
            "role": user.get("role", "user"),
            "subjects": subjects_for_user(user)
        })
    except Exception as e:
        return jsonify({"success": False, "message": str(e)}), 500

# ==================== ADMIN ROUTES ====================

@app.route('/api/admin/storage', methods=['GET'])
def storage_status():
    persistent = _using_postgres()
    return jsonify({
        "persistent": persistent,
        "backend": "postgres" if persistent else "ephemeral-file"
    })


@app.route('/api/admin/users', methods=['GET'])
def get_users():
    try:
        users_data = load_users()
        users = []
        for user in users_data.get("users", []):
            item = dict(user)
            item["subjects"] = subjects_for_user(user)
            users.append(item)
        return jsonify({"users": users})
    except Exception as e:
        return jsonify({"error": str(e)}), 500

@app.route('/api/admin/add-user', methods=['POST'])
def add_user():
    try:
        data = request.get_json(force=True)
        email = data.get('email', '').strip().lower()

        if not email:
            return jsonify({"success": False, "message": "Email is required"}), 400

        users_data = load_users()
        existing = [u for u in users_data.get("users", []) if u["email"].lower() == email]

        if existing:
            return jsonify({"success": False, "message": "User already exists"}), 409

        subjects = normalize_subjects(data.get("subjects"), default_all=True)
        if not subjects:
            return jsonify({"success": False, "message": "Select at least one subject"}), 400

        new_user = {
            "email": email,
            "active": True,
            "role": "user",
            "added_at": datetime.now().strftime("%Y-%m-%d"),
            "subjects": subjects
        }
        users_data.setdefault("users", []).append(new_user)
        save_users(users_data)

        return jsonify({"success": True, "message": "User added successfully", "user": new_user})
    except Exception as e:
        return jsonify({"success": False, "message": str(e)}), 500

@app.route('/api/admin/toggle-user', methods=['POST'])
def toggle_user():
    try:
        data = request.get_json(force=True)
        email = data.get('email', '').strip().lower()
        active = data.get('active', True)

        users_data = load_users()
        updated = False

        for user in users_data.get("users", []):
            if user["email"].lower() == email:
                user["active"] = bool(active)
                updated = True
                break

        if not updated:
            return jsonify({"success": False, "message": "User not found"}), 404

        save_users(users_data)
        return jsonify({"success": True})
    except Exception as e:
        return jsonify({"success": False, "message": str(e)}), 500


@app.route('/api/admin/update-subjects', methods=['POST'])
def update_user_subjects():
    try:
        data = request.get_json(force=True)
        email = data.get('email', '').strip().lower()
        subjects = normalize_subjects(data.get('subjects'), default_all=False)

        if not email:
            return jsonify({"success": False, "message": "Email is required"}), 400
        if not subjects:
            return jsonify({"success": False, "message": "Select at least one subject"}), 400

        users_data = load_users()
        updated_user = None

        for user in users_data.get("users", []):
            if user["email"].lower() == email:
                if user.get("role") == "admin":
                    user["subjects"] = list(ALL_SUBJECTS)
                else:
                    user["subjects"] = subjects
                updated_user = user
                break

        if not updated_user:
            return jsonify({"success": False, "message": "User not found"}), 404

        save_users(users_data)
        return jsonify({
            "success": True,
            "subjects": subjects_for_user(updated_user)
        })
    except Exception as e:
        return jsonify({"success": False, "message": str(e)}), 500


@app.route('/api/subjects', methods=['GET'])
def list_subjects():
    return jsonify({"subjects": list(ALL_SUBJECTS)})

# ==================== EXISTING ROUTES ====================

@app.route('/')
def root():
    # Site URL always opens on a fresh login screen
    return send_from_directory('.', 'login.html')

@app.route('/app')
def app_page():
    return send_from_directory('.', 'index.html')

@app.route('/<path:path>')
def static_files(path):
    return send_from_directory('.', path)

@app.route('/api/generate-pdf', methods=['POST'])
def generate_pdf_api():
    try:
        data = request.get_json(force=True)
        ids = data.get('ids', [])
        title = data.get('title', 'Test Paper')

        if not ids:
            return jsonify({"error": "No question IDs provided"}), 400

        subject = data.get('subject', 'Mathematics')
        all_q = load_questions(subject)
        selected = [q for q in all_q if q["id"] in ids]

        if not selected:
            return jsonify({"error": "No valid questions found"}), 400

        pdf_bytes = build_pdf(selected, title=title)
        
        if not pdf_bytes:
            return jsonify({"error": "PDF generation returned empty"}), 500

        return send_file(
            BytesIO(pdf_bytes),
            mimetype='application/pdf',
            as_attachment=True,
            download_name=f"{title.replace(' ', '_')}.pdf"
        )
    except Exception as e:
        print("=== ERROR ===")
        traceback.print_exc()
        return jsonify({"error": str(e)}), 500

@app.route('/api/generate-docx', methods=['POST'])
def generate_docx_api():
    try:
        if not HAS_DOCX:
            return jsonify({"error": "python-docx not installed on server. Run: pip install python-docx"}), 500

        data = request.get_json(force=True)
        ids = data.get('ids', [])
        title = data.get('title', 'Test Paper')

        if not ids:
            return jsonify({"error": "No question IDs provided"}), 400

        subject = data.get('subject', 'Mathematics')
        all_q = load_questions(subject)
        selected = [q for q in all_q if q["id"] in ids]

        if not selected:
            return jsonify({"error": "No valid questions found"}), 400

        docx_bytes = build_docx(selected, title=title)
        
        if not docx_bytes:
            return jsonify({"error": "Word generation returned empty"}), 500

        return send_file(
            BytesIO(docx_bytes),
            mimetype='application/vnd.openxmlformats-officedocument.wordprocessingml.document',
            as_attachment=True,
            download_name=f"{title.replace(' ', '_')}.docx"
        )
    except Exception as e:
        print("=== ERROR (DOCX) ===")
        traceback.print_exc()
        return jsonify({"error": str(e)}), 500

if __name__ == '__main__':
    import os
    port = int(os.environ.get("PORT", 5001))
    print(f"Khanya Test Maker server running on http://0.0.0.0:{port}")
    print("  - Login: /login")
    print("  - Admin: /admin")
    app.run(host='0.0.0.0', port=port, debug=True)
