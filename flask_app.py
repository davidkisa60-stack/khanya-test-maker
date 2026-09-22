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

# Simple JSON user store
USERS_FILE = Path(__file__).parent / "data" / "users.json"

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
    if not USERS_FILE.exists():
        USERS_FILE.parent.mkdir(parents=True, exist_ok=True)
        return {"users": []}
    with open(USERS_FILE, "r") as f:
        return json.load(f)

def save_users(data):
    USERS_FILE.parent.mkdir(parents=True, exist_ok=True)
    with open(USERS_FILE, "w") as f:
        json.dump(data, f, indent=2)


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
def index():
    # Serve the main app (login protection is handled client-side + login page)
    try:
        return send_from_directory('.', 'index.html')
    except:
        return "<h1>Khanya Test Maker</h1><p>index.html not found.</p>"

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
