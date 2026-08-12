#!/usr/bin/env python3
"""
IMPROVED Local script to generate questions.json for ONE exam paper (scanned/dark PDFs).

Key improvements (v3-level for dark scanned papers):
- Much stronger dark-image cleanup: aggressive autocontrast + thresholding
  to force pure white backgrounds and crisp black diagrams.
- Better filters and enhancement that actually works on Lesotho/ECoL scanned papers.
- Still filters tiny junk images.
- Per-page image grouping (only attaches relevant diagrams).

Run (on Windows):
    pip install pymupdf pillow easyocr
    python generate_paper_questions_v2.py "C:/Users/BrainTech Holdings/.../Maths P1 2018.pdf" --year 2018 --paper "P1 2018"

After running:
- Review the generated questions_YYYY.json
- Fix titles, topics, and "images" lists manually (most important step)
- Paste the JSON here for merge into master.

The image enhancement now happens BEFORE saving, and produces clean white-bg PNGs.
"""

import fitz  # pymupdf
import os
import sys
import json
import re
import argparse
from pathlib import Path
from PIL import Image, ImageEnhance, ImageOps, ImageFilter, ImageStat
import io

try:
    import easyocr
    HAS_EASYOCR = True
except ImportError:
    HAS_EASYOCR = False

# ====================== TUNABLE FILTERS (updated for dark scanned papers) ======================
MIN_IMAGE_WIDTH = 120
MIN_IMAGE_HEIGHT = 80
MIN_IMAGE_AREA = 15000
MIN_BRIGHTNESS = 60          # slightly higher bar

# Strong enhancement settings for scanned exam papers
ENHANCE_DARK_IMAGES = True
AUTOCONTRAST_CUTOFF = 1      # clip 1% darkest + lightest pixels
BRIGHTNESS_BOOST = 2.2
CONTRAST_BOOST = 1.85
THRESHOLD = 195              # pixels > this become pure white (key for dark backgrounds)
SHARPEN_STRENGTH = 2         # how many times to sharpen after thresholding

MAX_IMAGES_PER_QUESTION = 2
# ============================================================

def clean_scanned_diagram(img: Image.Image) -> Image.Image:
    """
    Aggressive cleanup specifically for scanned exam papers.
    Goal: pure white background + crisp black lines/text.
    """
    # Work in grayscale for best control
    gray = img.convert("L")

    # 1. Stretch the histogram (removes overall darkness)
    gray = ImageOps.autocontrast(gray, cutoff=AUTOCONTRAST_CUTOFF)

    # 2. Strong brightness & contrast boost
    enhancer = ImageEnhance.Brightness(gray)
    gray = enhancer.enhance(BRIGHTNESS_BOOST)

    enhancer = ImageEnhance.Contrast(gray)
    gray = enhancer.enhance(CONTRAST_BOOST)

    # 3. Threshold: this is the magic step that kills gray/sepia backgrounds
    # Everything above THRESHOLD becomes pure white (255), below becomes black (0)
    def make_binary(p):
        return 255 if p > THRESHOLD else 0

    binary = gray.point(make_binary, mode="L")

    # 4. Sharpen to recover fine lines after thresholding
    for _ in range(SHARPEN_STRENGTH):
        binary = binary.filter(ImageFilter.SHARPEN)

    # 5. Convert to RGB (white bg + black ink) for clean saving
    rgb = Image.merge("RGB", (binary, binary, binary))
    return rgb

def is_likely_question_image(img_path):
    """Return True if the image looks like a useful diagram/table/graph."""
    try:
        with Image.open(img_path) as im:
            w, h = im.size
            area = w * h
            if w < MIN_IMAGE_WIDTH or h < MIN_IMAGE_HEIGHT or area < MIN_IMAGE_AREA:
                return False, "too_small"

            gray = im.convert("L")
            stat = ImageStat.Stat(gray)
            brightness = stat.mean[0]

            if brightness < MIN_BRIGHTNESS or ENHANCE_DARK_IMAGES:
                # Always run the strong cleanup for scanned papers
                cleaned = clean_scanned_diagram(im)
                cleaned.save(img_path.with_suffix(".png"), "PNG", optimize=True)
                # remove original if it had different extension
                if img_path.suffix.lower() != ".png":
                    try:
                        img_path.unlink()
                    except:
                        pass
                return True, "enhanced_clean_white_bg"

            return True, "ok"
    except Exception as e:
        return False, f"error:{e}"

def clean_body(text):
    if not text:
        return ""
    cleaned = re.sub(r'\.{3,}\s*\[\d+\]', '', text)
    cleaned = re.sub(r'\s*\[\d+\]', '', cleaned)
    cleaned = cleaned.replace('$', '').replace('\\times', '×').replace('\\pi', 'π')
    cleaned = re.sub(r' +', ' ', cleaned)
    cleaned = re.sub(r'\n\((?=[a-z]\)|[ivx]+\))', r'\n\n(', cleaned)
    cleaned = re.sub(r'\n\s+\((?=[a-z]\)|[ivx]+\))', r'\n\n(', cleaned)
    cleaned = re.sub(r'\n{3,}', '\n\n', cleaned).strip()
    cleaned = re.sub(r'0?ECoL\s*\d{4}', '', cleaned)
    cleaned = re.sub(r'0178/\d{2}/[A-Za-z/]+\d{2}', '', cleaned, flags=re.IGNORECASE)
    cleaned = re.sub(r'\[Turn over\]', '', cleaned, flags=re.IGNORECASE)
    cleaned = re.sub(r'NOT\s*TO\s*SCALE', '', cleaned, flags=re.IGNORECASE)
    cleaned = re.sub(r'©\s*ECoL.*', '', cleaned, flags=re.IGNORECASE)
    return cleaned.strip()

