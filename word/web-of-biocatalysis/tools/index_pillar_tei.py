#!/usr/bin/env python3
"""
Build a compact, incremental per-pillar TEI cache for fast, pillar-focused retrieval.

Outputs JSON at literature/core_output/pillar_cache/<pillar_id>.json with entries like:
{
  "meta": { key, doi, title, year, journal, primary_pillar, all_pillars, confidence },
  "abstract": str,
  "keywords": [str],
  "sections": { intro, methods, results, discussion, conclusion },
  "salient": [str],
  "entities": { enzymes:[], cofactors:[], materials:[], solvents:[] },
  "quality": { tei_chars_total:int, snippets_len:int, has_keywords:bool, section_map:[str], indexed_at:str, tei_mtime: float }
}

Usage:
  python3 literature/tools/index_pillar_tei.py --pillar-id 02 --pillar-name "Design & Engineering" [--include-secondary] [--max-papers 500] [--refresh]
"""
import argparse
import csv
import json
import os
import re
import time
import hashlib
from pathlib import Path
from typing import Dict, Any, List, Optional
import xml.etree.ElementTree as ET

# Project root should be the workspace dir containing this script (.. from tools/)
ROOT = Path(__file__).resolve().parents[1]
# Library layout aligned with generate_pillars.py
LIB_DIR = ROOT / "library"
CORE_OUTPUT = LIB_DIR / "core_output"
INDEX_CSV = LIB_DIR / "literature_index" / "papers.csv"
ASSIGN_CSV_PRIMARY = CORE_OUTPUT / "per_paper_primary_pillar.csv"
ASSIGN_CSV_ALL = CORE_OUTPUT / "combined_pillar_assignments_complete.csv"
# Literature base directory containing per-paper folders with tei.xml
LIT_DIR = LIB_DIR / "literature"
# Pillar caches live under library/cache_for-llm/pillars to match generate_pillars.py
CACHE_DIR = LIB_DIR / "cache_for-llm" / "pillars"
# Crossref cache directory for metadata augmentation
CROSSREF_DIR = LIB_DIR / "cache_for-llm" / "crossref"
SCHEMA_VERSION = "1.1"

SECTION_HEAD_MAP = {
    "intro": ["introduction"],
    "methods": ["methods", "materials and methods", "experimental"],
    "results": ["results", "results and discussion"],
    "discussion": ["discussion"],
    "conclusion": ["conclusion", "conclusions", "summary"],
}

RE_ENZYMES = re.compile(r"(monooxygenase|peroxygenase|p450|baeyer[- ]villiger|ketoreductase|alcohol dehydrogenase|transaminase|aminotransferase|irre?d|ired|redam|amd?h|mao|lyase|hydrolase|esterase|lipase|amidase|nitrilase|glycosyl(transferase|idase))",
                        re.IGNORECASE)
RE_COF = re.compile(r"\b(NADP?H?|FAD|FMN|PLP|ATP)\b", re.IGNORECASE)
RE_MATS = re.compile(r"(immobiliz\w*|carrier|support|resin|agarose|glyoxyl|epoxy|boronic|clea|clec|sol[- ]gel|hydrogel|mof|magnetic nanoparticles|silica|sba-15|mcm-41)", re.IGNORECASE)
RE_SOLV = re.compile(r"(ionic liquid|deep eutectic|\bDES\b|biphasic|two[- ]liquid[- ]phase|supercritical CO2|scCO2|organic solvent)", re.IGNORECASE)


def read_csv(path: Path, limit: Optional[int] = None) -> List[Dict[str, Any]]:
    rows: List[Dict[str, Any]] = []
    if not path.exists():
        return rows
    with path.open("r", encoding="utf-8", newline="") as f:
        reader = csv.DictReader(f)
        for i, row in enumerate(reader):
            rows.append(row)
            if limit and i + 1 >= limit:
                break
    return rows


essential_cols = ["key", "doi", "title", "year", "journal", "primary_pillar", "all_pillars", "confidence"]


def normalize_text(s: str) -> str:
    return re.sub(r"\s+", " ", (s or "").strip())


