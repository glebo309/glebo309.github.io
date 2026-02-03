#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Ultimate standalone literature pipeline with 7-method PDF acquisition
This version can be run directly without import issues
"""

import argparse
import csv
import json
import math
import tempfile
import subprocess
import sys
import time
import os
from pathlib import Path
from typing import Optional, Dict, Any, List
from urllib.parse import urljoin, urlparse

import pandas as pd
from tqdm import tqdm
import requests

# Add the parent directory to Python path to import local modules
sys.path.insert(0, str(Path(__file__).parent.parent))

try:
    from pipeline.config import load_config
    from pipeline.storage import Store
    from pipeline.sources import (
        fetch_crossref,
        fetch_semanticscholar,
        fetch_unpaywall,
        best_pdf_url_from_unpaywall,
    )
    from pipeline.grobid_client import grobid_process_pdf
    from pipeline.tei_utils import parse_tei, get_title, get_abstract, get_body_text, get_references
    from pipeline.extract import run_extraction
except ImportError as e:
    print(f"Error importing modules: {e}")
    print("Make sure you're running this from the literature directory")
    print("Or try: cd .. && python pipeline/ultimate_pipeline.py")
    sys.exit(1)

# ------------------------- helpers -------------------------

def normalize_doi(s: str) -> str:
    s = (s or "").strip()
    s = s.replace("https://doi.org/", "").replace("http://doi.org/", "")
    s = s.replace("doi:", "").replace("DOI:", "")
    return s.strip().lower()

def already_processed(store: Store, doi: str, min_stage: str = "extracted") -> bool:
    """Return True if this DOI has already reached min_stage."""
    doi = normalize_doi(doi)
    if min_stage == "tei":
        return store.tei_path(doi).exists()
    return store.extracted_path(doi).exists()

def merge_meta(cr: Dict[str, Any], s2: Dict[str, Any], oa: Dict[str, Any]) -> Dict[str, Any]:
    # title
    title = ((" ".join(cr.get("title") or [])) or s2.get("title") or "").strip()

    # year
    year = None
    try:
        y = (cr.get("issued") or {}).get("date-parts", [[None]])[0][0]
        year = int(y) if y else None
    except Exception:
        year = s2.get("year")

    # authors
    authors: List[str] = []
    for a in (cr.get("author") or []):
        nm = " ".join([a.get("given", ""), a.get("family", "")]).strip()
        if nm:
            authors.append(nm)
    if not authors and s2.get("authors"):
        authors = [a.get("name", "").strip() for a in s2.get("authors") if a.get("name")]

    # journal
    journal = ""
    cont = (cr.get("short-container-title") or cr.get("container-title") or [])
    if cont:
        journal = cont[0]
    elif s2.get("journal"):
        j = s2.get("journal")
        journal = j.get("name") if isinstance(j, dict) else str(j)

    oa_pdf, license_ = best_pdf_url_from_unpaywall(oa or {})

    return {
        "title": title,
        "year": year,
        "authors": authors,
        "journal": journal,
        "crossref": cr,
        "semanticscholar": s2,
        "unpaywall": oa,
        "oa_pdf_url": oa_pdf,
        "oa_license": license_,
    }

def upsert_index(store: Store, row: Dict[str, Any]) -> None:
    """Overwrite/update a single DOI row in the global index CSV."""
    idx_path = store.index_csv()
    if idx_path.exists():
        df = pd.read_csv(idx_path)
        df = df[df["doi"].str.lower() != row["doi"].lower()]
        df = pd.concat([df, pd.DataFrame([row])], ignore_index=True)
    else:
        df = pd.DataFrame([row])
    df.to_csv(idx_path, index=False)

# ------------------------- Ultimate PDF fetching system -------------------------

UA_DEFAULT = "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124 Safari/537.36"

def _session_with_headers() -> requests.Session:
    s = requests.Session()
    s.headers.update({"User-Agent": UA_DEFAULT})
    return s

def _try_fetch_oa_pdf(session: requests.Session, url: str, outpath: Path) -> None:
    """Original OA PDF fetching method"""
    with session.get(url, stream=True, timeout=90, allow_redirects=True) as r:
        r.raise_for_status()
        with outpath.open("wb") as f:
            for chunk in r.iter_content(chunk_size=1 << 20):
                if chunk:
                    f.write(chunk)

def _try_fetch_semantic_scholar_pdf(doi: str, outpath: Path) -> None:
    """Enhanced Semantic Scholar PDF fetching"""
    url = f"https://api.semanticscholar.org/graph/v1/paper/DOI:{doi}"
    params = {
        'fields': 'title,url,openAccessPdf,externalIds,venue'
    }
    headers = {"User-Agent": UA_DEFAULT}
    
    response = requests.get(url, params=params, headers=headers, timeout=30)
    response.raise_for_status()
    
    data = response.json()
    
    # Check for open access PDF
    open_access_pdf = data.get('openAccessPdf')
    if open_access_pdf and open_access_pdf.get('url'):
        pdf_url = open_access_pdf['url']
        
        session = _session_with_headers()
        with session.get(pdf_url, stream=True, timeout=60, allow_redirects=True) as r:
            r.raise_for_status()
            with outpath.open("wb") as f:
                for chunk in r.iter_content(chunk_size=1024*1024):
                    if chunk:
                        f.write(chunk)
        
        if outpath.stat().st_size < 1024:
            raise RuntimeError("Downloaded file too small")
        
        return
    
    raise RuntimeError("No PDF found via Semantic Scholar")

def _try_fetch_arxiv_pdf(doi: str, outpath: Path) -> None:
    """Try to get PDF from arXiv if it's an arXiv paper"""
    url = f"https://api.crossref.org/works/{doi}"
    headers = {"User-Agent": UA_DEFAULT}
    
    response = requests.get(url, headers=headers, timeout=30)
    response.raise_for_status()
    
    data = response.json()
    work = data.get('message', {})
    
    # Look for arXiv ID in various fields
    arxiv_id = None
    
    # Check URL
    url_field = work.get('URL', '')
    if 'arxiv.org' in url_field.lower():
        arxiv_id = url_field.split('/')[-1]
    
    # Check alternative-id
    for alt_id in work.get('alternative-id', []):
        if alt_id.startswith('arXiv:'):
            arxiv_id = alt_id.replace('arXiv:', '')
    
    if not arxiv_id:
        raise RuntimeError("Not an arXiv paper")
    
    # Download from arXiv
    arxiv_pdf_url = f"https://arxiv.org/pdf/{arxiv_id}.pdf"
    
    session = _session_with_headers()
    with session.get(arxiv_pdf_url, stream=True, timeout=60, allow_redirects=True) as r:
        r.raise_for_status()
        with outpath.open("wb") as f:
            for chunk in r.iter_content(chunk_size=1024*1024):
                if chunk:
                    f.write(chunk)
    
    if outpath.stat().st_size < 1024:
        raise RuntimeError("Downloaded arXiv file too small")

