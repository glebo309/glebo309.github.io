#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Build core_reviews caches from TEI XMLs.

- v1:  literature/cache/core_reviews/core_reviews.json
- v2:  literature/cache/core_reviews/core_reviews_v2.json

Usage (fast, no LLM):
  python3 literature/tools/build_core_reviews_cache.py \
    --tei-dir backbone/core_reviews/tei --v2

Add LLM enrichment later with --enrich-llm (requires Ollama).
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import sys
from datetime import datetime
from pathlib import Path
from typing import List, Dict, Any, Optional
import xml.etree.ElementTree as ET

# -------- Paths --------
# ROOT should point to the project root (the directory containing this 'tools/' folder).
# The file path is: <ROOT>/tools/build_core_reviews_cache.py, so go up 1 level.
ROOT = Path(__file__).resolve().parents[1]
DEFAULT_TEI_DIR = ROOT / "backbone" / "core_reviews" / "tei"
# Write caches where the pillar generator reads them by default
DEFAULT_OUT_V1 = ROOT / "library" / "cache_for-llm" / "core_reviews" / "core_reviews.json"
DEFAULT_OUT_V2 = ROOT / "library" / "cache_for-llm" / "core_reviews" / "core_reviews_v2.json"

# -------- Regex --------
DOI_RE = re.compile(r"10\.\d{4,9}/\S+", re.I)
YEAR_RE = re.compile(r"(19|20)\d{2}")

# -------- TEI helpers (namespace-agnostic) --------
def _text(el: Optional[ET.Element]) -> str:
    if el is None:
        return ""
    try:
        return " ".join("".join(el.itertext()).split())
    except Exception:
        return " ".join((el.text or "").split())

def _norm_space(s: str) -> str:
    return re.sub(r"\s+", " ", (s or "").strip())

def _localname(tag: Optional[str]) -> str:
    if not tag:
        return ""
    return tag.rsplit("}", 1)[-1] if "}" in tag else tag

def _desc_by_local(root: ET.Element, name: str) -> List[ET.Element]:
    return [el for el in root.iter() if _localname(el.tag) == name]

def _children_by_local(root: ET.Element, name: str) -> List[ET.Element]:
    return [ch for ch in list(root) if _localname(ch.tag) == name]

def _first_by_local(root: ET.Element, name: str) -> Optional[ET.Element]:
    for el in root.iter():
        if _localname(el.tag) == name:
            return el
    return None

# -------- Field extractors --------
def _extract_authors(tei: ET.Element) -> str:
    out: List[str] = []
    for pers in _desc_by_local(tei, "persName"):
        surname = _norm_space(_text(_first_by_local(pers, "surname")))
        forename = _norm_space(_text(_first_by_local(pers, "forename")))
        nm = ", ".join([x for x in [surname, forename] if x])
        if nm:
            out.append(nm)
    if not out:
        for aut in _desc_by_local(tei, "author"):
            nm = _norm_space(_text(aut))
            if nm:
                out.append(nm)
    # order-preserving dedupe
    seen = set()
    uniq: List[str] = []
    for a in out:
        if a not in seen:
            seen.add(a)
            uniq.append(a)
    return "; ".join(uniq[:25])

def _strip_doi_tail(d: str) -> str:
    return d.rstrip(".,;:)\n\r\t ")

def _extract_doi(tei: ET.Element) -> str:
    # Prefer explicit idno(type=doi)
    for idno in _desc_by_local(tei, "idno"):
        typ = ((idno.get("type") or idno.get("subtype") or "")).lower()
        if "doi" in typ:
            cand = _strip_doi_tail(_text(idno))
            m = DOI_RE.search(cand)
            if m:
                return _strip_doi_tail(m.group(0))
            if cand.lower().startswith("10."):
                return _strip_doi_tail(cand)
    # Fallback: scan all refs/notes
    blobs: List[str] = []
    for tag in ("ref", "note", "bibl", "biblStruct", "listBibl"):
        for el in _desc_by_local(tei, tag):
            t = _text(el)
            if t:
                blobs.append(t)
    blob = " \n".join(blobs)
    m = DOI_RE.search(blob)
    return _strip_doi_tail(m.group(0)) if m else ""

