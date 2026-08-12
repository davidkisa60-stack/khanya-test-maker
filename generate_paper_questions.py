#!/usr/bin/env python3
"""
Local script to generate a questions.json for ONE exam paper (e.g. 2018 P1).

Run this on your Windows machine next to your PDF.

What it does:
1. Extracts page preview images (so you can read the paper).
2. Extracts all embedded images (diagrams, tables, graphs).
3. Tries to OCR the pages (installs easyocr if needed).
4. Attempts to split into questions using numbering + marks.
5. Creates clean titles, body_markdown (no dots, good spacing), basic latex.
6. Outputs questions_YYYY.json ready for you to review and paste here.

Usage:
    pip install pymupdf pillow easyocr
    python generate_paper_questions.py "C:\path\to\Maths P1 2018.pdf" --year 2018 --paper "P1 2018"

After running:
- Review the generated questions_2018.json
- Fix titles, topics, and which images belong to which question.
- Paste the whole JSON file content here so I can merge it into the master bank.

You can also edit the QUESTIONS list manually in the script before the final build step.
"""

import fitz  # pymupdf
import os
import sys
import json
import re
import argparse
from pathlib import Path
from PIL import Image
import io

try:
    import easyocr
    HAS_EASYOCR = True
except ImportError:
    HAS_EASYOCR = False

def clean_body(text):
    """Remove answer dots, clean, add spacing between subparts."""
    if not text:
        return ""
    cleaned = re.sub(r'\.{3,}\s*\[\d+\]', '', text)
    cleaned = re.sub(r'\s*\[\d+\]', '', cleaned)
    cleaned = cleaned.replace('$', '').replace('\\times', '×').replace('\\pi', 'π')
    cleaned = re.sub(r' +', ' ', cleaned)
    # Add blank lines between (a), (b), (i), etc.
    cleaned = re.sub(r'\n\((?=[a-z]\)|[ivx]+\))', r'\n\n(', cleaned)
    cleaned = re.sub(r'\n\s+\((?=[a-z]\)|[ivx]+\))', r'\n\n(', cleaned)
    cleaned = re.sub(r'\n{3,}', '\n\n', cleaned).strip()
    return cleaned

def make_title(text):
    """Create a clean stem-only title."""
    first_line = text.split('\n')[0].strip()
    title = re.sub(r'^(The diagram shows|The table shows|Given|Solve|Find|Calculate|Express|Factorise|Expand)\s*', '', first_line, flags=re.IGNORECASE)
    title = title[:65].strip()
    if len(title) > 60:
        title = title[:57] + "..."
    return title or "Untitled Question"

def guess_topic(text):
    """Very basic topic guesser - improve as needed."""
    t = text.lower()
    if any(x in t for x in ['venn', 'set', 'union', 'intersect']):
        return "Sets"
    if any(x in t for x in ['probability', 'spinner', 'fair']):
        return "Probability"
    if any(x in t for x in ['gradient', 'midpoint', 'vector', 'polygon', 'angle', 'triangle', 'circle', 'shaded', 'area']):
        return "Geometry"
    if any(x in t for x in ['matrix', 'expand', 'factorise', 'solve', 'equation', 'algebra']):
        return "Algebra"
    if any(x in t for x in ['percentage', 'standard form', 'fraction', 'estimate', 'number']):
        return "Number"
    if any(x in t for x in ['table', 'mode', 'median', 'frequency']):
        return "Statistics"
    return "Unknown"

