#!/usr/bin/env python3
"""
Build a master, LLM-assisted pillar foundation JSON with a single global evidence array (S1..Sn)
plus local-LLM extracted fragments and heuristic candidates so external large models can stitch
without additional lookup.

Output path: literature/foundations/<ID>_foundation.json
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import time
from collections import Counter, defaultdict
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Dict, List, Any

try:
    import requests
except Exception:  # allow running without network deps (will just skip LLM calls)
    requests = None  # type: ignore
try:
    import yaml
except Exception:
    yaml = None  # type: ignore

ROOT = Path(__file__).resolve().parents[2]
CACHE_DIR = ROOT / "literature" / "cache"
PILLAR_CACHE_DIR = CACHE_DIR / "pillars"
CORE_REVIEWS_V2 = CACHE_DIR / "core_reviews" / "core_reviews_v2.json"
INDEX_CSV = ROOT / "literature" / "index" / "papers.csv"
FOUNDATIONS_DIR = ROOT / "literature" / "foundations"


# ----------------------------- Helpers ---------------------------------

def _read_json(p: Path) -> Any:
    return json.loads(p.read_text(encoding="utf-8")) if p.exists() else None


def _write_json(p: Path, obj: Any) -> None:
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps(obj, ensure_ascii=False, indent=2), encoding="utf-8")


def _sha256_file(p: Path) -> str:
    if not p.exists():
        return ""
    h = hashlib.sha256()
    with p.open("rb") as f:
        for chunk in iter(lambda: f.read(65536), b""):
            h.update(chunk)
    return h.hexdigest()


def _clean_year(y) -> int | None:
    if y is None:
        return None
    try:
        # Common cases: 2021, "2021", "2005.0", 2005.0, "2005-01-01"
        if isinstance(y, int):
            yi = y
        else:
            s = str(y).strip()
            m = re.match(r"^(\d{4})", s)
            if m:
                yi = int(m.group(1))
            else:
                yi = int(float(s))
        if 1800 <= yi <= 2100:
            return yi
    except Exception:
        return None
    return None


def _normalize_doi(doi: str) -> str:
    if not doi:
        return ""
    d = doi.strip().lower()
    # strip URL prefixes and leading 'doi:'
    d = re.sub(r"^https?://(dx\.)?doi\.org/", "", d)
    if d.startswith("doi:"):
        d = d[4:]
    # unify ANGE->ANIE
    if d.startswith("10.1002/ange."):
        d = d.replace("10.1002/ange.", "10.1002/anie.")
    return d.rstrip('.')


# -------------------------- Foundation build ----------------------------

@dataclass
class BuilderConfig:
    pillar: str
    years_back: int = 25
    max_evidence: int = 180
    include_core_reviews: bool = True
    ollama_host: str | None = None
    ollama_model: str | None = None
    prompts_yaml: Path | None = None


def _load_definition_md(pillar_id: str) -> str:
    name_map = {
        "02": "02_design_engineering",
    }
    sub = name_map.get(pillar_id, f"{pillar_id}")
    md_path = ROOT / "backbone" / "pillars" / sub / "definition.md"
    return md_path.read_text(encoding="utf-8") if md_path.exists() else ""


def _load_pillar_cache(pillar_id: str) -> List[Dict[str, Any]]:
    p = PILLAR_CACHE_DIR / f"{pillar_id}.json"
    data = _read_json(p) or {}
    # Newer cache schema uses top-level key 'entries' with per-paper dicts
    if isinstance(data, dict):
        entries = data.get("entries", []) or data.get("items", []) or []
        # Normalize to a light list of dicts with common fields
        out: List[Dict[str, Any]] = []
        for e in entries:
            m = (e.get("meta") or {}) if isinstance(e, dict) else {}
            out.append({
                "doi": (m.get("doi") or m.get("key") or ""),
                "title": (m.get("title") or ""),
                "year": (m.get("year") or ""),
                "venue": (m.get("journal") or m.get("venue") or ""),
                # prefer salient if present; else try sections or chunks
                "salient": (e.get("salient") or []),
                "sections": (e.get("sections") or {}),
                "snippet": (e.get("abstract") or ""),
                "tags": (e.get("keywords") or []),
            })
        return out
    return []


def _collect_evidence(items: List[Dict[str, Any]], years_back: int, max_evidence: int) -> List[Dict[str, Any]]:
    # Filter by year
    now_year = datetime.now(timezone.utc).year
    filtered = []
    for it in items:
        y = _clean_year(it.get("year"))
        if y is None:
            continue
        if years_back and y < now_year - years_back:
            continue
        # Prefer salient text if present, and coerce to string
        raw_salient = it.get("salient")
        if isinstance(raw_salient, list):
            salient_text = " ".join([s for s in raw_salient if isinstance(s, str)])
        elif isinstance(raw_salient, str):
            salient_text = raw_salient
        else:
            salient_text = ""
        sections = it.get("sections") or {}
        sec_intro = sections.get("intro") if isinstance(sections, dict) else None
        sec_conc = sections.get("conclusion") if isinstance(sections, dict) else None
        snippet = salient_text or sec_intro or sec_conc or it.get("snippet") or ""
        if isinstance(snippet, list):
            snippet = " ".join([s for s in snippet if isinstance(s, str)])
        elif not isinstance(snippet, str):
            snippet = str(snippet) if snippet is not None else ""
        doi = _normalize_doi(it.get("doi", ""))
        rec = {
            "doi": doi,
            "title": it.get("title", "").strip(),
            "year": y,
            "venue": it.get("venue", "").strip(),
            "snippet": snippet.strip(),
            "source": "pillar_cache",
            "tags": list({t for t in (it.get("tags") or []) if isinstance(t, str)})
        }
        filtered.append(rec)
    # Deduplicate by DOI then (title, year)
    seen = set()
    deduped = []
    for rec in filtered:
        key = rec["doi"] or (rec["title"].lower(), rec["year"])  # fallback if no DOI
        if key in seen:
            continue
        seen.add(key)
        deduped.append(rec)
    # Sort deterministic: year desc, then title asc
    deduped.sort(key=lambda r: (r.get("year") or 0, r.get("title", "")), reverse=True)
    deduped = deduped[:max_evidence]
    return deduped


def _attach_core_reviews(core_reviews_v2: Dict[str, Any]) -> List[Dict[str, Any]]:
    """Adapt to v2 cache with top-level object and 'entries' list.
    Build a compact bundle from available fields: meta, topics, sections.
    """
    out: List[Dict[str, Any]] = []
    if not isinstance(core_reviews_v2, dict):
        return out
    entries = core_reviews_v2.get("entries") or []
    for e in entries:
        meta = (e.get("meta") or {})
        topics = (e.get("topics") or [])
        sections = (e.get("sections") or [])
        # Convert sections to compact key_sections with name and clipped summary
        key_sections = []
        for s in sections[:5]:
            nm = (s.get("title") or "Section").strip()
            txt = (s.get("text") or "").strip()
            if txt:
                txt = (txt.replace("\n", " ")[:420]).rstrip()
            key_sections.append({"name": nm, "summary": txt})
        doi = meta.get("doi") or e.get("id") or ""
        out.append({
            "doi": _normalize_doi(doi),
            "title": (meta.get("title") or "").strip(),
            "year": str(meta.get("year") or ""),
            "venue": (meta.get("journal") or meta.get("venue") or "").strip(),
            "authors": (meta.get("authors") or "").strip(),
            "bundle": {
                "header": (meta.get("title") or "").strip(),
                "topics": topics[:12],
                "key_sections": key_sections[:3],
            }
        })
    return out


def _assign_evidence_ids(ev: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    # Already year-desc sorted.
    out = []
    for i, rec in enumerate(ev, start=1):
        r = dict(rec)
        r["sid"] = i
        r["id"] = f"S{i}"
        out.append(r)
    return out


def _evidence_block(evidence: List[Dict[str, Any]]) -> str:
    lines = []
    for e in evidence:
        doi_part = f" — doi:{e['doi']}" if e.get("doi") else ""
        yr = e.get("year")
        if isinstance(yr, int):
            yr = str(yr)
        lines.append(f"S{e['sid']} ({yr or ''}) — {e.get('title','')}{doi_part}: { (e.get('snippet') or '') }")
    return "\n".join(lines)


def _methods_clusters(evidence: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    buckets = [
        ("microfluidic_uhts", "Microfluidic UHTS", ["droplet", "microfluid", "facs", "ultrahigh-throughput", "picodroplet"]),
        ("cast_ism", "CAST/ISM", ["cast", "iterative saturation", "site-saturation", "focused saturation"]),
        ("stabilization", "Consensus/Ancestral & Stabilization", ["consensus", "ancestral", "thermostab", "Δtm", "delta tm", "stability"]),
        ("ml_guided", "ML-guided", ["machine learning", "active learning", "surrogate", "bayes", "random forest"]),
    ]
    out: List[Dict[str, Any]] = []
    for bid, label, kws in buckets:
        refs: List[Dict[str, Any]] = []
        seen: set[tuple[str, str]] = set()
        for e in evidence:
            blob = (e.get("title", "") + " " + (e.get("snippet") or "")).lower()
            if any(kw in blob for kw in kws):
                k = (e.get("doi") or "", e.get("title") or "")
                if k in seen:
                    continue
                seen.add(k)
                refs.append({"title": e.get("title", ""), "year": str(e.get("year", "")), "doi": e.get("doi", "")})
        if refs:
            out.append({"id": bid, "label": label, "refs": refs[:4]})
    return out


def _design_pattern_candidates(evidence: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    patterns = [
        ("Tunnel widening", ["tunnel", "access channel", "exit channel"]),
        ("Consensus/Ancestral", ["consensus", "ancestral"]),
        ("Focused saturation (CAST/ISM)", ["cast", "focused saturation", "iterative saturation"]),
    ]
    out: List[Dict[str, Any]] = []
    for name, kws in patterns:
        sids: List[int] = []
        snips: List[str] = []
        for e in evidence:
            text = (e.get("title", "") + " " + (e.get("snippet") or "")).lower()
            if any(kw in text for kw in kws):
                sids.append(e["sid"])  # type: ignore[index]
                snips.append((e.get("snippet") or "")[:220])
        if len(set(sids)) >= 2:
            out.append({"pattern_hint": name, "evidence_sids": sorted(set(sids))[:6], "snippets": snips[:3]})
    return out


def _open_questions_candidates(evidence: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    keys = ["we could not", "remains unclear", "limitation", "challenge", "future work", "trade-off"]
    out: List[Dict[str, Any]] = []
    for e in evidence:
        txt = (e.get("snippet") or "").lower()
        if any(k in txt for k in keys):
            out.append({"sid": e["sid"], "text": e.get("snippet", "")})  # type: ignore[index]
    return out[:12]


def _timeline_candidates(evidence: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    out: List[Dict[str, Any]] = []
    for e in evidence:
        y = e.get("year")
        try:
            yi = int(y) if not isinstance(y, int) else y
        except Exception:
            yi = 0
        if yi:
            out.append({
                "year": yi,
                "event": (e.get("title", "")[:120]),
                "impact": "",
                "doi": e.get("doi", ""),
                "sid": e["sid"],  # type: ignore[index]
            })
    return sorted(out, key=lambda r: r["year"])[:18]


def _ollama_chat(host: str, model: str, system: str, user: str, timeout: int = 120) -> str:
    if not (requests and host and model):
        return ""
    url = host.rstrip("/") + "/api/chat"
    payload = {
        "model": model,
        "messages": [
            {"role": "system", "content": system},
            {"role": "user", "content": user},
        ],
        "stream": False,
        "options": {"num_predict": 600, "temperature": 0.2, "repeat_penalty": 1.05},
        "keep_alive": "5m",
    }
    try:
        r = requests.post(url, json=payload, timeout=timeout)
        if r.ok:
            data = r.json()
            return (data.get("message", {}) or {}).get("content", "").strip()
    except Exception:
        return ""
    return ""


def _load_prompts(p: Path) -> Dict[str, Any]:
    if yaml is None or not p.exists():
        return {}
    try:
        return yaml.safe_load(p.read_text(encoding="utf-8")) or {}
    except Exception:
        return {}


def _build_metrics(evidence: List[Dict[str, Any]], all_items_count: int) -> Dict[str, Any]:
    years = [e.get("year") for e in evidence if isinstance(e.get("year"), int)]
    by_year = Counter(years)
    by_year_list = [
        {"year": y, "n": by_year[y]} for y in sorted(by_year, reverse=True)
    ]
    median_year = 0
    if years:
        s = sorted(years)
        mid = len(s)//2
        median_year = s[mid] if len(s) % 2 == 1 else int((s[mid-1] + s[mid]) / 2)
    counts = {
        "total_papers_in_pillar_cache": int(all_items_count),
        "with_structured_extraction": int(len(evidence)),
    }
    return {
        "counts": counts,
        "by_year": by_year_list,
        "central_tendency": {"median_year": median_year},
    }


def _heuristic_entities(evidence: List[Dict[str, Any]]) -> Dict[str, Any]:
    enzymes, techniques, metrics, keywords = set(), set(), set(), set()
    for e in evidence:
        text = (e.get("snippet") or "") + " " + (e.get("title") or "")
        t = text.lower()
        # Very light heuristics
        if "reductase" in t:
            enzymes.add("reductase")
        if "nitrilase" in t:
            enzymes.add("nitrilase")
        if "consensus" in t or "ancestral" in t:
            techniques.add("consensus design")
        if "dna shuffling" in t:
            techniques.add("DNA shuffling")
        if "microfluid" in t or "droplet" in t:
            techniques.add("droplet screening")
        if "tunnel" in t or "access channel" in t:
            keywords.add("tunnel engineering")
        if "epistasis" in t:
            keywords.add("epistasis")
        if "cast" in t or "ism" in t:
            techniques.add("CAST/ISM")
        if "Δtm" in t.lower() or "delta tm" in t or "tm " in t:
            metrics.add("ΔTm")
        if " ee" in t or "enantioselectivity" in t:
            metrics.add("ee")
        if "kcat" in t or "km" in t:
            metrics.add("kcat/KM")
    return {
        "enzymes": sorted(enzymes),
        "techniques": sorted(techniques),
        "metrics": sorted(metrics),
        "keywords": sorted(keywords),
    }


def _make_indices(evidence: List[Dict[str, Any]]) -> Dict[str, Any]:
    doi_map: Dict[str, List[str]] = defaultdict(list)
    for e in evidence:
        doi = e.get("doi")
        if doi:
            doi_map[doi].append(e["id"])
    by_year_desc = [e["id"] for e in sorted(evidence, key=lambda r: (r.get("year") or 0, r.get("title", "")), reverse=True)]
    return {
        "doi_to_evidence_ids": doi_map,
        "by_year_desc": by_year_desc,
    }


def _section_slices(evidence: List[Dict[str, Any]]) -> Dict[str, Any]:
    # Simple default: overview prefers a small diverse set (first 12 from by_year_desc)
    overview_ids = [e["id"] for e in evidence[:12]]
    hist_ids = [e["id"] for e in evidence[:20]]
    return {
        "overview": {
            "preferred_evidence_ids": overview_ids,
            "notes": "Favor one stability, one focusing tactic, one throughput example."
        },
        "history": {
            "preferred_evidence_ids": hist_ids,
            "notes": "Chronological selection with review waypoints."
        }
    }


def build_foundation(cfg: BuilderConfig) -> Dict[str, Any]:
    pillar_id = cfg.pillar
    items = _load_pillar_cache(pillar_id)
    evidence_raw = _collect_evidence(items, years_back=cfg.years_back, max_evidence=cfg.max_evidence)
    evidence = _assign_evidence_ids(evidence_raw)
    ev_block = _evidence_block(evidence)

    core_reviews = _read_json(CORE_REVIEWS_V2) if cfg.include_core_reviews else {}
    # Heuristic enrichments
    methods_clusters = _methods_clusters(evidence)
    design_cands = _design_pattern_candidates(evidence)
    openq_cands = _open_questions_candidates(evidence)
    timeline = _timeline_candidates(evidence)

    # Local LLM fragments for overview (optional)
    prompts = _load_prompts(cfg.prompts_yaml) if cfg.prompts_yaml else {}
    lx = (prompts.get("local_extractors") or {}) if isinstance(prompts, dict) else {}
    def _sys(tag: str) -> str:
        return (
            "You write compact, precise scientific text. Use only the provided EVIDENCE. "
            "End EVERY sentence with [S#]. Forbid: first/earliest/began with/invented by."
        )
    definition_text = _load_definition_md(pillar_id)
    # pack user content with DEFINITION + optional compact core bundles + EVIDENCE block
    core_attached = []
    for cr in _attach_core_reviews(core_reviews)[:3]:
        sec = "; ".join([f"{ks['name']}: {ks['summary']}" for ks in cr.get("bundle", {}).get("key_sections", [])[:2]])
        core_attached.append(f"- {cr.get('title','')}: {sec}")
    core_bundle = ("CORE_REVIEW_BUNDLES:\n" + "\n".join(core_attached) + "\n\n") if core_attached else ""
    def _pack_user(task_text: str) -> str:
        return "\n".join([
            "DEFINITION:\n" + (definition_text.strip()[:900] if definition_text else "(none)") + "\n",
            core_bundle,
            "EVIDENCE (S1..Sn):\n" + ev_block + "\n",
            "TASK:\n" + (task_text or ""),
        ])

    intro_p = (lx.get("overview_intro") or {}).get("prompt", "Write 2–3 sentences …")
    examples_p = (lx.get("overview_examples") or {}).get("prompt", "Write 2–3 sentences …")
    when_p = (lx.get("overview_when") or {}).get("prompt", "Write 2–3 sentences …")
    ml_p = (lx.get("overview_ml_integration") or {}).get("prompt", "Write 2–3 sentences …")
    frag_intro = _ollama_chat(cfg.ollama_host or "", cfg.ollama_model or "", _sys("intro"), _pack_user(intro_p))
    frag_examples = _ollama_chat(cfg.ollama_host or "", cfg.ollama_model or "", _sys("examples"), _pack_user(examples_p))
    frag_when = _ollama_chat(cfg.ollama_host or "", cfg.ollama_model or "", _sys("when"), _pack_user(when_p))
    frag_ml = _ollama_chat(cfg.ollama_host or "", cfg.ollama_model or "", _sys("ml"), _pack_user(ml_p))

    foundation = {
        "meta": {
            "pillar_id": pillar_id,
            "pillar_name": "Design & Engineering" if pillar_id == "02" else pillar_id,
            "version": 1,
            "generated_at": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
            "foundation_hash": "",
            "builder": "foundation_builder v0.2",
            "inputs": {
                "definition_md_path": str(ROOT / "backbone" / "pillars" / ("02_design_engineering" if pillar_id == "02" else pillar_id) / "definition.md"),
                "pillar_cache_path": str(PILLAR_CACHE_DIR / f"{pillar_id}.json"),
                "core_reviews_cache_v2_path": str(CORE_REVIEWS_V2),
                "prompts_yaml_path": str(cfg.prompts_yaml) if cfg.prompts_yaml else "",
                "ollama_host": cfg.ollama_host or "",
                "ollama_model": cfg.ollama_model or "",
            }
        },
        "definition": {"text_md": definition_text},
        "core_reviews": _attach_core_reviews(core_reviews),
        "metrics": _build_metrics(evidence, all_items_count=len(items)),
        "methods": {"clusters": methods_clusters},
        "history": {"phases": [], "timeline_candidates": timeline},
        "design_patterns_candidates": design_cands,
        "open_questions_candidates": openq_cands,
        "entities": _heuristic_entities(evidence),
        "evidence": evidence,
        "evidence_block": ev_block,
        "indices": _make_indices(evidence),
        "section_slices": {
            "overview": {
                "sids": [e["sid"] for e in evidence[:12]],
                "fragments": {
                    "intro": frag_intro or "",
                    "examples": frag_examples or "",
                    "when": frag_when or "",
                    "ml_integration": frag_ml or "",
                }
            }
        },
        "provenance": {
            "dedupe_rules": [["10.1002/ange.", "10.1002/anie."]],
            "normalizers": ["lowercase_doi", "strip_trailing_punct"],
            "hashes": {
                "pillar_cache": _sha256_file(PILLAR_CACHE_DIR / f"{pillar_id}.json"),
                "core_reviews_v2": _sha256_file(CORE_REVIEWS_V2),
                "definition_md": _sha256_file(ROOT / "backbone" / "pillars" / ("02_design_engineering" if pillar_id == "02" else pillar_id) / "definition.md"),
                "prompts_yaml": _sha256_file(cfg.prompts_yaml) if cfg.prompts_yaml else "",
            },
            "selector_defaults": {
                "min_confidence": 0.55,
                "max_snippet_chars": 900,
                "rank_formula": "0.45*recency + 0.35*confidence + 0.20*metric_signal",
                "years_back_default": cfg.years_back,
            },
            "llm": {
                "host": cfg.ollama_host or "",
                "model": cfg.ollama_model or "",
                "endpoint": "chat",
                "timeout_s": 120,
                "retries": 2,
            }
        }
    }
    return foundation


def main():
    ap = argparse.ArgumentParser(description="Build master pillar foundation JSON (LLM-assisted)")
    ap.add_argument("--pillar", required=True, help="pillar ID, e.g., 02")
    ap.add_argument("--years-back", type=int, default=25)
    ap.add_argument("--max-evidence", type=int, default=40)
    ap.add_argument("--include-core-reviews", action="store_true", help="include core review bundles (default true)")
    ap.add_argument("--ollama-host", default=os.environ.get("OLLAMA_HOST", "http://127.0.0.1:11434"))
    ap.add_argument("--ollama-model", default=os.environ.get("OLLAMA_MODEL", "qwen3:4b"))
    ap.add_argument("--prompts", default=str(ROOT / "backbone" / "pillars" / "02_design_engineering" / "sections" / "prompts.yaml"))
    ap.add_argument("--out", required=True, help="output JSON path under literature/foundations/")
    args = ap.parse_args()

    cfg = BuilderConfig(
        pillar=args.pillar,
        years_back=args.years_back,
        max_evidence=args.max_evidence,
        include_core_reviews=True if args.include_core_reviews or True else False,  # default True
        ollama_host=args.ollama_host,
        ollama_model=args.ollama_model,
        prompts_yaml=Path(args.prompts) if args.prompts else None,
    )
    foundation = build_foundation(cfg)
    out_path = Path(args.out)
    _write_json(out_path, foundation)
    # set overall foundation hash
    try:
        data = json.loads(out_path.read_text(encoding="utf-8"))
        data["meta"]["foundation_hash"] = "sha256:" + hashlib.sha256(out_path.read_bytes()).hexdigest()
        _write_json(out_path, data)
    except Exception:
        pass
    print(f"Wrote foundation: {out_path}")


if __name__ == "__main__":
    main()
