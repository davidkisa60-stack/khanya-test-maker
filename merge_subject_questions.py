#!/usr/bin/env python3
"""
Multi-subject question merger for the Arena paper system.
Usage:
    python merge_subject_questions.py --subject biology --paste-file cleaned.json
    or
    python merge_subject_questions.py --subject mathematics   (will prompt for paste)
"""

import json
import argparse
import os
import sys
from datetime import datetime
from pathlib import Path

SUBJECTS_BASE = Path(__file__).parent / "subjects"
SUBJECTS_CONFIG = SUBJECTS_BASE / "subjects.json"

def load_subjects_config():
    with open(SUBJECTS_CONFIG, "r") as f:
        return json.load(f)

def get_subject_folder(subject_id):
    config = load_subjects_config()
    for s in config["subjects"]:
        if s["id"] == subject_id:
            return SUBJECTS_BASE / s["folder"] / "data" / "questions.json"
    raise ValueError(f"Subject '{subject_id}' not found in subjects.json")

def load_questions(subject_path):
    if subject_path.exists():
        with open(subject_path, "r") as f:
            return json.load(f)
    return []

def save_questions(subject_path, questions):
    subject_path.parent.mkdir(parents=True, exist_ok=True)
    with open(subject_path, "w") as f:
        json.dump(questions, f, indent=2)

def generate_unique_id(year, paper, original_num, subject_id):
    """Generate subject-aware unique IDs"""
    subject_code = {
        "mathematics": "M",
        "biology": "BIO",
        "physical_science": "PS",
        "physics": "PHY",
        "chemistry": "CHEM",
        "economics": "ECON",
        "development_studies": "DS",
        "accounting": "ACC"
    }.get(subject_id, subject_id[:3].upper())

    # For P1 keep simple (like before), for P2/P3 use prefix
    if "P1" in paper:
        return f"{year}Q{str(original_num).zfill(2)}"
    else:
        paper_code = paper.replace(" ", "").upper()  # e.g. P22024
        return f"{year}{paper_code}-Q{str(original_num).zfill(2)}"

def merge_questions(current_questions, new_questions, subject_id):
    """Merge logic with ID uniqueness per subject"""
    existing_ids = {q["id"] for q in current_questions}

    added = []
    skipped = []

    for q in new_questions:
        year = q.get("year")
        paper = q.get("paper", "")
        original_num = q.get("original_num", q.get("id", "").split("-")[-1])

        new_id = generate_unique_id(year, paper, original_num, subject_id)

        # Avoid duplicates
        if new_id in existing_ids:
            skipped.append(new_id)
            continue

        q["id"] = new_id
        q["year"] = year
        q["paper"] = paper
        added.append(q)
        existing_ids.add(new_id)

    # Sort by year then original_num
    all_questions = current_questions + added
    all_questions.sort(key=lambda x: (x.get("year", 0), x.get("original_num", 0)))

    return all_questions, added, skipped

def main():
    parser = argparse.ArgumentParser(description="Merge cleaned questions into a subject bank")
    parser.add_argument("--subject", required=True, help="Subject id (e.g. biology, mathematics)")
    parser.add_argument("--paste-file", help="Path to cleaned JSON array file")
    args = parser.parse_args()

    subject_path = get_subject_folder(args.subject)

    print(f"→ Merging into: {subject_path}")

    current = load_questions(subject_path)
    print(f"Current questions in {args.subject}: {len(current)}")

    if args.paste_file:
        with open(args.paste_file, "r") as f:
            new_questions = json.load(f)
    else:
        print("\nPaste the cleaned JSON array below (end with an empty line):")
        lines = []
        while True:
            try:
                line = input()
                if line.strip() == "":
                    break
                lines.append(line)
            except EOFError:
                break
        new_questions = json.loads("\n".join(lines))

    print(f"New questions to merge: {len(new_questions)}")

    merged, added, skipped = merge_questions(current, new_questions, args.subject)

    save_questions(subject_path, merged)

    # Only update legacy single file when merging Mathematics (temporary backward compat)
    # Do NOT touch it for other subjects — keeps the old Maths bank safe as backup.
    if args.subject == "mathematics":
        legacy_path = Path(__file__).parent / "data" / "questions.json"
        if legacy_path.exists():
            save_questions(legacy_path, merged)

    # Timestamped backup
    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    backup_dir = subject_path.parent / "backups"
    backup_dir.mkdir(exist_ok=True)
    backup_file = backup_dir / f"questions_{ts}.json"
    save_questions(backup_file, merged)

    print("\n✅ Merge complete!")
    print(f"   Total questions in {args.subject}: {len(merged)}")
    print(f"   Newly added: {len(added)}")
    if skipped:
        print(f"   Skipped (duplicates): {len(skipped)}")
    print(f"   Backup saved to: {backup_file}")
    print(f"\nNext step: Hard refresh your browser (Ctrl+Shift+R) and switch to the '{args.subject}' subject.")

if __name__ == "__main__":
    main()