def _try_fetch_crossref_links(doi: str, outpath: Path) -> None:
    """Enhanced Crossref link following"""
    url = f"https://api.crossref.org/works/{doi}"
    headers = {"User-Agent": UA_DEFAULT}
    
    response = requests.get(url, headers=headers, timeout=30)
    response.raise_for_status()
    
    data = response.json()
    work = data.get('message', {})
    
    # Collect potential PDF URLs
    pdf_urls = []
    
    # Check URL field
    if 'URL' in work:
        pdf_urls.append(work['URL'])
    
    # Check link field
    for link in work.get('link', []):
        if link.get('content-type') == 'application/pdf':
            pdf_urls.append(link.get('URL'))
        elif 'pdf' in link.get('URL', '').lower():
            pdf_urls.append(link.get('URL'))
    
    # Check resource field
    for resource in work.get('resource', {}).get('primary', {}).get('URL', []):
        if isinstance(resource, str):
            pdf_urls.append(resource)
    
    # Try each potential PDF URL
    session = _session_with_headers()
    
    for pdf_url in pdf_urls:
        if not pdf_url:
            continue
            
        try:
            # Follow redirects and check content type
            with session.get(pdf_url, stream=True, timeout=60, allow_redirects=True) as r:
                content_type = r.headers.get('content-type', '').lower()
                
                # Check if it's actually a PDF
                if 'pdf' in content_type or pdf_url.lower().endswith('.pdf'):
                    r.raise_for_status()
                    with outpath.open("wb") as f:
                        for chunk in r.iter_content(chunk_size=1024*1024):
                            if chunk:
                                f.write(chunk)
                    
                    if outpath.stat().st_size > 1024:  # Valid PDF
                        return
                    else:
                        # File too small, try next URL
                        continue
        except Exception:
            continue
    
    raise RuntimeError("No accessible PDF found via Crossref")

