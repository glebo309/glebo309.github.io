#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Complete enhanced literature pipeline with citation-based fallback and 7-method PDF acquisition
Standalone version - includes all functionality
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
import re
import ast
from pathlib import Path
from typing import Optional, Dict, Any, List, Set, Tuple
from urllib.parse import urljoin, urlparse, quote
from concurrent.futures import ThreadPoolExecutor, as_completed
from threading import Lock

import pandas as pd
from tqdm import tqdm
import requests

# Add the parent directory to Python path to import local modules
sys.path.insert(0, str(Path(__file__).parent.parent))

try:
    from pipeline.config import load_config
    from pipeline.storage import Store, doi_to_slug
    from pipeline.sources import (
        fetch_crossref,
        fetch_semanticscholar,
        fetch_unpaywall,
        best_pdf_url_from_unpaywall,
    )
    from pipeline.grobid_client import grobid_process_pdf
    import pipeline.sources as sources
    from pipeline.tei_utils import parse_tei, get_title, get_abstract, get_body_text, get_references
    from pipeline.extract import run_extraction
except ImportError as e:
    print(f"Error importing modules: {e}")
    print("Make sure you're running this from the literature directory")
    print("Or adjust the import paths for your setup")
    sys.exit(1)

# ------------------------- helpers -------------------------
INDEX_LOCK = Lock()

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

def _try_sanitize_pdf(src: Path, store: 'Store') -> Optional[Path]:
    """
    Attempt to repair a problematic PDF using pikepdf, returning a new temp file.
    Returns None if pikepdf is not available or repair fails.
    """
    try:
        import pikepdf  # type: ignore
    except Exception:
        return None

    try:
        tmp_out = Path(tempfile.mkstemp(dir=store.tmp, suffix=".pdf")[1])
        with pikepdf.open(str(src)) as pdf:
            pdf.save(str(tmp_out))
        # Basic sanity check
        if tmp_out.exists() and tmp_out.stat().st_size > 1024:
            return tmp_out
    except Exception:
        try:
            if 'tmp_out' in locals() and tmp_out.exists():
                tmp_out.unlink(missing_ok=True)
        except Exception:
            pass

def _try_fetch_pypaperbot_by_title(title: str, year: Optional[int], outpath: Path, temp_dir: Path) -> None:
    """Use PyPaperBot to search by title (and year hint) and download a PDF.
    Raises on failure.
    """
    # Prepare temp dir
    safe_key = re.sub(r"[^\w]+", "_", (title or "untitled"))[:60]
    pypb_download_dir = temp_dir / f"pypb_title_{safe_key}"
    pypb_download_dir.mkdir(exist_ok=True)

    try:
        query = f"{title} {year}" if year else title
        cmd = [
            sys.executable, "-m", "PyPaperBot",
            "--search", query,
            "--dwn-dir", str(pypb_download_dir),
            "--scholar",  # prefer Google Scholar
            "--limit", "1",
        ]
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=180)
        if result.returncode != 0:
            raise RuntimeError(f"PyPaperBot search failed: {result.stderr.strip()[:200]}")

        # Find a PDF
        pdf_files = list(pypb_download_dir.glob("*.pdf"))
        if not pdf_files:
            raise RuntimeError("PyPaperBot title search produced no PDFs")
        downloaded_pdf = pdf_files[0]
        if downloaded_pdf.stat().st_size < 1024:
            raise RuntimeError("PyPaperBot title PDF too small")
        downloaded_pdf.rename(outpath)
    finally:
        try:
            import shutil
            shutil.rmtree(pypb_download_dir, ignore_errors=True)
        except Exception:
            pass
    return None

def upsert_index(store: Store, row: Dict[str, Any]) -> None:
    """Overwrite/update a single DOI row in the global index CSV."""
    idx_path = store.index_csv()
    with INDEX_LOCK:
        if idx_path.exists():
            df = pd.read_csv(idx_path)
            df = df[df["doi"].str.lower() != row["doi"].lower()]
            df = pd.concat([df, pd.DataFrame([row])], ignore_index=True)
        else:
            df = pd.DataFrame([row])
        df.to_csv(idx_path, index=False)

# ------------------------- Citation-based search -------------------------

def search_paper_by_citation(title: str, authors: List[str], year: Optional[int], journal: str = "") -> Optional[str]:
    """
    Search for a paper's DOI using title, authors, and other metadata
    Returns DOI if found, None otherwise
    """
    
    # Clean title for search
    clean_title = re.sub(r'[^\w\s]', '', title).strip()
    
    # Method 1: Search Crossref
    doi = _search_crossref_by_metadata(clean_title, authors, year, journal)
    if doi:
        return doi
    
    # Method 2: Search Semantic Scholar
    doi = _search_semantic_scholar_by_metadata(clean_title, authors, year)
    if doi:
        return doi
    
    # Fallbacks: try broader searches when the title may be truncated
    # Crossref broad bibliographic search
    doi = _search_crossref_by_metadata(clean_title, [], None, "")
    if doi:
        return doi
    # Semantic Scholar broad title-only
    doi = _search_semantic_scholar_by_metadata(clean_title, [], None)
    if doi:
        return doi
    
    return None

def _search_crossref_by_metadata(title: str, authors: List[str], year: Optional[int], journal: str) -> Optional[str]:
    """Search Crossref API by title, authors, etc."""
    try:
        # Attempt 1: title-focused search with year filter
        headers = {"User-Agent": UA_DEFAULT}
        base_url = "https://api.crossref.org/works"

        def find_match(items):
            for item in items:
                cand_title = (" ".join(item.get('title') or [])).strip()
                if not cand_title:
                    continue
                if _titles_match(title, cand_title):
                    item_year = None
                    published = item.get('published-print') or item.get('issued')
                    if published and 'date-parts' in published:
                        try:
                            item_year = published['date-parts'][0][0]
                        except (IndexError, TypeError):
                            pass
                    if year and item_year and abs(item_year - year) > 1:
                        continue
                    return item.get('DOI')
            return None

        # Exact title query
        params = {"query.title": title, "rows": 20}
        if year:
            params["filter"] = f"from-pub-date:{year-1},until-pub-date:{year+1}"
        r = requests.get(base_url, params=params, headers=headers, timeout=20)
        if r.ok:
            doi = find_match(((r.json() or {}).get('message') or {}).get('items') or [])
            if doi:
                return doi

        # Broader bibliographic query
        params = {"query.bibliographic": title, "rows": 50}
        r = requests.get(base_url, params=params, headers=headers, timeout=20)
        if r.ok:
            doi = find_match(((r.json() or {}).get('message') or {}).get('items') or [])
            if doi:
                return doi
        
    except Exception as e:
        print(f"Crossref search failed: {e}")
    
    return None