def make_clean_title(text):
    first_line = text.split('\n')[0].strip()
    first_line = re.sub(r'^\d+\s*', '', first_line)
    title = re.sub(r'^(The diagram shows|The table shows|Given|Solve|Find|Calculate|Express|Factorise|Expand|Work out|Write down)\s*', '', first_line, flags=re.IGNORECASE)
    title = title[:70].strip()
    if len(title) > 65:
        title = title[:62] + "..."
    return title or "Untitled Question"

def guess_topic(text):
    t = text.lower()
    if any(x in t for x in ['venn', 'set notation', 'union', 'intersect', 'a ∩', 'a ∪']):
        return "Sets"
    if any(x in t for x in ['probability', 'spinner', 'card', 'chosen at random', 'fair']):
        return "Probability"
    if any(x in t for x in ['gradient', 'midpoint', 'vector', 'polygon', 'angle', 'triangle', 'circle', 'shaded', 'area', 'isosceles', 'perimeter', 'ring']):
        return "Geometry"
    if any(x in t for x in ['matrix', 'expand', 'factorise', 'solve', 'equation', 'algebra', 'function', 'f(x)']):
        return "Algebra"
    if any(x in t for x in ['percentage', 'standard form', 'fraction', 'estimate', 'prime', 'irrational', 'square number', 'ratio', 'speed', 'km/h', 'time']):
        return "Number"
    if any(x in t for x in ['table', 'mode', 'median', 'frequency', 'pie chart', 'row number', 'pattern of numbers']):
        return "Statistics"
    return "Unknown"

def extract_paper(pdf_path, year, paper_name, output_dir):
    os.makedirs(output_dir, exist_ok=True)
    images_dir = os.path.join(output_dir, "images")
    pages_dir = os.path.join(output_dir, "page_previews")
    os.makedirs(images_dir, exist_ok=True)
    os.makedirs(pages_dir, exist_ok=True)

    doc = fitz.open(pdf_path)
    print(f"Processing {len(doc)} pages from {pdf_path}...")

    page_good_images = {}

    for page_num in range(len(doc)):
        page = doc[page_num]
        pix = page.get_pixmap(dpi=150)   # higher dpi helps diagrams
        preview_path = os.path.join(pages_dir, f"page_{page_num+1:03d}.png")
        pix.save(preview_path)

        page_good_images[page_num] = []

        for img_idx, img in enumerate(page.get_images(full=True)):
            try:
                xref = img[0]
                base = doc.extract_image(xref)
                ext = base.get("ext", "png")
                img_name = f"page{page_num+1:03d}_img{img_idx+1:02d}.{ext}"
                img_path = Path(images_dir) / img_name
                with open(img_path, "wb") as f:
                    f.write(base["image"])

                keep, reason = is_likely_question_image(img_path)
                if keep:
                    page_good_images[page_num].append(str(img_path.name))
                    if "enhanced" in reason:
                        print(f"  Cleaned dark image → white background: {img_path.name}")
                else:
                    try:
                        img_path.unlink()
                    except:
                        pass
            except:
                pass

    print(f"Kept {sum(len(v) for v in page_good_images.values())} useful images after strong cleanup.")

    # OCR section unchanged
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

    # Question detection (same as before)
    questions = []
    current_q = {"num": None, "text": "", "marks": 0, "page": 0}

    for page_idx, text in enumerate(page_texts):
        lines = text.split('\n')
        for line in lines:
            match = re.match(r'^\s*(\d{1,2})[\.\s]', line.strip())
            if match:
                if current_q["num"] is not None:
                    questions.append(current_q)
                current_q = {
                    "num": int(match.group(1)),
                    "text": line.strip() + "\n",
                    "marks": 0,
                    "page": page_idx
                }
            else:
                current_q["text"] += line + "\n"

            m = re.search(r'\[(\d+)\]', line)
            if m:
                current_q["marks"] = int(m.group(1))

    if current_q["num"] is not None:
        questions.append(current_q)

    print(f"Detected {len(questions)} questions (verify this number yourself).")

    structured = []
    used_images = set()

    for idx, q in enumerate(questions, 1):
        qid = f"{year}-Q{idx:02d}"
        clean_text = clean_body(q["text"])
        title = make_clean_title(clean_text)
        topic = guess_topic(clean_text)

        page_imgs = page_good_images.get(q["page"], []) + page_good_images.get(q["page"]+1, [])
        attached = []
        for img in page_imgs:
            if img not in used_images and len(attached) < MAX_IMAGES_PER_QUESTION:
                attached.append(img)
                used_images.add(img)

        entry = {
            "id": qid,
            "year": year,
            "paper": paper_name,
            "original_num": q["num"],
            "topic": topic,
            "title": title,
            "body_markdown": clean_text,
            "latex": clean_text.replace('\n', '\\n'),
            "total_marks": q.get("marks", 2),
            "images": attached
        }
        structured.append(entry)

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
    parser = argparse.ArgumentParser(description="Improved question extractor for scanned exam papers (strong white-bg cleanup)")
    parser.add_argument("pdf", help="Path to the exam PDF")
    parser.add_argument("--year", type=int, required=True, help="Exam year (e.g. 2018)")
    parser.add_argument("--paper", default="P1", help="Paper identifier (e.g. 'P1 2018')")
    parser.add_argument("--out", default=None, help="Output folder name")
    args = parser.parse_args()

    out_dir = args.out or f"extracted_{args.year}"
    extract_paper(args.pdf, args.year, args.paper, out_dir)
