#!/usr/bin/env python3
"""
Enhanced generate_paper.py for Khanya Test Maker
- Clean titles and no branding
- Sequential numbering
- No dotted dashes and no blank working space
- Improved math display: unicode superscripts for indices, bolder fraction bars
- Extra spacing between sub-parts (a), (b), (i), etc.
- Supports PDF (reportlab) and Word .docx (python-docx)
- Custom paper title supported
"""

import argparse
import json
import random
import re
from pathlib import Path
from io import BytesIO

from reportlab.lib.pagesizes import A4
from reportlab.lib.units import cm, mm
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, Image, HRFlowable
from reportlab.lib.enums import TA_LEFT, TA_CENTER, TA_JUSTIFY
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.pdfgen import canvas as pdfcanvas

try:
    pdfmetrics.registerFont(TTFont('DejaVu', '/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf'))
    pdfmetrics.registerFont(TTFont('DejaVuBold', '/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf'))
    MAIN_FONT = 'DejaVu'
    BOLD_FONT = 'DejaVuBold'
except:
    MAIN_FONT = 'Helvetica'
    BOLD_FONT = 'Helvetica-Bold'

# Optional Word support
try:
    from docx import Document
    from docx.shared import Pt, Inches, Cm, RGBColor
    from docx.enum.text import WD_ALIGN_PARAGRAPH
    from docx.oxml import OxmlElement
    from docx.oxml.ns import qn
    HAS_DOCX = True
except ImportError:
    HAS_DOCX = False

BASE_DIR = Path(__file__).parent
IMAGES_DIR = BASE_DIR / "assets" / "images"

# Per-subject data paths are derived dynamically from the subject name.
# This matches the folder structure used by the frontend (js/app.js getSubjectDataPath).
# Adding a new subject in the UI + creating subjects/<folder>/data/questions.json
# will automatically work on the backend without code changes.
def get_subject_data_path(subject="Mathematics"):
    """Return the questions.json path for the given subject (case sensitive as in UI)."""
    if not subject:
        subject = "Mathematics"
    folder = subject.lower().replace(" ", "_")
    return BASE_DIR / "subjects" / folder / "data" / "questions.json"


def load_questions(subject="Mathematics"):
    """Load questions for a specific subject (supports per-subject data)."""
    path = get_subject_data_path(subject)
    if not path.exists():
        print(f"Warning: No questions file for {subject} at {path}. Using empty list.")
        return []
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)




def get_question_by_id(qid, questions):
    for q in questions:
        if q["id"] == qid:
            return q
    return None


def pretty_math(text):
    """Improve display of indices, matrices, and fraction bars."""
    if not text:
        return text

    # Unicode superscripts for powers/indices (0-9)
    sup_map = str.maketrans("0123456789", "⁰¹²³⁴⁵⁶⁷⁸⁹")
    text = re.sub(r'\^(\d+)', lambda m: m.group(1).translate(sup_map), text)

    # Make fraction division lines look bolder (text representation)
    text = text.replace('────────────', '════════════════════')
    text = text.replace('──────', '══════════')
    text = text.replace('────────', '════════════')

    # Minor matrix improvement for readability (keeps it simple)
    text = re.sub(r'\((\d+)\s+(\d+)\s*;\s*(\d+)\s+(\d+)\)', r'⎛\1  \2⎞\n⎝\3  \4⎠', text)

    return text


# Sub-question labels: (a), (b), (i), (ii) …
# Function notation like h(x) or g(x) has a letter immediately before '(' and must not split.
_SUBQ_SPLIT = re.compile(r'(?=(?<![A-Za-z0-9])\((?:[a-z]|[ivx]+)\)(?:\s|$))')
_SUBQ_START = re.compile(r'^\((?:[a-z]|[ivx]+)\)(?:\s|$)')


def split_subquestions(body):
    """Break on (a)/(i) parts only. Keep h(x), g(x) on the same line."""
    if not body:
        return []
    return [p for p in (part.strip() for part in _SUBQ_SPLIT.split(body)) if p]


def is_subquestion_part(text):
    return bool(text and _SUBQ_START.match(text.strip()))


def clean_body_for_pdf(body):
    """Remove dotted answer lines and prepare clean text for display."""
    if not body:
        return ""
    cleaned = body
    cleaned = re.sub(r'\.{3,}', '', cleaned)          # remove all long dots/dashes
    cleaned = re.sub(r'\s*\[\d+\]', '', cleaned)      # remove [n] marks
    cleaned = cleaned.replace('$', '').replace('\\times', '×').replace('\\pi', 'π')
    cleaned = cleaned.replace('\\', '')
    cleaned = re.sub(r' +', ' ', cleaned)
    cleaned = re.sub(r'\n{3,}', '\n\n', cleaned).strip()
    cleaned = pretty_math(cleaned)
    return cleaned