def _extract_title(tei: ET.Element) -> str:
    header = _first_by_local(tei, "teiHeader")
    if header is not None:
        for el in _desc_by_local(header, "title"):
            t = _norm_space(_text(el))
            if t:
                return t
    front = _first_by_local(tei, "front")
    if front is not None:
        doc = _first_by_local(front, "docTitle")
        if doc is not None:
            parts = _desc_by_local(doc, "titlePart")
            if parts:
                t = _norm_space(" ".join(_text(p) for p in parts if _text(p)))
                if t:
                    return t
            t = _norm_space(_text(_first_by_local(doc, "title")))
            if t:
                return t
    for el in _desc_by_local(tei, "title"):
        t = _norm_space(_text(el))
        if t:
            return t
    return ""

def _extract_journal(tei: ET.Element) -> str:
    for el in _desc_by_local(tei, "title"):
        lvl = (el.get("level") or "").lower()
        if lvl in ("j", "journal"):
            t = _norm_space(_text(el))
            if t:
                return t
    for el in _desc_by_local(tei, "monogr"):
        t = _norm_space(_text(el))
        if t:
            return t
    # last resort: any title
    for el in _desc_by_local(tei, "title"):
        t = _norm_space(_text(el))
        if t:
            return t
    return ""

def _extract_year(tei: ET.Element, fallback_from_name: str = "") -> str:
    for date_el in _desc_by_local(tei, "date"):
        when = (date_el.get("when") or "").strip()
        if when and YEAR_RE.match(when[:4]):
            return when[:4]
        val = _text(date_el)
        m = YEAR_RE.search(val)
        if m:
            return m.group(0)
    m = YEAR_RE.search(fallback_from_name)
    return m.group(0) if m else ""

def _extract_snippet(tei: ET.Element) -> str:
    abstract = _first_by_local(tei, "abstract")
    if abstract is not None:
        for p in _desc_by_local(abstract, "p"):
            s = _norm_space(_text(p))
            if s:
                return s[:280]
    body = _first_by_local(tei, "body")
    if body is not None:
        for p in _desc_by_local(body, "p"):
            s = _norm_space(_text(p))
            if s:
                return s[:280]
    return ""

def _extract_keywords(tei: ET.Element) -> List[str]:
    topics: List[str] = []
    for kw in _desc_by_local(tei, "keywords"):
        for term in _desc_by_local(kw, "term"):
            t = _norm_space(_text(term))
            if t:
                topics.append(t)
    if not topics:
        fronts = []
        fr = _first_by_local(tei, "front")
        if fr is not None:
            fronts.append(fr)
        ab = _first_by_local(tei, "abstract")
        if ab is not None:
            fronts.append(ab)
        for blk in fronts:
            full = _text(blk)
            m = re.search(r"(?im)^\s*keywords\s*[:\-]\s*(.+)$", full)
            if m:
                raw = m.group(1)
                cand = re.split(r"\s*[;，,]\s*", raw)
                topics = [c.strip().strip('.') for c in cand if c.strip()]
                break
    seen = set()
    out: List[str] = []
    for t in topics:
        k = t.lower()
        if k not in seen:
            seen.add(k)
            out.append(t)
    return out[:40]

def _collect_text(el: ET.Element, max_chars: int = 1200) -> str:
    chunks: List[str] = []
    ps = _desc_by_local(el, "p")
    if ps:
        for p in ps:
            s = _norm_space(_text(p))
            if s:
                chunks.append(s)
                if sum(len(c) for c in chunks) >= max_chars:
                    break
    else:
        s = _norm_space(_text(el))
        if s:
            chunks.append(s)
    joined = "\n\n".join(chunks)
    return joined[:max_chars]