def _search_semantic_scholar_by_metadata(title: str, authors: List[str], year: Optional[int]) -> Optional[str]:
    """Search Semantic Scholar API by title and authors"""
    try:
        url = "https://api.semanticscholar.org/graph/v1/paper/search"
        headers = {"User-Agent": UA_DEFAULT}

        def try_query(q: str, limit: int) -> Optional[str]:
            params = {'query': q, 'limit': limit, 'fields': 'title,authors,year,externalIds'}
            resp = requests.get(url, params=params, headers=headers, timeout=20)
            if not resp.ok:
                return None
            data = resp.json()
            for paper in data.get('data', []) or []:
                paper_title = paper.get('title', '')
                if _titles_match(title, paper_title):
                    if year:
                        py = paper.get('year')
                        if py and abs(py - year) > 1:
                            continue
                    ext = paper.get('externalIds') or {}
                    if 'DOI' in ext and ext['DOI']:
                        return ext['DOI']
            return None

        # Attempt with year boosted
        q1 = f"{title} {year}" if year else title
        doi = try_query(q1, 15)
        if doi:
            return doi
        # Title-only, larger limit
        doi = try_query(title, 25)
        if doi:
            return doi
        
    except Exception as e:
        print(f"Semantic Scholar search failed: {e}")
    
    return None

def _titles_match(title1: str, title2: str) -> bool:
    """Robust, lenient title matcher.
    - Exact or prefix match (handles truncated titles)
    - Jaccard similarity over token sets with a moderate threshold
    """
    if not title1 or not title2:
        return False

    a = re.sub(r"\s+", " ", title1.strip().lower())
    b = re.sub(r"\s+", " ", title2.strip().lower())
    if not a or not b:
        return False
    if a == b:
        return True
    # Prefix either direction to allow truncation
    if a.startswith(b[:25]) or b.startswith(a[:25]):
        return True

    # Token-based Jaccard similarity
    def toks(s: str) -> set:
        return set(re.sub(r"[^\w\s]", "", s).split())

    ta, tb = toks(a), toks(b)
    if not ta or not tb:
        return False
    inter = len(ta & tb)
    uni = len(ta | tb)
    sim = (inter / uni) if uni else 0.0
    return sim >= 0.6

# ------------------------- Ultimate PDF fetching system -------------------------

UA_DEFAULT = "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124 Safari/537.36"
# Whether to prioritize repositories (OA/Semantic Scholar) before publisher
PREFER_REPOSITORIES = True

def _session_with_headers() -> requests.Session:
    s = requests.Session()
    s.headers.update({"User-Agent": UA_DEFAULT})
    return s

def _extract_doi_from_tei(text: str) -> Optional[str]:
    """Extract a DOI from TEI XML text using a regex."""
    if not text:
        return None
    # Common DOI pattern
    m = re.search(r"\b10\.[0-9]{4,9}/\S+\b", text, flags=re.IGNORECASE)
    if not m:
        return None
    doi = m.group(0)
    # Trim trailing punctuation or XML entities
    doi = doi.rstrip('.,;\')\"]')
    return normalize_doi(doi)

def _rename_paper_dir(store: 'Store', old_key: str, new_key: str) -> None:
    """Move/merge a paper directory from a temporary key to the DOI-based key."""
    try:
        import shutil
        old_dir = store.paper_dir(old_key)
        new_dir = store.paper_dir(new_key)
        if old_dir == new_dir:
            return
        if not old_dir.exists():
            return
        new_dir.mkdir(parents=True, exist_ok=True)
        # Move files that don't already exist in the destination
        for p in old_dir.iterdir():
            dest = new_dir / p.name
            if dest.exists():
                # Special-case logs: append
                if p.name == "logs.txt":
                    try:
                        dest.write_text(dest.read_text(encoding="utf-8") + p.read_text(encoding="utf-8"), encoding="utf-8")
                    except Exception:
                        pass
                continue
            try:
                shutil.move(str(p), str(dest))
            except Exception:
                pass
        # Remove old dir if empty
        try:
            old_dir.rmdir()
        except Exception:
            pass
    except Exception:
        pass

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
    # Fallback: try title search -> openAccessPdf
    try:
        title = (data.get('title') or '').strip()
        if title:
            s2_url = "https://api.semanticscholar.org/graph/v1/paper/search"
            params = {"query": title, "limit": 8, "fields": "title,openAccessPdf"}
            r = requests.get(s2_url, params=params, headers=headers, timeout=20)
            if r.ok:
                dd = r.json()
                for p in (dd.get('data') or []):
                    if not _titles_match(title, p.get('title', '')):
                        continue
                    oap = p.get('openAccessPdf') or {}
                    pdf_url = oap.get('url')
                    if not pdf_url:
                        continue
                    session = _session_with_headers()
                    with session.get(pdf_url, stream=True, timeout=60, allow_redirects=True) as r2:
                        r2.raise_for_status()
                        with outpath.open("wb") as f:
                            for chunk in r2.iter_content(chunk_size=1024*1024):
                                if chunk:
                                    f.write(chunk)
                    if outpath.stat().st_size > 1024:
                        return
    except Exception:
        pass
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
        # Publisher-specific fast paths by DOI prefix
        try:
            prefix = doi.split('/')[0]
        except Exception:
            prefix = ''
        # Nature / Springer (10.1038)
        if prefix == '10.1038':
            candidates = [
                f"https://www.nature.com/articles/{doi.split('/')[-1]}.pdf",
                f"https://www.nature.com/articles/{doi.split('/')[-1]}/pdf",
            ]
            for cand in candidates:
                try:
                    with session.get(cand, stream=True, timeout=45, allow_redirects=True, headers={"Accept": "application/pdf", "User-Agent": UA_DEFAULT}) as r:
                        if 'pdf' in r.headers.get('Content-Type', '').lower():
                            r.raise_for_status()
                            with outpath.open("wb") as f:
                                for chunk in r.iter_content(chunk_size=1024*1024):
                                    if chunk:
                                        f.write(chunk)
                            if outpath.stat().st_size > 1024:
                                return
                except Exception:
                    pass
        # OUP (10.1093)
        if prefix == '10.1093':
            base = f"https://academic.oup.com/doi/{doi}"
            candidates = [
                f"https://academic.oup.com/doi/pdf/{doi}",
                f"{base}/pdf",
            ]
            for cand in candidates:
                try:
                    with session.get(cand, stream=True, timeout=45, allow_redirects=True, headers={"Accept": "application/pdf", "User-Agent": UA_DEFAULT}) as r:
                        if 'pdf' in r.headers.get('Content-Type', '').lower():
                            r.raise_for_status()
                            with outpath.open("wb") as f:
                                for chunk in r.iter_content(chunk_size=1024*1024):
                                    if chunk:
                                        f.write(chunk)
                            if outpath.stat().st_size > 1024:
                                return
                except Exception:
                    pass
        # Science/AAAS (10.1126)
        if prefix == '10.1126':
            candidates = [
                f"https://www.science.org/doi/pdf/{doi}",
                f"https://www.science.org/doi/epdf/{doi}",
            ]
            for cand in candidates:
                try:
                    with session.get(cand, stream=True, timeout=45, allow_redirects=True, headers={"Accept": "application/pdf", "User-Agent": UA_DEFAULT}) as r:
                        if 'pdf' in r.headers.get('Content-Type', '').lower():
                            r.raise_for_status()
                            with outpath.open("wb") as f:
                                for chunk in r.iter_content(chunk_size=1024*1024):
                                    if chunk:
                                        f.write(chunk)
                            if outpath.stat().st_size > 1024:
                                return
                except Exception:
                    pass

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
                    content_type = r.headers.get('content-type', '')
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