def _try_fetch_publisher_direct(doi: str, outpath: Path) -> None:
    """Try to get PDF directly from publisher website"""
    try:
        from bs4 import BeautifulSoup
    except ImportError:
        raise RuntimeError("BeautifulSoup not available (install beautifulsoup4)")
    
    doi_url = f"https://doi.org/{doi}"
    session = _session_with_headers()
    
    try:
        # Get the DOI page
        response = session.get(doi_url, timeout=30, allow_redirects=True)
        response.raise_for_status()
        
        # Look for PDF download links in the HTML
        soup = BeautifulSoup(response.text, 'html.parser')
        
        # Common PDF link patterns
        pdf_links = []
        
        # Look for links with "pdf" in href
        for link in soup.find_all('a', href=True):
            href = link['href']
            if 'pdf' in href.lower() or 'download' in href.lower():
                # Make absolute URL
                if href.startswith('/'):
                    href = urljoin(response.url, href)
                elif not href.startswith('http'):
                    href = urljoin(response.url, href)
                pdf_links.append(href)
        
        # Try each PDF link
        for pdf_url in pdf_links[:5]:  # Try up to 5 links
            try:
                with session.get(pdf_url, stream=True, timeout=60, allow_redirects=True) as r:
                    content_type = r.headers.get('content-type', '').lower()
                    if 'pdf' in content_type:
                        r.raise_for_status()
                        with outpath.open("wb") as f:
                            for chunk in r.iter_content(chunk_size=1024*1024):
                                if chunk:
                                    f.write(chunk)
                        
                        if outpath.stat().st_size > 1024:
                            return
            except Exception:
                continue
                
    except Exception as e:
        pass
    
    raise RuntimeError("No PDF found via publisher direct access")

def _try_fetch_scihub(doi: str, outpath: Path) -> None:
    """Original Sci-Hub method with better error handling"""
    try:
        from scihub import SciHub
    except Exception as e:
        raise RuntimeError(f"scihub_unavailable: {e}")
    
    try:
        sh = SciHub()
        res = sh.download(doi, path=str(outpath))
        if (not outpath.exists()) or outpath.stat().st_size < 1024:
            raise RuntimeError("scihub_download_empty_or_failed")
    except Exception as e:
        # More specific error handling
        if "download" in str(e):
            raise RuntimeError(f"scihub_method_error: {e}")
        else:
            raise RuntimeError(f"scihub_general_error: {e}")

def _check_pypaperbot_available() -> bool:
    """Enhanced PyPaperBot availability check"""
    try:
        # First check import
        import PyPaperBot
        
        # Then check command
        result = subprocess.run([sys.executable, "-m", "PyPaperBot", "--help"], 
                              capture_output=True, text=True, timeout=10)
        return result.returncode == 0
    except Exception:
        return False

def _try_fetch_pypaperbot(doi: str, outpath: Path, temp_dir: Path) -> None:
    """Enhanced PyPaperBot with better error handling"""
    # Create a temporary download directory for PyPaperBot
    pypb_download_dir = temp_dir / f"pypb_{doi.replace('/', '_').replace('.', '_')}"
    pypb_download_dir.mkdir(exist_ok=True)
    
    try:
        # Run PyPaperBot with the DOI
        cmd = [
            sys.executable, "-m", "PyPaperBot",
            "--doi", doi,
            "--dwn-dir", str(pypb_download_dir),
            "--use-doi-as-filename"
        ]
        
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=180)
        
        if result.returncode != 0:
            error_msg = result.stderr or result.stdout or "Unknown PyPaperBot error"
            raise RuntimeError(f"PyPaperBot failed (code {result.returncode}): {error_msg}")
        
        # Find the downloaded PDF
        pdf_files = list(pypb_download_dir.glob("*.pdf"))
        if not pdf_files:
            all_files = list(pypb_download_dir.glob("*"))
            if all_files:
                raise RuntimeError(f"PyPaperBot downloaded files but no PDFs: {[f.name for f in all_files]}")
            else:
                raise RuntimeError("PyPaperBot completed but no files downloaded")
        
        # Move the first PDF file to our target location
        downloaded_pdf = pdf_files[0]
        if downloaded_pdf.stat().st_size < 1024:
            raise RuntimeError(f"PyPaperBot downloaded small file ({downloaded_pdf.stat().st_size} bytes)")
        
        # Move to target location
        downloaded_pdf.rename(outpath)
        
    finally:
        # Clean up temporary directory
        try:
            import shutil
            shutil.rmtree(pypb_download_dir, ignore_errors=True)
        except Exception:
            pass