def _extract_sections(tei: ET.Element) -> List[Dict[str, Any]]:
    sections: List[Dict[str, Any]] = []
    body = _first_by_local(tei, "body")
    if body is None:
        return sections
    def walk(div: ET.Element, level: int = 1):
        head = None
        for ch in list(div):
            if _localname(ch.tag) == "head":
                head = ch; break
        title = _norm_space(_text(head))
        content = _collect_text(div, max_chars=1500)
        if not title:
            first = content.split(". ", 1)[0] or content[:80]
            title = _norm_space(first[:120])
        if title or content:
            sections.append({"title": title, "level": level, "text": content})
        for child in list(div):
            if _localname(child.tag) == "div":
                walk(child, level + 1)
    for top in _children_by_local(body, "div"):
        walk(top, 1)
    if not sections:
        sections.append({"title": "Body", "level": 1, "text": _collect_text(body, max_chars=1500)})
    return sections[:60]

# -------- v1 parsing --------
def parse_tei_file(path: Path) -> Dict[str, Any]:
    try:
        tree = ET.parse(str(path))
        tei = tree.getroot()
    except Exception as e:
        sys.stderr.write(f"Failed to parse TEI: {path.name}: {e}\n")
        return {}
    title = _extract_title(tei)
    authors = _extract_authors(tei)
    doi = _extract_doi(tei)
    journal = _extract_journal(tei)
    year = _extract_year(tei, fallback_from_name=path.name)
    snippet = _extract_snippet(tei)
    topics = _extract_keywords(tei)
    sections = _extract_sections(tei)
    try:
        rel_tei = str(path.resolve().relative_to(ROOT))
    except Exception:
        rel_tei = path.name
    return {
        "id": doi or path.stem,
        "meta": {
            "title": title,
            "year": year,
            "doi": doi,
            "journal": journal,
            "authors": authors,
        },
        "salient": [snippet] if snippet else [],
        "topics": topics,
        "sections": sections,
        "source": "core_review",
        "tei_path": rel_tei,
    }

def build_core_reviews_cache(tei_dir: Path, progress: bool = False) -> Dict[str, Any]:
    entries: List[Dict[str, Any]] = []
    files = sorted(tei_dir.glob("*.tei.xml"))
    total = len(files)
    for i, p in enumerate(files, 1):
        if progress:
            print(f"[v1] {i}/{total} {p.name}", flush=True)
        rec = parse_tei_file(p)
        if rec:
            entries.append(rec)
    # stable ordering helps diffs & deterministic prompts
    entries.sort(key=lambda e: (-(int(e["meta"]["year"]) if str(e["meta"]["year"]).isdigit() else 0),
                                e["meta"]["title"]))
    return {
        "schema_version": "1.0",
        "generated": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        "entries": entries,
    }

# -------- v2 enrichment layer --------
def _sha256_file(p: Path) -> str:
    h = hashlib.sha256()
    try:
        with p.open('rb') as f:
            for chunk in iter(lambda: f.read(8192), b''):
                h.update(chunk)
    except Exception:
        return ""
    return h.hexdigest()

def _extract_citations(tei: ET.Element) -> List[Dict[str, str]]:
    items: List[Dict[str, str]] = []
    text = []
    for tag in ("listBibl", "biblStruct", "bibl", "ref", "note", "ptr"):
        for el in _desc_by_local(tei, tag):
            t = _text(el)
            if t:
                text.append(t)
    blob = " \n".join(text)
    for m in DOI_RE.finditer(blob):
        d = _strip_doi_tail(m.group(0))
        items.append({"doi": d, "normalized": d.lower()})
    seen = set()
    out = []
    for it in items:
        k = it["normalized"]
        if k not in seen:
            seen.add(k)
            out.append(it)
    return out[:200]