def build_latex_document(selected_questions, title="Test Paper"):
    """Optional LaTeX output (unchanged structure)."""
    latex = r"""\documentclass[11pt,a4paper]{article}
\usepackage[margin=1.5cm]{geometry}
\usepackage{amsmath,amssymb}
\usepackage{enumitem}
\usepackage{graphicx}
\usepackage{fancyhdr}
\pagestyle{fancy}
\fancyhf{}
\rhead{\small }
\lhead{\small }
\title{\textbf{""" + title + r"""}}
\date{}
\begin{document}
\maketitle
\noindent\textbf{Instructions:} Answer all questions. Show your working where required.

\vspace{0.5cm}
"""
    for idx, q in enumerate(selected_questions, 1):
        latex += f"\n\\noindent\\textbf{{{idx}. {q['title']}}} \\hfill [{q['total_marks']} marks]\n\n"
        latex += q['latex'] + "\n\n"
        for img in q.get("images", []):
            latex += f"\\begin{{center}}\\includegraphics[width=0.65\\textwidth]{{assets/images/{img}}}\\end{{center}}\n\\vspace{{0.2cm}}\n"
        latex += "\\vspace{0.4cm}\n"
    latex += r"\end{document}"
    return latex



class NumberedCanvas(pdfcanvas.Canvas):
    """Canvas that writes 'Page X of Y' at the bottom centre of every page."""

    def __init__(self, *args, **kwargs):
        pdfcanvas.Canvas.__init__(self, *args, **kwargs)
        self._saved_page_states = []

    def showPage(self):
        self._saved_page_states.append(dict(self.__dict__))
        self._startPage()

    def save(self):
        page_count = len(self._saved_page_states)
        for state in self._saved_page_states:
            self.__dict__.update(state)
            self._draw_page_number(page_count)
            pdfcanvas.Canvas.showPage(self)
        pdfcanvas.Canvas.save(self)

    def _draw_page_number(self, page_count):
        self.setFont(MAIN_FONT, 9)
        self.setFillColorRGB(0.25, 0.25, 0.25)
        page = self._pageNumber
        self.drawCentredString(A4[0] / 2.0, 1.15 * cm, f"Page {page} of {page_count}")


def build_pdf(selected_questions, title="Test Paper"):
    """Print-ready PDF: A4, generous margins, page numbers, no workings space."""
    buf = BytesIO()
    # Print-friendly A4 margins (room for binding / hole punch + footer)
    doc = SimpleDocTemplate(
        buf, pagesize=A4,
        leftMargin=2.0*cm,
        rightMargin=2.0*cm,
        topMargin=2.0*cm,
        bottomMargin=2.2*cm,
    )
    styles = getSampleStyleSheet()
    q_style = ParagraphStyle('Q', fontName=BOLD_FONT, fontSize=11, spaceBefore=10, spaceAfter=4)
    body_style = ParagraphStyle('Body', fontName=MAIN_FONT, fontSize=10, leading=14, spaceAfter=2, alignment=TA_LEFT)

    story = []
    # No title, no instructions. Page numbers are drawn by NumberedCanvas.
    story.append(Spacer(1, 2*mm))

    for idx, q in enumerate(selected_questions, 1):
        story.append(Paragraph(f"<b>{idx}.</b>  <font color='#15803d'>[{q['total_marks']} marks]</font>", q_style))

        body = clean_body_for_pdf(q.get('body_markdown', q.get('latex', '')))

        # Split on real sub-parts (a), (b), (i) — never on function notation h(x)
        parts = split_subquestions(body)
        if not parts:
            parts = [body] if body else []
        for part in parts:
            para_text = part.replace('\n', '<br/>')
            # Word joiner so ReportLab will not wrap between h and (x)
            para_text = re.sub(r'([A-Za-z])\(', r'\1&#8288;(', para_text)
            story.append(Paragraph(para_text, body_style))

            if is_subquestion_part(part):
                story.append(Spacer(1, 3*mm))

        # Images (only attached ones, properly scaled)
        for img_name in q.get("images", []):
            p = IMAGES_DIR / img_name
            if p.exists():
                try:
                    story.append(Spacer(1, 2*mm))
                    img = Image(str(p))
                    max_w = 11 * cm
                    max_h = 8 * cm
                    if img.imageWidth > 0 and img.imageHeight > 0:
                        scale = min(max_w / img.imageWidth, max_h / img.imageHeight)
                        img.drawWidth = img.imageWidth * scale
                        img.drawHeight = img.imageHeight * scale
                    else:
                        img.drawWidth = max_w
                        img.drawHeight = max_h
                    story.append(img)
                    story.append(Spacer(1, 2*mm))
                except Exception as e:
                    print(f"Warning: could not add image {img_name}: {e}")
                    pass

        # Modest gap before the next question (not working space)
        story.append(Spacer(1, 8*mm))

    doc.build(story, canvasmaker=NumberedCanvas)
    buf.seek(0)
    return buf.getvalue()