# ---------------- Crossref augmentation helpers ----------------
def _doi_to_crossref_path(doi: str) -> Path | None:
    """Map a DOI to a crossref cache file path if present.
    Crossref cache filenames replace non alnum with underscores.
    We try a few normalized variants.
    """
    if not doi:
        return None
    candidates = set()
    d = doi.strip()
    d1 = d.lower()
    d2 = re.sub(r"[^0-9a-zA-Z]+", "_", d1)
    candidates.add(d2 + ".json")
    # common normalization: collapse multiple underscores
    d3 = re.sub(r"_+", "_", d2).strip("_")
    candidates.add(d3 + ".json")
    for name in candidates:
        p = CROSSREF_DIR / name
        if p.exists():
            return p
    return None


def _load_crossref(doi: str) -> dict:
    p = _doi_to_crossref_path(doi)
    if not p:
        return {}
    try:
        return json.loads(p.read_text(encoding="utf-8")) or {}
    except Exception:
        return {}


def _merge_crossref_into_meta(meta: dict, cr: dict) -> dict:
    """Merge a subset of Crossref fields into entry.meta."""
    if not cr:
        return meta
    m = dict(meta)
    m.setdefault("journal", cr.get("container-title") or cr.get("container_title") or m.get("journal"))
    m.setdefault("publisher", cr.get("publisher"))
    m.setdefault("url", cr.get("URL") or cr.get("url"))
    # volume/issue/pages may be nested
    m.setdefault("volume", cr.get("volume"))
    m.setdefault("issue", cr.get("issue"))
    page = cr.get("page") or cr.get("pageFirst")
    if page:
        m.setdefault("page", page)
    # type/subject
    m.setdefault("pub_type", cr.get("type"))
    subjects = cr.get("subject") or []
    if subjects:
        m.setdefault("subjects", subjects)
    # reference count / is_oa
    if cr.get("reference-count") is not None:
        m.setdefault("reference_count", cr.get("reference-count"))
    license = (cr.get("license") or [{}])
    if isinstance(license, list) and license:
        m.setdefault("license", license[0].get("URL"))
    return m


def pick_first_text(elems: List[ET.Element]) -> str:
    buf: List[str] = []
    for el in elems:
        t = ET.tostring(el, encoding="unicode", method="text")
        if t:
            buf.append(normalize_text(t))
    return "\n".join([x for x in buf if x])