def _download_pdf_with_ultimate_fallbacks(doi_key: str,
                                        doi: str,
                                        meta: Dict[str, Any],
                                        store: Store) -> Optional[Path]:
    """
    Ultimate PDF download with comprehensive fallback system:
    1. OA PDF (Unpaywall) - Free, legal sources
    2. Semantic Scholar - Open access repository
    3. arXiv - Preprint server
    4. Crossref direct links - Publisher provided links
    5. Publisher direct - Scrape publisher website
    6. Sci-Hub - Traditional fallback
    7. PyPaperBot - Multi-source aggregator
    """
    session = _session_with_headers()
    tmp_pdf = Path(tempfile.mkstemp(dir=store.tmp, suffix=".pdf")[1])
    tried = []
    
    # Add small delay to be respectful to APIs
    time.sleep(0.5)

    # 1) OA PDF (Unpaywall) - Free and legal
    pdf_url = (meta.get("oa_pdf_url") or "").strip()
    if pdf_url:
        try:
            _try_fetch_oa_pdf(session, pdf_url, tmp_pdf)
            store.append_log(doi_key, "✓ OA PDF fetched successfully")
            return tmp_pdf
        except Exception as e:
            tried.append(f"oa:{type(e).__name__}")
            store.append_log(doi_key, f"✗ OA fetch failed: {e}")

    # 2) Semantic Scholar - Academic repository
    if doi:
        try:
            store.append_log(doi_key, "→ Attempting Semantic Scholar...")
            _try_fetch_semantic_scholar_pdf(doi, tmp_pdf)
            store.append_log(doi_key, "✓ Semantic Scholar PDF fetched successfully")
            return tmp_pdf
        except Exception as e:
            tried.append(f"semantic_scholar:{type(e).__name__}")
            store.append_log(doi_key, f"✗ Semantic Scholar failed: {e}")

    # 3) arXiv - Preprint server
    if doi:
        try:
            store.append_log(doi_key, "→ Checking arXiv...")
            _try_fetch_arxiv_pdf(doi, tmp_pdf)
            store.append_log(doi_key, "✓ arXiv PDF fetched successfully")
            return tmp_pdf
        except Exception as e:
            tried.append(f"arxiv:{type(e).__name__}")
            store.append_log(doi_key, f"✗ arXiv failed: {e}")

    # 4) Crossref direct links - Publisher metadata
    if doi:
        try:
            store.append_log(doi_key, "→ Trying Crossref direct links...")
            _try_fetch_crossref_links(doi, tmp_pdf)
            store.append_log(doi_key, "✓ Crossref PDF fetched successfully")
            return tmp_pdf
        except Exception as e:
            tried.append(f"crossref:{type(e).__name__}")
            store.append_log(doi_key, f"✗ Crossref direct failed: {e}")

    # 5) Publisher direct access - Website scraping
    if doi:
        try:
            store.append_log(doi_key, "→ Attempting publisher direct access...")
            _try_fetch_publisher_direct(doi, tmp_pdf)
            store.append_log(doi_key, "✓ Publisher direct PDF fetched successfully")
            return tmp_pdf
        except Exception as e:
            tried.append(f"publisher:{type(e).__name__}")
            store.append_log(doi_key, f"✗ Publisher direct failed: {e}")

    # 6) Sci-Hub - Traditional fallback
    if doi:
        try:
            store.append_log(doi_key, "→ Attempting Sci-Hub...")
            _try_fetch_scihub(doi, tmp_pdf)
            store.append_log(doi_key, "✓ Sci-Hub PDF fetched successfully")
            return tmp_pdf
        except Exception as e:
            tried.append(f"scihub:{type(e).__name__}")
            store.append_log(doi_key, f"✗ Sci-Hub failed: {e}")

    # 7) PyPaperBot - Multi-source aggregator
    if doi and _check_pypaperbot_available():
        try:
            store.append_log(doi_key, "→ Attempting PyPaperBot...")
            _try_fetch_pypaperbot(doi, tmp_pdf, store.tmp)
            store.append_log(doi_key, "✓ PyPaperBot PDF fetched successfully")
            return tmp_pdf
        except Exception as e:
            tried.append(f"pypaperbot:{type(e).__name__}")
            store.append_log(doi_key, f"✗ PyPaperBot failed: {e}")

    # Clean up if all methods failed
    try:
        tmp_pdf.unlink(missing_ok=True)
    except Exception:
        pass
    
    store.append_log(doi_key, f"✗ NO_PDF after all 7 fallback methods [{', '.join(tried) or 'none'}]")
    return None

