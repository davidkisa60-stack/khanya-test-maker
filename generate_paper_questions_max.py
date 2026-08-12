#!/usr/bin/env python3
"""
MAX-RECALL Question Extractor for Scanned Exam Papers (ECoL / Lesotho style)

Goal: Extract AS MANY QUESTIONS AS POSSIBLE from a single paper.
- Extremely relaxed / almost no filtering on text blocks.
- Images are dumped completely unfiltered (you will crop/assign manually later).
- Every question entry gets "images": [] (empty list) so you can fill them by hand.
- Heavy per-page fallback: if OCR/text splitting is weak on a page, we still create entries.
- Designed for papers where normal scripts only recover 8/14 or 10/19 questions.

This is the script to use when you need "all questions first, images later".

REQUIREMENTS (run once on your Windows machine):
    pip install pymupdf pillow easyocr

USAGE (example for a 14-question paper):
    python generate_paper_questions_max.py "C:\Users\BrainTech Holdings\Downloads\Maths P2 2021.pdf" --year 2021 --paper "P2 2021"

What you get:
- A folder like extracted_Maths_P2_2021/
  - page_previews/          ← high-res pages for you to read
  - all_raw_images/         ← EVERY image extracted from the PDF (no size filter)
  - questions_2021.json     ← the JSON with as many entries as we could find
- Open the page_previews to read the real questions.
- Edit the questions_2021.json:
    - Clean/fix titles and body_markdown (OCR will be imperfect).
    - Fill in "images": ["page003_img01.png", ...] from the all_raw_images folder.
    - Add proper topics and marks.
- Then paste the cleaned array here so I can merge it into the master.

Key philosophy of this script:
- We would rather output 14 slightly messy entries than miss 6 questions.
- Images are never the reason a question is dropped.
- You do the final quality control + image assignment (you said you prefer this anyway).

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
    print("WARNING: easyocr not installed. Text extraction will be limited to embedded text (worse for scanned papers).")
    print("         Run: pip install easyocr  (then re-run this script)")

# ====================== MAX-RECALL SETTINGS (very permissive) ======================
# We deliberately do NOT filter images aggressively here.
# We want every possible diagram/table/graph so you can assign them later.

# Text / question detection is also very loose
MIN_TEXT_BLOCK_LENGTH = 20          # very small blocks still count
QUESTION_NUMBER_PATTERNS = [
    r'^\s*(\d{1,2})[\.\)]\s',       # 1. or 1)
    r'^\s*Q?\s*(\d{1,2})\s',        # Q1 or 1 
    r'^\s*(\d{1,2})\s+[A-Z]',       # 1 The diagram...
]

# If a page produces fewer than this many questions, we do aggressive fallback
MIN_QUESTIONS_PER_PAGE_FALLBACK = 1

# Image extraction: almost no filtering (user will curate)
SAVE_EVERY_IMAGE = True
MIN_IMAGE_AREA_FOR_SAVING = 300     # tiny icons still saved — you can ignore them

# OCR settings (only used if easyocr is available)
OCR_LANGUAGES = ['en']
OCR_GPU = False                     # set to True if you have a good GPU

# Output folder naming
# ================================================================================

def get_ocr_reader():
    if not HAS_EASYOCR:
        return None
    try:
        print("Loading easyocr (this can take 10-30 seconds the first time)...")
        reader = easyocr.Reader(OCR_LANGUAGES, gpu=OCR_GPU)
        print("easyocr ready.")
        return reader
    except Exception as e:
        print(f"Failed to load easyocr: {e}")
        return None

def ocr_page(page, reader, dpi=200):
    """Render page at good resolution and OCR it."""
    if reader is None:
        return ""
    pix = page.get_pixmap(dpi=dpi)
    img_bytes = pix.tobytes("png")
    try:
        results = reader.readtext(img_bytes, detail=0, paragraph=True)
        return "\n".join(results)
    except Exception as e:
        print(f"  OCR error on page: {e}")
        return ""

def extract_text_blocks(page):
    """Get text blocks from pymupdf (fast, no OCR)."""
    blocks = []
    for b in page.get_text("blocks"):
        text = b[4].strip()
        if len(text) >= MIN_TEXT_BLOCK_LENGTH:
            blocks.append(text)
    return blocks

def is_question_start(line):
    """Very permissive check for start of a new question."""
    line = line.strip()
    if not line:
        return False
    for pattern in QUESTION_NUMBER_PATTERNS:
        if re.match(pattern, line):
            return True
    # Also catch lines that start with a number followed by capital or common words
    if re.match(r'^\s*\d{1,2}\s+[A-Z]', line):
        return True
    return False

def split_into_questions(page_text, page_num):
    """
    Extremely relaxed splitter.
    Returns list of (question_number_or_None, raw_text) tuples.
    """
    lines = page_text.splitlines()
    questions = []
    current_num = None
    current_text = []

    for line in lines:
        if is_question_start(line):
            # Save previous question if we have one
            if current_text:
                questions.append((current_num, "\n".join(current_text).strip()))
            # Start new
            match = re.search(r'(\d{1,2})', line)
            current_num = int(match.group(1)) if match else None
            current_text = [line]
        else:
            current_text.append(line)

    # Don't forget the last one
    if current_text:
        questions.append((current_num, "\n".join(current_text).strip()))

    # If we got almost nothing, treat the whole page as one big entry
    if len(questions) < MIN_QUESTIONS_PER_PAGE_FALLBACK and page_text.strip():
        # Try to guess a number from the page
        guess = None
        m = re.search(r'(\d{1,2})[\.\)]', page_text[:200])
        if m:
            guess = int(m.group(1))
        questions = [(guess, page_text.strip())]

    return questions

def clean_body(raw):
    """Light cleaning — user will do the heavy lifting."""
    if not raw:
        return ""
    text = raw
    # Remove common exam junk (very light)
    text = re.sub(r'^\s*\d{1,2}\s*/\s*\d{1,2}\s*/\s*O?N?/\s*\d{2}.*$', '', text, flags=re.MULTILINE)
    text = re.sub(r'\[Turn over\]', '', text, flags=re.IGNORECASE)
    text = re.sub(r'0\s*ECoL.*$', '', text, flags=re.IGNORECASE)
    text = re.sub(r'\n{3,}', '\n\n', text)
    text = text.strip()
    return text

def make_title(raw):
    """Best-effort short title from first meaningful line."""
    lines = [l.strip() for l in raw.splitlines() if l.strip()]
    if not lines:
        return "Untitled Question"
    first = lines[0]
    # Strip leading number
    first = re.sub(r'^\s*\d{1,2}[\.\)]?\s*', '', first)
    # Take first ~70 chars
    title = first[:70].strip()
    if len(first) > 70:
        title += "..."
    return title or "Untitled Question"

def guess_topic(raw):
    t = raw.lower()
    if any(x in t for x in ['chord', 'circle', 'parallel', 'midpoint', 'vector', 'polygon', 'prism', 'rhombus', 'kite', 'bearing', 'sector']):
        return "Geometry"
    if any(x in t for x in ['function', 'composite', 'linear programming', 'inequality', 'solve', 'factorise', 'expand']):
        return "Algebra"
    if any(x in t for x in ['probability', 'bag', 'ball', 'spinner']):
        return "Probability"
    if any(x in t for x in ['speed', 'time', 'graph', 'distance']):
        return "Number"
    if any(x in t for x in ['range', 'median', 'mode', 'frequency']):
        return "Statistics"
    if any(x in t for x in ['surd', 'root', '√']):
        return "Surds"
    return "Unknown"

def extract_all_images_unfiltered(doc, output_images_dir):
    """Dump EVERY image in the PDF with no meaningful filtering."""
    os.makedirs(output_images_dir, exist_ok=True)
    saved = []
    for page_num in range(len(doc)):
        page = doc[page_num]
        for img_idx, img in enumerate(page.get_images(full=True)):
            xref = img[0]
            try:
                base = doc.extract_image(xref)
                image_bytes = base["image"]
                ext = base.get("ext", "png")
                name = f"page{page_num+1:03d}_img{img_idx+1:02d}.{ext}"
                path = os.path.join(output_images_dir, name)
                with open(path, "wb") as f:
                    f.write(image_bytes)
                saved.append(name)
            except Exception:
                pass
    return saved

def main():
    parser = argparse.ArgumentParser(description="MAX-RECALL question extractor")
    parser.add_argument("pdf_path", help="Path to the exam PDF")
    parser.add_argument("--year", type=int, required=True, help="Exam year (e.g. 2021)")
    parser.add_argument("--paper", required=True, help='Paper label (e.g. "P2 2021")')
    parser.add_argument("--out", default=None, help="Output folder name (default: auto)")
    args = parser.parse_args()

    pdf_path = Path(args.pdf_path)
    if not pdf_path.exists():
        print(f"ERROR: PDF not found: {pdf_path}")
        sys.exit(1)

    year = args.year
    paper_label = args.paper

    base_name = pdf_path.stem.replace(" ", "_")
    out_dir = args.out or f"extracted_{base_name}"
    out_dir = Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)

    previews_dir = out_dir / "page_previews"
    images_dir = out_dir / "all_raw_images"
    previews_dir.mkdir(exist_ok=True)
    images_dir.mkdir(exist_ok=True)

    print(f"\n=== MAX-RECALL EXTRACTOR ===")
    print(f"PDF: {pdf_path}")
    print(f"Year: {year}   Paper: {paper_label}")
    print(f"Output folder: {out_dir}\n")

    doc = fitz.open(str(pdf_path))
    print(f"Total pages: {len(doc)}")

    reader = get_ocr_reader()

    all_questions = []
    question_counter = 1

    for page_num in range(len(doc)):
        page = doc[page_num]

        # 1. Always save a readable page preview
        pix = page.get_pixmap(dpi=150)
        preview_path = previews_dir / f"page_{page_num+1:03d}.png"
        pix.save(str(preview_path))

        # 2. Get text (OCR first, fallback to embedded)
        page_text = ""
        if reader:
            page_text = ocr_page(page, reader)
        if not page_text.strip():
            page_text = "\n".join(extract_text_blocks(page))

        # 3. Split into questions (very permissive)
        q_blocks = split_into_questions(page_text, page_num)

        print(f"Page {page_num+1}: detected {len(q_blocks)} question block(s)")

        for orig_num, raw in q_blocks:
            body = clean_body(raw)
            if len(body) < 15:          # still too tiny? keep it anyway
                body = raw.strip()

            title = make_title(raw)
            topic = guess_topic(raw)

            q = {
                "id": f"{year}-Q{question_counter:02d}",
                "year": year,
                "paper": paper_label,
                "original_num": orig_num if orig_num else question_counter,
                "topic": topic,
                "title": title,
                "body_markdown": body,
                "latex": "",
                "total_marks": 0,           # you will fill this
                "images": [],               # YOU will fill these from all_raw_images/
                "_page": page_num + 1,
                "_raw_ocr": raw[:300] + "..." if len(raw) > 300 else raw   # for your reference
            }
            all_questions.append(q)
            question_counter += 1

    # 4. Extract ALL images with almost zero filtering
    print("\nExtracting every image from the PDF (no aggressive filtering)...")
    all_img_names = extract_all_images_unfiltered(doc, str(images_dir))
    print(f"Saved {len(all_img_names)} raw images to {images_dir}")

    doc.close()

    # 5. Write the JSON (max questions, empty images)
    json_path = out_dir / f"questions_{year}.json"
    with open(json_path, "w", encoding="utf-8") as f:
        json.dump(all_questions, f, indent=2, ensure_ascii=False)

    print(f"\n=== EXTRACTION COMPLETE ===")
    print(f"Generated {len(all_questions)} question entries (aiming for close to actual count).")
    print(f"JSON: {json_path}")
    print(f"Page previews (for reading): {previews_dir}")
    print(f"All raw images (assign manually): {images_dir}")
    print("\nNEXT STEPS:")
    print("1. Open the page_previews folder and read the real paper.")
    print("2. Edit the questions_YYYY.json:")
    print("   - Fix/improve titles and body_markdown (OCR is never perfect).")
    print("   - Set realistic total_marks for each question.")
    print("   - Fill 'images' arrays using files from all_raw_images/ (you crop/choose).")
    print("   - Improve topics if the guesser was wrong.")
    print("3. Paste the final cleaned JSON array here so I can merge it.")
    print("\nThis script deliberately over-generates entries rather than missing questions.")
    print("You now have the raw material — the quality control is in your hands (as preferred).")

if __name__ == "__main__":
    main()