def _scrape_pdf_from_landing(landing_url: str, outpath: Path) -> bool:
    """Best-effort scrape to find a PDF link on a landing page and download it.
    Returns True if a valid PDF was saved to outpath.
    """
    try:
        from bs4 import BeautifulSoup
    except Exception:
        return False
    session = _session_with_headers()
    # Fetch landing page
    try:
        r = session.get(landing_url, timeout=30, allow_redirects=True)
        r.raise_for_status()
    except Exception:
        return False
    soup = BeautifulSoup(r.text, 'html.parser')
    candidates = []
    # <a> tags
    for a in soup.find_all('a', href=True):
        href = a['href']
        if href.lower().endswith('.pdf'):
            candidates.append(urljoin(r.url, href))
    # <link> tags
    for lk in soup.find_all('link', href=True):
        href = lk['href']
        typ = (lk.get('type') or '').lower()
        if href.lower().endswith('.pdf') or 'pdf' in typ:
            candidates.append(urljoin(r.url, href))
    # Deduplicate while preserving order
    seen = set()
    uniq = []
    for c in candidates:
        if c not in seen:
            seen.add(c)
            uniq.append(c)
    # Try downloads
    for pdf_url in uniq[:5]:
        try:
            with session.get(pdf_url, stream=True, timeout=60, allow_redirects=True, headers={"Accept": "application/pdf", "User-Agent": UA_DEFAULT}) as rr:
                ctype = rr.headers.get('Content-Type', '')
                if 'pdf' not in ctype.lower() and not pdf_url.lower().endswith('.pdf'):
                    continue
                rr.raise_for_status()
                with outpath.open('wb') as f:
                    for chunk in rr.iter_content(chunk_size=1 << 20):
                        if chunk:
                            f.write(chunk)
            if outpath.stat().st_size > 1024:
                return True
        except Exception:
            continue
    return False

def _try_fetch_scihub(doi: str, outpath: Path) -> None:
    """Working SciHub method using manual access (FIXED!)"""
    
    # Working SciHub domains (tested and verified)
    scihub_domains = [
        "https://sci-hub.se",
        "https://sci-hub.ren"
    ]
    
    headers = {
        'User-Agent': 'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36'
    }
    
    for domain in scihub_domains:
        try:
            scihub_url = f"{domain}/{doi}"
            
            session = requests.Session()
            session.headers.update(headers)
            
            response = session.get(scihub_url, timeout=30, allow_redirects=True)
            response.raise_for_status()
            
            # Check if direct PDF
            if response.headers.get('content-type', '').startswith('application/pdf'):
                with outpath.open('wb') as f:
                    f.write(response.content)
                
                if outpath.stat().st_size > 1024:
                    return  # Success!
                else:
                    continue  # Try next domain
            
            # Parse HTML for PDF links
            try:
                from bs4 import BeautifulSoup
            except ImportError:
                raise RuntimeError("BeautifulSoup required for SciHub")
            
            soup = BeautifulSoup(response.content, 'html.parser')
            
            pdf_links = []
            for link in soup.find_all(['a', 'iframe', 'embed']):
                href = link.get('href') or link.get('src')
                if href and ('.pdf' in href.lower()):
                    if not href.startswith('http'):
                        if href.startswith('//'):
                            href = f"https:{href}"
                        elif href.startswith('/'):
                            href = f"{domain}{href}"
                        else:
                            href = f"{domain}/{href}"
                    pdf_links.append(href)
            
            # Try downloading PDFs
            for pdf_url in pdf_links[:3]:
                try:
                    pdf_response = session.get(pdf_url, timeout=60, allow_redirects=True)
                    pdf_response.raise_for_status()
                    
                    content_type = pdf_response.headers.get('content-type', '')
                    if 'pdf' in content_type.lower() or pdf_url.endswith('.pdf'):
                        with outpath.open('wb') as f:
                            f.write(pdf_response.content)
                        
                        if outpath.stat().st_size > 1024:
                            return  # Success!
                    
                except Exception:
                    continue
            
        except Exception:
            continue  # Try next domain
    
    raise RuntimeError("SciHub download failed from all working domains")

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
                                        store: Store,
                                        exclude_sources: Optional[Set[str]] = None) -> Tuple[Optional[Path], Optional[str]]:
    """
    OPTIMIZED PDF download with efficient ordering:
    1. Open Access (Unpaywall) - Free, legal, fast
    2. Semantic Scholar - Academic repository, good quality
    3. Publisher Direct - Often fastest when available
    4. PyPaperBot - Multi-source aggregator, good success rate
    5. SciHub - Reliable fallback (FIXED!)
    6. arXiv - Preprint server (specialized)
    7. Crossref - Last resort backup
    """
    session = _session_with_headers()
    tmp_pdf = Path(tempfile.mkstemp(dir=store.tmp, suffix=".pdf")[1])
    tried = []
    exclude_sources = exclude_sources or set()
    
    # Small delay to be respectful
    time.sleep(0.5)

    # 1) Open Access (Unpaywall)
    if doi and ("unpaywall" not in exclude_sources):
        try:
            store.append_log(doi_key, "→ Attempting Open Access (Unpaywall)...")
            oa_url = meta.get("oa_pdf_url") or ""
            if not oa_url:
                # Try to derive from Unpaywall data
                oa = meta.get("unpaywall") or {}
                oa_url, _lic = best_pdf_url_from_unpaywall(oa or {})
            if oa_url:
                _try_fetch_oa_pdf(session, oa_url, tmp_pdf)
                store.append_log(doi_key, "✓ Open Access PDF fetched")
                return tmp_pdf, "unpaywall"
            else:
                # NEW: iterate all oa_locations as a broader fallback
                oa = meta.get("unpaywall") or {}
                got = False
                for loc in (oa.get("oa_locations") or []):
                    cand = loc.get("url_for_pdf") or loc.get("url") or ""
                    if not cand:
                        continue
                    try:
                        _try_fetch_oa_pdf(session, cand, tmp_pdf)
                        store.append_log(doi_key, f"✓ OA location PDF fetched: {cand}")
                        got = True
                        return tmp_pdf, "unpaywall"
                    except Exception:
                        continue
                if not got:
                    raise RuntimeError("No OA URL available")
        except Exception as e:
            tried.append(f"unpaywall:{type(e).__name__}")
            store.append_log(doi_key, f"✗ Unpaywall failed: {e}")

    # 2/3) Order Semantic Scholar vs Publisher based on PREFER_REPOSITORIES
    if PREFER_REPOSITORIES:
        # 2) Semantic Scholar (OA)
        if doi and ("semanticscholar" not in exclude_sources):
            try:
                store.append_log(doi_key, "→ Attempting Semantic Scholar...")
                _try_fetch_semantic_scholar_pdf(doi, tmp_pdf)
                store.append_log(doi_key, "✓ Semantic Scholar PDF fetched successfully")
                return tmp_pdf, "semanticscholar"
            except Exception as e:
                tried.append(f"semanticscholar:{type(e).__name__}")
                store.append_log(doi_key, f"✗ Semantic Scholar failed: {e}")

            # NEW: Title-based S2 OA PDF fallback even when DOI is known
            try:
                title = (meta.get("title") or "").strip()
                year = meta.get("year")
                if title:
                    store.append_log(doi_key, "→ S2 title-based OA PDF fallback...")
                    s2_url = "https://api.semanticscholar.org/graph/v1/paper/search"
                    params = {"query": f"{title} {year}" if year else title, "limit": 10, "fields": "title,openAccessPdf,year"}
                    r = requests.get(s2_url, params=params, headers={"User-Agent": UA_DEFAULT}, timeout=20)
                    if r.ok:
                        dd = r.json()
                        for p in (dd.get('data') or []):
                            if not _titles_match(title, p.get('title', '')):
                                continue
                            if year and p.get('year') and abs(int(p.get('year')) - int(year)) > 2:
                                continue
                            oap = p.get('openAccessPdf') or {}
                            pdf_url = oap.get('url')
                            if not pdf_url:
                                continue
                            with session.get(pdf_url, stream=True, timeout=60, allow_redirects=True) as r2:
                                r2.raise_for_status()
                                with tmp_pdf.open("wb") as f:
                                    for chunk in r2.iter_content(chunk_size=1 << 20):
                                        if chunk:
                                            f.write(chunk)
                            if tmp_pdf.stat().st_size > 1024:
                                store.append_log(doi_key, "✓ S2 title-based OA PDF fetched")
                                return tmp_pdf, "semanticscholar_title"
            except Exception as e:
                store.append_log(doi_key, f"S2 title-based fallback failed: {e}")
        # 3) Publisher second
        if doi and ("publisher" not in exclude_sources):
            try:
                store.append_log(doi_key, "→ Attempting publisher direct access...")
                _try_fetch_publisher_direct(doi, tmp_pdf)
                store.append_log(doi_key, "✓ Publisher direct PDF fetched successfully")
                return tmp_pdf, "publisher"
            except Exception as e:
                tried.append(f"publisher:{type(e).__name__}")
                store.append_log(doi_key, f"✗ Publisher direct failed: {e}")
    else:
        # 2) Publisher first
        if doi and ("publisher" not in exclude_sources):
            try:
                store.append_log(doi_key, "→ Attempting publisher direct access...")
                _try_fetch_publisher_direct(doi, tmp_pdf)
                store.append_log(doi_key, "✓ Publisher direct PDF fetched successfully")
                return tmp_pdf, "publisher"
            except Exception as e:
                tried.append(f"publisher:{type(e).__name__}")
                store.append_log(doi_key, f"✗ Publisher direct failed: {e}")
        # 3) Semantic Scholar second
        if doi and ("semantic_scholar" not in exclude_sources):
            try:
                store.append_log(doi_key, "→ Attempting Semantic Scholar...")
                _try_fetch_semantic_scholar_pdf(doi, tmp_pdf)
                store.append_log(doi_key, "✓ Semantic Scholar PDF fetched successfully")
                return tmp_pdf, "semantic_scholar"
            except Exception as e:
                tried.append(f"semantic_scholar:{type(e).__name__}")
                store.append_log(doi_key, f"✗ Semantic Scholar failed: {e}")

    # 4) PyPaperBot - MULTI-SOURCE AGGREGATOR, GOOD SUCCESS RATE
    if doi and _check_pypaperbot_available() and ("pypaperbot" not in exclude_sources):
        try:
            store.append_log(doi_key, "→ Attempting PyPaperBot...")
            _try_fetch_pypaperbot(doi, tmp_pdf, store.tmp)
            store.append_log(doi_key, "✓ PyPaperBot PDF fetched successfully")
            return tmp_pdf, "pypaperbot"
        except Exception as e:
            tried.append(f"pypaperbot:{type(e).__name__}")
            store.append_log(doi_key, f"✗ PyPaperBot failed: {e}")

    # 5) SciHub - RELIABLE FALLBACK (NOW FIXED!)
    if doi and ("scihub" not in exclude_sources):
        try:
            store.append_log(doi_key, "→ Attempting SciHub (fixed method)...")
            _try_fetch_scihub(doi, tmp_pdf)
            store.append_log(doi_key, "✓ SciHub PDF fetched successfully")
            return tmp_pdf, "scihub"
        except Exception as e:
            tried.append(f"scihub:{type(e).__name__}")
            store.append_log(doi_key, f"✗ SciHub failed: {e}")

    # 6) arXiv - SPECIALIZED FOR PREPRINTS
    if doi and ("arxiv" not in exclude_sources):
        try:
            store.append_log(doi_key, "→ Checking arXiv...")
            _try_fetch_arxiv_pdf(doi, tmp_pdf)
            store.append_log(doi_key, "✓ arXiv PDF fetched successfully")
            return tmp_pdf, "arxiv"
        except Exception as e:
            tried.append(f"arxiv:{type(e).__name__}")
            store.append_log(doi_key, f"✗ arXiv failed: {e}")

    # 7) Crossref Direct Links - LAST RESORT BACKUP
    if doi and ("crossref" not in exclude_sources):
        try:
            store.append_log(doi_key, "→ Trying Crossref direct links...")
            _try_fetch_crossref_links(doi, tmp_pdf)
            store.append_log(doi_key, "✓ Crossref PDF fetched successfully")
            return tmp_pdf, "crossref"
        except Exception as e:
            tried.append(f"crossref:{type(e).__name__}")
            store.append_log(doi_key, f"✗ Crossref direct failed: {e}")

    # Clean up if all methods failed
    try:
        tmp_pdf.unlink(missing_ok=True)
    except Exception:
        pass
    
    store.append_log(doi_key, f"✗ NO_PDF after all 7 optimized methods [{', '.join(tried) or 'none'}]")
    return None, None