def parse_tei(tei_path: Path) -> Dict[str, Any]:
    try:
        tree = ET.parse(tei_path)
        root = tree.getroot()
    except Exception:
        return {}
    ns = {"tei": root.tag.split("}")[0].strip("{") if "}" in root.tag else ""}

    # Abstract
    abstract = ""
    try:
        abs_nodes = root.findall('.//tei:abstract', ns) if ns["tei"] else root.findall('.//abstract')
        abstract = pick_first_text(abs_nodes)
    except Exception:
        pass

    # Keywords
    keywords: List[str] = []
    try:
        kw_nodes = root.findall('.//tei:keywords//tei:term', ns) if ns["tei"] else root.findall('.//keywords//term')
        for kw in kw_nodes:
            t = normalize_text(ET.tostring(kw, encoding="unicode", method="text"))
            if t:
                keywords.append(t)
    except Exception:
        pass

    # Authors (concise string and list)
    authors_list: List[str] = []
    try:
        auth_nodes = root.findall('.//tei:author', ns) if ns["tei"] else root.findall('.//author')
        for a in auth_nodes:
            # Prefer persName/surname + forename when available
            pers = a.find('tei:persName', ns) if ns["tei"] else a.find('persName')
            if pers is not None:
                surname = normalize_text(ET.tostring(pers.find('tei:surname', ns) if ns["tei"] else pers.find('surname'), encoding="unicode", method="text")) if (pers is not None) else ""
                forename = normalize_text(ET.tostring(pers.find('tei:forename', ns) if ns["tei"] else pers.find('forename'), encoding="unicode", method="text")) if (pers is not None) else ""
                name = ", ".join([p for p in [surname, forename] if p]) if surname or forename else ""
            else:
                name = normalize_text(ET.tostring(a, encoding="unicode", method="text"))
            if name:
                authors_list.append(name)
    except Exception:
        pass

    # Sections
    sections: Dict[str, str] = {}
    section_map: List[str] = []
    other_buf: List[str] = []
    try:
        divs = root.findall('.//tei:text//tei:body//tei:div', ns) if ns["tei"] else root.findall('.//text//body//div')
        for d in divs:
            head = d.find('tei:head', ns) if ns["tei"] else d.find('head')
            head_text = normalize_text(ET.tostring(head, encoding="unicode", method="text")) if head is not None else ""
            body_text = normalize_text(ET.tostring(d, encoding="unicode", method="text"))
            if not body_text:
                continue
            # Assign to canonical section if matches
            assigned = False
            ht = head_text.lower()
            for sec, keys in SECTION_HEAD_MAP.items():
                if any(k in ht for k in keys):
                    sections.setdefault(sec, "")
                    if len(sections[sec]) < 2400:
                        add = body_text[:2400]
                        sections[sec] = add
                        section_map.append(sec)
                        assigned = True
                        break
            if not assigned:
                # Keep first non-empty as intro fallback
                if "intro" not in sections and head_text:
                    sections["intro"] = body_text[:2400]
                    section_map.append("intro")
                else:
                    # capture to 'other' bucket for retrieval
                    if body_text:
                        other_buf.append(body_text)
    except Exception:
        pass
    if other_buf and "other" not in sections:
        sections["other"] = ("\n\n".join(other_buf))[:2400]

    # Figures and tables captions (brief)
    captions: List[str] = []
    try:
        fig_nodes = root.findall('.//tei:figure', ns) if ns["tei"] else root.findall('.//figure')
        for f in fig_nodes:
            cap = f.find('tei:figDesc', ns) if ns["tei"] else f.find('figDesc')
            if cap is not None:
                t = normalize_text(ET.tostring(cap, encoding="unicode", method="text"))
                if t:
                    captions.append(t[:240])
        tbl_nodes = root.findall('.//tei:table', ns) if ns["tei"] else root.findall('.//table')
        for tnode in tbl_nodes:
            cap = tnode.find('tei:head', ns) if ns["tei"] else tnode.find('head')
            if cap is not None:
                t = normalize_text(ET.tostring(cap, encoding="unicode", method="text"))
                if t:
                    captions.append(t[:240])
    except Exception:
        pass

    # Salient sentences: take top 2–3 from abstract/intro with indicative verbs
    salient: List[str] = []
    def split_sentences(txt: str) -> List[str]:
        parts = re.split(r"(?<=[.!?])\s+", txt)
        return [normalize_text(p) for p in parts if p and len(p) > 20]
    s_pool = split_sentences(abstract) + split_sentences(sections.get("intro", ""))
    for s in s_pool:
        if len(salient) >= 3:
            break
        if re.search(r"(we (report|demonstrate|show|present)|first|improv|engineer|mutant|scale|industrial)", s, re.IGNORECASE):
            salient.append(s[:240])
    # fallback
    if not salient:
        for s in s_pool[:2]:
            salient.append(s[:240])

    # Derive a brief summary from salient or abstract
    summary = ""
    try:
        if salient:
            summary = " ".join(salient[:2])[:360]
        elif abstract:
            ss = split_sentences(abstract)
            summary = " ".join(ss[:2])[:360]
    except Exception:
        summary = ""

    # Entities
    all_text = "\n".join([abstract] + list(sections.values()))
    enzymes = sorted(set(m.group(0).lower() for m in RE_ENZYMES.finditer(all_text)))
    cof = sorted(set(m.group(0).upper() for m in RE_COF.finditer(all_text)))
    mats = sorted(set(m.group(0).lower() for m in RE_MATS.finditer(all_text)))
    solv = sorted(set(m.group(0).lower() for m in RE_SOLV.finditer(all_text)))

    # Organisms (simple patterns)
    RE_ORG = re.compile(r"(e\.\s*coli|escherichia coli|bacillus subtilis|saccharomyces cerevisiae|pichia pastoris|yeast|aspergillus|streptomyces)", re.IGNORECASE)
    orgs = sorted(set(m.group(0).lower() for m in RE_ORG.finditer(all_text)))

    # Methods tags inferred from text
    text_lc = (all_text or "").lower()
    methods_tags: List[str] = []
    def _has_any(kws: List[str]) -> bool:
        return any(kw in text_lc for kw in kws)
    if _has_any(["microfluidic", "droplet", "facs", "ultrahigh-throughput", "uhts"]):
        methods_tags.append("Microfluidic UHTS")
    if _has_any(["cast", "focused saturation", "iterative saturation", "ism"]):
        methods_tags.append("CAST/ISM")
    if _has_any(["machine learning", "active learning", "surrogate", "ml model", "random forest", "xgboost", "neural"]):
        methods_tags.append("ML-guided libraries")
    if _has_any(["ancestral", "consensus"]):
        methods_tags.append("Ancestral/consensus stabilization")

    quality = {
        "tei_chars_total": len(all_text),
        "snippets_len": sum(len(v) for v in sections.values()),
        "has_keywords": bool(keywords),
        "has_abstract": bool(abstract),
        "n_sections_mapped": len(set(section_map)),
        "has_captions": False,
        "n_refs": 0,
        "section_map": section_map,
        "abstract_len": len(abstract),
        "summary_len": len(summary),
    }

    return {
        "abstract": abstract,
        "keywords": keywords,
        "sections": sections,
        "salient": salient,
        "entities": {"enzymes": enzymes, "cofactors": cof, "materials": mats, "solvents": solv, "organisms": orgs},
        "captions": captions,
        "summary": summary,
        "methods_tags": methods_tags,
        "authors_list": authors_list,
        "quality": quality,
    }