# ------------------------- seed reading -------------------------

def read_curated_seeds(store):
    curated_file = store.base / "curated" / "curated_seeds.csv"
    pdf_dir = store.base / "curated" / "pdf"

    if not curated_file.exists():
        print(f"⚠️ curated_seeds.csv not found at {curated_file}")
        return []

    df = pd.read_csv(curated_file)
    rows = []

    for _, r in df.iterrows():
        row = r.to_dict()
        pdf_path = str(row.get("pdf_path") or "").strip()

        if pdf_path and not Path(pdf_path).is_absolute():
            candidate = pdf_dir / pdf_path
            if candidate.exists():
                pdf_path = candidate

        if (not pdf_path) or (not Path(pdf_path).exists()):
            doi = str(row.get("doi", "")).strip()
            if doi:
                suffix = doi.split("/")[-1]
                matches = list(pdf_dir.glob(f"*{suffix}*.pdf"))
                if matches:
                    pdf_path = matches[0]

        if (not pdf_path) or (not Path(pdf_path).exists()):
            title = str(row.get("title", "")).strip()
            if title:
                matches = list(pdf_dir.glob(f"*{title[:40]}*.pdf"))
                if matches:
                    pdf_path = matches[0]

        if pdf_path:
            pdf_path = str(Path(pdf_path).resolve())

        row["pdf_path"] = pdf_path
        rows.append(row)

    return rows

def read_auto_seeds(store: Store) -> List[Dict[str, str]]:
    """Load automatically classified seeds from the core_output location."""
    seeds: List[Dict[str, str]] = []
    auto_path = store.base / "core_output" / "combined_pillar_assignments.csv"
    if auto_path.exists():
        df = pd.read_csv(auto_path)
        for _, r in df.iterrows():
            doi_raw = r.get("doi")
            if not doi_raw or str(doi_raw).lower() == "nan":
                doi = ""
            else:
                doi = str(doi_raw).strip()

            title = (r.get("title") or "").strip()
            if not doi and not title:
                continue
            seeds.append({
                "doi": doi.lower(),
                "title": title,
                "pillar": (r.get("pillar") or "").strip(),
                "priority": "auto",
                "source": "classification",
                "notes": "",
            })
    else:
        print(f"⚠️ auto seeds not found at {auto_path}")
    return seeds

# ------------------------- core processor -------------------------