# (duplicate _titles_match removed)


def _try_pdf_search_without_doi(paper_key: str, title: str, authors: List[str], 
                               year: Optional[int], store) -> Tuple[Optional[Path], Optional[str]]:
    """
    For papers without DOI: try to discover DOI from title/authors/year, then run
    the 7-method PDF acquisition using the discovered DOI.
    Returns (pdf_path, discovered_doi) where either may be None.
    """
    store.append_log(paper_key, "→ Attempting title-based DOI discovery...")

    # Discover DOI
    discovered_doi = search_paper_by_citation(title, authors, year)
    if not discovered_doi:
        store.append_log(paper_key, "✗ DOI not found via title-based search")
        # NEW: try to fetch an open-access PDF by title via Semantic Scholar, then let GROBID extract DOI
        try:
            url = "https://api.semanticscholar.org/graph/v1/paper/search"
            headers = {"User-Agent": UA_DEFAULT}
            q = f"{title} {year}" if year else title
            params = {"query": q, "limit": 12, "fields": "title,openAccessPdf,year,url"}
            r = requests.get(url, params=params, headers=headers, timeout=20)
            if r.ok:
                data = r.json()
                for paper in (data.get("data") or []):
                    if not _titles_match(title, paper.get("title", "")):
                        continue
                    if year:
                        py = paper.get("year")
                        if py and abs(py - year) > 2:
                            continue
                    # 1) direct OA PDF
                    oap = paper.get("openAccessPdf") or {}
                    pdf_url = oap.get("url")
                    if pdf_url:
                        tmp_pdf = Path(tempfile.mkstemp(dir=store.tmp, suffix=".pdf")[1])
                        session = _session_with_headers()
                        with session.get(pdf_url, stream=True, timeout=60, allow_redirects=True) as resp:
                            resp.raise_for_status()
                            with tmp_pdf.open("wb") as f:
                                for chunk in resp.iter_content(chunk_size=1 << 20):
                                    if chunk:
                                        f.write(chunk)
                        if tmp_pdf.stat().st_size >= 1024:
                            store.append_log(paper_key, "✓ Open-access PDF fetched via Semantic Scholar title search")
                            return tmp_pdf, None
                        tmp_pdf.unlink(missing_ok=True)
                    # 2) landing page scrape as a last resort
                    landing = (paper.get("url") or "").strip()
                    if landing:
                        try:
                            tmp_pdf = Path(tempfile.mkstemp(dir=store.tmp, suffix=".pdf")[1])
                            if _scrape_pdf_from_landing(landing, tmp_pdf):
                                store.append_log(paper_key, f"✓ PDF scraped from landing page: {landing}")
                                return tmp_pdf, None
                            else:
                                tmp_pdf.unlink(missing_ok=True)
                        except Exception:
                            pass
        except Exception as e:
            store.append_log(paper_key, f"Semantic Scholar title-PDF fallback failed: {e}")
        # 3) PyPaperBot by title as a last-ditch fallback
        try:
            if _check_pypaperbot_available():
                tmp_pdf = Path(tempfile.mkstemp(dir=store.tmp, suffix=".pdf")[1])
                _try_fetch_pypaperbot_by_title(title, year, tmp_pdf, store.tmp)
                if tmp_pdf.exists() and tmp_pdf.stat().st_size > 1024:
                    store.append_log(paper_key, "✓ PDF fetched via PyPaperBot title search")
                    return tmp_pdf, None
                else:
                    try:
                        tmp_pdf.unlink(missing_ok=True)
                    except Exception:
                        pass
        except Exception as e:
            store.append_log(paper_key, f"PyPaperBot title fallback failed: {e}")
        return None, None

    store.append_log(paper_key, f"✓ DOI found via citation search: {discovered_doi}")

    # Build minimal meta and run optimized acquisition
    meta = {
        "title": title,
        "authors": authors,
        "year": year,
        "journal": "",
        "doi": discovered_doi,
        "fallback_search": True,
    }
    pdf_path, _src = _download_pdf_with_ultimate_fallbacks(paper_key, discovered_doi, meta, store)
    if pdf_path:
        store.append_log(paper_key, "✓ PDF acquired after DOI discovery")
        return pdf_path, discovered_doi

    store.append_log(paper_key, "✗ PDF acquisition failed after DOI discovery")
    return None, discovered_doi

