#!/usr/bin/env python3
"""
Build structured data for the math paper website.
Parses extracted questions, improves LaTeX, copies images, outputs JSON + assets.
"""

import os
import json
import shutil
import re
from pathlib import Path

SOURCE_DIR = "/home/user/extracted_questions"
OUTPUT_DIR = "/home/user/math_paper_site"
DATA_DIR = os.path.join(OUTPUT_DIR, "data")
ASSETS_DIR = os.path.join(OUTPUT_DIR, "assets", "images")
os.makedirs(DATA_DIR, exist_ok=True)
os.makedirs(ASSETS_DIR, exist_ok=True)

TOPICS = ["Number", "Algebra", "Geometry", "Sets", "Probability", "Statistics"]

# Improved clean LaTeX bodies for each question (proper LaTeX for MathJax / pdflatex)
# These are fragments that can be wrapped in \begin{enumerate} or sections in a paper.
IMPROVED_LATEX = {
    "01": r"""Evaluate
\begin{enumerate}[label=(\alph*)]
\item 20\% of M450.
\item $0.5 \div \dfrac{2}{3}$.
\item $64^{1/3}$.
\end{enumerate}""",
    "02": r"""Express 36 seconds as a fraction of an hour in its simplest form.""",
    "03": r"""$A = 3.2 \times 10^{3}$ and $B = 2.4 \times 10^{2}$.

Work out, leaving the answer in standard form.
\begin{enumerate}[label=(\alph*)]
\item $2B$.
\item $A - B$.
\end{enumerate}""",
    "04": r"""Estimate the value of
\[\dfrac{36.88 \times 2.87}{1.56^{2}}.\]""",
    "05": r"""Expand and simplify $-2(x - 3)$.""",
    "06": r"""Solve the equations
\begin{enumerate}[label=(\alph*)]
\item $27 = 3x - 6$.
\item $x^{2} + 7x + 12 = 0$.
\end{enumerate}""",
    "07": r"""Factorise fully
\begin{enumerate}[label=(\alph*)]
\item $2b^{2} - 2$.
\item $ac + ad - bc - bd$.
\end{enumerate}""",
    "08": r"""A flight from place A started at 20:47.

It took 7 hours 36 minutes to arrive at place B, whose time zone is 2 hours behind that of place A.

Find the time at place B on arrival.""",
    "09": r"""The ratio of exterior angle to interior angle of a polygon is $2 : 7$.

Find the number of sides of the polygon.""",
    "10": r"""$V = \dfrac{1}{3} \pi r^{2} h$

\begin{enumerate}[label=(\alph*)]
\item Find, in terms of $\pi$, the value of $V$ when $r = 6$ and $h = 5$.
\item Make $h$ the subject of the formula.
\end{enumerate}""",
    "11": r"""The Venn diagram shows elements of the universal set, set $A$ and set $B$.

\begin{enumerate}[label=(\alph*)]
\item Use set notation to complete the statement: $\{a, b, c\} \ldots\ldots A$.
\item Find
  \begin{enumerate}[label=(\roman*)]
  \item $A \cap B$.
  \item $n(A \cup B)'$.
  \end{enumerate}
\item Shade $A' \cap B$.
\end{enumerate}""",
    "12": r"""Given $A = \begin{pmatrix} 6 & 0 \\ 1 & 2 \end{pmatrix}$ and $B = \begin{pmatrix} 2 & 3 \\ 1 & 1 \end{pmatrix}$,

evaluate
\begin{enumerate}[label=(\alph*)]
\item $2B$.
\item $A - B$.
\end{enumerate}""",
    "13": r"""$P(-3, -3)$ and $Q(2, 12)$ are the points on a straight line.

Find
\begin{enumerate}[label=(\alph*)]
\item the gradient of $PQ$.
\item the coordinates of the midpoint of $PQ$.
\end{enumerate}""",
    "14": r"""$\overrightarrow{PQ} = \begin{pmatrix} 5 \\ 12 \end{pmatrix}$ and $P(1, 2)$.

Find
\begin{enumerate}[label=(\alph*)]
\item the coordinates of $Q$.
\item the magnitude of $\overrightarrow{PQ}$.
\end{enumerate}""",
    "15": r"""The diagram shows a rectangle with an inscribed sector of $45^\circ$.

Calculate, in terms of $\pi$, the area of the shaded parts.

Give your answer in the form $a - b\pi$, where $a$ and $b$ are integers.""",
    "16": r"""The diagram shows a circle centre $O$ and $AD$ as the diameter.

$BC$ is parallel to $AD$ and $EF$ is a tangent to the circle at $C$.

Angle $OCB = 42^\circ$.

Find the size of
\begin{enumerate}[label=(\alph*)]
\item the angle $ECB$.
\item the angle $ODC$.
\end{enumerate}""",
    "17": r"""The diagram shows a right-angled triangle $BCD$.

$BC = 8$ units and $BD = 17$ units.

Find
\begin{enumerate}[label=(\alph*)]
\item the length of $CD$.
\item the exact value of $\cos \angle CBD$.
\end{enumerate}""",
    "18": r"""The diagram shows the regions of two fair spinners with pointers at the rest positions.

\begin{enumerate}[label=(\alph*)]
\item Spinner 2 is spun once. Find the probability that the pointer lands at the region 2.
\item The two spinners are spun simultaneously. Find the probability that both pointers land at an even number.
\end{enumerate}""",
    "19": r"""The table shows the results of 60 children asked about the number of toys they have.

\begin{center}
\begin{tabular}{|c|c|c|c|c|c|c|}
\hline
Number of toys & 0 & 1 & 2 & 3 & 4 & 5 \\
\hline
Frequency & 12 & 8 & 5 & 9 & 17 & 9 \\
\hline
\end{tabular}
\end{center}

\begin{enumerate}[label=(\alph*)]
\item Find
  \begin{enumerate}[label=(\roman*)]
  \item the mode of the distribution.
  \item the median of the distribution.
  \end{enumerate}
\item Two more children are asked about the number of toys they have.

Explain clearly, between the mode, mean and median, what would change.
\end{enumerate}"""
}