def process_one(cfg,
                store: Store,
                doi: str,
                pillar: Optional[str],
                force: bool = False,
                local_pdf: Optional[str] = None) -> Dict[str, Any]:
    """Core processor with ultimate PDF downloading."""
    doi = normalize_doi(doi) if doi else doi

    # Quick skip check
    if doi and (not force) and already_processed(store, doi, min_stage="extracted"):
        meta = {}
        if store.meta_path(doi).exists():
            meta = json.loads(store.meta_path(doi).read_text())
        status = "extracted_ok"
        index_row = {
            "doi": doi,
            "title": meta.get("title", ""),
            "year": meta.get("year", ""),
            "journal": meta.get("journal", ""),
            "pillar_primary": meta.get("pillar_primary", ""),
            "tei": "yes" if store.tei_path(doi).exists() else "no",
            "extracted": "yes",
            "status": status,
        }
        upsert_index(store, index_row)
        store.append_log(doi, "SKIP (already processed)")
        return index_row

    # Per-paper directory setup
    if not doi and local_pdf:
        pseudo = Path(local_pdf).stem
        doi_key = f"no-doi::{pseudo}"
    else:
        doi_key = doi

    pdir = store.paper_dir(doi_key)
    pdir.mkdir(parents=True, exist_ok=True)
    store.append_log(doi_key, f"START doi={doi or ''} pillar={pillar or ''} local_pdf={local_pdf or ''} force={force}")

    # ---- metadata ----
    meta_path = store.meta_path(doi_key)
    meta: Dict[str, Any] = {}
    if meta_path.exists() and not force:
        meta = json.loads(meta_path.read_text())
    else:
        if local_pdf and not doi:
            meta = {
                "doi": doi or "",
                "pillar_primary": pillar or "",
                "title": "",
                "year": None,
                "authors": [],
                "journal": "",
                "crossref": {},
                "semanticscholar": {},
                "unpaywall": {},
                "oa_pdf_url": "",
                "oa_license": "",
            }
        else:
            cr = fetch_crossref(doi) if doi else {}
            s2 = fetch_semanticscholar(doi) if doi else {}
            oa = fetch_unpaywall(doi, cfg["unpaywall"]["email"]) if doi else {}
            meta = merge_meta(cr, s2, oa) if doi else {}
            meta["doi"] = doi or ""
            if not meta.get("pillar_primary"):
                meta["pillar_primary"] = pillar or ""
        store.write_json(meta_path, meta)
        store.append_log(doi_key, "metadata saved")

    status = "init"

    # ---- TEI (GROBID) with ultimate PDF fetching ----
    tei_path = store.tei_path(doi_key)
    if tei_path.exists() and not force:
        status = "tei_ok"
    else:
        if local_pdf:
            # Curated: use local PDF directly
            src_pdf = Path(local_pdf)
            if not src_pdf.exists():
                store.append_log(doi_key, f"CURATED_PDF_MISSING: {src_pdf}")
                status = "curated_pdf_missing"
            else:
                try:
                    tei_xml = grobid_process_pdf(
                        src_pdf,
                        cfg["grobid"]["url"],
                        cfg["grobid"],
                        timeout_sec=int(cfg["grobid"].get("timeout_sec", 120)),
                    )
                    tei_path.write_text(tei_xml, encoding="utf-8")
                    store.append_log(doi_key, "Grobid TEI saved (curated)")
                    status = "tei_ok"
                except Exception as e:
                    store.append_log(doi_key, f"Grobid error (curated): {e}")
                    status = "tei_failed"
        else:
            # Auto: ultimate PDF download with 7 fallback methods
            tmp_pdf = _download_pdf_with_ultimate_fallbacks(doi_key, doi, meta, store)
            if not tmp_pdf:
                status = "locked_no_pdf"
                store.append_log(doi_key, "Skipping Grobid (no accessible PDF after all 7 attempts)")
            else:
                try:
                    tei_xml = grobid_process_pdf(
                        tmp_pdf,
                        cfg["grobid"]["url"],
                        cfg["grobid"],
                        timeout_sec=int(cfg["grobid"].get("timeout_sec", 120)),
                    )
                    tei_path.write_text(tei_xml, encoding="utf-8")
                    store.append_log(doi_key, "Grobid TEI saved (auto)")
                    status = "tei_ok"
                except Exception as e:
                    store.append_log(doi_key, f"Grobid/PDF error (auto): {e}")
                    status = "tei_failed"
                finally:
                    try:
                        tmp_pdf.unlink(missing_ok=True)
                    except Exception:
                        pass

    # ---- extraction (LLM) ----
    extracted_path = store.extracted_path(doi_key)
    if status == "tei_ok" and (not extracted_path.exists() or force):
        try:
            root = parse_tei(tei_path.read_text(encoding="utf-8"))
            title = meta.get("title") or get_title(root)
            abstract = get_abstract(root)
            body_excerpt = get_body_text(root, max_chars=int(cfg["extraction"]["max_chars_for_llm"]))

            out = run_extraction(
                cfg["ollama"]["host"],
                cfg["ollama"]["model"],
                meta.get("pillar_primary", ""),
                title,
                abstract,
                body_excerpt,
                max_chars=int(cfg["extraction"]["max_chars_for_llm"]),
                temperature=float(cfg["extraction"].get("temperature", 0.0)),
            )
            out["_refs"] = get_references(root, max_n=50)
            out["_title"] = title
            out["_abstract"] = (abstract or "")[:1000]

            store.write_json(extracted_path, out)
            store.append_log(doi_key, "extraction saved")
            status = "extracted_ok"
        except Exception as e:
            store.append_log(doi_key, f"extract error: {e}")
            status = "extracted_failed"

    # ---- index upsert ----
    index_row = {
        "doi": doi or doi_key,
        "title": meta.get("title", ""),
        "year": meta.get("year", ""),
        "journal": meta.get("journal", ""),
        "pillar_primary": meta.get("pillar_primary", ""),
        "tei": "yes" if store.tei_path(doi_key).exists() else "no",
        "extracted": "yes" if store.extracted_path(doi_key).exists() else "no",
        "status": status,
    }
    upsert_index(store, index_row)

    store.append_log(doi_key, f"DONE status={status}")
    return index_row

# ------------------------- enhanced runner -------------------------