# ------------------------- Enhanced seed reading -------------------------

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

def read_auto_seeds_enhanced(store: Store) -> List[Dict[str, Any]]:
    """
    Enhanced version that handles papers without DOIs using citation data
    """
    seeds: List[Dict[str, Any]] = []
    auto_path = store.base / "core_output" / "combined_pillar_assignments.csv"
    
    if not auto_path.exists():
        print(f"⚠️ auto seeds not found at {auto_path}")
        return seeds
    
    df = pd.read_csv(auto_path)
    
    for _, r in df.iterrows():
        row_dict = r.to_dict()
        
        # Get DOI
        doi_raw = row_dict.get("doi")
        if not doi_raw or str(doi_raw).lower() == "nan" or pd.isna(doi_raw):
            doi = ""
        else:
            doi = str(doi_raw).strip()
        
        # Get other metadata
        title = str(row_dict.get("title", "")).strip()
        year = row_dict.get("year")
        journal = str(row_dict.get("journal", "")).strip()
        
        # Parse authors
        authors_str = str(row_dict.get("authors", "")).strip()
        authors = []
        if authors_str and authors_str != "nan":
            try:
                # Try to parse as list literal safely
                if authors_str.startswith('['):
                    parsed = ast.literal_eval(authors_str)
                    if isinstance(parsed, list):
                        authors = [str(a).strip() for a in parsed if str(a).strip()]
                    else:
                        authors = [str(parsed).strip()]
                else:
                    authors = [authors_str]
            except Exception:
                authors = [authors_str]
        
        # If no DOI, try to find one using citation data
        if not doi and title:
            print(f"🔍 Searching for DOI: {title}")
            found_doi = search_paper_by_citation(title, authors, year, journal)
            if found_doi:
                doi = found_doi
                print(f"✅ Found DOI: {doi}")
            else:
                print(f"❌ No DOI found for: {title}")
        
        # Skip if still no DOI and no title
        if not doi and not title:
            print(f"⚠️ Skipping row with no DOI or title")
            continue
        
        # Create seed entry
        seed = {
            "doi": doi.lower() if doi else "",
            "title": title,
            "pillar": str(row_dict.get("pillar", "")).strip(),
            "priority": "auto",
            "source": "classification",
            "notes": "",
            "year": year,
            "journal": journal,
            "authors": authors,
            "raw_citation": str(row_dict.get("raw_citation", "")).strip(),
            "fallback_search": not bool(doi_raw and str(doi_raw).lower() != "nan")  # Mark if we had to search
        }
        
        seeds.append(seed)
    
    print(f"📊 Processed {len(seeds)} auto seeds ({len([s for s in seeds if s['fallback_search']])} required DOI search)")
    return seeds

# ------------------------- Enhanced processing -------------------------