def extract_paper(pdf_path, year, paper_name, output_dir):
    os.makedirs(output_dir, exist_ok=True)
    images_dir = os.path.join(output_dir, "images")
    pages_dir = os.path.join(output_dir, "page_previews")
    os.makedirs(images_dir, exist_ok=True)
    os.makedirs(pages_dir, exist_ok=True)

    doc = fitz.open(pdf_path)
    print(f"Processing {len(doc)} pages...")

    # 1. Extract page previews and embedded images
    all_images = []
    for page_num in range(len(doc)):
        page = doc[page_num]
        # Page preview
        pix = page.get_pixmap(dpi=120)
        preview_path = os.path.join(pages_dir, f"page_{page_num+1:03d}.png")
        pix.save(preview_path)

        # Embedded images
        for img_idx, img in enumerate(page.get_images(full=True)):
            try:
                xref = img[0]
                base = doc.extract_image(xref)
                ext = base.get("ext", "png")
                img_name = f"page{page_num+1:03d}_img{img_idx+1:02d}.{ext}"
                img_path = os.path.join(images_dir, img_name)
                with open(img_path, "wb") as f:
                    f.write(base["image"])
                all_images.append({"page": page_num+1, "name": img_name, "path": img_path})
            except:
                pass

    print(f"Extracted {len(all_images)} images and {len(doc)} page previews.")

    # 2. OCR pages
    page_texts = []
    if HAS_EASYOCR:
        print("Running OCR (easyocr)... this can take time on first run.")
        reader = easyocr.Reader(['en'], gpu=False)
        for i in range(len(doc)):
            preview = os.path.join(pages_dir, f"page_{i+1:03d}.png")
            results = reader.readtext(preview, detail=0, paragraph=True)
            page_texts.append("\n".join(results))
    else:
        print("easyocr not installed. Using placeholder text.")
        print("Install with: pip install easyocr")
        for i in range(len(doc)):
            page_texts.append(f"[OCR TEXT FOR PAGE {i+1} - PLEASE REPLACE WITH ACTUAL TEXT FROM PREVIEW]")

    doc.close()

    # 3. Simple question splitter (looks for numbers + marks)
    questions = []
    current_q = {"num": None, "text": "", "marks": 0, "page_start": 1}

    for page_idx, text in enumerate(page_texts):
        lines = text.split('\n')
        for line in lines:
            # Detect start of new question (e.g. "1.", "2 ", "Question 3")
            match = re.match(r'^\s*(\d{1,2})[\.\s]', line.strip())
            if match:
                if current_q["num"] is not None:
                    questions.append(current_q)
                current_q = {
                    "num": int(match.group(1)),
                    "text": line.strip() + "\n",
                    "marks": 0,
                    "page_start": page_idx + 1
                }
            else:
                current_q["text"] += line + "\n"

            # Detect marks
            m = re.search(r'\[(\d+)\]', line)
            if m:
                current_q["marks"] = int(m.group(1))

    if current_q["num"] is not None:
        questions.append(current_q)

    print(f"Detected {len(questions)} questions (you should verify this number).")

    # 4. Build structured entries
    structured = []
    img_index = 0
    for idx, q in enumerate(questions, 1):
        qid = f"{year}-Q{idx:02d}"
        clean_text = clean_body(q["text"])
        title = make_title(clean_text)
        topic = guess_topic(clean_text)

        # Very naive image assignment: attach next few images from this page range
        # You will edit this manually after running!
        attached = []
        for _ in range(2):  # attach up to 2 images per question by default
            if img_index < len(all_images):
                attached.append(all_images[img_index]["name"])
                img_index += 1

        entry = {
            "id": qid,
            "year": year,
            "paper": paper_name,
            "original_num": q["num"],
            "topic": topic,
            "title": title,
            "body_markdown": clean_text,
            "latex": clean_text.replace('\n', '\\n'),  # rough
            "total_marks": q.get("marks", 2),
            "images": attached
        }
        structured.append(entry)

    # 5. Save per-paper JSON
    out_file = os.path.join(output_dir, f"questions_{year}.json")
    with open(out_file, "w", encoding="utf-8") as f:
        json.dump(structured, f, indent=2, ensure_ascii=False)

    print(f"\n✅ Generated: {out_file}")
    print("IMPORTANT: Open the file and:")
    print("  - Verify question count and numbering")
    print("  - Fix titles (make them short stems)")
    print("  - Correct 'images' lists (only keep diagrams that actually belong)")
    print("  - Fix topics if wrong")
    print("  - Improve body_markdown if OCR mangled it")
    print("\nThen paste the entire content of the JSON file here so I can merge it.")

if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("pdf", help="Path to the exam PDF")
    parser.add_argument("--year", type=int, required=True, help="Year of the paper, e.g. 2018")
    parser.add_argument("--paper", default="P1", help="Paper name, e.g. 'P1 2018'")
    parser.add_argument("--out", default=None, help="Output folder (default: extracted_YYYY)")
    args = parser.parse_args()

    pdf_path = args.pdf
    year = args.year
    paper_name = args.paper
    out_dir = args.out or f"extracted_{year}"

    if not os.path.exists(pdf_path):
        print(f"PDF not found: {pdf_path}")
        sys.exit(1)

    extract_paper(pdf_path, year, paper_name, out_dir)
