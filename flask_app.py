#!/usr/bin/env python3
"""
Flask for Khanya Test Maker - clean, supports custom paper title + PDF and Word export
"""

from flask import Flask, request, send_file, jsonify, send_from_directory, make_response
from io import BytesIO
from pathlib import Path
import traceback
import sys
import os

sys.path.append(str(Path(__file__).parent))

from generate_paper import load_questions, build_pdf, build_docx, get_question_by_id, HAS_DOCX

app = Flask(__name__, static_folder='.', static_url_path='')

# === CORS for Netlify frontend (important for split deployment) ===
ALLOWED_ORIGINS = os.environ.get("ALLOWED_ORIGINS", "*")

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

@app.route('/')
def index():
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
    print("  - PDF:  POST /api/generate-pdf   {ids: [...], title: '...'}")
    print("  - Word: POST /api/generate-docx  {ids: [...], title: '...'}")
    app.run(host='0.0.0.0', port=port, debug=True)