def process_one_enhanced(cfg,
                        store: Store,
                        seed: Dict[str, Any],
                        force: bool = False,
                        local_pdf: Optional[str] = None) -> Dict[str, Any]:
    """
    Enhanced processor that can handle papers with or without DOIs
    """
    
    doi = seed.get("doi", "").strip()
    title = seed.get("title", "").strip()
    pillar = seed.get("pillar", "").strip()
    
    # Create a unique key for papers without DOI
    if doi:
        paper_key = doi
    else:
        # Use title + year as key for papers without DOI
        year = seed.get("year", "")
        safe_title = re.sub(r'[^\w\s]', '', title)[:50]  # Safe filename
        paper_key = f"no-doi::{safe_title}_{year}".replace(" ", "_")
    
    # Check if already processed
    if not force and already_processed(store, paper_key, min_stage="extracted"):
        meta = {}
        meta_path = store.meta_path(paper_key)
        if meta_path.exists():
            meta = json.loads(meta_path.read_text())
        
        status = "extracted_ok"
        index_row = {
            "doi": doi or paper_key,
            "title": meta.get("title", title),
            "year": meta.get("year", seed.get("year", "")),
            "journal": meta.get("journal", seed.get("journal", "")),
            "pillar_primary": meta.get("pillar_primary", pillar),
            "tei": "yes" if store.tei_path(paper_key).exists() else "no",
            "extracted": "yes",
            "status": status,
        }
        upsert_index(store, index_row)
        store.append_log(paper_key, "SKIP (already processed)")
        return index_row

    # Setup directories
    pdir = store.paper_dir(paper_key)
    pdir.mkdir(parents=True, exist_ok=True)
    store.append_log(paper_key, f"START doi={doi} title={title[:50]} pillar={pillar} force={force}")

    # ---- Enhanced metadata collection ----
    meta_path = store.meta_path(paper_key)
    meta: Dict[str, Any] = {}
    
    if meta_path.exists() and not force:
        meta = json.loads(meta_path.read_text())
    else:
        if local_pdf and not doi:
            # Curated without DOI
            meta = {
                "doi": doi,
                "pillar_primary": pillar,
                "title": title,
                "year": seed.get("year"),
                "authors": seed.get("authors", []),
                "journal": seed.get("journal", ""),
                "crossref": {},
                "semanticscholar": {},
                "unpaywall": {},
                "oa_pdf_url": "",
                "oa_license": "",
                "fallback_search": seed.get("fallback_search", False)
            }
        else:
            # Try to get metadata using DOI or fallback search, with caching
            if doi:
                # Try cache first (7 days)
                cr = store.read_cache_json("crossref", doi, max_age_hours=24*7) or {}
                if not cr:
                    cr = fetch_crossref(doi, timeout=int(cfg.get("fetch", {}).get("timeout_sec", 90)))
                    if cr:
                        store.write_cache_json("crossref", doi, cr)

                s2 = store.read_cache_json("semanticscholar", doi, max_age_hours=24*7) or {}
                if not s2:
                    s2 = fetch_semanticscholar(doi, timeout=int(cfg.get("fetch", {}).get("timeout_sec", 90)))
                    if s2:
                        store.write_cache_json("semanticscholar", doi, s2)

                oa = store.read_cache_json("unpaywall", doi, max_age_hours=24*7) or {}
                if not oa:
                    oa = fetch_unpaywall(doi, cfg["unpaywall"]["email"], timeout=int(cfg.get("fetch", {}).get("timeout_sec", 90)))
                    if oa:
                        store.write_cache_json("unpaywall", doi, oa)
            else:
                cr, s2, oa = {}, {}, {}
            
            meta = merge_meta(cr, s2, oa) if doi else {}
            
            # Fill in metadata from seed if missing
            if not meta.get("title"):
                meta["title"] = title
            if not meta.get("year"):
                meta["year"] = seed.get("year")
            if not meta.get("journal"):
                meta["journal"] = seed.get("journal", "")
            if not meta.get("authors"):
                meta["authors"] = seed.get("authors", [])
            
            meta["doi"] = doi
            meta["pillar_primary"] = pillar
            meta["fallback_search"] = seed.get("fallback_search", False)
            meta["raw_citation"] = seed.get("raw_citation", "")
        
        store.write_json(meta_path, meta)
        store.append_log(paper_key, "metadata saved (enhanced)")

    status = "init"

    # ---- Normalize folder to DOI-based key if possible ----
    if doi and paper_key != doi:
        try:
            _rename_paper_dir(store, paper_key, doi)
            paper_key = doi
        except Exception:
            pass

    # ---- PDF acquisition and TEI processing ----
    tei_path = store.tei_path(paper_key)
    if tei_path.exists() and not force:
        status = "tei_ok"
    else:
        if local_pdf:
            # Use local PDF
            src_pdf = Path(local_pdf)
            if not src_pdf.exists():
                store.append_log(paper_key, f"CURATED_PDF_MISSING: {src_pdf}")
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
                    store.append_log(paper_key, "Grobid TEI saved (curated)")
                    status = "tei_ok"
                except Exception as e:
                    store.append_log(paper_key, f"Grobid error (curated): {e}")
                    status = "tei_failed"
        else:
            # Try PDF acquisition with 7 methods
            src_used: Optional[str] = None
            if doi:
                tmp_pdf, src_used = _download_pdf_with_ultimate_fallbacks(paper_key, doi, meta, store)
            else:
                # For papers without DOI, try to discover DOI and fetch PDF
                store.append_log(paper_key, "No DOI available - limited PDF search options")
                tmp_pdf, discovered_doi = _try_pdf_search_without_doi(
                    paper_key, title, meta.get("authors", []), meta.get("year"), store
                )
                if discovered_doi:
                    # Update local doi and metadata for downstream and indexing
                    # Move directory to DOI-based slug and switch key/paths
                    try:
                        _rename_paper_dir(store, paper_key, discovered_doi)
                    except Exception:
                        pass
                    paper_key = discovered_doi
                    tei_path = store.tei_path(paper_key)
                    meta_path = store.meta_path(paper_key)
                    doi = discovered_doi
                    meta["doi"] = discovered_doi
                    meta["fallback_search"] = True
                    # Backfill cached metadata for discovered DOI
                    cr = store.read_cache_json("crossref", doi, max_age_hours=24*7) or {}
                    s2 = store.read_cache_json("semanticscholar", doi, max_age_hours=24*7) or {}
                    oa = store.read_cache_json("unpaywall", doi, max_age_hours=24*7) or {}
                    # Persist updated metadata
                    store.write_json(meta_path, meta)
            
            if not tmp_pdf:
                status = "locked_no_pdf"
                store.append_log(paper_key, "Skipping Grobid (no accessible PDF)")
            else:
                try:
                    tei_xml = grobid_process_pdf(
                        tmp_pdf,
                        cfg["grobid"]["url"],
                        cfg["grobid"],
                        timeout_sec=int(cfg["grobid"].get("timeout_sec", 120)),
                    )
                    tei_path.write_text(tei_xml, encoding="utf-8")
                    store.append_log(paper_key, "Grobid TEI saved (auto)")
                    status = "tei_ok"
                    # If we started without a DOI, try to extract it from TEI and normalize
                    if not doi:
                        extracted_doi = _extract_doi_from_tei(tei_xml)
                        if extracted_doi:
                            try:
                                store.append_log(paper_key, f"DOI discovered from TEI: {extracted_doi}")
                                _rename_paper_dir(store, paper_key, extracted_doi)
                                paper_key = extracted_doi
                                doi = extracted_doi
                                # refresh paths under new key
                                tei_path = store.tei_path(paper_key)
                                meta_path = store.meta_path(paper_key)
                                # persist updated meta
                                meta["doi"] = doi
                                meta["fallback_search"] = True
                                store.write_json(meta_path, meta)
                            except Exception as e_norm:
                                store.append_log(paper_key, f"Directory/metadata normalization after DOI extract failed: {e_norm}")
                except Exception as e:
                    # Retry with sanitized PDF if BAD_INPUT_DATA or similar
                    err = str(e)
                    store.append_log(paper_key, f"Grobid/PDF error (auto): {e}")
                    if "BAD_INPUT_DATA" in err or "conversion failed" in err:
                        # First try: re-download from an alternate source and retry once
                        alt_pdf = None
                        try:
                            exclude = {src_used} if src_used else set()
                            store.append_log(paper_key, f"Retrying: re-downloading PDF excluding source {exclude or '{}'}")
                            alt_pdf, _alt_src = _download_pdf_with_ultimate_fallbacks(paper_key, doi, meta, store, exclude_sources=exclude)
                        except Exception as e_alt:
                            store.append_log(paper_key, f"Alternate re-download failed: {e_alt}")

                        if alt_pdf:
                            try:
                                store.append_log(paper_key, "Retrying GROBID with alternate PDF copy")
                                tei_xml = grobid_process_pdf(
                                    alt_pdf,
                                    cfg["grobid"]["url"],
                                    cfg["grobid"],
                                    timeout_sec=int(cfg["grobid"].get("timeout_sec", 120)),
                                )
                                tei_path.write_text(tei_xml, encoding="utf-8")
                                store.append_log(paper_key, "Grobid TEI saved (auto, alt re-download)")
                                status = "tei_ok"
                            except Exception as e3:
                                store.append_log(paper_key, f"Grobid retry with alternate PDF failed: {e3}")
                                # Fall through to sanitize
                            finally:
                                try:
                                    if status == "tei_ok":
                                        alt_pdf.unlink(missing_ok=True)
                                except Exception:
                                    pass

                        if status != "tei_ok":
                            # Second try: sanitize and retry
                            repaired = _try_sanitize_pdf(tmp_pdf, store)
                            if repaired:
                                try:
                                    store.append_log(paper_key, "Retrying GROBID with sanitized PDF")
                                    tei_xml = grobid_process_pdf(
                                        repaired,
                                        cfg["grobid"]["url"],
                                        cfg["grobid"],
                                        timeout_sec=int(cfg["grobid"].get("timeout_sec", 120)),
                                    )
                                    tei_path.write_text(tei_xml, encoding="utf-8")
                                    store.append_log(paper_key, "Grobid TEI saved (auto, sanitized)")
                                    status = "tei_ok"
                                except Exception as e2:
                                    store.append_log(paper_key, f"Grobid retry failed after sanitize: {e2}")
                                    status = "tei_failed"
                                finally:
                                    try:
                                        repaired.unlink(missing_ok=True)
                                    except Exception:
                                        pass
                            else:
                                status = "tei_failed"
                    else:
                        status = "tei_failed"
                finally:
                    try:
                        if status == "tei_ok":
                            if tmp_pdf and tmp_pdf.exists():
                                tmp_pdf.unlink(missing_ok=True)
                        else:
                            # Keep acquired PDF for manual GROBID; move to deterministic, slugified name
                            try:
                                keep_path = store.tmp / f"{doi_to_slug(paper_key)}.pdf"
                                if tmp_pdf and tmp_pdf.exists():
                                    if tmp_pdf.resolve() != keep_path.resolve():
                                        keep_path.parent.mkdir(parents=True, exist_ok=True)
                                        tmp_pdf.rename(keep_path)
                                store.append_log(paper_key, f"Kept acquired PDF for manual processing: {keep_path}")
                            except Exception as _e:
                                store.append_log(paper_key, f"Failed to keep tmp PDF: {_e}")
                    except Exception:
                        pass

    # ---- LLM extraction ----
    extracted_path = store.extracted_path(paper_key)
    if status == "tei_ok" and (not extracted_path.exists() or force):
        try:
            root = parse_tei(tei_path.read_text(encoding="utf-8"))
            extraction_title = meta.get("title") or get_title(root)
            abstract = get_abstract(root)
            body_excerpt = get_body_text(root, max_chars=int(cfg["extraction"]["max_chars_for_llm"]))

            out = run_extraction(
                cfg["ollama"]["host"],
                cfg["ollama"]["model"],
                meta.get("pillar_primary", ""),
                extraction_title,
                abstract,
                body_excerpt,
                max_chars=int(cfg["extraction"]["max_chars_for_llm"]),
                temperature=float(cfg["extraction"].get("temperature", 0.0)),
            )
            out["_refs"] = get_references(root, max_n=50)
            out["_title"] = extraction_title
            out["_abstract"] = (abstract or "")[:1000]

            store.write_json(extracted_path, out)
            store.append_log(paper_key, "extraction saved")
            status = "extracted_ok"
        except Exception as e:
            store.append_log(paper_key, f"extract error: {e}")
            status = "extracted_failed"

    # ---- Index update ----
    index_row = {
        "doi": doi or paper_key,
        "title": meta.get("title", title),
        "year": meta.get("year", ""),
        "journal": meta.get("journal", ""),
        "pillar_primary": meta.get("pillar_primary", ""),
        "tei": "yes" if store.tei_path(paper_key).exists() else "no",
        "extracted": "yes" if store.extracted_path(paper_key).exists() else "no",
        "status": status,
        "fallback_search": meta.get("fallback_search", False)
    }
    upsert_index(store, index_row)

    store.append_log(paper_key, f"DONE status={status}")
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
    
    # Citation search breakdown
    if "fallback_search" in df.columns:
        fallback_count = len(df[df["fallback_search"] == True])
        print(f"\nDOI discovery:")
        print(f"  Papers with original DOI: {total - fallback_count}")
        print(f"  Papers found via citation search: {fallback_count}")
    
    print("="*60)

