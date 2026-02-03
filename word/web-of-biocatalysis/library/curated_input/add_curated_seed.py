#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import re
import argparse
from pathlib import Path
import pandas as pd
from pdfminer.high_level import extract_text

BASE = Path("/Users/glenn/Documents/SecondBrain/_PROTOTYPE/literature/curated")
PDF_DIR = BASE / "pdf"
CURATED_CSV = BASE / "curated_seeds.csv"
CURATED_CSV.parent.mkdir(parents=True, exist_ok=True)

DOI_RX = re.compile(r'\b10\.\d{4,9}/[^\s"<>]+', re.I)

def extract_doi_from_pdf(pdf_path: Path) -> str | None:
    try:
        text = extract_text(str(pdf_path)) or ""
    except Exception:
        return None
    m = DOI_RX.search(text)
    if not m:
        return None
    doi = m.group(0)
    # normalize
    doi = doi.replace("https://doi.org/", "").replace("http://doi.org/", "")
    doi = doi.replace("DOI:", "").replace("doi:", "").strip()
    return doi

def load_existing() -> pd.DataFrame:
    if CURATED_CSV.exists():
        df = pd.read_csv(CURATED_CSV)
        # normalize columns if old schema was used
        if "pillar" in df.columns and "pillar_primary" not in df.columns:
            df = df.rename(columns={"pillar": "pillar_primary"})
        for col in ["pdf_path", "pillar_primary", "doi"]:
            if col not in df.columns:
                df[col] = ""
        # keep only the columns pipeline expects
        return df[["pdf_path", "pillar_primary", "doi"]].copy()
    return pd.DataFrame(columns=["pdf_path", "pillar_primary", "doi"])

def main():
    ap = argparse.ArgumentParser(description="Scan curated_pdfs and (up)date curated_seeds.csv")
    ap.add_argument("--pillar", default="", help="Default pillar to assign for new rows (optional)")
    ap.add_argument("--dry-run", action="store_true", help="Do not write CSV, just print actions")
    args = ap.parse_args()

    if not PDF_DIR.exists():
        raise SystemExit(f"Missing folder: {PDF_DIR}")

    df = load_existing()
    have_dois = set(x.lower() for x in df["doi"].dropna().astype(str))
    have_paths = set(df["pdf_path"].dropna().astype(str))

    new_rows = []

    for pdf in sorted(PDF_DIR.glob("*.pdf")):
        # pdf_path relative to curated_pdfs (so you can move the whole tree easily)
        rel_path = pdf.name

        # skip if exact path already present
        if rel_path in have_paths:
            continue

        doi = extract_doi_from_pdf(pdf)
        if not doi:
            print(f"❌ No DOI found in {pdf.name}")
            continue

        if doi.lower() in have_dois:
            # same DOI already present with some other file; don’t add a duplicate row
            print(f"⚠️ DOI already present, skipping new row for {pdf.name}: {doi}")
            continue

        new_rows.append({"pdf_path": rel_path, "pillar_primary": args.pillar, "doi": doi})
        print(f"✅ {pdf.name}  ->  doi={doi}")

    if not new_rows:
        print("ℹ️ No new PDFs processed.")
        return

    df_new = pd.DataFrame(new_rows, columns=["pdf_path", "pillar_primary", "doi"])
    df_out = pd.concat([df, df_new], ignore_index=True)

    # final dedupe: by doi first, then by pdf_path (preserve first occurrence)
    df_out = df_out.drop_duplicates(subset=["doi"], keep="first")
    df_out = df_out.drop_duplicates(subset=["pdf_path"], keep="first")

    if args.dry_run:
        print("\n--- DRY RUN ---")
        print(df_out.tail(len(df_new)).to_string(index=False))
        return

    df_out.to_csv(CURATED_CSV, index=False)
    print(f"💾 Updated {CURATED_CSV} with {len(new_rows)} new entries.")

if __name__ == "__main__":
    main()
