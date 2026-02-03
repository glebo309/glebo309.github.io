#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Generate pillar sections by constructing the evidence directly from caches.
- Builds evidence from:
  - library/cache_for-llm/pillars/<ID>.json (pillar cache; includes secondary by default)
  - library/cache_for-llm/core_reviews/core_reviews_v2.json (core reviews cache)
- Produces markdown under pillars/<ID_*>/sections/generated/
- Optionally compiles the final pillar page from template.md and sections.yaml

Usage:
    python tools/generate_pillar_sections.py --pillar 02 \
        --ollama-endpoint auto --ollama-timeout 120 --ollama-retries 1

    python tools/generate_pillar_sections.py --pillar all

Notes:
- This script performs the LLM calls. To ensure pillar caches exist/refresh,
  run tools/build_pillar_cache.py first (it will also create foundation JSONs for auditing if desired).
"""

from __future__ import annotations

import argparse
import json
import os
import re
from datetime import date
from pathlib import Path
from typing import Dict, Any, List, Tuple

import pandas as pd
import requests

# ---------- Paths ----------
ROOT = Path(__file__).resolve().parents[1]
PILLARS_DIR = ROOT / "pillars"
LIT_DIR = ROOT / "library"
INDEX_DIR = LIT_DIR / "literature_index"
INDEX_CSV = INDEX_DIR / "index.csv"
PAPERS_CSV = INDEX_DIR / "papers.csv"
CORE_REV_CACHE_JSON_V2 = LIT_DIR / "cache_for-llm" / "core_reviews" / "core_reviews_v2.json"
CACHE_DIR = LIT_DIR / "cache_for-llm" / "pillars"

# ---------- IO utils ----------

def read_text(p: Path) -> str:
    return p.read_text(encoding="utf-8") if p.exists() else ""


def write_text(p: Path, s: str) -> None:
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(s, encoding="utf-8")

# ---------- Template helpers ----------

def substitute(template: str, sections: Dict[str, str]) -> str:
    def _rep(m):
        key = m.group(1)
        return sections.get(key, "")
    return re.sub(r"\{\{section:([^}]+)\}\}", _rep, template)

try:
    import yaml
except Exception:
    yaml = None


def load_sections_controller(pillar_dir: Path) -> tuple[list[str], dict[str, bool]]:
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
        "provenance",
    ]
    default_enabled = {k: True for k in default_order}
    cfg_path = pillar_dir / "sections" / "sections.yaml"
    if yaml is not None and cfg_path.exists():
        try:
            cfg = yaml.safe_load(cfg_path.read_text(encoding="utf-8")) or {}
            order = cfg.get("order") or default_order
            enabled = cfg.get("enabled") or {}
            for k in order:
                if k not in enabled:
                    enabled[k] = True
            order = [str(x) for x in order if x]
            return order, enabled
        except Exception:
            pass
    return default_order, default_enabled

# ---------- Citation validation helpers ----------
FORBIDDEN_RE = re.compile(r"\b(first|earliest|began with|originated|invented by)\b", re.I)
TAG_RE = re.compile(r"\[S(\d+)\]")
MULTI_TAG_RE = re.compile(r"\[(?:\s*S(\d+)\s*(?:[,;]\s*S(\d+)\s*)+|S(\d+))\]")


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
    def repl(m):
        nums = re.findall(r"S(\d+)", m.group(0))
        return "".join([f"[S{n}]" for n in nums])
    return MULTI_TAG_RE.sub(repl, text or "")


def enforce_paragraph_limits(text: str, max_words: int, max_sentences: int | None = None) -> str:
    def _clip_words(s: str, mw: int) -> str:
        words = s.split()
        return s if len(words) <= mw else " ".join(words[:mw]).rstrip()
    def _limit_sentences(s: str, ms: int) -> str:
        parts = re.split(r"(?<=[.!?])\s+", s.strip())
        return s.strip() if len(parts) <= ms else " ".join(parts[:ms]).strip()
    paras = [p for p in re.split(r"\n\s*\n+", text or "") if p.strip()]
    fixed: List[str] = []
    for p in paras:
        p2 = _clip_words(p.strip(), max_words)
        if max_sentences is not None:
            p2 = _limit_sentences(p2, max_sentences)
        fixed.append(p2)
    return "\n\n".join(fixed)

# ---------- Evidence building from caches ----------

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


def load_pillar_cache_by_id(pillar_id: str) -> dict:
    p = CACHE_DIR / f"{pillar_id}.json"
    try:
        if p.exists():
            return json.loads(p.read_text(encoding="utf-8")) or {}
    except Exception:
        return {}
    return {}


def build_page_evidence_pool(core_cache_v2: dict, pillar_cache: dict, limit_pillar: int = 12) -> Tuple[List[Dict[str, Any]], str]:
    ev_items: List[Dict[str, Any]] = []
    lines: List[str] = []
    # Core reviews items
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

# ---------- LLM plumbing (Ollama) ----------

def load_config() -> dict:
    candidates = [ROOT / "literature" / "config.yaml", ROOT / "config.yaml"]
    for p in candidates:
        if p.exists():
            try:
                if yaml is None:
                    return {}
                return yaml.safe_load(p.read_text(encoding="utf-8")) or {}
            except Exception:
                return {}
    return {}


def get_ollama(cfg: dict) -> tuple[str, str]:
    host = (((cfg or {}).get("ollama") or {}).get("host") or "").strip() or os.environ.get("OLLAMA_HOST", "")
    model = (((cfg or {}).get("ollama") or {}).get("model") or "llama3")
    return host, model


def llm_generate_ollama(host: str, model: str, system_prompt: str, user_prompt: str, timeout: int = 120) -> str:
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

    endpoint = getattr(llm_generate_ollama, "_endpoint", "auto")
    retries = getattr(llm_generate_ollama, "_retries", 1)
    verbose = getattr(llm_generate_ollama, "_verbose", False)

    def _attempt(fn, name: str) -> str:
        last = ""
        for _ in range(max(1, int(retries))):
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
    out = _attempt(_try_chat, "chat")
    if out:
        return out
    out = _attempt(_try_generate, "generate")
    if out:
        return out
    return _attempt(_try_v1chat, "v1chat")

# ---------- Main ----------

def main() -> int:
    ap = argparse.ArgumentParser(description="Generate pillar sections from pillar/core caches")
    ap.add_argument("--pillar", default="02", help="pillar ID (e.g., 02) or 'all'")
    ap.add_argument("--no-llm", action="store_true", help="skip LLM calls and only emit stubs")
    ap.add_argument("--compile", action="store_true", help="compile the final page using template.md and sections.yaml")
    # Ollama controls
    ap.add_argument("--ollama-endpoint", choices=["auto", "generate", "chat", "v1chat"], default="auto")
    ap.add_argument("--ollama-timeout", type=int, default=120)
    ap.add_argument("--ollama-retries", type=int, default=1)
    ap.add_argument("--ollama-verbose", action="store_true")
    args = ap.parse_args()

    # Resolve pillars
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

    cfg = load_config()
    ollama_host, ollama_model = get_ollama(cfg)

    core_v2 = load_core_reviews_cache_v2()

    for pillar_dir in pillars:
        pillar_id = pillar_dir.name[:2]
        gen_dir = pillar_dir / "sections" / "generated"
        gen_dir.mkdir(parents=True, exist_ok=True)

        # Evidence pool from caches (pillar + core reviews)
        pillar_cache = load_pillar_cache_by_id(pillar_id)
        evidence_items, _ = build_page_evidence_pool(core_v2, pillar_cache, limit_pillar=12)
        ev_block = evidence_block(evidence_items)

        # Defaults when skipping LLM
        overview_out = "(overview generation skipped)\n" if args.no_llm else ""
        history_narrative_out = "(history narrative generation skipped)\n" if args.no_llm else ""
        history_timeline_out = "(timeline generation skipped)\n" if args.no_llm else ""

        val_lines: List[str] = []

        if (not args.no_llm) and ollama_host:
            # Prompts
            sys_overview = (
                "Write a concise 2-paragraph overview. Use only the provided EVIDENCE. "
                "Append a citation tag like [S3] to sentences directly supported by an evidence item."
            )
            usr_overview = "\n\n".join([
                "EVIDENCE (S1..Sn):\n" + ev_block,
                "Seed: Write a concise 2-paragraph overview grounded in the above evidence.",
            ])
            llm_generate_ollama._endpoint = args.ollama_endpoint
            llm_generate_ollama._retries = args.ollama_retries
            llm_generate_ollama._verbose = args.ollama_verbose
            resp_ov = llm_generate_ollama(ollama_host, ollama_model, sys_overview, usr_overview, timeout=args.ollama_timeout)
            try:
                if resp_ov:
                    write_text(gen_dir / "overview_raw.md", resp_ov)
            except Exception:
                pass
            resp_ov = _expand_multi_citations(resp_ov or "")
            unmapped_ov = _find_unmapped_tags(resp_ov, len(evidence_items))
            if unmapped_ov:
                val_lines.append(f"overview: stripped unmapped tags: {sorted(set(unmapped_ov))}")
                resp_ov = _strip_unmapped_tags(resp_ov, len(evidence_items))
            raw = (resp_ov or "").strip()
            if raw:
                overview_out = enforce_paragraph_limits(raw, max_words=140)

            # History narrative
            sys_hist_narr = (
                "You write compact, chronological historical narratives. Use only the provided EVIDENCE. "
                "Append [S#] tags to directly supported claims. Forbid: first/earliest/began with/originated/invented by."
            )
            usr_hist_narr = "\n\n".join([
                "EVIDENCE (S1..Sn):\n" + ev_block,
                "Write a compact narrative (3–4 short paragraphs).",
            ])
            resp_hn = llm_generate_ollama(ollama_host, ollama_model, sys_hist_narr, usr_hist_narr, timeout=args.ollama_timeout)
            try:
                if resp_hn:
                    write_text(gen_dir / "history_narrative_raw.md", resp_hn)
            except Exception:
                pass
            resp_hn = _expand_multi_citations(resp_hn or "")
            unmapped_hn = _find_unmapped_tags(resp_hn, len(evidence_items))
            if unmapped_hn:
                val_lines.append(f"history_narrative: stripped unmapped tags: {sorted(set(unmapped_hn))}")
                resp_hn = _strip_unmapped_tags(resp_hn, len(evidence_items))
            raw_hn = (resp_hn or "").strip()
            if raw_hn:
                history_narrative_out = enforce_paragraph_limits(raw_hn, max_words=100, max_sentences=4)

            # History timeline
            sys_hist_tl = (
                "Produce a concise timeline. One line per item: Year — Event — Impact [S#] when supported. "
                "Use only the provided EVIDENCE; forbid first/earliest/originated claims."
            )
            usr_hist_tl = "\n\n".join([
                "EVIDENCE (S1..Sn):\n" + ev_block,
                "Produce a compact timeline: Year — Event — Impact. 10–12 lines.",
            ])
            resp_ht = llm_generate_ollama(ollama_host, ollama_model, sys_hist_tl, usr_hist_tl, timeout=args.ollama_timeout)
            try:
                if resp_ht:
                    write_text(gen_dir / "history_timeline_raw.md", resp_ht)
            except Exception:
                pass
            resp_ht = _expand_multi_citations(resp_ht or "")
            unmapped_ht = _find_unmapped_tags(resp_ht, len(evidence_items))
            if unmapped_ht:
                val_lines.append(f"history_timeline: stripped unmapped tags: {sorted(set(unmapped_ht))}")
                resp_ht = _strip_unmapped_tags(resp_ht, len(evidence_items))
            raw_ht = (resp_ht or "").strip()
            if raw_ht:
                history_timeline_out = raw_ht

        # Safety net stubs
        if not (overview_out or "").strip():
            overview_out = "⚠️ Not generated"
        if not (history_narrative_out or "").strip():
            history_narrative_out = "⚠️ Not generated"
        if not (history_timeline_out or "").strip():
            history_timeline_out = "⚠️ Not generated"

        # Write generated sections
        write_text(gen_dir / "overview.md", overview_out or "")
        write_text(gen_dir / "history_narrative.md", history_narrative_out or "")
        write_text(gen_dir / "history_timeline.md", history_timeline_out or "")

        # Write validation log if collected
        if val_lines:
            write_text(gen_dir / "validation_log.md", "\n".join(val_lines) + "\n")

        # Optional compile (opt-in)
        if args.compile:
            template_path = pillar_dir / "template.md"
            if not template_path.exists():
                print(f"Missing template: {template_path}")
            else:
                order, enabled = load_sections_controller(pillar_dir)
                template = read_text(template_path)
                sections_map: Dict[str, str] = {}
                for sec in order:
                    if enabled.get(sec, True):
                        sections_map[sec] = read_text(gen_dir / f"{sec}.md")
                for sec in order:
                    if not enabled.get(sec, True):
                        pat = rf"(?ms)^\s*##[^\n]*\n\s*\{{\{{section:{re.escape(sec)}\}}\}}\s*\n?"
                        template = re.sub(pat, "", template)
                compiled = substitute(template, sections_map)
                compiled = compiled.replace("{{date}}", date.today().isoformat())
                # No global reference remap here; foundation consumer tools can add it if needed
                write_text(pillar_dir / "compiled.md", compiled)
                print(f"Compiled: {pillar_dir / 'compiled.md'}")

        print(f"Generated sections for pillar {pillar_id}")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