def load_assignments(primary_only: bool = True) -> Dict[str, Dict[str, Any]]:
    """Load paper assignments.
    Preference order:
      1) core_output/per_paper_primary_pillar.csv
      2) core_output/combined_pillar_assignments_complete.csv
      3) library/literature_index/papers.csv (fallback via pillar_primary)
    Returns a dict keyed by paper key/doi, with at least title/year/journal/doi and pillar fields.
    """
    def _rows_or_empty(p: Path) -> List[Dict[str, Any]]:
        try:
            return read_csv(p)
        except Exception:
            return []

    rows = _rows_or_empty(ASSIGN_CSV_PRIMARY)
    if not rows:
        rows = _rows_or_empty(ASSIGN_CSV_ALL)
    used_fallback_index = False
    if not rows:
        rows = _rows_or_empty(INDEX_CSV)
        used_fallback_index = bool(rows)

    idx: Dict[str, Dict[str, Any]] = {}
    for r in rows:
        key = (r.get("key") or r.get("doi") or r.get("title") or "").strip()
        if not key:
            continue
        # Normalize minimal fields expected downstream
        if used_fallback_index:
            r = {
                "key": key,
                "doi": (r.get("doi") or "").strip(),
                "title": (r.get("title") or "").strip(),
                "year": r.get("year"),
                "journal": r.get("journal") or r.get("venue"),
                "primary_pillar": r.get("pillar_primary") or "",
                "all_pillars": r.get("pillar_secondary") or "",
                "confidence": r.get("confidence") or "",
            }
        idx[key] = r
    return idx


def matches_pillar(r: Dict[str, Any], pillar_name: str, include_secondary: bool) -> bool:
    prim = (r.get("primary_pillar") or r.get("pillar_primary") or "").strip()
    if prim and pillar_name.lower() in prim.lower():
        return True
    if include_secondary:
        allp = (r.get("all_pillars") or r.get("pillar_secondary") or "").lower()
        return pillar_name.lower() in allp
    return False


