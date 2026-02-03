#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Compile the final Pillar 02 page by stitching generated section markdown into the template
and performing citation remapping + References append.

Usage:
  python pillars/02_design_engineering/compile_piller_02.py \
    [--include-secondary] [--max-papers 30]

This script intentionally does NOT generate sections or foundation packs.
Run literature/tools/generate_pillars.py first to produce sections/generated/*.md
and any foundation JSON.
"""
import sys
from pathlib import Path
from datetime import date
import json
import re

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

# Reuse generation utilities from the pillar generator
from literature.tools.generate_pillars import (
    load_sections_controller,
    read_text,
    write_text,
    substitute,
    ensure_pillar_cache,
    load_pillar_cache,
    load_core_reviews_cache_v2,
    build_page_evidence_pool,
    rewrite_global_citations_and_build_refs,
    _clean_year,
    _normalize_doi,
    _is_internal_or_missing_doi,
    TAG_RE,
)

import argparse
import pandas as pd

PILLAR_DIR = ROOT / "pillars" / "02_design_engineering"
LIT_DIR = ROOT / "literature"
INDEX_DIR = LIT_DIR / "index"
INDEX_CSV = INDEX_DIR / "index.csv"
PAPERS_CSV = INDEX_DIR / "papers.csv"

def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--include-secondary", action="store_true", help="include secondary pillar matches in cache")
    ap.add_argument("--max-papers", type=int, default=30, help="cap for evidence derivation")
    args = ap.parse_args()

    template_path = PILLAR_DIR / "template.md"
    if not template_path.exists():
        print(f"Missing template: {template_path}")
        return 1

    order, enabled = load_sections_controller(PILLAR_DIR)
    gen_dir = PILLAR_DIR / "sections" / "generated"

    template = read_text(template_path)
    sections: dict[str, str] = {}
    for sec in order:
        if enabled.get(sec, True):
            sections[sec] = read_text(gen_dir / f"{sec}.md")
    # Remove disabled sections' header + placeholder blocks from the template
    for sec in order:
        if not enabled.get(sec, True):
            pat = rf"(?ms)^\s*##[^\n]*\n\s*\{{\{{section:{re.escape(sec)}\}}\}}\s*\n?"
            template = re.sub(pat, "", template)

    compiled = substitute(template, sections)
    compiled = compiled.replace("{{date}}", date.today().isoformat())

    # Prepare evidence pool for [S#] rewrite
    # Try caches first; if empty, fallback to index.csv/papers.csv
    try:
        cache_path = ensure_pillar_cache("02", "Design & Engineering", args.include_secondary, args.max_papers, False)
        cache = load_pillar_cache(cache_path)
    except Exception:
        cache = {}
    core_cache_v2_final = load_core_reviews_cache_v2()
    ev_page_items_final, _ = build_page_evidence_pool(core_cache_v2_final, cache, limit_pillar=12)

    # Fallback from index
    source_csv = INDEX_CSV if INDEX_CSV.exists() else (PAPERS_CSV if PAPERS_CSV.exists() else None)
    if not ev_page_items_final and source_csv:
        try:
            df = pd.read_csv(source_csv)
            dfp_final = df[df["pillar_primary"].fillna("").str.contains("Design & Engineering", case=False, na=False)].copy()
            if not dfp_final.empty:
                dfp_final = dfp_final.sort_values(by=["year", "title"], ascending=[False, True]).head(12)
                ev_page_items_final = []
                for _, r in dfp_final.iterrows():
                    title = (r.get("title") or "").strip()
                    year = _clean_year(r.get("year"))
                    doi_raw = str(r.get("doi") or "").strip()
                    doi_norm = _normalize_doi(doi_raw)
                    doi_out = "" if _is_internal_or_missing_doi(doi_raw) else doi_norm
                    if title:
                        ev_page_items_final.append({
                            "title": title,
                            "year": year,
                            "doi": doi_out,
                            "snippet": "",
                        })
        except Exception:
            pass

    try:
        compiled, refs_md = rewrite_global_citations_and_build_refs(compiled, ev_page_items_final)
        if refs_md:
            compiled = compiled.rstrip() + "\n\n" + refs_md
    except Exception:
        pass

    # Foundation-based fallback: use any pillar-local foundation packs if needed
    if TAG_RE.search(compiled or "") and "## References" not in (compiled or ""):
        try:
            fdir = PILLAR_DIR / "sections" / "foundation"
            ev2 = []
            if fdir.exists():
                for fp in sorted(fdir.glob("*_foundation.json")):
                    try:
                        data = json.loads(read_text(fp))
                    except Exception:
                        continue
                    for it in (data.get("evidence_list") or []):
                        t = (it.get("title") or "").strip()
                        if not t:
                            continue
                        y = _clean_year(it.get("year"))
                        doi_raw = str(it.get("doi") or "").strip()
                        doi_norm = _normalize_doi(doi_raw)
                        doi_out = "" if _is_internal_or_missing_doi(doi_raw) else doi_norm
                        ev2.append({"title": t, "year": y, "doi": doi_out, "snippet": (it.get("snippet") or "")})
            if ev2:
                compiled, refs2 = rewrite_global_citations_and_build_refs(compiled, ev2)
                if refs2:
                    compiled = compiled.rstrip() + "\n\n" + refs2
        except Exception:
            pass

    existing = list(PILLAR_DIR.glob("pillar-02-*.md"))
    out_path = existing[0] if existing else PILLAR_DIR / "pillar-02-design_engineering.md"
    write_text(out_path, compiled)
    print(f"Updated {out_path}")
    return 0

if __name__ == "__main__":
    raise SystemExit(main())