def _add_docx_page_number(paragraph):
    """Insert a PAGE field so Word shows page numbers when printed."""
    run = paragraph.add_run()

    def _fld(char_type):
        el = OxmlElement("w:fldChar")
        el.set(qn("w:fldCharType"), char_type)
        return el

    begin = _fld("begin")
    instr = OxmlElement("w:instrText")
    instr.set(qn("xml:space"), "preserve")
    instr.text = " PAGE "
    end = _fld("end")

    run._r.append(begin)
    run._r.append(instr)
    run._r.append(end)


def build_docx(selected_questions, title="Test Paper"):
    """Word document export with print margins, no workings space."""
    if not HAS_DOCX:
        raise ImportError("python-docx is not installed. Please run: pip install python-docx")

    doc = Document()

    # Print-friendly A4-style margins
    for section in doc.sections:
        section.page_width = Cm(21.0)
        section.page_height = Cm(29.7)
        section.top_margin = Cm(2.0)
        section.bottom_margin = Cm(2.0)
        section.left_margin = Cm(2.0)
        section.right_margin = Cm(2.0)
        footer = section.footer
        footer.is_linked_to_previous = False
        fp = footer.paragraphs[0] if footer.paragraphs else footer.add_paragraph()
        fp.alignment = WD_ALIGN_PARAGRAPH.CENTER
        run = fp.add_run("Page ")
        run.font.size = Pt(9)
        run.font.color.rgb = RGBColor(80, 80, 80)
        _add_docx_page_number(fp)
        run = fp.add_run()
        run.font.size = Pt(9)

    # Title
    p = doc.add_paragraph()
    run = p.add_run(title)
    run.bold = True
    run.font.size = Pt(16)
    p.alignment = WD_ALIGN_PARAGRAPH.CENTER

    # No instructions (per request)
    doc.add_paragraph()  # breathing space

    for idx, q in enumerate(selected_questions, 1):
        # Question header
        p = doc.add_paragraph()
        run = p.add_run(f"{idx}.")
        run.bold = True
        run.font.size = Pt(11)
        run = p.add_run(f"   [{q['total_marks']} marks]")
        run.font.size = Pt(10)
        run.font.color.rgb = RGBColor(21, 128, 61)   # emerald green

        # Body text with improvements
        body = clean_body_for_pdf(q.get('body_markdown', q.get('latex', '')))

        # Add paragraphs with extra space after sub-parts
        for line in body.split('\n'):
            line = line.strip()
            if not line:
                continue
            p = doc.add_paragraph(line)
            p.paragraph_format.space_after = Pt(3)

            if is_subquestion_part(line):
                p.paragraph_format.space_after = Pt(6)   # extra space between (a), (b), etc.

        # Images
        for img_name in q.get("images", []):
            pth = IMAGES_DIR / img_name
            if pth.exists():
                try:
                    doc.add_picture(str(pth), width=Inches(4.5))
                    doc.add_paragraph()
                except Exception as e:
                    print(f"Warning: could not add image to docx {img_name}: {e}")

        # Modest gap before the next question (not working space)
        gap = doc.add_paragraph()
        gap.paragraph_format.space_after = Pt(10)

    # Return as bytes
    buf = BytesIO()
    doc.save(buf)
    buf.seek(0)
    return buf.getvalue()


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--ids")
    parser.add_argument("--random", action="store_true")
    parser.add_argument("--num", type=int, default=6)
    parser.add_argument("--output", default="paper")
    parser.add_argument("--latex-only", action="store_true")
    parser.add_argument("--title", default="Test Paper")
    parser.add_argument("--subject", default="Mathematics",
                        help="Subject name e.g. Mathematics, Biology, Physics (matches UI)")
    parser.add_argument("--format", choices=["pdf", "docx"], default="pdf",
                        help="Output format: pdf or docx (default: pdf)")
    args = parser.parse_args()

    qs = load_questions(args.subject)
    sel = []
    if args.ids:
        for i in args.ids.split(","):
            q = get_question_by_id(i.strip(), qs)
            if q:
                sel.append(q)
    elif args.random:
        sel = random.sample(qs, min(args.num, len(qs)))

    if not sel:
        print("No questions selected")
        return

    # Always write LaTeX (for reference)
    tex = build_latex_document(sel, title=args.title)
    Path(args.output).with_suffix(".tex").write_text(tex, encoding="utf-8")
    print("LaTeX written")

    if args.format == "docx":
        if not HAS_DOCX:
            print("Error: python-docx not installed. Run: pip install python-docx")
            return
        docx_bytes = build_docx(sel, title=args.title)
        out_path = Path(args.output).with_suffix(".docx")
        out_path.write_bytes(docx_bytes)
        print("Word document written")
    else:
        # PDF (default)
        pdfb = build_pdf(sel, title=args.title)
        Path(args.output).with_suffix(".pdf").write_bytes(pdfb)
        print("PDF written")

    print("Done with", len(sel), "questions")


if __name__ == "__main__":
    main()