def _llm_generate_ollama(host: str, model: str, system_prompt: str, user_prompt: str,
                         timeout: int = 60,
                         endpoint: str = "auto",
                         retries: int = 0,
                         verbose: bool = False) -> str:
    try:
        import requests
    except Exception as e:
        sys.stderr.write(f"LLM call setup error (requests missing): {e}\n")
        return ""
    base = host.rstrip('/')
    sys_txt = system_prompt.strip()
    usr_txt = user_prompt.strip()

    def try_generate():
        url = base + '/api/generate'
        payload = {
            "model": model,
            "prompt": f"<|system|>\n{sys_txt}\n<|user|>\n{usr_txt}",
            "stream": False,
            "options": {"num_predict": 300, "temperature": 0.2, "repeat_penalty": 1.05},
            "keep_alive": "5m",
        }
        r = requests.post(url, json=payload, timeout=timeout)
        if r.status_code == 200:
            js = r.json()
            return (js.get("response") or js.get("data") or "").strip()
        if verbose:
            sys.stderr.write(f"/api/generate -> {r.status_code}: {r.text[:200]}\n")
        if r.status_code != 404:
            r.raise_for_status()
        return None

    def try_chat():
        url = base + '/api/chat'
        payload = {
            "model": model,
            "messages": [
                {"role": "system", "content": sys_txt},
                {"role": "user", "content": usr_txt},
            ],
            "stream": False,
            "options": {"num_predict": 300, "temperature": 0.2, "repeat_penalty": 1.05},
            "keep_alive": "5m",
        }
        r = requests.post(url, json=payload, timeout=timeout)
        if r.status_code == 200:
            js = r.json() or {}
            msg = js.get("message") or {}
            content = msg.get("content")
            if isinstance(content, list):
                return "".join(part.get("content", "") for part in content).strip()
            return (content or "").strip()
        if verbose:
            sys.stderr.write(f"/api/chat -> {r.status_code}: {r.text[:200]}\n")
        if r.status_code != 404:
            r.raise_for_status()
        return None

    def try_openai():
        url = base + '/v1/chat/completions'
        payload = {
            "model": model,
            "messages": [
                {"role": "system", "content": sys_txt},
                {"role": "user", "content": usr_txt},
            ],
            "stream": False,
        }
        r = requests.post(url, json=payload, timeout=timeout)
        if r.status_code == 200:
            js = r.json() or {}
            choices = js.get("choices") or []
            if choices:
                return (choices[0].get("message", {}) or {}).get("content", "") or ""
        if verbose:
            sys.stderr.write(f"/v1/chat/completions -> {r.status_code}: {r.text[:200]}\n")
        if r.status_code != 404:
            r.raise_for_status()
        return None

    order = ["generate", "chat", "openai"] if endpoint == "auto" else [endpoint]
    attempt = 0
    while True:
        attempt += 1
        for ep in order:
            try:
                if ep == "generate":
                    out = try_generate()
                elif ep == "chat":
                    out = try_chat()
                else:
                    out = try_openai()
                if out:
                    return out
            except Exception as e:
                if verbose:
                    sys.stderr.write(f"LLM endpoint {ep} error: {e}\n")
                continue
        if attempt > max(0, retries):
            break
        # small backoff
        try:
            import time as _t
            _t.sleep(min(2 * attempt, 5))
        except Exception:
            pass
    sys.stderr.write("LLM call failed: tried " + ", ".join(f"/{'api/' if ep!='openai' else 'v1/'}{'chat' if ep=='chat' else ('generate' if ep=='generate' else 'chat/completions')}" for ep in order) + "\n")
    return ""

def _pick_available_model(host: str, requested: Optional[str]) -> Optional[str]:
    if not host:
        return requested
    try:
        import requests
        url = host.rstrip('/') + '/api/tags'
        r = requests.get(url, timeout=8)
        r.raise_for_status()
        names = [m.get('name') for m in (r.json().get('models') or []) if m.get('name')]
        if not names:
            return requested
        if requested and requested in names:
            return requested
        for pref in ['qwen3:4b','qwen2.5:7b','gemma3:4b','deepseek-r1:7b','llama3','llama3.1','phi4','mistral:7b']:
            for n in names:
                if pref in n:
                    sys.stderr.write(f"Using available Ollama model: {n}\n")
                    return n
        return names[0]
    except Exception:
        return requested

def _distill_summary_llm(host: str, model: str, title: str, sections: List[Dict[str, Any]],
                         endpoint: str = "auto", timeout: int = 90, retries: int = 1, verbose: bool = False) -> str:
    text = "\n\n".join((s.get("text") or "")[:600] for s in sections[:3])
    sys_p = "You are a scientific editor. Produce a 200–300 word, structured abstract that is clear and non-redundant."
    usr_p = f"Title: {title}\nBody snippets:\n{text}\n\nWrite a structured abstract with 3 short paragraphs: Background; Advances; Outlook."
    out = _llm_generate_ollama(host, model, sys_p, usr_p, timeout=timeout, endpoint=endpoint, retries=retries, verbose=verbose)
    return out[:1600]