def build_cache(args: argparse.Namespace) -> int:
    CACHE_DIR.mkdir(parents=True, exist_ok=True)
    cache_path = CACHE_DIR / f"{args.pillar_id}.json"
    existing: Dict[str, Any] = {}
    if cache_path.exists() and not args.refresh:
        try:
            existing = json.loads(cache_path.read_text(encoding="utf-8"))
        except Exception:
            existing = {}

    assignments = load_assignments(primary_only=not args.include_secondary)
    out: Dict[str, Any] = {
        "pillar_id": args.pillar_id,
        "pillar_name": args.pillar_name,
        "generated_at": time.strftime("%Y-%m-%d %H:%M:%S"),
        "schema_version": SCHEMA_VERSION,
        "entries": []
    }

    count = 0
    def looks_like_doi(s: str) -> bool:
        s = (s or "").strip()
        return "/" in s and len(s) < 255 and not s.lower().startswith("http")

    def safe_slug_component(s: str, max_len: int = 120) -> str:
        # Replace non-filename-friendly chars, collapse spaces, and truncate
        import re as _re
        s = (s or "").strip().lower()
        s = _re.sub(r"[^a-z0-9._-]+", "_", s)
        if len(s) > max_len:
            s = s[:max_len].rstrip("_-")
        return s or "unk"

    for key, meta in assignments.items():
        if not matches_pillar(meta, args.pillar_name, args.include_secondary):
            continue
        # Locate TEI by normalized key (doi-based directory or slug)
        # Try DOI folder first
        tei_path = None
        doi = (meta.get("doi") or "").strip()
        if looks_like_doi(doi):
            doi_dir = LIT_DIR / doi.replace("/", "_")
            cand = doi_dir / "tei.xml"
            try:
                if cand.exists():
                    tei_path = cand
            except OSError:
                tei_path = None
        if tei_path is None:
            # Fallback: search by slug directory within literature/
            slug_dir = LIT_DIR / safe_slug_component(meta.get("key") or meta.get("title") or key)
            cand = slug_dir / "tei.xml"
            try:
                if cand.exists():
                    tei_path = cand
            except OSError:
                tei_path = None
        if tei_path is None or not tei_path.exists():
            continue

        stat = tei_path.stat()
        tei_mtime = stat.st_mtime
        tei_checksum = ""
        try:
            data = tei_path.read_bytes()
            tei_checksum = hashlib.md5(data).hexdigest()
        except Exception:
            pass
        prev = None
        if existing:
            prev = next((e for e in existing.get("entries", []) if (e.get("meta", {}).get("doi") == doi or e.get("meta", {}).get("key") == key)), None)
        # Skip if unchanged
        if prev and abs(prev.get("quality", {}).get("tei_mtime", 0) - tei_mtime) < 0.5 and not args.refresh:
            out["entries"].append(prev)
            count += 1
            if count >= args.max_papers:
                break
            continue

        parsed = parse_tei(tei_path)
        if not parsed:
            continue
        # Build retrieval-ready chunks (sentence-aware) from abstract + sections
        def split_sentences_smart(txt: str) -> List[str]:
            # simple sentence segmentation with fallback; avoids breaking decimals/DOIs crudely
            if not txt:
                return []
            sents = re.split(r"(?<=[^A-Z].[.!?])\s+(?=[A-Z])", txt)
            if len(sents) <= 1:
                sents = re.split(r"(?<=[.!?])\s+", txt)
            return [s for s in (normalize_text(s) for s in sents) if s]

        def chunk_by_sentences(txt: str, size: int, overlap: int) -> List[Dict[str, int | str]]:
            sents = split_sentences_smart(txt)
            chunks: List[Dict[str, int | str]] = []
            cur = ""
            cur_start = 0
            pos = 0
            for s in sents:
                # find this sentence in txt from pos
                try:
                    idx = txt.index(s, pos)
                except ValueError:
                    idx = pos
                if not cur:
                    cur_start = idx
                # if adding exceeds size, flush
                if cur and len(cur) + 1 + len(s) > max(1, size):
                    chunks.append({"start": cur_start, "end": cur_start + len(cur), "text": cur})
                    # overlap by characters
                    if overlap > 0 and len(cur) > overlap:
                        cur = cur[-overlap:]
                        cur_start = cur_start + (len(cur) - overlap)
                    else:
                        cur = ""
                cur = (cur + (" " if cur else "") + s) if s else cur
                pos = idx + len(s)
            if cur:
                chunks.append({"start": cur_start, "end": cur_start + len(cur), "text": cur})
            return chunks

        chunks: List[Dict[str, Any]] = []
        cid = 0
        for sec_name, sec_text in ([("abstract", parsed.get("abstract", ""))] + list(parsed.get("sections", {}).items())):
            for ch in chunk_by_sentences(sec_text, args.chunk_size, args.chunk_overlap):
                text = ch["text"]
                chunks.append({
                    "id": f"{key}:{cid}",
                    "section": sec_name,
                    "text": text,
                    "start": ch["start"],
                    "end": ch["end"],
                    "hash": hashlib.md5(text.encode("utf-8")).hexdigest(),
                    "source": "tei",
                })
                cid += 1

        # References (TEI biblStruct + in-text DOI fallback)
        refs: List[Dict[str, str]] = []
        try:
            # TEI bibliographic structures
            bibl_nodes = root.findall('.//tei:listBibl//tei:biblStruct', ns) if ns["tei"] else root.findall('.//listBibl//biblStruct')
            for b in bibl_nodes:
                title_el = b.find('.//tei:title', ns) if ns["tei"] else b.find('.//title')
                idno_el = b.find('.//tei:idno[@type="DOI"]', ns) if ns["tei"] else b.find('.//idno')
                title_txt = normalize_text(ET.tostring(title_el, encoding="unicode", method="text")) if title_el is not None else ""
                doi_txt = normalize_text(ET.tostring(idno_el, encoding="unicode", method="text")) if idno_el is not None else ""
                if title_txt or doi_txt:
                    refs.append({"title": title_txt, "doi": doi_txt})
            # Fallback: DOIs in text
            all_txt = "\n".join([parsed.get("abstract", "")] + list(parsed.get("sections", {}).values()))
            seen = set(x.get("doi") for x in refs if x.get("doi"))
            for m in re.finditer(r"10\.[0-9]{4,9}/[-._;()/:A-Z0-9]+", all_txt, flags=re.IGNORECASE):
                doi = m.group(0)
                if doi not in seen:
                    refs.append({"title": "", "doi": doi})
                    seen.add(doi)
        except Exception:
            pass

        # Crossref augmentation
        cr = _load_crossref(doi)

        entry = {
            "meta": {
                "key": key,
                "doi": doi,
                "title": (meta.get("title") or "").strip(),
                "year": meta.get("year"),
                "journal": meta.get("journal"),
                "primary_pillar": meta.get("primary_pillar"),
                "all_pillars": meta.get("all_pillars"),
                "confidence": meta.get("confidence"),
                "authors": ", ".join((parsed.get("authors_list") or [])[:12]),
            },
            **parsed,
            "provenance": {"tei_path": str(tei_path)},
            "chunks": chunks,
            "references": refs,
        }
        # Merge crossref into meta (non-destructive defaults)
        entry["meta"] = _merge_crossref_into_meta(entry["meta"], cr)
        entry["quality"]["tei_mtime"] = tei_mtime
        entry["quality"]["tei_checksum_md5"] = tei_checksum
        entry["quality"]["indexed_at"] = time.strftime("%Y-%m-%d %H:%M:%S")
        entry["quality"]["n_chunks"] = len(chunks)
        entry["quality"]["has_captions"] = bool(parsed.get("captions"))
        entry["quality"]["n_refs"] = len(refs)
        out["entries"].append(entry)
        count += 1
        if count >= args.max_papers:
            break

    cache_path.write_text(json.dumps(out, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"Wrote cache: {cache_path} with {len(out['entries'])} entries")
    return 0


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--pillar-id", required=True, help="Pillar ID like 02")
    ap.add_argument("--pillar-name", required=True, help="Pillar display name, e.g., 'Design & Engineering'")
    ap.add_argument("--include-secondary", action="store_true", help="Include matches in all_pillars as well")
    ap.add_argument("--max-papers", type=int, default=500, help="Cap number of indexed papers")
    ap.add_argument("--refresh", action="store_true", help="Force re-index regardless of mtime")
    ap.add_argument("--chunk-size", type=int, default=800, help="Chunk size in characters for retrieval chunks")
    ap.add_argument("--chunk-overlap", type=int, default=120, help="Character overlap between chunks")
    args = ap.parse_args()
    return build_cache(args)


if __name__ == "__main__":
    raise SystemExit(main())
