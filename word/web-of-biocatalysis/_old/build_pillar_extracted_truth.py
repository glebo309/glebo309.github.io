#!/usr/bin/env python3
"""
Build pillar extracted-truth JSON: a ground-truth evidence pack with all available, deduped evidence
for a given pillar. This is intended to be the primary input for downstream generators.

Default output: library/extracted_truth/<pillar>_extracted_truth.json
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List

try:
    import yaml  # optional, for prompts path only
except Exception:
    yaml = None  # type: ignore

# Project root is the workspace dir containing this script (.. from tools/)
ROOT = Path(__file__).resolve().parents[1]

# Align with current repo layout
LIB_DIR = ROOT / "library"
CACHE_DIR = LIB_DIR / "cache_for-llm"
PILLAR_CACHE_DIR = CACHE_DIR / "pillars"
CORE_REVIEWS_V2 = CACHE_DIR / "core_reviews" / "core_reviews_v2.json"
INDEX_CSV = LIB_DIR / "literature_index" / "papers.csv"
OUT_DIR_DEFAULT = LIB_DIR / "extracted_truth"


def _read_json(p: Path) -> Any:
    return json.loads(p.read_text(encoding="utf-8")) if p.exists() else None


def _write_json(p: Path, obj: Any) -> None:
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps(obj, ensure_ascii=False, indent=2), encoding="utf-8")


def _normalize_doi(doi: str) -> str:
    if not doi:
        return ""
    d = doi.strip().lower()
    d = re.sub(r"^https?://(dx\.)?doi\.org/", "", d)
    if d.startswith("doi:"):
        d = d[4:]
    if d.startswith("10.1002/ange."):
        d = d.replace("10.1002/ange.", "10.1002/anie.")
    return d.rstrip(".")


def _clean_year(y) -> int | None:
    if y is None:
        return None
    try:
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


@dataclass
class BuilderConfig:
    pillar: str
    years_back: int = 25
    max_evidence: int = 180
    include_core_reviews: bool = True


def _load_pillar_cache(pillar_id: str) -> List[Dict[str, Any]]:
    p = PILLAR_CACHE_DIR / f"{pillar_id}.json"
    data = _read_json(p) or {}
    if isinstance(data, dict):
        entries = data.get("entries", []) or data.get("items", []) or []
        out: List[Dict[str, Any]] = []
        for e in entries:
            m = (e.get("meta") or {}) if isinstance(e, dict) else {}
            out.append({
                "doi": (m.get("doi") or m.get("key") or ""),
                "title": (m.get("title") or ""),
                "year": (m.get("year") or ""),
                "venue": (m.get("journal") or m.get("venue") or ""),
                "salient": (e.get("salient") or []),
                "sections": (e.get("sections") or {}),
                "snippet": (e.get("abstract") or ""),
                "tags": (e.get("keywords") or []),
            })
        return out
    return []


def _collect_evidence(items: List[Dict[str, Any]], years_back: int, max_evidence: int) -> List[Dict[str, Any]]:
    now_year = datetime.now(timezone.utc).year
    filtered = []
    for it in items:
        y = _clean_year(it.get("year"))
        if y is None:
            continue
        if years_back and y < now_year - years_back:
            continue
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
            "snippet": (snippet or "").strip(),
            "source": "pillar_cache",
            "tags": list({t for t in (it.get("tags") or []) if isinstance(t, str)})
        }
        filtered.append(rec)
    # dedupe
    seen = set()
    deduped = []
    for rec in filtered:
        key = rec["doi"] or (rec["title"].lower(), rec["year"])  # fallback
        if key in seen:
            continue
        seen.add(key)
        deduped.append(rec)
    # sort deterministic
    deduped.sort(key=lambda r: (r.get("year") or 0, r.get("title", "")), reverse=True)
    return deduped[:max_evidence]


def _assign_ids(ev: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    out = []
    for i, rec in enumerate(ev, start=1):
        r = dict(rec)
        r["sid"] = i
        r["id"] = f"S{i}"
        out.append(r)
    return out


def build_extracted_truth(cfg: BuilderConfig) -> Dict[str, Any]:
    pillar_id = cfg.pillar
    items = _load_pillar_cache(pillar_id)
    evidence_raw = _collect_evidence(items, years_back=cfg.years_back, max_evidence=cfg.max_evidence)
    evidence = _assign_ids(evidence_raw)

    payload = {
        "meta": {
            "pillar_id": pillar_id,
            "version": 1,
            "generated_at": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
            "builder": "pillar_extracted_truth v0.1",
            "inputs": {
                "pillar_cache_path": str(PILLAR_CACHE_DIR / f"{pillar_id}.json"),
                "core_reviews_cache_v2_path": str(CORE_REVIEWS_V2),
                "index_csv": str(INDEX_CSV),
            }
        },
        "evidence": evidence,
        "indices": {
            "by_year_desc": [e["id"] for e in sorted(evidence, key=lambda r: (r.get("year") or 0, r.get("title", "")), reverse=True)]
        }
    }
    return payload


def main():
    ap = argparse.ArgumentParser(description="Build pillar extracted-truth JSON")
    ap.add_argument("--pillar", required=True, help="pillar ID, e.g., 02")
    ap.add_argument("--years-back", type=int, default=25)
    ap.add_argument("--max-evidence", type=int, default=180)
    ap.add_argument("--out", default="", help="output JSON path; defaults to library/extracted_truth/<pillar>_extracted_truth.json")
    args = ap.parse_args()

    cfg = BuilderConfig(
        pillar=args.pillar,
        years_back=args.years_back,
        max_evidence=args.max_evidence,
        include_core_reviews=True,
    )
    payload = build_extracted_truth(cfg)
    out_path = Path(args.out) if args.out else (OUT_DIR_DEFAULT / f"{args.pillar}_extracted_truth.json")
    _write_json(out_path, payload)
    try:
        data = json.loads(out_path.read_text(encoding="utf-8"))
        data.setdefault("meta", {})["truth_hash"] = "sha256:" + hashlib.sha256(out_path.read_bytes()).hexdigest()
        _write_json(out_path, data)
    except Exception:
        pass
    print(f"Wrote extracted truth: {out_path}")


if __name__ == "__main__":
    main()