def print_statistics(store: Store) -> None:
    """Print helpful statistics about the processing results"""
    idx_path = store.index_csv()
    if not idx_path.exists():
        print("No index file found yet")
        return
    
    df = pd.read_csv(idx_path)
    
    print("\n" + "="*60)
    print("📊 PROCESSING STATISTICS")
    print("="*60)
    
    total = len(df)
    extracted = len(df[df["extracted"] == "yes"])
    tei_only = len(df[(df["tei"] == "yes") & (df["extracted"] == "no")])
    locked = len(df[df["status"] == "locked_no_pdf"])
    
    print(f"Total papers processed: {total}")
    print(f"✅ Fully extracted: {extracted} ({extracted/total*100:.1f}%)")
    print(f"📄 TEI only (no extraction): {tei_only} ({tei_only/total*100:.1f}%)")
    print(f"🔒 No PDF accessible: {locked} ({locked/total*100:.1f}%)")
    
    # Status breakdown
    print(f"\nStatus breakdown:")
    status_counts = df["status"].value_counts()
    for status, count in status_counts.items():
        print(f"  {status}: {count}")
    
    # Pillar breakdown
    if "pillar_primary" in df.columns:
        print(f"\nBy research pillar:")
        pillar_counts = df["pillar_primary"].value_counts()
        for pillar, count in pillar_counts.items():
            if pillar and str(pillar) != "nan":
                print(f"  {pillar}: {count}")
    
    print("="*60)