def _distill_section_summaries_llm(host: str, model: str, sections: List[Dict[str, Any]], max_sections: int = 4,
                                   endpoint: str = "auto", timeout: int = 90, retries: int = 1, verbose: bool = False) -> List[Dict[str, str]]:
    res: List[Dict[str, str]] = []
    for s in sections[:max_sections]:
        title = s.get("title") or "Section"
        txt = (s.get("text") or "")[:800]
        sys_p = "Summarize the section in 3–4 sentences: what it covers, what is emphasized, and why it matters."
        usr_p = f"Title: {title}\nText:\n{txt}"
        summ = _llm_generate_ollama(host, model, sys_p, usr_p, timeout=timeout, endpoint=endpoint, retries=retries, verbose=verbose)
        if not summ.strip():
            seg = txt.split(". ")
            synth = ". ".join(seg[:2]).strip()
            summ = (synth[:420] + ("…" if len(synth) > 420 else "")) if synth else txt[:420]
        res.append({"title": title, "summary": summ[:800]})
    return res

def _extract_concepts_llm(host: str, model: str, sections: List[Dict[str, Any]],
                          endpoint: str = "auto", timeout: int = 60, retries: int = 1, verbose: bool = False) -> List[Dict[str, Any]]:
    blob = "\n\n".join((s.get("text") or "")[:400] for s in sections[:6])
    sys_p = "Extract key concepts, techniques, and enzyme classes as a JSON list of objects with fields: term, canonical (if applicable), aliases (optional)."
    usr_p = f"Text:\n{blob}\nReturn JSON only."
    resp = _llm_generate_ollama(host, model, sys_p, usr_p, timeout=timeout, endpoint=endpoint, retries=retries, verbose=verbose)
    try:
        data = json.loads(resp)
        if isinstance(data, list):
            return data[:40]
    except Exception:
        pass
    return []

def _tag_roles_llm(host: str, model: str, sections: List[Dict[str, Any]], max_sections: int = 10,
                   endpoint: str = "auto", timeout: int = 60, retries: int = 1, verbose: bool = False) -> List[Dict[str, Any]]:
    res = []
    for s in sections[:max_sections]:
        title = s.get("title") or "Section"
        txt = (s.get("text") or "")[:400]
        sys_p = "Assign role tags to the section: choose from [intro, methods, results, perspective, future_outlook]. Return JSON array."
        usr_p = f"Title: {title}\nText: {txt}\nRespond as JSON array of strings."
        tags = []
        try:
            parsed = json.loads(_llm_generate_ollama(host, model, sys_p, usr_p,
                                                     timeout=timeout, endpoint=endpoint,
                                                     retries=retries, verbose=verbose) or "[]")
            if isinstance(parsed, list):
                tags = [str(t) for t in parsed][:5]
        except Exception:
            tags = []
        res.append({"section_title": title, "tags": tags})
    return res

def _build_prompt_bundle(title: str, year: str, journal: str,
                         topics: List[str],
                         sections: List[Dict[str, Any]],
                         section_summaries: List[Dict[str, str]]) -> Dict[str, Any]:
    y = (year or "").strip()
    j = (journal or "").strip()
    hdr_tail = f"{y}{', ' + j if j else ''}" if y or j else ""
    header = f"{title}{' (' + hdr_tail + ')' if hdr_tail else ''}"

    def pick(fallback_idx: int) -> str:
        if section_summaries:
            return (section_summaries[min(fallback_idx, len(section_summaries)-1)].get("summary") or "")
        if sections:
            return (sections[min(fallback_idx, len(sections)-1)].get("text") or "")[:300]
        return ""

    return {
        "header": header,
        "topics": topics[:8],
        "key_sections": [
            {"name": "Background",     "summary": pick(0)},
            {"name": "Key advances",   "summary": pick(1)},
            {"name": "Future outlook", "summary": pick(2)},
        ],
    }