def parse_question_md(md_path):
    with open(md_path, "r", encoding="utf-8") as f:
        content = f.read()
    
    # Remove source footer
    content = re.split(r"\n---\n", content)[0].strip()
    
    # Extract title (e.g. **Question 1**)
    title_match = re.search(r"\*\*Question (\d+)\*\*", content)
    qnum = int(title_match.group(1)) if title_match else 0
    
    # Body is everything after the title line
    lines = content.splitlines()
    body_lines = []
    in_body = False
    for line in lines:
        if re.match(r"\*\*Question \d+\*\*", line):
            in_body = True
            continue
        if in_body:
            body_lines.append(line)
    
    body = "\n".join(body_lines).strip()
    
    # Try to extract total marks (sum of [n])
    marks = sum(int(m) for m in re.findall(r"\[(\d+)\]", content))
    
    return {
        "original_num": qnum,
        "body_markdown": body,
        "total_marks": marks
    }

def get_images_for_question(qdir):
    """Return list of image filenames in the question dir (relative to qdir)."""
    images = []
    for f in sorted(os.listdir(qdir)):
        if f.lower().endswith((".png", ".jpg", ".jpeg")):
            images.append(f)
    return images

def main():
    questions = []
    
    for topic in TOPICS:
        topic_dir = os.path.join(SOURCE_DIR, topic)
        if not os.path.isdir(topic_dir):
            continue
        
        for qfolder in sorted(os.listdir(topic_dir)):
            if not qfolder.startswith("Question_"):
                continue
            
            qid = qfolder.split("_")[1]  # "01", "02", ...
            qdir = os.path.join(topic_dir, qfolder)
            md_path = os.path.join(qdir, "question.md")
            
            if not os.path.exists(md_path):
                continue
            
            parsed = parse_question_md(md_path)
            
            # Get images and copy them with prefixed names
            raw_images = get_images_for_question(qdir)
            image_list = []
            
            for img_name in raw_images:
                src = os.path.join(qdir, img_name)
                # New name: Q01_question_area.png or Q01_venn_diagram1.png
                new_name = f"Q{qid}_{img_name}"
                dst = os.path.join(ASSETS_DIR, new_name)
                shutil.copy2(src, dst)
                image_list.append(new_name)
            
            # Build record
            qdata = {
                "id": f"Q{qid}",
                "original_num": parsed["original_num"],
                "topic": topic,
                "title": f"Question {parsed['original_num']}",
                "body_markdown": parsed["body_markdown"],
                "latex": IMPROVED_LATEX.get(qid, parsed["body_markdown"]),
                "total_marks": parsed["total_marks"],
                "images": image_list,
                "source_page": None  # could add later if needed
            }
            questions.append(qdata)
            print(f"Processed {qdata['id']} ({topic}) - marks: {qdata['total_marks']}, images: {len(image_list)}")
    
    # Sort by original number
    questions.sort(key=lambda x: x["original_num"])
    
    # Write JSON
    json_path = os.path.join(DATA_DIR, "questions.json")
    with open(json_path, "w", encoding="utf-8") as f:
        json.dump(questions, f, indent=2, ensure_ascii=False)
    
    print(f"\nWrote {len(questions)} questions to {json_path}")
    print(f"Images copied to {ASSETS_DIR}")
    
    # Also write a simple topics summary
    summary = {}
    for q in questions:
        summary.setdefault(q["topic"], []).append(q["id"])
    
    with open(os.path.join(DATA_DIR, "topics_summary.json"), "w") as f:
        json.dump(summary, f, indent=2)
    
    print("Done building data.")

if __name__ == "__main__":
    main()