# ------------------------- Environment checks -------------------------

def check_environment(cfg: Dict[str, Any]) -> int:
    """Validate external services and credentials."""
    ok = True

    # GROBID
    try:
        grobid_url = cfg.get("grobid", {}).get("url", "").rstrip("/")
        r = requests.get(f"{grobid_url}/api/isalive", timeout=5)
        if r.status_code == 200:
            print("✅ GROBID reachable and healthy")
        else:
            print(f"❌ GROBID unhealthy (status {r.status_code}) at {grobid_url}")
            ok = False
    except Exception as e:
        print(f"❌ GROBID check failed: {e}")
        ok = False

    # Unpaywall email
    email = (cfg.get("unpaywall", {}).get("email") or "").strip()
    if email:
        print(f"✅ Unpaywall email configured: {email}")
    else:
        print("❌ Unpaywall email missing in config.yaml under unpaywall.email")
        ok = False

    # PyPaperBot
    if _check_pypaperbot_available():
        print("✅ PyPaperBot available")
    else:
        print("⚠️ PyPaperBot not available (optional). pip install PyPaperBot")

    # BeautifulSoup
    try:
        import bs4  # noqa: F401
        print("✅ BeautifulSoup available for publisher scraping")
    except Exception:
        print("⚠️ BeautifulSoup not available (optional). pip install beautifulsoup4 lxml")

    # Ollama
    try:
        ollama = cfg.get("ollama", {})
        host = (ollama.get("host") or "").rstrip("/")
        if host:
            r = requests.get(f"{host}/api/tags", timeout=5)
            if r.ok:
                print(f"✅ Ollama reachable at {host}")
            else:
                print(f"⚠️ Ollama responded with status {r.status_code} at {host}")
        else:
            print("ℹ️ Ollama host not configured (LLM extraction may be limited)")
    except Exception as e:
        print(f"⚠️ Ollama check failed: {e}")

    return 0 if ok else 2

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

    # Apply fetch config to module-level settings
    fetch_cfg = cfg.get("fetch", {})
    # declare globals before usage to avoid local binding
    global UA_DEFAULT, PREFER_REPOSITORIES
    ua_default_local = UA_DEFAULT
    ua = fetch_cfg.get("user_agent") or ua_default_local
    timeout_cfg = int(fetch_cfg.get("timeout_sec", 90))
    prefer_repos = bool(fetch_cfg.get("prefer_repositories", True))

    # Set globals
    UA_DEFAULT = ua
    PREFER_REPOSITORIES = prefer_repos
    # Also propagate to pipeline.sources and reset its session cache
    try:
        sources.UA_DEFAULT = ua
        sources._SESSION = None  # force rebuild with new headers
    except Exception:
        pass

    ap = argparse.ArgumentParser(description="Complete enhanced pipeline with citation-based DOI search and 7-method PDF acquisition")
    ap.add_argument("--force", action="store_true", help="reprocess even if already extracted")
    ap.add_argument("--min-stage", choices=["tei", "extracted"], default="extracted",
                    help="dedupe threshold when skipping already-processed DOIs")
    ap.add_argument("--install-deps", action="store_true", 
                    help="Install all dependencies (PyPaperBot, BeautifulSoup, etc.)")
    ap.add_argument("--stats-only", action="store_true",
                    help="Only show processing statistics without running pipeline")
    ap.add_argument("--test-doi", type=str,
                    help="Test PDF acquisition for a single DOI")
    ap.add_argument("--check", action="store_true", help="Validate GROBID, Unpaywall email, Ollama, and optional tools")
    ap.add_argument("--workers", type=int, default=4, help="Number of worker threads for auto papers (default 4)")
    # Expose grobid flags with defaults 0 for stability
    ap.add_argument("--consolidate-header", type=int, choices=[0,1], default=0,
                    help="GROBID consolidateHeader flag (0/1)")
    ap.add_argument("--consolidate-citations", type=int, choices=[0,1], default=0,
                    help="GROBID consolidateCitations flag (0/1)")
    ap.add_argument("--tei-coordinates", type=int, choices=[0,1], default=0,
                    help="GROBID teiCoordinates flag (0/1)")
    args = ap.parse_args()

    # Apply CLI overrides for Grobid flags (defaults 0)
    cfg.setdefault("grobid", {})
    cfg["grobid"]["consolidate_header"] = int(getattr(args, "consolidate_header", 0))
    cfg["grobid"]["consolidate_citations"] = int(getattr(args, "consolidate_citations", 0))
    cfg["grobid"]["tei_coordinates"] = int(getattr(args, "tei_coordinates", 0))

    # Stats only mode
    if args.check:
        return check_environment(cfg)

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
        test_pdf, _src = _download_pdf_with_ultimate_fallbacks(doi, doi, meta, store)
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
        "✅ Crossref direct links",
        "✅ Citation-based DOI discovery"
    ])

    print("Available PDF acquisition methods:")
    for cap in capabilities:
        print(f"  {cap}")
    
    working_methods = len([c for c in capabilities if c.startswith("✅")])
    print(f"\n🎯 {working_methods} out of 8 methods available (including DOI discovery)")

    # Track failures for this run
    failures: List[Dict[str, Any]] = []

    # 1) Curated first (local PDFs)
    curated = read_curated_seeds(store)
    print(f"\n📚 Processing {len(curated)} curated papers...")
    
    curated_success = 0
    for row in tqdm(curated, desc="Curated PDFs"):
        doi = normalize_doi(row["doi"]) if row.get("doi") else ""
        seed = {
            "doi": doi,
            "title": "",
            "pillar": row.get("pillar", ""),
            "fallback_search": False
        }
        try:
            # Skip if already processed and not forcing
            paper_key = doi if doi else ("no-doi::" + re.sub(r'[^\w\s]', '', seed["title"])[:50])
            if (not args.force) and already_processed(store, paper_key, min_stage=args.min_stage):
                continue

            result = process_one_enhanced(cfg, store, seed, force=args.force,
                                          local_pdf=row.get("pdf_path"))
            if result["status"] == "extracted_ok":
                curated_success += 1
            else:
                failures.append({
                    "doi": result.get("doi", doi),
                    "title": result.get("title", ""),
                    "status": result.get("status", "unknown"),
                    "note": "curated",
                })
        except Exception as e:
            print(f"[curated error] {row.get('pdf_path','?')}: {e}")
            failures.append({
                "doi": doi,
                "title": "",
                "status": "error",
                "note": str(e),
            })

    print(f"✅ Curated papers: {curated_success}/{len(curated)} successfully processed")

    # 2) Auto papers (enhanced with citation search)
    auto = read_auto_seeds_enhanced(store)
    
    already_done = set()
    if not args.force:
        idx_path = store.index_csv()
        if idx_path.exists():
            df_idx = pd.read_csv(idx_path)
            if args.min_stage == "extracted":
                already_done = set(df_idx.loc[df_idx["extracted"].eq("yes"), "doi"].str.lower())
            else:
                already_done = set(df_idx.loc[df_idx["tei"].eq("yes"), "doi"].str.lower())

    to_process = [seed for seed in auto 
                  if (seed["doi"] and seed["doi"] not in already_done) or 
                     (not seed["doi"]) or args.force]
    
    print(f"\n🤖 Processing {len(to_process)} auto-classified papers...")
    
    auto_success = 0
    pdf_acquired = 0
    doi_discovered = 0
    
    # Concurrent processing of auto seeds
    with ThreadPoolExecutor(max_workers=max(1, int(args.workers))) as ex:
        futures = {}
        for seed in to_process:
            if seed.get("fallback_search"):
                doi_discovered += 1
            futures[ex.submit(process_one_enhanced, cfg, store, seed, args.force)] = seed

        for _ in tqdm(as_completed(futures), total=len(futures), desc="Auto (Enhanced) DOIs"):
            future = _
            seed = futures[future]
            try:
                result = future.result()
                if result["status"] == "extracted_ok":
                    auto_success += 1
                    pdf_acquired += 1
                elif result.get("tei") == "yes":
                    pdf_acquired += 1
                else:
                    failures.append({
                        "doi": result.get("doi", seed.get("doi", "")),
                        "title": result.get("title", seed.get("title", "")),
                        "status": result.get("status", "unknown"),
                        "note": "auto",
                    })
            except Exception as e:
                paper_id = seed.get("doi") or seed.get("title", "unknown")[:30]
                print(f"[auto error] {paper_id}: {e}")
                failures.append({
                    "doi": seed.get("doi", ""),
                    "title": seed.get("title", ""),
                    "status": "error",
                    "note": str(e),
                })

    print(f"✅ Auto papers: {auto_success}/{len(to_process)} fully processed")
    print(f"📄 PDFs acquired: {pdf_acquired}/{len(to_process)} papers")
    print(f"🔍 DOIs discovered: {doi_discovered} papers found via citation search")

    # Write failed.csv for this run
    try:
        if failures:
            import csv as _csv
            failed_path = store.idx / "failed.csv"
            with failed_path.open("w", newline="", encoding="utf-8") as f:
                writer = _csv.DictWriter(f, fieldnames=["doi", "title", "status", "note", "tmp_pdf"])
                writer.writeheader()
                for r in failures:
                    paper_key = r.get("doi", "")
                    slug_name = doi_to_slug(paper_key) if paper_key else ""
                    tmp_path = str((store.tmp / f"{slug_name}.pdf").resolve()) if slug_name else ""
                    writer.writerow({
                        "doi": r.get("doi", ""),
                        "title": r.get("title", ""),
                        "status": r.get("status", ""),
                        "note": r.get("note", ""),
                        "tmp_pdf": tmp_path if Path(tmp_path).exists() else "",
                    })
            print(f"Saved failure report: {failed_path}")
    except Exception as e:
        print(f"Failed to write failed.csv: {e}")

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
            print("  • Install missing dependencies: python enhanced_pipeline.py --install-deps")
            print("  • Check that GROBID service is running")
            print("  • Verify Ollama is available for extraction")
            print("  • Some papers may genuinely not have accessible PDFs")

    return 0

if __name__ == "__main__":
    exit(main())