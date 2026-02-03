#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
GROBID → TEI → structured JSON/CSV for pillar classification.

Outputs per review (same filenames as your pipeline expects):
  - json/{review_id}.bibliography.json
  - json/{review_id}.sections.json
  - json/{review_id}.section_citations.csv
Plus a QA helper:
  - json/{review_id}.unmatched_citations.json

Key upgrades:
  - Robust DOI normalization & year/title extraction
  - Section text (full, cleaned) for better downstream classification
  - Wider citation discovery (<ref>, <ptr>, and citation <note>)
  - Backoff/retries for GROBID
"""

import argparse, csv, json, re, time, math
from pathlib import Path
from typing import Dict, List, Optional, Tuple, Iterable
import requests
from lxml import etree
from concurrent.futures import ThreadPoolExecutor, as_completed

NS = {"t": "http://www.tei-c.org/ns/1.0"}

# ---------- text utils ----------
WS = re.compile(r"\s+")
SOFT_HYPHEN = "\u00ad"
DOI_RE = re.compile(r'(10\.\d{4,9}/\S+)', re.I)

SKIP_SECTION_RX = re.compile(
    r'^\s*(references?|bibliograph\w*|acknowledg\w*|support\w* info|supplement\w*|appendix|author contribution|conflict of interest|funding)\s*:?$',
    re.I
)
def _pick_pdf_dir(root: Path) -> Path:
    """Return the first existing PDF directory under root."""
    for name in ("pdf", "PDF", "Pdf", "PDFs", "pdfs"):
        cand = root / name
        if cand.exists():
            return cand
    # default (will print a warning later if empty)
    return root / "pdf"

def clean_ws(s: str) -> str:
    if not s:
        return ""
    s = s.replace(SOFT_HYPHEN, "")
    s = re.sub(r'-\s+\n', '', s)  # end-line hyphenation (rare in TEI, safe anyway)
    s = s.replace("\u200b", "")   # zero-width space
    s = WS.sub(" ", s)
    return s.strip()

def normalize_doi(s: Optional[str]) -> str:
    if not s:
        return ""
    s = s.strip()
    s = re.sub(r'^https?://(dx\.)?doi\.org/', '', s, flags=re.I)
    s = s.replace("doi:", "").strip()
    m = DOI_RE.search(s)
    doi = m.group(1).lower() if m else ""
    # collapse German vs Int. Ed. duplicates
    doi = re.sub(r"^10\.1002/ange\.", "10.1002/anie.", doi)
    return doi

def first_text(root, xpath: str) -> Optional[str]:
    vals = root.xpath(xpath, namespaces=NS)
    if not vals:
        return None
    if isinstance(vals[0], str):
        return clean_ws(vals[0])
    return None

def join_all_text(root, xpath: str) -> str:
    # Joins all descendant text under xpath
    nodes = root.xpath(xpath, namespaces=NS)
    parts = []
    for n in nodes:
        txt = "".join(n.xpath(".//text()", namespaces=NS))
        parts.append(clean_ws(txt))
    return clean_ws(" ".join([p for p in parts if p]))

def best_year(b: etree._Element) -> Optional[int]:
    # Try multiple TEI locations for year
    candidates = []
    # imprint/date @when or text
    for y in b.xpath(".//t:imprint/t:date/@when | .//t:imprint/t:date/text()", namespaces=NS):
        y = str(y).strip()
        if len(y) >= 4 and y[:4].isdigit():
            candidates.append(y[:4])
    # biblScope unit='year'
    for y in b.xpath(".//t:biblScope[@unit='year']/@from | .//t:biblScope[@unit='year']/@to | .//t:biblScope[@unit='year']/text()", namespaces=NS):
        y = str(y).strip()
        if len(y) >= 4 and y[:4].isdigit():
            candidates.append(y[:4])
    # final pick
    for y in candidates:
        try:
            yi = int(y)
            # sanity: we accept 1800..current+1
            if 1800 <= yi <= time.gmtime().tm_year + 1:
                return yi
        except Exception:
            pass
    return None

def best_title(b: etree._Element) -> Optional[str]:
    # Prefer analytic main title, then other analytics, then monograph title
    xpaths = [
        ".//t:analytic/t:title[@type='main']/text()",
        ".//t:analytic/t:title/text()",
        ".//t:monogr/t:title[@type='main']/text()",
        ".//t:monogr/t:title/text()",
    ]
    for xp in xpaths:
        t = first_text(b, xp)
        if t:
            return t
    return None

def extract_all_dois(b: etree._Element) -> List[str]:
    dois = []
    # explicit DOI idno
    for val in b.xpath(".//t:idno[@type='DOI']/text()", namespaces=NS):
        nd = normalize_doi(val)
        if nd:
            dois.append(nd)
    # any idno that looks like doi (some TEI uses lowercased type, or URN)
    for val in b.xpath(".//t:idno/text()", namespaces=NS):
        sval = str(val).strip()
        # doi:... or full doi.org URL or bare 10.xxxx
        if "doi.org" in sval.lower() or sval.lower().startswith("doi:") or DOI_RE.search(sval):
            nd = normalize_doi(sval)
            if nd:
                dois.append(nd)
    # unique, preserve order
    seen = set()
    out = []
    for d in dois:
        if d not in seen:
            seen.add(d)
            out.append(d)
    return out

# ---------- GROBID ----------
def call_grobid(pdf_path: Path, out_tei: Path, host: str, max_retries: int = 4) -> None:
    # Conservative retry/backoff
    last_err = None
    for i in range(max_retries):
        try:
            with open(pdf_path, "rb") as f:
                r = requests.post(
                    f"{host.rstrip('/')}/api/processFulltextDocument",
                    files={"input": (pdf_path.name, f, "application/pdf")},
                    data={
                        "consolidateHeader": 1,
                        "consolidateCitations": 1,
                        "generateIDs": 1,
                        "teiCoordinates": "figure"
                    },
                    timeout=(30, 300),  # connect, read
                )
            r.raise_for_status()
            text = r.text
            out_tei.write_text(text, encoding="utf-8")
            return
        except Exception as e:
            last_err = e
            sleep_s = min(2 ** i, 20)
            print(f"    [warn] GROBID attempt {i+1}/{max_retries} failed: {e} → retrying in {sleep_s}s")
            time.sleep(sleep_s)
    raise RuntimeError(f"GROBID failed after {max_retries} attempts: {last_err}")

# ---------- TEI parsing ----------
def parse_bibliography(tei_text: str) -> Dict[str, dict]:
    root = etree.fromstring(tei_text.encode("utf-8"))
    out: Dict[str, dict] = {}

    for b in root.xpath("//t:listBibl/t:biblStruct", namespaces=NS):
        bid = b.get("{http://www.w3.org/XML/1998/namespace}id") or ""
        # raw citation (safe fallback)
        raw = " ".join(b.xpath(".//text()", namespaces=NS)).strip()
        raw = clean_ws(raw)

        # fields
        dois = extract_all_dois(b)
        doi = dois[0] if dois else None
        title = best_title(b)

        year = best_year(b)

        # extra (not used by classifier but useful to keep)
        container = first_text(b, ".//t:monogr/t:title/text()")
        volume = first_text(b, ".//t:imprint/t:biblScope[@unit='volume']/text()")
        issue  = first_text(b, ".//t:imprint/t:biblScope[@unit='issue']/text()")
        fpage  = first_text(b, ".//t:imprint/t:biblScope[@unit='page']/@from") or \
                 first_text(b, ".//t:imprint/t:biblScope[@unit='page']/text()")
        lpage  = first_text(b, ".//t:imprint/t:biblScope[@unit='page']/@to")
        pages  = None
        if fpage and lpage:
            pages = f"{fpage}-{lpage}"
        elif fpage:
            pages = fpage

        out[bid] = {
            "xml_id": bid,
            "raw_citation": raw,
            "doi": doi,
            "all_dois": dois,
            "title": title,
            "year": year,
            "container": container,
            "volume": volume,
            "issue": issue,
            "pages": pages,
        }
    return out

def iter_citation_targets(elem: etree._Element) -> Iterable[Tuple[str, str]]:
    """
    Yield (marker_text, target_xml_id) pairs from <ref>, <ptr>, and citation <note>.
    Handles multiple targets in a single @target (space-separated).
    """
    # <ref type="bibr" target="#b1 #b2">[1,2]</ref>
    for r in elem.xpath(".//t:ref[@type='bibr' or starts-with(@target,'#b')]", namespaces=NS):
        marker = clean_ws("".join(r.xpath(".//text()", namespaces=NS)))
        tgt = (r.get("target") or "").strip()
        if not tgt:
            continue
        ids = [t.lstrip("#") for t in tgt.split() if t.strip()]
        for rid in ids:
            yield (marker, rid)

    # <ptr type="bibr" target="#b12">
    for p in elem.xpath(".//t:ptr[@type='bibr' or starts-with(@target,'#b')]", namespaces=NS):
        marker = ""  # ptr often has no visible marker
        tgt = (p.get("target") or "").strip()
        if not tgt:
            continue
        ids = [t.lstrip("#") for t in tgt.split() if t.strip()]
        for rid in ids:
            yield (marker, rid)

    # Some TEI encodes citations in <note type="citation">
    for n in elem.xpath(".//t:note[@type='citation']", namespaces=NS):
        marker = clean_ws("".join(n.xpath(".//text()", namespaces=NS)))
        tgt = (n.get("target") or "").strip()
        if tgt:
            ids = [t.lstrip("#") for t in tgt.split() if t.strip()]
            for rid in ids:
                yield (marker, rid)

def normalize_header(h: str) -> str:
    # strip numbering and trailing punctuation: "2.3 Materials and Methods:" → "Materials and Methods"
    h = clean_ws(h)
    h = re.sub(r'^\s*\d+(\.\d+)*\s*[\)\.\-–—]\s*', '', h)
    h = re.sub(r'^\s*\d+(\.\d+)*\s+', '', h)
    h = h.rstrip(" :;")
    return h

def parse_sections_and_cites(tei_text: str) -> List[dict]:
    root = etree.fromstring(tei_text.encode("utf-8"))
    sections: List[dict] = []

    # TEI may nest <div>; get all meaningful ones
    divs = root.xpath("//t:text//t:div", namespaces=NS)

    for div in divs:
        # header candidates
        header = join_all_text(div, "./t:head")
        header = header or join_all_text(div, ".//t:head[1]")
        if not header:
            # fallback: first paragraph preview
            p_preview = join_all_text(div, ".//t:p[1]")
            header = p_preview[:80] + "…" if p_preview else "Untitled section"

        raw_header = header
        header = normalize_header(header)

        # Skip uninformative sections (but only if they really look like refs/acks)
        if SKIP_SECTION_RX.match(header):
            continue

        # full text (concatenate paragraphs; keep to reasonable size)
        paras = div.xpath(".//t:p", namespaces=NS)
        if paras:
            texts = []
            for p in paras:
                pt = "".join(p.xpath(".//text()", namespaces=NS))
                texts.append(clean_ws(pt))
            full_text = clean_ws(" ".join(texts))
        else:
            full_text = clean_ws("".join(div.xpath(".//text()", namespaces=NS)))

        snippet = (full_text[:1500] + ("…" if len(full_text) > 1500 else ""))
        # citation hooks
        cites = []
        for marker, rid in iter_citation_targets(div):
            if marker or rid:
                cites.append({"ref_marker": marker, "target_xml_id": rid})

        # Optional page range
        pages = None
        pbs = div.xpath(".//t:pb/@n", namespaces=NS)
        if pbs:
            pages = f"pp. {pbs[0]}–{pbs[-1]}"

        # record
        if header.strip() or full_text or cites:
            sections.append({
                "header": header,
                "raw_header": raw_header,
                "text": full_text,
                "snippet": snippet,
                "pages": pages,
                "citations": cites
            })

    # Fallback: whole body as one section
    if not sections:
        body = clean_ws("".join(root.xpath("//t:body//text()", namespaces=NS)))
        refs = list(iter_citation_targets(root))
        cites = [{"ref_marker": m, "target_xml_id": t} for (m, t) in refs]
        sections.append({"header": "Full text", "raw_header": "Full text",
                         "text": body, "snippet": body[:1500], "pages": None, "citations": cites})
    return sections

# ---------- writers ----------
def write_join_csv(review_id: str, sections: list, bib: dict, csv_path: Path, unmatched_path: Path):
    unmatched = []
    with csv_path.open("w", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        w.writerow(["review_id","section_header","ref_marker","target_xml_id",
                    "raw_citation","doi","title","year"])
        for s in sections:
            sh = s["header"]
            for c in s["citations"]:
                b = bib.get(c["target_xml_id"], None)
                if b:
                    w.writerow([review_id, sh, c.get("ref_marker",""), c.get("target_xml_id",""),
                                b.get("raw_citation",""), b.get("doi",""), b.get("title",""), b.get("year","")])
                else:
                    w.writerow([review_id, sh, c.get("ref_marker",""), c.get("target_xml_id",""),
                                "", "", "", ""])
                    unmatched.append({"section_header": sh, **c})

    if unmatched:
        unmatched_path.write_text(json.dumps({"review_id": review_id, "unmatched": unmatched},
                                             ensure_ascii=False, indent=2), encoding="utf-8")

def process_pdf(pdf: Path, tei_dir: Path, out_dir: Path, host: str, redo: bool) -> Tuple[str, List[str]]:
    review_id = pdf.stem
    tei_path  = tei_dir / f"{review_id}.tei.xml"
    bib_json  = out_dir / f"{review_id}.bibliography.json"
    sec_json  = out_dir / f"{review_id}.sections.json"
    join_csv  = out_dir / f"{review_id}.section_citations.csv"
    unmatched_json = out_dir / f"{review_id}.unmatched_citations.json"

    logs = [f"[+] {review_id}"]

    if redo or not tei_path.exists():
        try:
            call_grobid(pdf, tei_path, host=host)
            # polite gap
            time.sleep(0.3)
        except Exception as e:
            logs.append(f"    GROBID error: {e}")
            return review_id, logs

    try:
        tei = tei_path.read_text(encoding="utf-8", errors="replace")
    except Exception as e:
        logs.append(f"    TEI read error: {e}")
        return review_id, logs

    try:
        bib = parse_bibliography(tei)
        secs = parse_sections_and_cites(tei)
    except Exception as e:
        logs.append(f"    TEI parse error: {e}")
        return review_id, logs

    # persist
    bib_json.write_text(json.dumps({"review_id": review_id, "bibliography": bib}, ensure_ascii=False, indent=2),
                        encoding="utf-8")
    sec_json.write_text(json.dumps({"review_id": review_id, "sections": secs}, ensure_ascii=False, indent=2),
                        encoding="utf-8")
    write_join_csv(review_id, secs, bib, join_csv, unmatched_json)

    logs.append(f"    wrote: {bib_json.name}, {sec_json.name}, {join_csv.name}" +
                (", unmatched_citations.json" if unmatched_json.exists() else ""))
    return review_id, logs

# ---------- main ----------
def main():
    script_dir = Path(__file__).resolve().parent                      # .../_PROTOTYPE/backbone
    default_root = script_dir / "core_reviews"                        # ← THIS EXISTS

    ap = argparse.ArgumentParser()
    ap.add_argument("--root", default=str(default_root),
                    help="Path to reviews folder containing pdf/, tei/, json/")
    ap.add_argument("--host", default="http://localhost:8070", help="GROBID host")
    ap.add_argument("--redo", action="store_true")
    ap.add_argument("--max-pdfs", type=int, default=0)
    ap.add_argument("--workers", type=int, default=1)
    args = ap.parse_args()

    root = Path(args.root)
    pdf_dir = root / "pdf"
    tei_dir = root / "tei"
    out_dir = root / "json"
    tei_dir.mkdir(parents=True, exist_ok=True)
    out_dir.mkdir(parents=True, exist_ok=True)

    pdfs = sorted(pdf_dir.glob("*.pdf"))
    if args.max_pdfs > 0:
        pdfs = pdfs[:args.max_pdfs]
    if not pdfs:
        print(f"No PDFs in {pdf_dir}")
        return

    if args.workers <= 1:
        for pdf in pdfs:
            _, logs = process_pdf(pdf, tei_dir, out_dir, host=args.host, redo=args.redo)
            for line in logs:
                print(line)
    else:
        from concurrent.futures import ThreadPoolExecutor, as_completed
        with ThreadPoolExecutor(max_workers=args.workers) as ex:
            futs = [ex.submit(process_pdf, pdf, tei_dir, out_dir, args.host, args.redo) for pdf in pdfs]
            for fut in as_completed(futs):
                _, logs = fut.result()
                for line in logs:
                    print(line)

if __name__ == "__main__":
    main()