def _fallback_section_summaries(sections: List[Dict[str, Any]], max_sections: int = 6) -> List[Dict[str, str]]:
    out: List[Dict[str, str]] = []
    for s in sections[:max_sections]:
        title = s.get("title") or "Section"
        txt = (s.get("text") or "").strip()
        if not txt:
            out.append({"title": title, "summary": ""}); continue
        seg = re.split(r"(?<=[.!?])\s+", txt)
        synth = " ".join(seg[:2]).strip()
        summary = (synth[:420] + ("…" if len(synth) > 420 else "")) if synth else txt[:420]
        out.append({"title": title, "summary": summary})
    return out

def upgrade_to_v2(entry_v1: Dict[str, Any],
                  tei_path_abs: Path,
                  tei_root: ET.Element,
                  llm_host: Optional[str],
                  llm_model: Optional[str],
                  enrich_llm: bool,
                  llm_endpoint: str = "auto",
                  llm_timeout: int = 90,
                  llm_retries: int = 1,
                  llm_verbose: bool = False,
                  llm_fail_fast: bool = False) -> Dict[str, Any]:
    e = dict(entry_v1)
    meta = e.get("meta", {})
    sections = e.get("sections", [])
    topics = e.get("topics", [])

    e["hash"] = {"tei_sha256": _sha256_file(tei_path_abs), "tei_bytes": tei_path_abs.stat().st_size if tei_path_abs.exists() else 0}
    e.setdefault("raw", {})
    e["raw"]["topics"] = topics
    e["raw"]["sections"] = sections
    e["raw"]["citations"] = _extract_citations(tei_root)

    e.setdefault("llm", {})
    if enrich_llm and llm_host and llm_model:
        summ = _distill_summary_llm(llm_host, llm_model, meta.get("title", ""), sections,
                                    endpoint=llm_endpoint, timeout=llm_timeout, retries=llm_retries, verbose=llm_verbose)
        if not summ and llm_fail_fast:
            # switch to fallback mode for entire entry
            enrich_llm = False
        else:
            e["llm"]["summary"] = summ
            e["llm"]["section_summaries"] = _distill_section_summaries_llm(llm_host, llm_model, sections,
                                                                             endpoint=llm_endpoint, timeout=llm_timeout, retries=llm_retries, verbose=llm_verbose)
            e["llm"]["concept_map"] = _extract_concepts_llm(llm_host, llm_model, sections,
                                                               endpoint=llm_endpoint, timeout=llm_timeout, retries=llm_retries, verbose=llm_verbose)
            e["llm"]["roles"] = _tag_roles_llm(llm_host, llm_model, sections,
                                                 endpoint=llm_endpoint, timeout=llm_timeout, retries=llm_retries, verbose=llm_verbose)
        e["llm"]["vocab_map"] = {}
        e["llm"]["seeds"] = {"model": llm_model, "built": datetime.now().strftime("%Y-%m-%d"), "temperature": 0.2}
    else:
        e["llm"]["summary"] = (e.get("salient") or [""])[0]
        e["llm"]["section_summaries"] = _fallback_section_summaries(sections)
        e["llm"]["concept_map"] = []
        e["llm"]["roles"] = []
        e["llm"]["vocab_map"] = {}
        e["llm"]["seeds"] = {}

    e["vector"] = {
        "embed_model": "none",
        "sections": [
            {"ref": f"raw.sections[{i}]", "embedding": [], "cluster": None, "len": len((s.get("text") or ""))}
            for i, s in enumerate(sections[:12])
        ],
        "section_summaries": [
            {"ref": f"llm.section_summaries[{i}]", "embedding": [], "cluster": None, "len": len((s.get("summary") or ""))}
            for i, s in enumerate(e["llm"].get("section_summaries", [])[:12])
        ],
    }

    e.setdefault("bundles", {})
    e["bundles"]["prompt_ready"] = _build_prompt_bundle(
        meta.get("title", ""), meta.get("year", ""), meta.get("journal", ""),
        topics, sections, e["llm"].get("section_summaries", [])
    )

    e["provenance"] = {
        "tei_extractor": "v1.4",
        "llm_enricher": "on" if enrich_llm else "off",
        "embedding_index": "none",
        "updated": datetime.now().strftime("%Y-%m-%dT%H:%M:%S")
    }
    return e

