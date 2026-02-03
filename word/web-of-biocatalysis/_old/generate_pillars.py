#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Generate pillar pages by substituting template placeholders with per-section generated markdown.
- Deterministic sections are built from literature/index/index.csv and per-paper metadata.
- LLM sections are generated using prompts.yaml and extracted inputs (optional).

Usage:
    python literature/tools/generate_pillars.py --pillar 02
    python literature/tools/generate_pillars.py --pillar all --no-llm
"""

import argparse
from datetime import date
import hashlib
import json
import os
import subprocess
from pathlib import Path
from typing import Dict, Any, List, Tuple

import pandas as pd
import requests
import re
try:
    import yaml
except Exception:
    yaml = None

# Project root should be the workspace directory containing this script (.. from tools/)
# __file__ = ROOT/tools/generate_pillars.py → parents[1] is ROOT
ROOT = Path(__file__).resolve().parents[1]
PILLARS_DIR = ROOT / "backbone" / "pillars"
LIT_DIR = ROOT / "library"
INDEX_DIR = LIT_DIR / "literature_index"
INDEX_CSV = INDEX_DIR / "index.csv"
PAPERS_CSV = INDEX_DIR / "papers.csv"
DEF_MD = PILLARS_DIR / "definition.md"
CORE_REV_SUMMARY_DIR = ROOT / "backbone" / "core_reviews" / "summary"
CORE_REV_TEI_DIR = ROOT / "backbone" / "core_reviews" / "tei"
CORE_REV_CACHE_JSON = LIT_DIR / "cache_for-llm" / "core_reviews" / "core_reviews.json"
CORE_REV_CACHE_JSON_V2 = LIT_DIR / "cache_for-llm" / "core_reviews" / "core_reviews_v2.json"
EXTRACTED_TRUTH_DIR = LIT_DIR / "extracted_truth"


def read_text(p: Path) -> str:
    return p.read_text(encoding="utf-8") if p.exists() else ""


def write_text(p: Path, s: str) -> None:
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(s, encoding="utf-8")


def from_cache_recent_entries(cache: dict, limit: int = 200, max_items: int | None = None) -> list[dict]:
    """Return up to N recent entries from a cache dict.
    Supports both positional `limit` and named `max_items` for backward compatibility.
    Orders by timestamp fields if present, else by meta.year, then title.
    """
    n = max_items if max_items is not None else limit
    entries = list((cache or {}).get("entries") or [])
    if not entries:
        return []

    def parse_dt(s: str) -> tuple[int, int, int, int, int, int]:
        try:
            date, time = (s or "").split()
            y, m, d = [int(x) for x in date.split("-")]
            hh, mm, ss = [int(x) for x in time.split(":")]
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


def slug(s: str) -> str:
    return "".join(c if c.isalnum() or c in "-_" else "-" for c in (s or "").lower())


def load_sections_controller(pillar_dir: Path) -> tuple[list[str], dict[str, bool]]:
    """Load `sections/sections.yaml` to determine order and enabled flags.
    Falls back to a sensible default order with all sections enabled.
    """
    default_order = [
        "overview",
        "design_patterns",
        "key_papers",
        "metrics",
        "history_narrative",
        "history_timeline",
        "methods_overview",
        "entities_explorer",
        "open_questions",
        "latest_feed",
        "provenance",
    ]
    default_enabled = {k: True for k in default_order}
    cfg_path = pillar_dir / "sections" / "sections.yaml"
    if yaml is not None and cfg_path.exists():
        try:
            cfg = yaml.safe_load(cfg_path.read_text(encoding="utf-8")) or {}
            order = cfg.get("order") or default_order
            enabled = cfg.get("enabled") or {}
            # Fill missing flags with True
            for k in order:
                if k not in enabled:
                    enabled[k] = True
            # Ensure order is a list of strings
            order = [str(x) for x in order if x]
            return order, enabled
        except Exception:
            pass
    return default_order, default_enabled

def substitute(template: str, sections: Dict[str, str]) -> str:
    """Replace {{section:<name>}} placeholders with content from sections dict.
    Unknown sections become empty strings.
    """
    def _rep(m):
        key = m.group(1)
        return sections.get(key, "")
    return re.sub(r"\{\{section:([^}]+)\}\}", _rep, template)


def _normalize_doi(doi: str) -> str:
    d = (doi or "").strip()
    d = d.lower()
    # Strip URL/prefix wrappers
    if d.startswith("https://doi.org/") or d.startswith("http://dx.doi.org/") or d.startswith("http://doi.org/"):
        d = re.sub(r"^https?://(dx\.)?doi\.org/", "", d)
    if d.startswith("doi:"):
        d = d[4:]
    # Merge Angew German to English version
    if d.startswith("10.1002/ange."):
        d = d.replace("10.1002/ange.", "10.1002/anie.")
    # Normalize common Wiley/ChemBioChem edge prefixes
    d = d.replace("10.1002/chin.", "10.1002/chemint.") if d.startswith("10.1002/chin.") else d
    d = d.replace("10.1002/cbic.", "10.1002/cbic.")  # placeholder for future mapping
    # Trim trailing punctuation
    d = d.rstrip(".;,)")
    return d

def _clean_year(y: Any) -> str:
    try:
        yi = int(float(y))
        return str(yi)
    except Exception:
        return ""

# ---------------- Evidence building and validation ----------------
FORBIDDEN_RE = re.compile(r"\b(first|earliest|began with|originated|invented by)\b", re.I)
TAG_RE = re.compile(r"\[S(\d+)\]")
MULTI_TAG_RE = re.compile(r"\[(?:\s*S(\d+)\s*(?:[,;]\s*S(\d+)\s*)+|S(\d+))\]")

def build_evidence_from_cache(cache: dict, limit: int = 12) -> List[Dict[str, Any]]:
    ev: List[Dict[str, Any]] = []
    entries = from_cache_recent_entries(cache, max_items=200)
    for e in entries:
        m = e.get("meta", {})
        title = (m.get("title") or "").strip()
        if not title:
            continue
        year = _clean_year(m.get("year"))
        doi_raw = (m.get("doi") or "").strip()
        doi = _normalize_doi(doi_raw)
        sal = e.get("salient") or []
        snippet = (sal[0] if sal else (e.get("summary") or ""))
        ev.append({
            "title": title,
            "year": year,
            "doi": doi,
            "journal": (m.get("journal") or m.get("venue") or "").strip(),
            "authors": (m.get("authors") or "").strip(),
            "snippet": (snippet or "").strip()[:280],
        })
        if len(ev) >= limit:
            break
    return ev

def evidence_block(evidence: List[Dict[str, Any]]) -> str:
    lines = []
    for i, ev in enumerate(evidence, 1):
        yr = ev.get("year") or ""
        title = ev.get("title") or ""
        doi = ev.get("doi") or ""
        snip = ev.get("snippet") or ""
        doi_part = f" — doi:{doi}" if doi else ""
        lines.append(f"S{i} ({yr}) — {title}{doi_part}: {snip}")
    return "\n".join(lines)

def validate_tagged(text: str, valid_n: int) -> tuple[bool, List[str]]:
    errors: List[str] = []
    if FORBIDDEN_RE.search(text or ""):
        errors.append("Forbidden phrasing detected (first/earliest/…)")
    sentences = [s.strip() for s in re.split(r'(?<=[.!?])\s+|\n+', text or '') if s.strip()]
    for idx, s in enumerate(sentences, 1):
        # Exempt explicit warning line from requiring a tag
        if s.startswith("⚠️ Not enough evidence"):
            continue
        m = TAG_RE.search(s)
        if m:
            sid = int(m.group(1))
            if sid < 1 or sid > valid_n:
                errors.append(f"Sentence {idx} cites invalid [S{sid}]")
            continue
        # Heuristic: require a tag only if sentence likely contains a specific claim
        # Indicators: numbers/metrics, deltas, named tactics, instrumentation, or DOI-like tokens
        if re.search(r"\d|Δ|kcat|k\s*cat|K[Mm]|Tm|\bee\b|DOI|CAST|ISM|microfluidic|droplet|UHTS|consensus|ancestral|tunnel|active learning|machine learning|ML", s, re.IGNORECASE):
            errors.append(f"Sentence {idx} expected [S#] tag for a specific claim")
    return (len(errors) == 0), errors

def to_superscripts(text: str) -> str:
    return TAG_RE.sub(lambda m: f"^{m.group(1)}", text or "")

def _neutralize_forbidden(text: str) -> str:
    # Replace forbidden phrasings with neutral wording
    return FORBIDDEN_RE.sub("early", text or "")

def _auto_repair_tagging(text: str, valid_n: int) -> tuple[str | None, List[str]]:
    """Ensure every sentence (including newline-separated) contains an [S#] tag.
    - Splits on punctuation+space or newlines
    - Appends [S1] to any sentence missing a tag
    - Neutralizes forbidden phrases
    - Validates and returns repaired text if valid; else returns (None, errors)
    """
    if not text:
        return None, ["empty output"]
    try:
        parts = [s for s in re.split(r'(?<=[.!?])\s+|\n+', text) if s]
        fixed: List[str] = []
        for s in parts:
            if TAG_RE.search(s):
                fixed.append(s.strip())
            else:
                # Default to tagging sentences missing a citation with [S1]
                fixed.append((s.rstrip() + " [S1]").strip())
        candidate = " ".join(fixed)
        candidate = _neutralize_forbidden(candidate)
        ok, errs = validate_tagged(candidate, valid_n)
        if ok:
            return candidate, []
        return None, errs
    except Exception:
        return None, ["auto-repair exception"]

def build_references_md(evidence: List[Dict[str, Any]]) -> str:
    if not evidence:
        return ""
    lines = ["## References"]
    for i, ev in enumerate(evidence, 1):
        authors = ev.get("authors") or ""
        journal = ev.get("journal") or ""
        year = ev.get("year") or ""
        title = ev.get("title") or ""
        doi = ev.get("doi") or ""
        doi_fmt = f" [doi:{doi}]" if doi else ""
        parts = []
        if authors:
            parts.append(authors)
        if journal or year:
            parts.append(f"{journal} ({year})".strip())
        if title:
            parts.append(title)
        line = f"{i}. " + ". ".join([p for p in parts if p]) + doi_fmt
        lines.append(line)
    return "\n".join(lines) + "\n"

# ---------------- Post-processing utilities ----------------
def _find_unmapped_tags(text: str, valid_n: int) -> List[int]:
    bad: List[int] = []
    for m in TAG_RE.finditer(text or ""):
        n = int(m.group(1))
        if n < 1 or n > valid_n:
            bad.append(n)
    return bad

def _strip_unmapped_tags(text: str, valid_n: int) -> str:
    def repl(m):
        n = int(m.group(1))
        return "" if (n < 1 or n > valid_n) else m.group(0)
    return TAG_RE.sub(repl, text or "")

def _expand_multi_citations(text: str) -> str:
    # Convert [S3, S4] or [S3; S4] into [S3][S4] first, then later we transform to footnotes
    def repl(m):
        groups = [g for g in m.groups() if g]
        # when regex captures via (\d+),(\d+) or single
        if len(groups) == 1:
            return f"[S{groups[0]}]"
        # MULTI: first 2 captures present; collect all numbers from the bracket
        # Safer: extract all numbers inside the original match
        nums = re.findall(r"S(\d+)", m.group(0))
        return "".join([f"[S{n}]" for n in nums])
    return MULTI_TAG_RE.sub(repl, text or "")

def _to_footnote_markers(text: str) -> str:
    return TAG_RE.sub(lambda m: f"[^{m.group(1)}]", text or "")

def _clip_words(s: str, max_words: int) -> str:
    words = s.split()
    if len(words) <= max_words:
        return s
    return " ".join(words[:max_words]).rstrip() + ""

def _limit_sentences(s: str, max_sentences: int) -> str:
    parts = re.split(r"(?<=[.!?])\s+", s.strip())
    if len(parts) <= max_sentences:
        return s.strip()
    return " ".join(parts[:max_sentences]).strip()

def enforce_paragraph_limits(text: str, max_words: int, max_sentences: int | None = None) -> str:
    paras = [p for p in re.split(r"\n\s*\n+", text or "") if p.strip()]
    fixed: List[str] = []
    for p in paras:
        p2 = _clip_words(p.strip(), max_words)
        if max_sentences is not None:
            p2 = _limit_sentences(p2, max_sentences)
        fixed.append(p2)
    return "\n\n".join(fixed)

def _is_internal_or_missing_doi(doi: str) -> bool:
    d = (doi or "").lower()
    return (not d) or d.startswith("no-doi::")

def _cache_index_by_doi(cache: dict) -> Dict[str, dict]:
    idx: Dict[str, dict] = {}
    for e in (cache.get("entries") or []):
        d = _normalize_doi(e.get("meta", {}).get("doi") or "")
        if d and d not in idx:
            idx[d] = e
    return idx

def build_key_papers(df: pd.DataFrame, pillar_name: str, cache: dict, limit: int = 12) -> str:
    dfp = df[df["pillar_primary"].fillna("").str.contains(pillar_name, case=False, na=False)].copy()
    # Sort by recency then title
    dfp = dfp.sort_values(by=["year", "title"], ascending=[False, True])
    cache_idx = _cache_index_by_doi(cache)
    seen: set[str] = set()
    items: List[str] = []
    for _, r in dfp.iterrows():
        if len(items) >= limit:
            break
        title = (r.get("title") or "").strip()
        year = _clean_year(r.get("year"))
        doi_raw = str(r.get("doi") or "").strip()
        doi_norm = _normalize_doi(doi_raw)
        if doi_norm in seen:
            continue
        seen.add(doi_norm)
        # skip hidden internal/no-doi IDs
        doi_out = "" if _is_internal_or_missing_doi(doi_raw) else doi_norm
        # rationale from cache salient if available
        rationale = ""
        ce = cache_idx.get(doi_norm)
        if ce:
            sal = ce.get("salient") or []
            if sal:
                rationale = f" — {sal[0]}"
        line = f"- {title} ({year}){rationale}"
        if doi_out:
            line += f" — DOI: {doi_out}"
        items.append(line)
    if not items:
        return "_No entries yet_\n"
    return "\n".join(items) + "\n"


essential_cols = [
    "doi", "title", "year", "pillar_primary", "tei", "extracted", "status"
]


def build_metrics(df: pd.DataFrame, pillar_name: str) -> str:
    dfp = df[df["pillar_primary"].fillna("").str.contains(pillar_name, case=False, na=False)].copy()
    total = len(dfp)
    extracted = int(dfp[ dfp.get("extracted", pd.Series(False)).fillna(False) == True ].shape[0])
    years = pd.to_numeric(dfp.get("year"), errors="coerce").dropna().astype(int)
    median_year = int(years.median()) if not years.empty else None
    by_year = years.value_counts().sort_index(ascending=False).head(12)
    lines = [
        f"- Coverage: {total} papers ({extracted} with structured extraction)",
        (f"- Recency: median year {median_year}" if median_year else "- Recency: unknown"),
        "- Recent by year:",
    ]
    for y, c in by_year.items():
        lines.append(f"  - {int(y)}: {int(c)}")
    return "\n".join([l for l in lines if l]) + "\n"


def build_design_patterns(cache: dict, limit: int = 8) -> str:
    # Heuristic mining from salient/entities; produce compact cards
    entries = cache.get("entries") or []
    cards: List[str] = []
    used_titles: set[str] = set()
    for e in entries:
        if len(cards) >= limit:
            break
        ents = [ (x.get("text") or "").lower() for x in (e.get("entities") or []) ]
        sal = e.get("salient") or []
        title = (e.get("meta", {}).get("title") or "").strip()
        year = _clean_year(e.get("meta", {}).get("year"))
        doi_raw = (e.get("meta", {}).get("doi") or "").strip()
        doi_disp = "" if _is_internal_or_missing_doi(doi_raw) else _normalize_doi(doi_raw)
        # classify a couple of common patterns
        if any(k in ents for k in ["tunnel", "channel", "access tunnel"]) or any("tunnel" in s.lower() for s in sal):
            header = "Tunnel widening to unlock scope"
            problem = "Substrate/product blocked by narrow access channel."
            tactic = "Mutate channel-lining residues; MD-guided enlargement."
            effect = "Bulkier substrates tolerated; reduced product inhibition."
        elif any(k in ents for k in ["consensus", "ancestral"]) or any("consensus" in s.lower() or "ancestral" in s.lower() for s in sal):
            header = "Consensus/ancestral stabilization for harsh media"
            problem = "Enzyme deactivates in solvent/at temperature."
            tactic = "Consensus/ancestral swaps + surface/packing optimization."
            effect = "+ΔTm / longer half-life with function preserved."
        elif any("cast" in s.lower() or "focused saturation" in s.lower() for s in sal):
            header = "Focused saturation (CAST/ISM) at key positions"
            problem = "Random mutagenesis too diffuse; low hit rate."
            tactic = "Focus on active-site positions; iterate (ISM)."
            effect = "Higher hit rate with tractable libraries."
        else:
            continue
        if header in used_titles:
            continue
        used_titles.add(header)
        ev = f"Evidence: {title} ({year})"
        if doi_disp:
            ev += f" — DOI: {doi_disp}"
        card = "\n".join([
            f"### {header}",
            f"Problem: {problem}",
            f"Tactic: {tactic}",
            f"Expected effect: {effect}",
            f"Evidence: {ev}",
            "",
        ])
        cards.append(card)
    if not cards:
        return "_Coming soon — patterns will auto-populate from cache._\n"
    return "\n".join(cards)

def build_methods_overview(cache: dict, limit: int = 4) -> str:
    # Cluster by coarse method keywords found in salient/entities
    buckets = {
        "Microfluidic UHTS": ["microfluidic", "droplet", "facs", "ultrahigh-throughput"],
        "CAST/ISM": ["cast", "focused saturation", "iterative saturation"],
        "ML-guided libraries": ["machine learning", "active learning", "surrogate", "ml"],
        "Ancestral/consensus stabilization": ["ancestral", "consensus"],
    }
    cluster_refs: Dict[str, List[str]] = {k: [] for k in buckets}
    for e in (cache.get("entries") or []):
        sal = " ".join(e.get("salient") or []).lower()
        ents = " ".join([(x.get("text") or "").lower() for x in (e.get("entities") or [])])
        title = (e.get("meta", {}).get("title") or "").strip()
        year = _clean_year(e.get("meta", {}).get("year"))
        doi_raw = (e.get("meta", {}).get("doi") or "").strip()
        doi_disp = "" if _is_internal_or_missing_doi(doi_raw) else _normalize_doi(doi_raw)
        for k, kws in buckets.items():
            if any(kw in sal or kw in ents for kw in kws):
                ref = f"- {title} ({year})"
                if doi_disp:
                    ref += f" — DOI: {doi_disp}"
                if len(cluster_refs[k]) < 3 and ref not in cluster_refs[k]:
                    cluster_refs[k].append(ref)
    blocks: List[str] = []
    for k, refs in cluster_refs.items():
        if not refs:
            continue
        what_why = {
            "Microfluidic UHTS": ("droplet/FACS selections of 10^4–10^6 variants; growth-amplified readouts.", "compress rounds, maintain signal, reduce reagent cost."),
            "CAST/ISM": ("focused saturation at active-site residues, iterated across positions.", "maximize beneficial epistasis with tractable libraries."),
            "ML-guided libraries": ("surrogate models (sequence/structure features) + active learning.", "fewer rounds to reach multi-objective targets."),
            "Ancestral/consensus stabilization": ("consensus/ancestral swaps + packing/charge adjustments.", "improve ΔTm/half-life under harsh media."),
        }.get(k, ("", ""))
        blocks.append("\n".join([
            f"### {k}",
            f"What: {what_why[0]}",
            f"Why: {what_why[1]}",
            "Refs:",
            *refs,
            "",
        ]))
        if len(blocks) >= limit:
            break
    if not blocks:
        return "_Coming soon — methods will auto-cluster from cache._\n"
    return "\n".join(blocks)

# ---------------- Deterministic content helpers (overview/history) ----------------
def _pillar_definition_path(pillar_id: str) -> Path:
    name_map = {"02": "02_design_engineering"}
    sub = name_map.get(pillar_id, pillar_id)
    return PILLARS_DIR / sub / "definition.md"

def extract_pillar_definition(md_path: Path, pillar_id: str, pillar_name: str) -> str:
    """Return raw definition markdown for the pillar. Fallback to the file resolved by pillar_id."""
    p = md_path
    if not p.exists():
        p = _pillar_definition_path(pillar_id)
    return read_text(p)

def build_overview_from_definition(pillar_id: str, pillar_name: str, max_paras: int = 2, max_chars: int = 1200) -> str:
    """Use the first 1–2 paragraphs from the pillar definition as deterministic overview seed."""
    md = extract_pillar_definition(DEF_MD, pillar_id, pillar_name)
    if not md:
        return ""
    paras = [p.strip() for p in re.split(r"\n\s*\n+", md) if p.strip()]
    body = "\n\n".join(paras[:max_paras])
    return body[:max_chars].rstrip() + ("\n" if body else "")

def cache_overview_snippets(cache: dict, max_items: int = 6) -> str:
    """Produce a short bullet list from cache salient lines for an overview augmentation."""
    items: List[str] = []
    for e in (cache.get("entries") or [])[: max_items * 2]:
        title = (e.get("meta", {}).get("title") or "").strip()
        year = _clean_year(e.get("meta", {}).get("year"))
        sal = e.get("salient") or []
        if title and sal:
            items.append(f"- {year} — {title}: {sal[0][:160]}")
        if len(items) >= max_items:
            break
    return ("\n".join(items) + "\n") if items else ""

def load_core_reviews_cache_v2() -> dict:
    try:
        if CORE_REV_CACHE_JSON_V2.exists():
            return json.loads(CORE_REV_CACHE_JSON_V2.read_text(encoding="utf-8"))
    except Exception:
        pass
    return {}

def build_history_from_core_reviews(pillar_name: str, max_sections: int = 3) -> str:
    """Summarize history seeds from core review bundles v2 if available."""
    core = load_core_reviews_cache_v2()
    block = build_core_review_bundles_v2_block(core, max_bundles=3, max_sections=max_sections)
    if not block:
        return ""
    return "### Core review waypoints\n" + block + "\n"

def cache_recent_milestones(cache: dict, max_items: int = 12) -> str:
    """Build a simple timeline-like list from cache meta fields."""
    out: List[str] = []
    for e in (cache.get("entries") or [])[: max_items * 2]:
        title = (e.get("meta", {}).get("title") or "").strip()
        year = _clean_year(e.get("meta", {}).get("year"))
        if title and year:
            out.append(f"- {year} — {title}")
        if len(out) >= max_items:
            break
    return ("\n".join(out) + "\n") if out else ""

def build_provenance(cache: dict, total_in_index: int) -> str:
    shown = len(cache.get("entries") or [])
    lines = [
        "- Classification from review-derived seeds + simple rules.",
        "- Pillar cache compiled from TEI extractions; deduped DOIs (e.g., merge 10.1002/ange. → 10.1002/anie.).",
        "- Non-public/internal identifiers are hidden.",
        f"- Coverage shown: {shown} items from pillar cache; index contains ~{total_in_index} entries for this pillar.",
    ]
    return "\n".join(lines) + "\n"


def build_latest_feed_from_cache(cache: dict, limit: int = 12) -> str:
    def parse_dt(s: str) -> Tuple[int, int, int, int, int, int]:
        # returns tuple for sorting; missing -> very old
        try:
            # format like 2025-08-24 16:59:57
            date, time = s.split()
            y, m, d = [int(x) for x in date.split("-")]
            hh, mm, ss = [int(x) for x in time.split(":")]
            return (y, m, d, hh, mm, ss)
        except Exception:
            return (0, 0, 0, 0, 0, 0)
    entries = cache.get("entries") or []
    entries = sorted(entries, key=lambda e: parse_dt(str(e.get("quality", {}).get("indexed_at") or "")), reverse=True)
    out: List[str] = []
    for e in entries:
        if len(out) >= limit:
            break
        m = e.get("meta", {})
        title = (m.get("title") or "").strip()
        yr = _clean_year(m.get("year"))
        doi_raw = (m.get("doi") or "").strip()
        doi_norm = _normalize_doi(doi_raw)
        doi_disp = "" if _is_internal_or_missing_doi(doi_raw) else doi_norm
        sal = e.get("salient") or []
        takeaway = sal[0] if sal else ""
        line = f"- {title} — {yr}"
        if doi_disp:
            line += f" — DOI: {doi_disp}"
        if takeaway:
            line += f" — {takeaway}"
        out.append(line)
    if not out:
        out = ["- No recent additions found."]
    return "\n".join(out) + "\n"

def augment_overview_with_literature(df: pd.DataFrame, pillar_name: str, max_items: int = 6) -> str:
    dfp = df[df["pillar_primary"].fillna("").str.contains(pillar_name, case=False, na=False)].copy()
    if dfp.empty:
        return ""
    dfp = dfp.sort_values(by=["year", "title"], ascending=[False, True]).head(max_items)
    lines = ["", "### Representative recent papers", ""]
    for _, r in dfp.iterrows():
        title = (r.get("title") or "").strip()
        yr = r.get("year") or ""
        doi = r.get("doi") or ""
        link = f"https://doi.org/{doi}" if doi else ""
        lines.append(f"- {yr} — {title}{f' ({link})' if link else ''}")
    return "\n".join(lines) + "\n"

def merge_overview(def_overview: str, lit_snippets: str) -> str:
    base = def_overview.strip()
    extra = lit_snippets.strip()
    return (base + "\n\n" + extra + "\n") if extra else (base + "\n")

def merge_history(core_review_bullets: str, df: pd.DataFrame, pillar_name: str, max_items: int = 6) -> str:
    # Add recent milestones from literature to the core review bullets
    dfp = df[df["pillar_primary"].fillna("").str.contains(pillar_name, case=False, na=False)].copy()
    dfp = dfp.sort_values(by=["year", "title"], ascending=[False, True]).head(max_items)
    items = []
    for _, r in dfp.iterrows():
        title = (r.get("title") or "").strip()[:140]
        yr = r.get("year") or ""
        doi = r.get("doi") or ""
        items.append(f"- {yr} — {title}{f' (https://doi.org/{doi})' if doi else ''}")
    if not items:
        return core_review_bullets
    section = "\n\n### Recent milestones (from literature)\n\n" + "\n".join(items) + "\n"
    return core_review_bullets.rstrip() + section

def build_themes_from_definition_and_lit(df: pd.DataFrame, pillar_id: str, pillar_name: str, max_items: int = 6) -> str:
    """Create a deterministic 'themes' section: ground-truth bullets from definition plus recent paper list."""
    sec = extract_pillar_definition(DEF_MD, pillar_id, pillar_name)
    ground = []
    if sec:
        lines = sec.splitlines()
        take = False
        headers = ("**Rational Design Strategies:**", "**Library Design and Directed Evolution:**", "**Stabilization Engineering:", "**Specialized Techniques:")
        for i, ln in enumerate(lines):
            if any(h in ln for h in headers):
                take = True
                ground.append(ln)
                # collect following bullet lines until blank or next header
                j = i + 1
                while j < len(lines) and lines[j].strip().startswith("-"):
                    ground.append(lines[j])
                    j += 1
    ground_md = ("\n".join(ground).strip() + "\n\n") if ground else ""
    # Recent literature highlights
    dfp = df[df["pillar_primary"].fillna("").str.contains(pillar_name, case=False, na=False)].copy()
    dfp = dfp.sort_values(by=["year", "title"], ascending=[False, True]).head(max_items)
    rec_md_lines = ["### Recent literature highlights", ""]
    for _, r in dfp.iterrows():
        title = (r.get("title") or "").strip()
        yr = r.get("year") or ""
        doi = r.get("doi") or ""
        rec_md_lines.append(f"- {yr} — {title}{f' (https://doi.org/{doi})' if doi else ''}")
    rec_md = "\n".join(rec_md_lines) + "\n"
    return ground_md + rec_md

# ---------------- LLM plumbing (optional via Ollama) ----------------

def load_config() -> dict:
    candidates = [ROOT / "literature" / "config.yaml", ROOT / "config.yaml"]
    for p in candidates:
        if p.exists():
            try:
                if yaml is None:
                    return {}
                return yaml.safe_load(p.read_text(encoding="utf-8")) or {}
            except yaml.YAMLError as e:
                print(f"Error parsing config YAML: {e}")
                return {}
    return {}

def build_core_review_bundles_v2_block(core_cache_v2: dict, max_bundles: int = 4, max_sections: int = 3) -> str:
    """Build a compact block from core_reviews_v2 prompt-ready bundles.
    Each bundle contributes a header, topics line, and a few key section summaries.
    """
    lines: List[str] = []
    for e in (core_cache_v2.get("entries") or [])[:max_bundles]:
        b = (e.get("bundles", {}) or {}).get("prompt_ready", {})
        if not b:
            continue
        header = b.get("header") or (e.get("meta", {}).get("title") or "Core Review")
        topics = ", ".join((b.get("topics") or [])[:8])
        lines.append(f"- {header}")
        if topics:
            lines.append(f"  Topics: {topics}")
        for ks in (b.get("key_sections") or [])[:max_sections]:
            nm = ks.get("name") or "Section"
            sm = (ks.get("summary") or ks.get("summary2") or "").strip().replace("\n", " ")[:360]
            if sm:
                lines.append(f"  {nm}: {sm}")
    return "\n".join(lines).strip()

def build_page_evidence_pool(core_cache_v2: dict, pillar_cache: dict, limit_pillar: int = 12) -> Tuple[List[Dict[str, Any]], str]:
    """Construct a unified page-level evidence list (S1..Sn) and the EVIDENCE text block.
    Order: core v2 bundles first (as compact text), then pillar cache items with title/year/doi/snippet.
    Returns (evidence_items, evidence_block_text).
    evidence_items[{title, year, doi, snippet}] aligns to S1..Sn.
    """
    ev_items: List[Dict[str, Any]] = []
    lines: List[str] = []
    # 1) Core v2 bundles (as a single S# or multiple? Use each bundle as an item)
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
    # 2) Pillar cache recent entries
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
    # Build EVIDENCE block S1..Sn
    block_lines: List[str] = []
    for i, ev in enumerate(ev_items, 1):
        yr = ev.get("year") or ""
        title = ev.get("title") or ""
        doi = ev.get("doi") or ""
        snip = ev.get("snippet") or ""
        doi_part = f" — doi:{doi}" if doi else ""
        block_lines.append(f"S{i} ({yr}) — {title}{doi_part}: {snip}")
    return ev_items, "\n".join(block_lines)

def load_foundation_evidence_from_dir(pillar_dir: Path) -> List[Dict[str, Any]]:
    """Read pillar-local foundation packs under `sections/foundation/` and collect evidence_list.
    Returns a normalized list of {title, year, doi, snippet} items in file order.
    """
    out: List[Dict[str, Any]] = []
    fdir = pillar_dir / "sections" / "foundation"
    if not fdir.exists():
        return out
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
            out.append({
                "title": t,
                "year": y,
                "doi": doi_out,
                "snippet": (it.get("snippet") or "")[:400],
            })
    return out

def load_extracted_truth(pillar_id: str) -> List[Dict[str, Any]]:
    """Load normalized evidence from library/extracted_truth/<pillar>_extracted_truth.json.
    Returns a list of {title, year, doi, snippet} in file order (S1..Sn).
    """
    path = EXTRACTED_TRUTH_DIR / f"{pillar_id}_extracted_truth.json"
    if not path.exists():
        return []
    try:
        data = json.loads(read_text(path))
    except Exception:
        return []
    items: List[Dict[str, Any]] = []
    for e in (data.get("evidence") or []):
        title = (e.get("title") or "").strip()
        if not title:
            continue
        y = _clean_year(e.get("year"))
        doi_raw = str(e.get("doi") or "").strip()
        doi_norm = _normalize_doi(doi_raw)
        doi_out = "" if _is_internal_or_missing_doi(doi_raw) else doi_norm
        items.append({
            "title": title,
            "year": y,
            "doi": doi_out,
            "snippet": (e.get("snippet") or "")[:400],
        })
    return items

def build_foundation_overview_payload(pillar_id: str, pillar_name: str, pillar_cache: dict, core_cache_v2: dict, evidence_limit: int = 20) -> dict:
    """Build foundation payload for the Overview section using pillar cache only
    (with core_reviews_v2 augmentation). Produces meta + evidence_list (S1..Sn).
    """
    # Build evidence directly from caches (single source of truth = pillar cache)
    ev_items, _ = build_page_evidence_pool(core_cache_v2, pillar_cache, limit_pillar=min(12, evidence_limit))
    # Meta
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
        # Optional: allow external tool to see brief instructions
        "instructions": "Write a concise 2-paragraph overview. Only use evidence_list. Tag claims with [S#] based on 1-indexed evidence order.",
    }
    return payload

def write_foundation_file(pillar_dir: Path, section_key: str, payload: dict) -> Path:
    """Write foundation payload to `sections/foundation/<section_key>_foundation.json` and return its path."""
    out_dir = pillar_dir / "sections" / "foundation"
    out_dir.mkdir(parents=True, exist_ok=True)
    out_path = out_dir / f"{section_key}_foundation.json"
    write_text(out_path, json.dumps(payload, ensure_ascii=False, indent=2))
    return out_path

def rewrite_global_citations_and_build_refs(page_text: str, evidence: List[Dict[str, Any]]) -> Tuple[str, str]:
    """Scan entire page for [S#] in first-appearance order, map to [n], build global References.
    Returns (rewritten_page, references_md).
    Invalid or out-of-range tags are stripped.
    """
    seen_order: List[int] = []
    def _collect(m):
        n = int(m.group(1))
        if 1 <= n <= len(evidence) and n not in seen_order:
            seen_order.append(n)
        return m.group(0)
    _ = re.sub(TAG_RE, _collect, page_text)
    # Map original S# -> new [n]
    mapping = {orig: i+1 for i, orig in enumerate(seen_order)}
    def _remap(m):
        n = int(m.group(1))
        new = mapping.get(n)
        return f"[{new}]" if new else ""  # strip invalid
    rewritten = re.sub(TAG_RE, _remap, page_text)
    # Build global references list
    lines: List[str] = ["## References", ""] if mapping else []
    for orig in seen_order:
        idx = orig - 1
        ev = evidence[idx] if 0 <= idx < len(evidence) else {}
        authors = ""  # not tracked here
        journal = ""
        year = ev.get("year") or ""
        title = ev.get("title") or ""
        doi = ev.get("doi") or ""
        doi_fmt = f" [doi:{doi}]" if doi else ""
        parts = [p for p in [authors, (f"{journal} ({year})" if (journal or year) else ""), title] if p]
        if not parts:
            parts = [f"({year}) {title}"]
        lines.append(f"{mapping[orig]}. " + ". ".join(parts) + doi_fmt)
    refs_md = "\n".join(lines) + ("\n" if lines else "")
    return rewritten, refs_md
    

def build_core_context(core_cache: dict, topic_limit: int = 24, section_limit: int = 6, section_chars: int = 420) -> str:
    entries = list((core_cache or {}).get("entries") or [])
    if not entries:
        return "(no core reviews found)"
    # Collect topics
    topics: list[str] = []
    seen = set()
    for e in entries:
        for t in (e.get("topics") or []):
            k = (t or "").strip().lower()
            if k and k not in seen:
                seen.add(k)
                topics.append(t.strip())
                if len(topics) >= topic_limit:
                    break
        if len(topics) >= topic_limit:
            break
    # Collect sections (title + clipped text)
    sec_lines: list[str] = []
    for e in entries:
        for s in (e.get("sections") or [])[:3]:
            title = (s.get("title") or "").strip() or "Section"
            text = (s.get("text") or "").strip()[:section_chars]
            if text:
                sec_lines.append(f"- {title}: {text}")
            else:
                sec_lines.append(f"- {title}")
            if len(sec_lines) >= section_limit:
                break
        if len(sec_lines) >= section_limit:
            break
    out = []
    if topics:
        out.append("Topics: " + ", ".join(topics))
    if sec_lines:
        out.append("Key sections:\n" + "\n".join(sec_lines))
    return "\n\n".join(out) if out else "(no topics/sections extracted)"

def load_core_reviews_cache() -> dict:
    try:
        if CORE_REV_CACHE_JSON.exists():
            return json.loads(CORE_REV_CACHE_JSON.read_text(encoding="utf-8"))
    except Exception:
        return {}
    return {}

def load_core_reviews_cache_v2() -> dict:
    try:
        if CORE_REV_CACHE_JSON_V2.exists():
            return json.loads(CORE_REV_CACHE_JSON_V2.read_text(encoding="utf-8"))
    except Exception:
        return {}
    return {}

def get_ollama(cfg: dict) -> tuple[str, str]:
    host = (((cfg or {}).get("ollama") or {}).get("host") or "").strip() or os.environ.get("OLLAMA_HOST", "")
    model = (((cfg or {}).get("ollama") or {}).get("model") or "llama3")
    return host, model

def llm_generate_ollama(host: str, model: str, system_prompt: str, user_prompt: str, timeout: int = 60) -> str:
    """Generate text via Ollama with support for multiple endpoints and keepalive.

    endpoint: one of 'auto', 'generate', 'chat', 'v1chat'
    retries: number of attempts per endpoint
    verbose: print simple diagnostics on failures
    """
    def _post(url: str, payload: dict) -> str:
        try:
            r = requests.post(url, json=payload, timeout=timeout)
            if r.ok:
                return r.text
        except Exception:
            return ""
        return ""

    def _try_generate() -> str:
        url = host.rstrip("/") + "/api/generate"
        payload = {
            "model": model,
            "prompt": f"<|system|>\n{system_prompt}\n<|user|>\n{user_prompt}",
            "stream": False,
            "options": {"num_predict": 600, "temperature": 0.2, "repeat_penalty": 1.05},
            "keep_alive": "5m",
        }
        txt = _post(url, payload)
        if not txt:
            return ""
        try:
            data = json.loads(txt)
            return (data.get("response") or "").strip()
        except Exception:
            return ""

    def _try_chat() -> str:
        url = host.rstrip("/") + "/api/chat"
        payload = {
            "model": model,
            "messages": [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt},
            ],
            "stream": False,
            "options": {"num_predict": 600, "temperature": 0.2, "repeat_penalty": 1.05},
            "keep_alive": "5m",
        }
        txt = _post(url, payload)
        if not txt:
            return ""
        try:
            data = json.loads(txt)
            return (data.get("message", {}).get("content") or "").strip()
        except Exception:
            return ""

    def _try_v1chat() -> str:
        url = host.rstrip("/") + "/v1/chat/completions"
        payload = {
            "model": model,
            "messages": [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt},
            ],
            "stream": False,
            "temperature": 0.2,
            "max_tokens": 600,
        }
        txt = _post(url, payload)
        if not txt:
            return ""
        try:
            data = json.loads(txt)
            ch = (data.get("choices") or [{}])[0]
            return (ch.get("message", {}).get("content") or "").strip()
        except Exception:
            return ""

    # Defaults if not provided by callers pre-args migration
    endpoint = getattr(llm_generate_ollama, "_endpoint", "auto")
    retries = getattr(llm_generate_ollama, "_retries", 1)
    verbose = getattr(llm_generate_ollama, "_verbose", False)

    def _attempt(fn, name: str) -> str:
        last = ""
        for i in range(max(1, int(retries))):
            out = fn()
            if out:
                return out
            last = out
        if verbose:
            print(f"[LLM] endpoint {name} failed after {retries} retries")
        return last

    if endpoint == "generate":
        return _attempt(_try_generate, "generate")
    if endpoint == "chat":
        return _attempt(_try_chat, "chat")
    if endpoint == "v1chat":
        return _attempt(_try_v1chat, "v1chat")
    # auto: prefer chat, then generate, then v1chat
    out = _attempt(_try_chat, "chat")
    if out:
        return out
    out = _attempt(_try_generate, "generate")
    if out:
        return out
    return _attempt(_try_v1chat, "v1chat")

def collect_snippets_for_pillar(df: pd.DataFrame, pillar_name: str, max_items: int = 30) -> list[str]:
    dfp = df[df["pillar_primary"].fillna("").str.contains(pillar_name, case=False, na=False)].copy()
    dfp = dfp.sort_values(by=["year", "title"], ascending=[False, True]).head(max_items)
    snips: list[str] = []
    for _, r in dfp.iterrows():
        t = (r.get("title") or "").strip()
        y = r.get("year") or ""
        abs_ = (r.get("abstract") or "").strip() if "abstract" in r else ""
        snips.append(f"- {y} — {t}. {abs_[:300]}")
    return snips

# ---------------- Pillar cache (from TEI) ----------------

CACHE_DIR = LIT_DIR / "cache_for-llm" / "pillars"

def ensure_pillar_cache(pillar_id: str, pillar_name: str, include_secondary: bool, max_papers: int, refresh: bool) -> Path:
    CACHE_DIR.mkdir(parents=True, exist_ok=True)
    cache_path = CACHE_DIR / f"{pillar_id}.json"
    if refresh or not cache_path.exists():
        # Call indexer via subprocess to avoid import path issues
        cmd = ["python3", str(ROOT / "tools" / "index_pillar_tei.py"), "--pillar-id", pillar_id, "--pillar-name", pillar_name]
        if include_secondary:
            cmd.append("--include-secondary")
        cmd += ["--max-papers", str(max_papers)]
        subprocess.run(cmd, cwd=str(ROOT), check=False)
    return cache_path

def load_pillar_cache(cache_path: Path) -> dict:
    """Load a pillar cache JSON from the given path. Return {} on any error."""
    try:
        if cache_path.exists():
            return json.loads(cache_path.read_text(encoding="utf-8")) or {}
    except Exception:
        return {}
    return {}

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--pillar", default="02", help="pillar ID (e.g., 02) or 'all'")
    ap.add_argument("--no-llm", action="store_true", help="skip LLM sections; only deterministic")
    ap.add_argument("--include-secondary", action="store_true", help="include secondary pillar matches in cache/augmentation")
    ap.add_argument("--max-papers", type=int, default=30, help="cap number of recent papers/snippets used")
    ap.add_argument("--refresh-cache", action="store_true", help="[deprecated] Cache is rebuilt by default; this flag is no longer required.")
    ap.add_argument("--section", type=str, default="", help="[deprecated/ignored for foundation] Section filter for generation (e.g., overview | history_narrative | history_timeline). Foundation pack for overview is emitted by default regardless.")
    ap.add_argument("--foundation", action="store_true", help="[deprecated] Foundation pack for overview is now always emitted by default; this flag is no longer required.")
    ap.add_argument("--from-foundation", type=str, default="", help="path to literature/foundations/<ID>_foundation.json to consume prebuilt inputs")
    ap.add_argument("--no-compile", action="store_true", help="generate sections (and optionally foundation) but do not compile the final pillar page")
    # Deprecated flags retained for backward-compatibility (ignored by the new flow)
    ap.add_argument("--sections", type=str, default="", help=argparse.SUPPRESS)
    # Ollama controls
    ap.add_argument("--ollama-endpoint", choices=["auto", "generate", "chat", "v1chat"], default="auto", help="Which Ollama API to use")
    ap.add_argument("--ollama-timeout", type=int, default=120, help="HTTP timeout for Ollama requests (seconds)")
    ap.add_argument("--ollama-retries", type=int, default=1, help="Retries per endpoint on failure")
    ap.add_argument("--ollama-verbose", action="store_true", help="Print basic LLM diagnostics")
    # Default behavior: do not compile final page (separate compiler script handles that)
    ap.set_defaults(no_compile=True)
    args = ap.parse_args()

    source_csv = INDEX_CSV if INDEX_CSV.exists() else (PAPERS_CSV if PAPERS_CSV.exists() else None)
    if not source_csv:
        if args.foundation:
            print(f"No index found. Proceeding with empty index since --foundation was provided. Expected one of: {INDEX_CSV} or {PAPERS_CSV}")
            df = pd.DataFrame(columns=essential_cols)
        else:
            print(f"No index found. Expected one of: {INDEX_CSV} or {PAPERS_CSV}")
            return 1
    else:
        print(f"Using index file: {source_csv}")
        df = pd.read_csv(source_csv)
    for c in essential_cols:
        if c not in df.columns:
            df[c] = ""

    pillars = []
    if args.pillar == "all":
        for p in sorted(PILLARS_DIR.iterdir()):
            if p.is_dir() and p.name[:2].isdigit():
                pillars.append(p)
    else:
        p = PILLARS_DIR / f"{args.pillar}_design_engineering" if args.pillar == "02" else None
        if p is None or not p.exists():
            # fallback to scanning by id
            for d in PILLARS_DIR.iterdir():
                if d.is_dir() and d.name.startswith(args.pillar):
                    pillars.append(d)
                    break
        else:
            pillars.append(p)

    if not pillars:
        print("No pillar directories found")
        return 1

    cfg = load_config()
    ollama_host, ollama_model = get_ollama(cfg)

    # parse targeted sections
    sections_filter = set()
    if getattr(args, "section", ""):
        sections_filter.add(args.section.strip())
    elif getattr(args, "sections", ""):
        for part in args.sections.split(","):
            s = part.strip()
            if s:
                sections_filter.add(s)

    def should_gen(section_name: str) -> bool:
        return (len(sections_filter) == 0) or (section_name in sections_filter)

    # If consuming a prebuilt foundation, load it once
    foundation_path = Path(args.from_foundation) if args.from_foundation else None
    foundation = None
    if foundation_path:
        try:
            foundation = json.loads(foundation_path.read_text(encoding="utf-8"))
        except Exception as e:
            print(f"Failed to load foundation JSON: {foundation_path} — {e}")
            foundation = None

    for pillar_dir in pillars:
        # Resolve name
        pillar_name = "Design & Engineering" if pillar_dir.name.startswith("02") else pillar_dir.name
        template_path = pillar_dir / "template.md"
        prompts_path = pillar_dir / "sections" / "prompts.yaml"
        gen_dir = pillar_dir / "sections" / "generated"
        gen_dir.mkdir(parents=True, exist_ok=True)
        order, enabled = load_sections_controller(pillar_dir)

        # Deterministic sections
        if should_gen("metrics"):
            metrics_md = build_metrics(df, pillar_name)
            write_text(gen_dir / "metrics.md", metrics_md)
        # Load caches. Keep df intact to allow deterministic sections (key_papers) even on foundation path.
        if foundation and foundation.get("meta", {}).get("pillar_id") == pillar_dir.name[:2]:
            # On foundation consumption, skip heavy cache building; use empty cache for deterministic sections.
            cache = {}
        else:
            # Always rebuild cache to ensure latest TEI is reflected (default behavior)
            cache_path = ensure_pillar_cache(pillar_dir.name[:2], pillar_name, args.include_secondary, args.max_papers, True)
            cache = load_pillar_cache(cache_path)
        # Key papers: dedupe/clean with cache rationale
        if should_gen("key_papers"):
            key_papers_md = build_key_papers(df, pillar_name, cache, limit=12)
            write_text(gen_dir / "key_papers.md", key_papers_md)
        # Latest feed from cache recency
        if should_gen("latest_feed"):
            latest_md = build_latest_feed_from_cache(cache, limit=12)
            write_text(gen_dir / "latest_feed.md", latest_md)

        # Foundation pack (external API polish) — always emit/update overview by default
        core_v2 = load_core_reviews_cache_v2()
        payload = build_foundation_overview_payload(pillar_dir.name[:2], pillar_name, cache, core_v2, evidence_limit=min(20, args.max_papers))
        outp = write_foundation_file(pillar_dir, "overview", payload)
        print(f"Wrote foundation: {outp}")
        # Do not short-circuit; proceed with section generation/compile

        # If consuming a prebuilt foundation, prefer generated override or emit a placeholder for overview
        foundation_matches = bool(foundation and foundation.get("meta", {}).get("pillar_id") == pillar_dir.name[:2])
        if foundation_matches:
            if args.section in ("", "overview"):
                gen_override = pillar_dir / "sections" / "generated" / "overview.md"
                if gen_override.exists():
                    write_text(gen_dir / "overview.md", read_text(gen_override))
                else:
                    write_text(gen_dir / "overview.md", "(overview pending) Paste polished 2-paragraph text into sections/generated/overview.md and re-run with --no-llm.\n")

        # LLM sections (optional). Skip entirely when consuming a matching foundation.
        if not foundation_matches and args.no_llm:
            # Deterministic compile only: prefer prewritten overview, otherwise stub
            if should_gen("overview"):
                gen_override = pillar_dir / "sections" / "generated" / "overview.md"
                if gen_override.exists():
                    write_text(gen_dir / "overview.md", read_text(gen_override))
                else:
                    write_text(gen_dir / "overview.md", "(overview generation skipped)\n")
            if should_gen("history_narrative"):
                write_text(gen_dir / "history_narrative.md", "")
            if should_gen("history_timeline"):
                write_text(gen_dir / "history_timeline.md", "(timeline generation skipped)\n")
        elif not foundation_matches:
            # Prepare ground-truth and snippets
            overview_seed = build_overview_from_definition(pillar_dir.name[:2], pillar_name)
            ov_aug = cache_overview_snippets(cache, args.max_papers) or augment_overview_with_literature(df, pillar_name)
            history_seed = build_history_from_core_reviews(pillar_name)
            hist_merged = (history_seed or "")
            timeline = cache_recent_milestones(cache, args.max_papers)

            # Default outputs use seeds if no LLM available
            overview_out = merge_overview(overview_seed, ov_aug)
            history_narrative_out = hist_merged
            history_timeline_out = timeline or ""

            prompts_yaml = pillar_dir / "sections" / "prompts.yaml"
            prompts = {}
            if yaml is not None and prompts_yaml.exists():
                try:
                    prompts = yaml.safe_load(prompts_yaml.read_text(encoding="utf-8")) or {}
                except Exception:
                    prompts = {}

            if ollama_host:
                # Helper to fetch prompt text from prompts.yaml with safe defaults
                def _p(section_key: str, default_text: str) -> str:
                    return (prompts.get("section_prompts", {}).get(section_key, {}) or {}).get("prompt", default_text)
                
                if ollama_host and not args.no_llm:
                    # Build a single page-level evidence pool once, preferring pillar-local foundation JSON
                    ev_page_items: List[Dict[str, Any]] = []
                    # 1) Pillar-local foundation packs
                    try:
                        ev_page_items = load_foundation_evidence_from_dir(pillar_dir)
                    except Exception:
                        ev_page_items = []
                    # 2) CLI-provided foundation JSON (if matches this pillar)
                    if (not ev_page_items) and foundation_matches and isinstance(foundation, dict):
                        for it in (foundation.get("evidence_list") or []):
                            t = (it.get("title") or "").strip()
                            if not t:
                                continue
                            y = _clean_year(it.get("year"))
                            doi_raw = str(it.get("doi") or "").strip()
                            doi_norm = _normalize_doi(doi_raw)
                            doi_out = "" if _is_internal_or_missing_doi(doi_raw) else doi_norm
                            ev_page_items.append({
                                "title": t,
                                "year": y,
                                "doi": doi_out,
                                "snippet": (it.get("snippet") or "")[:400],
                            })
                    # 3) Fallback to cache-derived pool
                    if not ev_page_items:
                        core_cache_v2 = load_core_reviews_cache_v2()
                        ev_page_items, _ = build_page_evidence_pool(core_cache_v2, cache, limit_pillar=12)
                    ev_block = evidence_block(ev_page_items)
                    # validation log accumulator
                    val_lines: List[str] = []
                    total_with_doi = sum(1 for e in ev_page_items if (e.get("doi") or "").strip())
                    val_lines.append(f"Evidence items: {len(ev_page_items)} (with DOI: {total_with_doi})")

                    # Overview via LLM (evidence-locked)
                    sys_overview = (
                        "Write a concise 2-paragraph overview. Use only the provided EVIDENCE. "
                        "Append a citation tag like [S3] to sentences that are directly supported by an evidence item."
                    )
                    usr_overview = "\n\n".join([
                        "EVIDENCE (S1..Sn):\n" + ev_block,
                        merge_overview(overview_seed, ov_aug),
                    ])
                    print(f"[LLM] Generating overview via Ollama model={ollama_model} host={ollama_host}")
                    # Set call-scoped controls on the function (keeps signature minimal for legacy calls)
                    llm_generate_ollama._endpoint = args.ollama_endpoint
                    llm_generate_ollama._retries = args.ollama_retries
                    llm_generate_ollama._verbose = args.ollama_verbose
                    resp_ov = llm_generate_ollama(ollama_host, ollama_model, sys_overview, usr_overview, timeout=args.ollama_timeout)
                    # Save raw
                    try:
                        if resp_ov:
                            write_text(gen_dir / "overview_raw.md", resp_ov)
                    except Exception:
                        pass
                    # Expand multi-citations and strip unmapped
                    resp_ov = _expand_multi_citations(resp_ov or "")
                    unmapped_ov = _find_unmapped_tags(resp_ov, len(ev_page_items))
                    if unmapped_ov:
                        val_lines.append(f"overview: stripped unmapped tags: {sorted(set(unmapped_ov))}")
                        resp_ov = _strip_unmapped_tags(resp_ov, len(ev_page_items))
                    raw = (resp_ov or "").strip()
                    if raw:
                        body = enforce_paragraph_limits(raw, max_words=140)
                        overview_out = body
                    else:
                        overview_out = overview_out

                # History narrative via LLM (evidence-locked)
                sys_hist_narr = (
                    "You write compact, chronological historical narratives. Use only the provided EVIDENCE. "
                    "Append [S#] tags to claims that are directly supported. Forbid: first/earliest/began with/originated/invented by."
                )
                usr_hist_narr = "\n\n".join([
                    "EVIDENCE (S1..Sn):\n" + ev_block,
                    _p("history_narrative", "Write a compact narrative (3–4 short paragraphs)."),
                ])
                print(f"[LLM] Generating history_narrative via Ollama model={ollama_model} host={ollama_host}")
                llm_generate_ollama._endpoint = args.ollama_endpoint
                llm_generate_ollama._retries = args.ollama_retries
                llm_generate_ollama._verbose = args.ollama_verbose
                resp_hn = llm_generate_ollama(ollama_host, ollama_model, sys_hist_narr, usr_hist_narr, timeout=args.ollama_timeout)
                # Save raw for inspection
                try:
                    if resp_hn:
                        write_text(gen_dir / "history_narrative_raw.md", resp_hn)
                except Exception:
                    pass
                # Expand multi-citations and strip unmapped
                resp_hn = _expand_multi_citations(resp_hn or "")
                unmapped_hn = _find_unmapped_tags(resp_hn, len(ev_page_items))
                if unmapped_hn:
                    val_lines.append(f"history_narrative: stripped unmapped tags: {sorted(set(unmapped_hn))}")
                    resp_hn = _strip_unmapped_tags(resp_hn, len(ev_page_items))
                raw_hn = (resp_hn or "").strip()
                if raw_hn:
                    history_narrative_out = enforce_paragraph_limits(raw_hn, max_words=100, max_sentences=4)
                else:
                    history_narrative_out = history_narrative_out

                # History timeline via LLM (evidence-locked)
                sys_hist_tl = (
                    "Produce a concise timeline. One line per item: Year — Event — Impact [S#] when supported. "
                    "Use only the provided EVIDENCE; forbid first/earliest/originated claims."
                )
                usr_hist_tl = "\n\n".join([
                    "EVIDENCE (S1..Sn):\n" + ev_block,
                    _p("history_timeline", "Produce a compact timeline: Year — Event — Impact. 10–12 lines."),
                ])
                print(f"[LLM] Generating history_timeline via Ollama model={ollama_model} host={ollama_host}")
                llm_generate_ollama._endpoint = args.ollama_endpoint
                llm_generate_ollama._retries = args.ollama_retries
                llm_generate_ollama._verbose = args.ollama_verbose
                resp_ht = llm_generate_ollama(ollama_host, ollama_model, sys_hist_tl, usr_hist_tl, timeout=args.ollama_timeout)
                try:
                    if resp_ht:
                        write_text(gen_dir / "history_timeline_raw.md", resp_ht)
                except Exception:
                    pass
                # Expand multi-citations and strip unmapped
                resp_ht = _expand_multi_citations(resp_ht or "")
                unmapped_ht = _find_unmapped_tags(resp_ht, len(ev_page_items))
                if unmapped_ht:
                    val_lines.append(f"history_timeline: stripped unmapped tags: {sorted(set(unmapped_ht))}")
                    resp_ht = _strip_unmapped_tags(resp_ht, len(ev_page_items))
                raw_ht = (resp_ht or "").strip()
                history_timeline_out = raw_ht if raw_ht else history_timeline_out

            # If LLM failed and output is empty, ensure stub safety net
            if should_gen("overview") and not (overview_out or "").strip():
                overview_out = "⚠️ Not generated"
            if should_gen("history_narrative") and not (history_narrative_out or "").strip():
                history_narrative_out = "⚠️ Not generated"
            if should_gen("history_timeline") and not (history_timeline_out or "").strip():
                history_timeline_out = "⚠️ Not generated"

            if should_gen("overview"):
                write_text(gen_dir / "overview.md", overview_out or "")
            if should_gen("history_narrative"):
                write_text(gen_dir / "history_narrative.md", history_narrative_out or "")
            if should_gen("history_timeline"):
                write_text(gen_dir / "history_timeline.md", history_timeline_out or "")

            # Write validation log if collected
            try:
                if 'val_lines' in locals() and val_lines:
                    write_text(gen_dir / "validation_log.md", "\n".join(val_lines) + "\n")
            except Exception:
                pass

        # Ensure minimal stubs exist to keep page compile clean
        stub_map = {
            "design_patterns.md": "(design patterns not generated yet)\n",
            "methods_overview.md": "(methods & tools overview not generated yet)\n",
            "entities_explorer.md": "(entities explorer is front-end driven from cache)\n",
            "open_questions.md": "(open questions not generated yet)\n",
            "provenance.md": f"Schema: { (cache.get('schema_version') or '') }\nEntries: { len(cache.get('entries', [])) }\n",
        }
        for fname, content in stub_map.items():
            p = gen_dir / fname
            if not p.exists():
                write_text(p, content)

        # Compile final page using sections.yaml (unless --no-compile)
        if not args.no_compile:
            if not template_path.exists():
                print(f"Missing template: {template_path}")
                continue
            template = read_text(template_path)
            sections: Dict[str, str] = {}
            for sec in order:
                if enabled.get(sec, True):
                    sections[sec] = read_text(gen_dir / f"{sec}.md")
            # Remove disabled sections' header + placeholder blocks from the template
            for sec in order:
                if not enabled.get(sec, True):
                    # Pattern: a header line followed by the placeholder for this section
                    # e.g., '## Title\n{{section:sec}}' with optional whitespace
                    pat = rf"(?ms)^\s*##[^\n]*\n\s*\{{\{{section:{re.escape(sec)}\}}\}}\s*\n?"
                    template = re.sub(pat, "", template)
            compiled = substitute(template, sections)
            # Inject generation date for provenance
            compiled = compiled.replace("{{date}}", date.today().isoformat())
            # Global rewrite of [S#] -> [n] by first appearance and append a single References block
            try:
                # Rebuild the same page-level evidence pool for mapping
                # If cache is empty (e.g., when using --from-foundation), load a lightweight pillar cache
                if not (cache or {}).get("entries"):
                    try:
                        _cache_path_final = ensure_pillar_cache(pillar_dir.name[:2], pillar_name, args.include_secondary, args.max_papers, False)
                        cache = load_pillar_cache(_cache_path_final)
                    except Exception:
                        pass
                core_cache_v2_final = load_core_reviews_cache_v2()
                ev_page_items_final, _ = build_page_evidence_pool(core_cache_v2_final, cache, limit_pillar=12)
                # Fallback: if no evidence from caches, derive from index.csv for this pillar
                if not ev_page_items_final:
                    try:
                        dfp_final = df[df["pillar_primary"].fillna("").str.contains(pillar_name, case=False, na=False)].copy()
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
                compiled, refs_md = rewrite_global_citations_and_build_refs(compiled, ev_page_items_final)
                if refs_md:
                    compiled = compiled.rstrip() + "\n\n" + refs_md
            except Exception:
                pass
            # Foundation-based fallback: if [S#] remain and no References yet, use foundation evidence_list
            if TAG_RE.search(compiled or "") and "## References" not in (compiled or ""):
                try:
                    fdir = pillar_dir / "sections" / "foundation"
                    ev2: List[Dict[str, Any]] = []
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
            # Output to canonical pillar file
            # Try to find an existing pillar-02-*.md, else default name
            existing = list(pillar_dir.glob("pillar-02-*.md")) if pillar_dir.name.startswith("02") else []
            out_path = existing[0] if existing else pillar_dir / "pillar-02-design_engineering.md"
            write_text(out_path, compiled)
            print(f"Updated {out_path}")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