def main():
    # Find config file
    script_dir = Path(__file__).resolve().parent
    config_paths = [
        script_dir / "config.yaml",
        script_dir.parent / "config.yaml",
        Path.cwd() / "config.yaml"
    ]
    
    config_path = None
    for path in config_paths:
        if path.exists():
            config_path = path
            break
    
    if not config_path:
        print("Error: config.yaml not found. Searched:")
        for path in config_paths:
            print(f"  {path}")
        return 1
    
    cfg = load_config(config_path)
    store = Store(Path(cfg["base_dir"]))

    ap = argparse.ArgumentParser(description="Ultimate literature processing pipeline with 7-method PDF acquisition")
    ap.add_argument("--force", action="store_true", help="reprocess even if already extracted")
    ap.add_argument("--min-stage", choices=["tei", "extracted"], default="extracted",
                    help="dedupe threshold when skipping already-processed DOIs")
    ap.add_argument("--install-deps", action="store_true", 
                    help="Install all dependencies (PyPaperBot, BeautifulSoup, etc.)")
    ap.add_argument("--stats-only", action="store_true",
                    help="Only show processing statistics without running pipeline")
    ap.add_argument("--test-doi", type=str,
                    help="Test PDF acquisition for a single DOI")
    args = ap.parse_args()

    # Stats only mode
    if args.stats_only:
        print_statistics(store)
        return 0

    # Install dependencies if requested
    if args.install_deps:
        print("Installing dependencies for ultimate PDF acquisition...")
        deps = [
            "PyPaperBot",
            "beautifulsoup4", 
            "setuptools"  # For distutils compatibility
        ]
        for dep in deps:
            try:
                subprocess.run([sys.executable, "-m", "pip", "install", dep], 
                             check=True, capture_output=True)
                print(f"✓ {dep} installed")
            except subprocess.CalledProcessError as e:
                print(f"✗ Failed to install {dep}: {e}")
        return 0

    # Test single DOI mode
    if args.test_doi:
        print(f"Testing PDF acquisition for DOI: {args.test_doi}")
        doi = normalize_doi(args.test_doi)
        
        # Get metadata first
        cr = fetch_crossref(doi)
        s2 = fetch_semanticscholar(doi)
        oa = fetch_unpaywall(doi, cfg["unpaywall"]["email"])
        meta = merge_meta(cr, s2, oa)
        
        print(f"Title: {meta.get('title', 'Unknown')}")
        print(f"Year: {meta.get('year', 'Unknown')}")
        print(f"Journal: {meta.get('journal', 'Unknown')}")
        print(f"OA PDF URL: {meta.get('oa_pdf_url', 'None')}")
        
        # Test PDF acquisition
        test_pdf = _download_pdf_with_ultimate_fallbacks(doi, doi, meta, store)
        if test_pdf:
            print(f"✅ PDF successfully acquired: {test_pdf}")
            print(f"File size: {test_pdf.stat().st_size:,} bytes")
            # Clean up test file
            test_pdf.unlink()
        else:
            print("❌ PDF acquisition failed with all methods")
        
        return 0

    # Check system capabilities
    print("🔍 Checking PDF acquisition capabilities...")
    
    capabilities = []
    
    # Check PyPaperBot
    if _check_pypaperbot_available():
        capabilities.append("✅ PyPaperBot (Google Scholar, Crossref, SciHub, SciDB)")
    else:
        try:
            import PyPaperBot
            print("⚠️ PyPaperBot installed but command test failed")
            print("  Try: pip install setuptools")
            capabilities.append("⚠️ PyPaperBot (may have issues)")
        except ImportError:
            capabilities.append("❌ PyPaperBot not available")

    # Check BeautifulSoup for publisher scraping
    try:
        import bs4
        capabilities.append("✅ Publisher website scraping (BeautifulSoup)")
    except ImportError:
        capabilities.append("❌ Publisher scraping not available (install beautifulsoup4)")

    # Check Sci-Hub
    try:
        from scihub import SciHub
        capabilities.append("✅ Sci-Hub")
    except ImportError:
        capabilities.append("❌ Sci-Hub not available")

    # Always available methods
    capabilities.extend([
        "✅ Open Access (Unpaywall)",
        "✅ Semantic Scholar",
        "✅ arXiv preprints", 
        "✅ Crossref direct links"
    ])

    print("Available PDF acquisition methods:")
    for cap in capabilities:
        print(f"  {cap}")
    
    working_methods = len([c for c in capabilities if c.startswith("✅")])
    print(f"\n🎯 {working_methods} out of 7 methods available")

    # 1) Curated first (local PDFs)
    curated = read_curated_seeds(store)
    print(f"\n📚 Processing {len(curated)} curated papers...")
    
    curated_success = 0
    for row in tqdm(curated, desc="Curated PDFs"):
        doi = normalize_doi(row["doi"]) if row.get("doi") else ""
        try:
            result = process_one(cfg, store,
                        doi=doi,
                        pillar=row.get("pillar", ""),
                        force=args.force,
                        local_pdf=row.get("pdf_path"))
            if result["status"] == "extracted_ok":
                curated_success += 1
        except Exception as e:
            print(f"[curated error] {row.get('pdf_path','?')}: {e}")

    print(f"✅ Curated papers: {curated_success}/{len(curated)} successfully processed")

    # 2) Auto (Ultimate 7-method PDF acquisition)
    auto = read_auto_seeds(store)
    already_done = set()
    if not args.force:
        idx_path = store.index_csv()
        if idx_path.exists():
            df_idx = pd.read_csv(idx_path)
            if args.min_stage == "extracted":
                already_done = set(df_idx.loc[df_idx["extracted"].eq("yes"), "doi"].str.lower())
            else:
                already_done = set(df_idx.loc[df_idx["tei"].eq("yes"), "doi"].str.lower())

    to_process = [row for row in auto if normalize_doi(row["doi"]) not in already_done or args.force]
    print(f"\n🤖 Processing {len(to_process)} auto-classified papers...")
    
    auto_success = 0
    pdf_acquired = 0
    
    for row in tqdm(to_process, desc="Auto (Ultimate) DOIs"):
        doi = normalize_doi(row["doi"])
        try:
            result = process_one(cfg, store,
                        doi=doi,
                        pillar=row.get("pillar", ""),
                        force=args.force,
                        local_pdf=None)
            
            if result["status"] == "extracted_ok":
                auto_success += 1
                pdf_acquired += 1
            elif result["tei"] == "yes":
                pdf_acquired += 1
                
        except Exception as e:
            print(f"[auto error] {doi}: {e}")

    print(f"✅ Auto papers: {auto_success}/{len(to_process)} fully processed")
    print(f"📄 PDFs acquired: {pdf_acquired}/{len(to_process)} papers")

    # Final statistics
    print_statistics(store)
    
    # Success rate summary
    total_processed = len(curated) + len(to_process)
    total_success = curated_success + auto_success
    if total_processed > 0:
        success_rate = total_success / total_processed * 100
        print(f"\n🎉 Overall success rate: {success_rate:.1f}% ({total_success}/{total_processed})")
        
        if success_rate < 50:
            print("\n💡 Tips to improve success rate:")
            print("  • Install missing dependencies: python ultimate_pipeline.py --install-deps")
            print("  • Check that GROBID service is running")
            print("  • Verify Ollama is available for extraction")
            print("  • Some papers may genuinely not have accessible PDFs")

    return 0

if __name__ == "__main__":
    exit(main())