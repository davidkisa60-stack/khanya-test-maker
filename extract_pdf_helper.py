#!/usr/bin/env python3
"""
Local extraction helper for Windows users.
Run this on your machine with the PDF.

Requirements:
pip install pymupdf pillow

It will:
- Extract all embedded images (diagrams, tables, graphs)
- Render full page previews (for you to read/OCR the text)
- Organize by page

Then, you can transcribe the questions while looking at the pages and images.
"""

import fitz
from PIL import Image
import os
import sys

def extract_from_pdf(pdf_path, output_folder):
    os.makedirs(output_folder, exist_ok=True)
    images_dir = os.path.join(output_folder, "images")
    pages_dir = os.path.join(output_folder, "page_previews")
    os.makedirs(images_dir, exist_ok=True)
    os.makedirs(pages_dir, exist_ok=True)

    doc = fitz.open(pdf_path)
    print(f"Processing {len(doc)} pages from {pdf_path}")

    total_images = 0
    for page_num in range(len(doc)):
        page = doc[page_num]
        
        # Render page preview (good for reading)
        pix = page.get_pixmap(dpi=120)
        page_img = os.path.join(pages_dir, f"page_{page_num+1:03d}.png")
        pix.save(page_img)
        
        # Extract embedded images
        for img_idx, img in enumerate(page.get_images(full=True)):
            xref = img[0]
            try:
                base_image = doc.extract_image(xref)
                image_bytes = base_image["image"]
                ext = base_image.get("ext", "png")
                img_name = f"page{page_num+1:03d}_img{img_idx+1:02d}.{ext}"
                img_path = os.path.join(images_dir, img_name)
                with open(img_path, "wb") as f:
                    f.write(image_bytes)
                total_images += 1
            except:
                pass
        
        if (page_num + 1) % 5 == 0:
            print(f"  Processed page {page_num+1}/{len(doc)}")

    doc.close()
    print(f"\nDone!")
    print(f"- Page previews: {pages_dir}")
    print(f"- Extracted images: {images_dir} ({total_images} files)")
    print("\nNext: Open the page_previews to read the questions.")
    print("Note which images belong to which question, and transcribe the text + marks.")

if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("Usage: python extract_pdf.py "path/to/your.pdf"")
        sys.exit(1)
    pdf = sys.argv[1]
    out = "extracted_" + os.path.splitext(os.path.basename(pdf))[0]
    extract_from_pdf(pdf, out)
