#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Build pillar caches and emit LLM-ready foundation JSON packs only (no LLM calls, no markdown generation).

Usage:
    python tools/build_pillar_cache.py --pillar 02
    python tools/build_pillar_cache.py --pillar all --max-papers 30

Outputs per pillar directory under pillars/<ID_*>/:
    sections/foundation/overview_foundation.json

Also ensures the pillar cache JSON exists/refreshes at:
    library/cache_for-llm/pillars/<ID>.json
"""

from __future__ import annotations

import argparse
import json
from datetime import date
from pathlib import Path
from typing import Dict, Any, List, Tuple

import pandas as pd

# -------- Paths --------
ROOT = Path(__file__).resolve().parents[1]
PILLARS_DIR = ROOT / "pillars"
LIT_DIR = ROOT / "library"
INDEX_DIR = LIT_DIR / "literature_index"
INDEX_CSV = INDEX_DIR / "index.csv"
PAPERS_CSV = INDEX_DIR / "papers.csv"
CORE_REV_CACHE_JSON_V2 = LIT_DIR / "cache_for-llm" / "core_reviews" / "core_reviews_v2.json"
CACHE_DIR = LIT_DIR / "cache_for-llm" / "pillars"

# -------- IO utils --------

def read_text(p: Path) -> str:
    return p.read_text(encoding="utf-8") if p.exists() else ""


def write_text(p: Path, s: str) -> None:
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(s, encoding="utf-8")


# -------- Helpers (mirrors from generate_pillars.py minimal) --------

def _clean_year(y: Any) -> str:
    try:
        yi = int(float(y))
        return str(yi)
    except Exception:
        return ""


def _normalize_doi(doi: str) -> str:
    import re
    d = (doi or "").strip().lower()
    if d.startswith("https://doi.org/") or d.startswith("http://dx.doi.org/") or d.startswith("http://doi.org/"):
        d = re.sub(r"^https?://(dx\.)?doi\.org/", "", d)
    if d.startswith("doi:"):
        d = d[4:]
    if d.startswith("10.1002/ange."):
        d = d.replace("10.1002/ange.", "10.1002/anie.")
    d = d.replace("10.1002/chin.", "10.1002/chemint.") if d.startswith("10.1002/chin.") else d
    d = d.rstrip(".;,)")
    return d


def _is_internal_or_missing_doi(doi: str) -> bool:
    d = (doi or "").lower()
    return (not d) or d.startswith("no-doi::")


def from_cache_recent_entries(cache: dict, limit: int = 200, max_items: int | None = None) -> list[dict]:
    n = max_items if max_items is not None else limit
    entries = list((cache or {}).get("entries") or [])
    if not entries:
        return []

    def parse_dt(s: str) -> tuple[int, int, int, int, int, int]:
        try:
            date_s, time_s = (s or "").split()
            y, m, d = [int(x) for x in date_s.split("-")]
            hh, mm, ss = [int(x) for x in time_s.split(":")]
            return (y, m, d, hh, mm, ss)
        except Exception:
            return (0, 0, 0, 0, 0, 0)

    def sort_key(e: dict):
        ts = e.get("ingested_at") or e.get("added_at") or ""
        dt = parse_dt(ts)
        m = e.get("meta", {}) or {}
        try:
            yr = int(_clean_year(m.get("year")))
        except Exception:
            yr = 0
        title = (m.get("title") or "").strip()
        return (dt, yr, title)

    entries.sort(key=sort_key, reverse=True)
    return entries[:n]


def load_core_reviews_cache_v2() -> dict:
    try:
        if CORE_REV_CACHE_JSON_V2.exists():
            return json.loads(CORE_REV_CACHE_JSON_V2.read_text(encoding="utf-8"))
    except Exception:
        pass
    return {}


def build_page_evidence_pool(core_cache_v2: dict, pillar_cache: dict, limit_pillar: int = 12) -> Tuple[List[Dict[str, Any]], str]:
    ev_items: List[Dict[str, Any]] = []
    lines: List[str] = []
    # Core reviews bundles as compact items (header + topics + key sections summaries if present)
    for e in (core_cache_v2.get("entries") or [])[:4]:
        b = (e.get("bundles", {}) or {}).get("prompt_ready", {})
        if not b:
            continue
        header = b.get("header") or (e.get("meta", {}).get("title") or "Core Review")
        year = (e.get("meta", {}).get("year") or "")
        journal = (e.get("meta", {}).get("journal") or e.get("meta", {}).get("venue") or "")
        hdr_tail = f"{year}{', ' + journal if journal else ''}" if year or journal else ""
        topics = ", ".join((b.get("topics") or [])[:8])
        parts = [f"{header}{' (' + hdr_tail + ')' if hdr_tail else ''}"]
        if topics:
            parts.append(f"Topics: {topics}")
        for ks in (b.get("key_sections") or [])[:3]:
            nm = ks.get("name") or "Section"
            sm = (ks.get("summary") or ks.get("summary2") or "").strip().replace("\n", " ")[:360]
            if sm:
                parts.append(f"{nm}: {sm}")
        snippet = " — ".join(parts)
        ev_items.append({
            "title": header,
            "year": str(year or ""),
            "doi": str(e.get("meta", {}).get("doi") or ""),
            "snippet": snippet[:400],
        })
    # Pillar cache recent entries
    for e in from_cache_recent_entries(pillar_cache, limit_pillar):
        m = e.get("meta", {})
        title = (m.get("title") or "").strip()
        year = _clean_year(m.get("year"))
        doi_raw = (m.get("doi") or "").strip()
        doi = _normalize_doi(doi_raw)
        doi_out = "" if _is_internal_or_missing_doi(doi_raw) else doi
        sal = e.get("salient") or []
        snippet = (sal[0] if sal else (e.get("summary") or ""))
        ev_items.append({
            "title": title,
            "year": year,
            "doi": doi_out,
            "snippet": (snippet or "").strip()[:280],
        })
    block_lines: List[str] = []
    for i, ev in enumerate(ev_items, 1):
        yr = ev.get("year") or ""
        title = ev.get("title") or ""
        doi = ev.get("doi") or ""
        snip = ev.get("snippet") or ""
        doi_part = f" — doi:{doi}" if doi else ""
        block_lines.append(f"S{i} ({yr}) — {title}{doi_part}: {snip}")
    return ev_items, "\n".join(block_lines)


def ensure_pillar_cache(pillar_id: str, pillar_name: str, max_papers: int, refresh: bool) -> Path:
    import subprocess
    CACHE_DIR.mkdir(parents=True, exist_ok=True)
    cache_path = CACHE_DIR / f"{pillar_id}.json"
    if refresh or not cache_path.exists():
        cmd = [
            "python3",
            str(ROOT / "tools" / "index_pillar_tei.py"),
            "--pillar-id", pillar_id,
            "--pillar-name", pillar_name,
            "--include-secondary",  # default behavior: include secondary matches
        ]
        cmd += ["--max-papers", str(max_papers)]
        subprocess.run(cmd, cwd=str(ROOT), check=False)
    return cache_path


def load_pillar_cache(cache_path: Path) -> dict:
    try:
        if cache_path.exists():
            return json.loads(cache_path.read_text(encoding="utf-8")) or {}
    except Exception:
        return {}
    return {}


def build_foundation_overview_payload(pillar_id: str, pillar_name: str, pillar_cache: dict, core_cache_v2: dict, evidence_limit: int = 20) -> dict:
    ev_items, _ = build_page_evidence_pool(core_cache_v2, pillar_cache, limit_pillar=min(12, evidence_limit))
    meta = {
        "pillar_id": pillar_id,
        "pillar_name": pillar_name,
        "section": "overview",
        "created_at": date.today().isoformat(),
        "schema": "foundation.v1",
    }
    payload = {
        "meta": meta,
        "evidence_list": ev_items,
        "instructions": "Write a concise 2-paragraph overview. Only use evidence_list. Tag claims with [S#] based on 1-indexed evidence order.",
    }
    return payload


# -------- CLI --------

essential_cols = [
    "doi", "title", "year", "pillar_primary", "tei", "extracted", "status"
]


def main() -> int:
    ap = argparse.ArgumentParser(description="Build pillar cache and emit foundation JSON only")
    ap.add_argument("--pillar", default="02", help="pillar ID (e.g., 02) or 'all'")
    ap.add_argument("--max-papers", type=int, default=30, help="cap number of recent papers/snippets used")
    args = ap.parse_args()

    source_csv = INDEX_CSV if INDEX_CSV.exists() else (PAPERS_CSV if PAPERS_CSV.exists() else None)
    if not source_csv:
        print(f"No index found. Expected one of: {INDEX_CSV} or {PAPERS_CSV}")
        df = pd.DataFrame(columns=essential_cols)
    else:
        print(f"Using index file: {source_csv}")
        df = pd.read_csv(source_csv)
    for c in essential_cols:
        if c not in df.columns:
            df[c] = ""

    pillars: List[Path] = []
    if args.pillar == "all":
        for p in sorted(PILLARS_DIR.iterdir()):
            if p.is_dir() and p.name[:2].isdigit():
                pillars.append(p)
    else:
        p = PILLARS_DIR / f"{args.pillar}_design_engineering" if args.pillar == "02" else None
        if p is None or not p.exists():
            for d in PILLARS_DIR.iterdir():
                if d.is_dir() and d.name.startswith(args.pillar):
                    pillars.append(d)
                    break
        else:
            pillars.append(p)

    if not pillars:
        print("No pillar directories found")
        return 1

    core_v2 = load_core_reviews_cache_v2()

    for pillar_dir in pillars:
        pillar_id = pillar_dir.name[:2]
        pillar_name = "Design & Engineering" if pillar_dir.name.startswith("02") else pillar_dir.name
        # Ensure cache (always includes secondary matches by default)
        cache_path = ensure_pillar_cache(pillar_id, pillar_name, args.max_papers, True)
        cache = load_pillar_cache(cache_path)
        # Build foundation payload (LLM-ready JSON)
        payload = build_foundation_overview_payload(pillar_id, pillar_name, cache, core_v2, evidence_limit=min(20, args.max_papers))
        out_path = pillar_dir / "sections" / "foundation" / "overview_foundation.json"
        write_text(out_path, json.dumps(payload, ensure_ascii=False, indent=2))
        print(f"Wrote foundation: {out_path}")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