# -------- CLI --------
def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--tei-dir", default=str(DEFAULT_TEI_DIR), help="Directory containing TEI XML files")
    ap.add_argument("--out", default="", help="Output JSON path (v1 or v2). If omitted: v1->core_reviews.json, v2->core_reviews_v2.json")
    ap.add_argument("--v2", action="store_true", help="Emit multi-layer v2 schema")
    ap.add_argument("--enrich-llm", action="store_true", help="Run LLM distillation (summary, section_summaries, concept_map, roles)")
    ap.add_argument("--ollama-host", default=os.environ.get("OLLAMA_HOST", ""), help="Ollama host, e.g. http://localhost:11434")
    ap.add_argument("--ollama-model", default="llama3", help="Ollama model name")
    ap.add_argument("--progress", action="store_true", help="Print progress lines during parsing/enrichment")
    # LLM controls
    ap.add_argument("--llm-endpoint", default="auto", choices=["auto", "generate", "chat", "openai"], help="Which Ollama API to use for generation")
    ap.add_argument("--llm-timeout", type=int, default=90, help="Per-request timeout in seconds for LLM calls")
    ap.add_argument("--llm-retries", type=int, default=1, help="Number of retry rounds across endpoints when LLM call fails")
    ap.add_argument("--llm-verbose", action="store_true", help="Verbose logging for LLM HTTP calls and errors")
    ap.add_argument("--fail-fast-llm", dest="fail_fast_llm", action="store_true", help="If first summary call fails, switch this entry to fallback mode")
    args = ap.parse_args()

    tei_dir = Path(args.tei_dir)
    if not tei_dir.exists():
        sys.stderr.write(f"TEI dir not found: {tei_dir}\n")
        return 2

    # Decide output path
    if args.out:
        out_path = Path(args.out)
    else:
        out_path = DEFAULT_OUT_V2 if args.v2 else DEFAULT_OUT_V1
    out_path.parent.mkdir(parents=True, exist_ok=True)

    # Build v1
    v1 = build_core_reviews_cache(tei_dir, progress=args.progress)

    if args.v2:
        llm_host = (args.ollama_host or "").strip()
        llm_model = _pick_available_model(llm_host, (args.ollama_model or "").strip()) if llm_host else (args.ollama_model or "").strip()
        # Echo effective LLM config for clarity
        print(f"[llm] host={llm_host or '(none)'} model={llm_model or '(none)'} "
              f"endpoint={args.llm_endpoint} timeout={args.llm_timeout}s retries={args.llm_retries}", flush=True)
        v2_entries = []
        total = len(v1.get("entries", []))
        for idx, e in enumerate(v1.get("entries", []), 1):
            tei_rel = e.get("tei_path") or ""
            tei_abs = ROOT / tei_rel if tei_rel else tei_dir / f"{e.get('id','unknown')}.tei.xml"
            try:
                tei_root = ET.parse(str(tei_abs)).getroot()
            except Exception:
                tei_root = ET.Element('TEI')
            if args.progress:
                title = (e.get('meta',{}) or {}).get('title') or e.get('id') or tei_abs.name
                mode = 'LLM' if args.enrich_llm and llm_host and llm_model else 'fallback'
                print(f"[v2] {idx}/{total} {mode}: {title[:72]}", flush=True)
            v2_entries.append(upgrade_to_v2(
                e, tei_abs, tei_root, llm_host, llm_model, enrich_llm=args.enrich_llm,
                llm_endpoint=args.llm_endpoint, llm_timeout=args.llm_timeout,
                llm_retries=args.llm_retries, llm_verbose=args.llm_verbose,
                llm_fail_fast=args.fail_fast_llm
            ))
        payload = {
            "schema_version": "2.0",
            "generated": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            "source": "tei->v2_builder",
            "entries": v2_entries,
        }
        out_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        print(f"Wrote {out_path} with {len(v2_entries)} entries")
    else:
        out_path.write_text(json.dumps(v1, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        print(f"Wrote {out_path} with {len(v1.get('entries', []))} entries")
    return 0

if __name__ == "__main__":
    raise SystemExit(main())
