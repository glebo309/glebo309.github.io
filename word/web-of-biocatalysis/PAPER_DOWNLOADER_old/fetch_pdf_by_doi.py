#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Standalone DOI-to-PDF fetcher using multiple methods.

This tool provides an interactive terminal dialog that asks for a DOI as input
and then attempts to find and download the PDF using a multi-method PDF
acquisition pipeline from pipeline_get-pdf_extract-to-xml.py.

Usage:
    python tools/fetch_pdf_by_doi.py
    
    Or with direct DOI:
    python tools/fetch_pdf_by_doi.py --doi "10.1038/nature12373"
"""

import argparse
import json
import os
import sys
import tempfile
import time
from pathlib import Path
from typing import Optional, Dict, Any

# Add the parent directory to Python path to import local modules
sys.path.insert(0, str(Path(__file__).parent.parent))

try:
    from tools.pipeline.config import load_config
    from tools.pipeline.storage import Store
    from tools.pipeline.sources import (
        fetch_crossref,
        fetch_semanticscholar,
        fetch_unpaywall,
        best_pdf_url_from_unpaywall,
    )
    from tools.pipeline.grobid_client import grobid_process_pdf
except ImportError as e:
    print(f"Error importing pipeline modules: {e}")
    print("Make sure you're running this from the project root directory")
    sys.exit(1)

# Import international sources module
try:
    from international_sources import try_fetch_from_international_sources
except ImportError:
    # If not available, create a dummy function
    def try_fetch_from_international_sources(*args, **kwargs):
        return None

# Import publisher patterns module
try:
    from publisher_patterns import try_fetch_from_publisher_patterns
except ImportError:
    # If not available, create a dummy function
    def try_fetch_from_publisher_patterns(*args, **kwargs):
        return None

# Import Google Scholar module
try:
    from google_scholar import try_fetch_from_google_scholar
except ImportError:
    # If not available, create a dummy function
    def try_fetch_from_google_scholar(*args, **kwargs):
        return None

# Import multi-language search module
try:
    from multilang_search import try_fetch_with_multilang
except ImportError:
    def try_fetch_with_multilang(*args, **kwargs):
        return None

# Import deep crawler module
try:
    from deep_crawler import try_fetch_deep_crawl
except ImportError:
    def try_fetch_deep_crawl(*args, **kwargs):
        return None

# Import Chinese crawler module
try:
    from chinese_crawler import try_fetch_chinese_sources
except ImportError:
    def try_fetch_chinese_sources(*args, **kwargs):
        return None

# Import the PDF fetching methods from the pipeline
try:
    import requests
    from urllib.parse import urljoin
    from bs4 import BeautifulSoup
except ImportError as e:
    print(f"Missing required dependencies: {e}")
    print("Please install: pip install requests beautifulsoup4")
    sys.exit(1)

# -------- Configuration --------
ROOT = Path(__file__).resolve().parents[1]
# Default to user's Desktop for easy access
DEFAULT_OUTPUT_DIR = Path.home() / "Desktop"
UA_DEFAULT = "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124 Safari/537.36"

# -------- Helper Functions --------

def clean_input(s: str) -> str:
    """Clean user input: remove quotes, extra whitespace, trailing punctuation"""
    s = (s or "").strip()
    # Remove leading/trailing quotes
    s = s.strip('"\'“”‘’')
    # Remove trailing punctuation that's not part of DOI
    s = s.rstrip('.,;:')
    # Collapse multiple spaces/newlines
    import re
    s = re.sub(r'\s+', ' ', s)
    return s.strip()

def extract_doi_from_text(s: str) -> Optional[str]:
    """Try to extract a DOI from arbitrary text using regex.
    
    Returns the first DOI found, or None.
    """
    import re
    # Pattern: 10.xxxx/yyyy (very permissive)
    pattern = r'10\.\S+/\S+'
    match = re.search(pattern, s)
    if match:
        doi = match.group(0)
        # Clean up trailing punctuation that might have been captured
        doi = doi.rstrip('.,;:)]}"\'')
        return doi
    return None

def normalize_doi(s: str) -> str:
    """Normalize DOI format"""
    s = (s or "").strip()
    s = s.replace("https://doi.org/", "").replace("http://doi.org/", "")
    s = s.replace("doi:", "").replace("DOI:", "")
    return s.strip()

def looks_like_doi(s: str) -> bool:
    """Heuristic check whether a string looks like a DOI"""
    if not s:
        return False
    s = s.strip()
    # Common patterns indicating a DOI
    if "doi.org" in s.lower():
        return True
    if s.lower().startswith("doi:"):
        return True
    # Try to extract DOI from text
    extracted = extract_doi_from_text(s)
    if extracted:
        return True
    # Bare DOI pattern (very rough): starts with 10. and has a slash
    s_norm = normalize_doi(s)
    return s_norm.startswith("10.") and "/" in s_norm

def resolve_query_to_doi(query: str, top_n: int = 5) -> list:
    """Resolve an arbitrary query (title/citation) to candidate DOIs using Crossref.

    Returns a list of dicts with keys: doi, title, year, journal, score.
    Empty list if no results or error.
    """
    query = (query or "").strip()
    if not query:
        return []

    import requests

    try:
        # Use Crossref's bibliographic search
        url = "https://api.crossref.org/works"
        params = {
            "query.bibliographic": query,
            "rows": top_n,
        }
        headers = {"User-Agent": UA_DEFAULT}
        r = requests.get(url, params=params, headers=headers, timeout=20)
        r.raise_for_status()
        data = r.json()
        items = (data.get("message") or {}).get("items") or []
        if not items:
            return []

        results = []
        for item in items:
            doi = item.get("DOI") or item.get("doi")
            if not doi:
                continue
            title = " ".join(item.get("title") or []) or "(no title)"
            year = None
            try:
                y = (item.get("issued") or {}).get("date-parts", [[None]])[0][0]
                year = int(y) if y else None
            except Exception:
                pass
            journal_list = item.get("short-container-title") or item.get("container-title") or []
            journal = journal_list[0] if journal_list else "(no journal)"
            score = item.get("score", 0)
            results.append({
                "doi": str(doi).strip(),
                "title": title,
                "year": year,
                "journal": journal,
                "score": score,
            })
        return results
    except Exception:
        return []

def _session_with_headers() -> requests.Session:
    """Create a session with proper headers"""
    s = requests.Session()
    s.headers.update({"User-Agent": UA_DEFAULT})
    return s

def _validate_pdf_file(path: Path) -> None:
    """Validate that a file is actually a PDF with stricter checks"""
    if not path.exists():
        raise RuntimeError("File does not exist")
    
    # Stricter size check: PDFs are rarely smaller than 50KB
    if path.stat().st_size < 50 * 1024:
        raise RuntimeError("File too small to be a valid PDF (< 50KB)")
    
    # Check PDF magic bytes and first 1KB for HTML content
    with path.open('rb') as f:
        header = f.read(1024)
        if not header.startswith(b'%PDF-'):
            raise RuntimeError("File does not start with PDF magic bytes")
        
        # Check if it's actually an HTML error page
        header_lower = header.lower()
        if b'<html' in header_lower or b'<!doctype' in header_lower or b'<body' in header_lower:
            raise RuntimeError("File is HTML, not PDF")
        
        # Check for common error page indicators
        if b'404' in header or b'error' in header_lower or b'access denied' in header_lower:
            raise RuntimeError("File appears to be an error page")

def merge_meta(cr: Dict[str, Any], s2: Dict[str, Any], oa: Dict[str, Any]) -> Dict[str, Any]:
    """Merge metadata from different sources"""
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
    authors = []
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

# -------- PDF Fetching Methods --------

def _try_fetch_oa_pdf(session: requests.Session, url: str, outpath: Path, retry: bool = True) -> None:
    """Fetch PDF from open access URL with retry on network errors"""
    try:
        with session.get(url, stream=True, timeout=90, allow_redirects=True) as r:
            r.raise_for_status()
            
            # Check content type
            content_type = r.headers.get('content-type', '').lower()
            if 'html' in content_type:
                raise RuntimeError("URL returned HTML instead of PDF")
            
            with outpath.open("wb") as f:
                for chunk in r.iter_content(chunk_size=1 << 20):
                    if chunk:
                        f.write(chunk)
            
            # Validate that it's actually a PDF
            _validate_pdf_file(outpath)
    except (requests.exceptions.Timeout, requests.exceptions.ConnectionError) as e:
        if retry:
            import time
            time.sleep(2)
            return _try_fetch_oa_pdf(session, url, outpath, retry=False)
        else:
            raise

def _try_fetch_semantic_scholar_pdf(doi: str, outpath: Path, retry: bool = True) -> None:
    """Fetch PDF from Semantic Scholar with retry on network errors"""
    try:
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
                
                # Check content type
                content_type = r.headers.get('content-type', '').lower()
                if 'html' in content_type:
                    raise RuntimeError("URL returned HTML instead of PDF")
                
                with outpath.open("wb") as f:
                    for chunk in r.iter_content(chunk_size=1024*1024):
                        if chunk:
                            f.write(chunk)
            
            # Validate that it's actually a PDF
            _validate_pdf_file(outpath)
            return
        
        raise RuntimeError("No PDF found via Semantic Scholar")
    except (requests.exceptions.Timeout, requests.exceptions.ConnectionError) as e:
        if retry:
            import time
            time.sleep(2)
            return _try_fetch_semantic_scholar_pdf(doi, outpath, retry=False)
        else:
            raise

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
    
    # Validate that it's actually a PDF
    _validate_pdf_file(outpath)

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
                    
                    try:
                        _validate_pdf_file(outpath)
                        return  # Valid PDF
                    except RuntimeError:
                        # Not a valid PDF, try next URL
                        continue
        except Exception:
            continue
    
    raise RuntimeError("No accessible PDF found via Crossref")

def _try_fetch_publisher_direct(doi: str, outpath: Path, retry: bool = True) -> None:
    """Try to get PDF directly from publisher website with retry on network errors"""
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
                        
                        try:
                            _validate_pdf_file(outpath)
                            return  # Valid PDF
                        except RuntimeError:
                            # Not a valid PDF, try next URL
                            continue
            except Exception:
                continue
                
    except (requests.exceptions.Timeout, requests.exceptions.ConnectionError) as e:
        if retry:
            import time
            time.sleep(2)
            return _try_fetch_publisher_direct(doi, outpath, retry=False)
        else:
            raise
    except Exception:
        pass
    
    raise RuntimeError("No PDF found via publisher direct access")

# Global flag to skip SciHub if it's unreachable
_SCIHUB_REACHABLE = None

def _check_scihub_reachable() -> bool:
    """Quick check if any SciHub domain is reachable."""
    global _SCIHUB_REACHABLE
    if _SCIHUB_REACHABLE is not None:
        return _SCIHUB_REACHABLE
    
    import requests
    test_domains = ["https://sci-hub.se", "https://sci-hub.st"]
    for domain in test_domains:
        try:
            r = requests.head(domain, timeout=3)
            if r.status_code < 500:
                _SCIHUB_REACHABLE = True
                return True
        except Exception:
            continue
    _SCIHUB_REACHABLE = False
    return False

def _try_fetch_scihub(doi: str, outpath: Path) -> None:
    """Working SciHub method using manual access"""
    
    # Working SciHub domains (updated list)
    scihub_domains = [
        "https://sci-hub.se",
        "https://sci-hub.ren", 
        "https://sci-hub.st",
        "https://sci-hub.ru",
        "https://sci-hub.wf",
        "https://sci-hub.shop",
        "https://sci-hub.hkvisa.net"
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
            content_type = response.headers.get('content-type', '').lower()
            if 'pdf' in content_type:
                with outpath.open("wb") as f:
                    f.write(response.content)
                _validate_pdf_file(outpath)
                return
            
            # Parse HTML to find PDF link
            soup = BeautifulSoup(response.content, 'html.parser')
            
            # Look for PDF download links
            pdf_links = []
            
            # Method 1: iframe with PDF
            for iframe in soup.find_all('iframe'):
                src = iframe.get('src', '')
                if src and ('pdf' in src.lower() or src.startswith('//')):
                    if src.startswith('//'):
                        src = 'https:' + src
                    elif src.startswith('/'):
                        src = domain + src
                    pdf_links.append(src)
            
            # Method 2: direct links to PDFs
            for link in soup.find_all('a', href=True):
                href = link['href']
                if 'pdf' in href.lower() or href.endswith('.pdf'):
                    if href.startswith('//'):
                        href = 'https:' + href
                    elif href.startswith('/'):
                        href = domain + href
                    pdf_links.append(href)
            
            # Method 3: button with onclick containing PDF URL
            for button in soup.find_all(['button', 'div'], onclick=True):
                onclick = button.get('onclick', '')
                if 'pdf' in onclick.lower():
                    # Extract URL from onclick
                    import re
                    url_match = re.search(r'https?://[^\s\'"]+\.pdf', onclick)
                    if url_match:
                        pdf_links.append(url_match.group(0))
            
            # Try each PDF link
            for pdf_url in pdf_links:
                try:
                    pdf_response = session.get(pdf_url, timeout=60, allow_redirects=True)
                    pdf_response.raise_for_status()
                    
                    if 'pdf' in pdf_response.headers.get('content-type', '').lower():
                        with outpath.open("wb") as f:
                            f.write(pdf_response.content)
                        _validate_pdf_file(outpath)
                        return
                except Exception:
                    continue
                    
        except Exception:
            continue  # Try next domain
    
    raise RuntimeError("SciHub download failed from all working domains")

def _check_pypaperbot_available() -> bool:
    """Enhanced PyPaperBot availability check with auto-install on first use"""
    try:
        # First check import
        import PyPaperBot  # type: ignore[import]
    except Exception:
        # Auto-install PyPaperBot into the current interpreter if missing
        try:
            import subprocess
            print("🔧 PyPaperBot not found, updating pip and installing it now...")
            # Update pip first, in case an old version is causing issues
            subprocess.run(
                [sys.executable, "-m", "pip", "install", "--upgrade", "pip"],
                check=False,
            )
            # Then install PyPaperBot
            subprocess.run(
                [sys.executable, "-m", "pip", "install", "PyPaperBot"],
                check=True,
            )
            # Try import again after installation
            import PyPaperBot  # type: ignore[import]
        except Exception:
            return False

    # Then check command works
    try:
        import subprocess
        result = subprocess.run(
            [sys.executable, "-m", "PyPaperBot", "--help"],
            capture_output=True,
            text=True,
            timeout=10,
        )
        return result.returncode == 0
    except Exception:
        return False

def _try_fetch_pypaperbot(doi: str, outpath: Path) -> None:
    """Enhanced PyPaperBot with better error handling"""
    import subprocess
    import tempfile
    import shutil
    
    # Create a temporary download directory for PyPaperBot
    with tempfile.TemporaryDirectory() as temp_dir:
        temp_path = Path(temp_dir)
        pypb_download_dir = temp_path / f"pypb_{doi.replace('/', '_').replace('.', '_')}"
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
            _validate_pdf_file(downloaded_pdf)
            
            # Move to target location
            shutil.copy2(str(downloaded_pdf), str(outpath))
            
        except Exception as e:
            raise RuntimeError(f"PyPaperBot error: {e}")

# Global flag to skip LibGen if it's unreachable
_LIBGEN_REACHABLE = None

def _check_libgen_reachable() -> bool:
    """Quick check if any LibGen mirror is reachable."""
    global _LIBGEN_REACHABLE
    if _LIBGEN_REACHABLE is not None:
        return _LIBGEN_REACHABLE
    
    import requests
    test_mirrors = ["https://libgen.is", "https://libgen.rs"]
    for mirror in test_mirrors:
        try:
            r = requests.head(mirror, timeout=3)
            if r.status_code < 500:
                _LIBGEN_REACHABLE = True
                return True
        except Exception:
            continue
    _LIBGEN_REACHABLE = False
    return False

def _try_fetch_libgen(doi: str, outpath: Path) -> None:
    """Try to fetch from Library Genesis"""
    
    libgen_mirrors = [
        "https://libgen.is",
        "https://libgen.rs", 
        "https://libgen.st"
    ]
    
    headers = {
        'User-Agent': 'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36'
    }
    
    for mirror in libgen_mirrors:
        try:
            # Search for the DOI
            search_url = f"{mirror}/scimag/"
            params = {"q": doi}
            
            session = requests.Session()
            session.headers.update(headers)
            
            response = session.get(search_url, params=params, timeout=30)
            response.raise_for_status()
            
            soup = BeautifulSoup(response.content, 'html.parser')
            
            # Look for download links in the search results
            for link in soup.find_all('a', href=True):
                href = link['href']
                if 'download' in href.lower() or 'get.php' in href:
                    if href.startswith('/'):
                        href = mirror + href
                    
                    try:
                        pdf_response = session.get(href, timeout=60, allow_redirects=True)
                        pdf_response.raise_for_status()
                        
                        content_type = pdf_response.headers.get('content-type', '').lower()
                        if 'pdf' in content_type:
                            with outpath.open("wb") as f:
                                f.write(pdf_response.content)
                            _validate_pdf_file(outpath)
                            return
                    except Exception:
                        continue
                        
        except Exception:
            continue
    
    raise RuntimeError("LibGen download failed from all mirrors")

def _try_fetch_pmc(doi: str, outpath: Path) -> None:
    """Try to fetch PDF from PubMed Central (PMC)"""
    try:
        # PMC OA API endpoint
        url = f"https://www.ncbi.nlm.nih.gov/pmc/utils/oa/oa.fcgi?id={doi}"
        headers = {"User-Agent": UA_DEFAULT}
        
        response = requests.get(url, headers=headers, timeout=30)
        response.raise_for_status()
        
        # Parse XML response
        from xml.etree import ElementTree as ET
        root = ET.fromstring(response.content)
        
        # Check for OA record
        if root.find('.//error') is not None:
            raise RuntimeError(f"PMC error: {root.find('.//error').text}")
            
        pdf_url = None
        for record in root.findall('.//record'):
            for link in record.findall('.//link[@format="pdf"]'):
                if link.get('href'):
                    pdf_url = link.get('href')
                    break
            if pdf_url:
                break
                
        if not pdf_url:
            raise RuntimeError("No PDF found in PMC")
            
        # Download PDF
        session = _session_with_headers()
        with session.get(pdf_url, stream=True, timeout=60) as r:
            r.raise_for_status()
            with outpath.open("wb") as f:
                for chunk in r.iter_content(chunk_size=1 << 20):
                    if chunk:
                        f.write(chunk)
                        
        _validate_pdf_file(outpath)
        return
    except Exception as e:
        raise RuntimeError(f"PMC download failed: {e}")

def _titles_match(a: str, b: str) -> bool:
    """Check if two titles match (from the original pipeline)"""
    a, b = (a or "").strip().lower(), (b or "").strip().lower()
    if not a or not b:
        return False
    if a == b:
        return True
    # Prefix match
    if a.startswith(b[:25]) or b.startswith(a[:25]):
        return True
    # Token-based Jaccard similarity
    def toks(s: str) -> set:
        import re
        return set(re.sub(r"[^\w\s]", "", s).split())
    ta, tb = toks(a), toks(b)
    if not ta or not tb:
        return False
    inter = len(ta & tb)
    uni = len(ta | tb)
    sim = (inter / uni) if uni else 0.0
    return sim >= 0.6

def download_pdf_with_fallbacks(doi: str, output_path: Path) -> bool:
    """
    PDF download using a multi-method system from pipeline_get-pdf_extract-to-xml.py:
    1. SciHub - shadow library fallback with multiple domains (fast, often successful)
    2. Open Access (Unpaywall) - free, legal, fast + all oa_locations fallback
    3. Semantic Scholar - academic repository + title-based fallback
    4. PubMed Central (PMC) - free, legal, fast
    5. Publisher Direct - often fastest when available
    6. International Sources - China, Russia, Iran, Korea, Spain, France, Brazil
    7. Publisher URL Patterns - supplemental directories, predictable URLs
    8. Google Scholar - university repositories, ResearchGate, Academia.edu
    9. Multi-language Search - translate title to Chinese, Russian, Korean
    10. Chinese Sources - CNKI, Wanfang, VIP, Chinese universities
    11. Deep Crawl - author homepages, institutional repositories
    12. PyPaperBot - multi-source aggregator
    13. Library Genesis (LibGen) - independent repository fallback
    14. arXiv - preprint server (specialized)
    15. Crossref - last-resort backup
    """
    session = _session_with_headers()
    tmp_pdf = Path(tempfile.mkstemp(suffix=".pdf")[1])
    tried = []
    
    print(f"Searching for PDF: {doi}")
    
    # First, gather metadata
    print("Gathering metadata...")
    cr = fetch_crossref(doi)
    s2 = fetch_semanticscholar(doi)
    oa = fetch_unpaywall(doi, "research@example.com")  # Use a placeholder email
    meta = merge_meta(cr, s2, oa)
    
    if meta.get("title"):
        print(f"Found paper: {meta['title']}")
        if meta.get("year"):
            print(f"Year: {meta['year']}")
        if meta.get("journal"):
            print(f"Journal: {meta['journal']}")
    
    # Add small delay to be respectful to APIs
    time.sleep(0.5)

    # 1) SciHub - try first as it is often most successful
    if doi:
        if not _check_scihub_reachable():
            print("SciHub not reachable; skipping.")
            tried.append("scihub:unreachable")
        else:
            try:
                print("Trying SciHub...")
                _try_fetch_scihub(doi, tmp_pdf)
                print("SciHub PDF downloaded successfully.")
                tmp_pdf.rename(output_path)
                return True
            except Exception as e:
                tried.append(f"scihub:{type(e).__name__}")
                print(f"SciHub failed: {e}")

    # 2-4) Parallel fallback group: Open Access, Semantic Scholar, PubMed Central (PMC)
    # Try these in parallel with 20s timeout each; first success wins
    if doi:
        print("Trying legal sources in parallel (Unpaywall, Semantic Scholar, PMC)...")
        
        import concurrent.futures
        
        def try_unpaywall():
            tmp = Path(tempfile.mkstemp(suffix=".pdf")[1])
            try:
                oa_url = meta.get("oa_pdf_url") or ""
                if not oa_url:
                    oa_data = meta.get("unpaywall") or {}
                    oa_url, _lic = best_pdf_url_from_unpaywall(oa_data or {})
                if oa_url:
                    _try_fetch_oa_pdf(session, oa_url, tmp)
                    return ("unpaywall", tmp)
                else:
                    # Try all oa_locations
                    oa_data = meta.get("unpaywall") or {}
                    for loc in (oa_data.get("oa_locations") or []):
                        cand = loc.get("url_for_pdf") or loc.get("url") or ""
                        if not cand:
                            continue
                        try:
                            _try_fetch_oa_pdf(session, cand, tmp)
                            return ("unpaywall", tmp)
                        except Exception:
                            continue
                raise RuntimeError("No OA URL available")
            except Exception as e:
                try:
                    tmp.unlink()
                except Exception:
                    pass
                raise e
        
        def try_semantic_scholar():
            tmp = Path(tempfile.mkstemp(suffix=".pdf")[1])
            try:
                _try_fetch_semantic_scholar_pdf(doi, tmp)
                return ("semanticscholar", tmp)
            except Exception as e:
                try:
                    tmp.unlink()
                except Exception:
                    pass
                raise e
        
        def try_pmc():
            tmp = Path(tempfile.mkstemp(suffix=".pdf")[1])
            try:
                _try_fetch_pmc(doi, tmp)
                return ("pmc", tmp)
            except Exception as e:
                try:
                    tmp.unlink()
                except Exception:
                    pass
                raise e
        
        with concurrent.futures.ThreadPoolExecutor(max_workers=3) as executor:
            futures = {
                executor.submit(try_unpaywall): "unpaywall",
                executor.submit(try_semantic_scholar): "semanticscholar",
                executor.submit(try_pmc): "pmc",
            }
            
            for future in concurrent.futures.as_completed(futures, timeout=20):
                method_name = futures[future]
                try:
                    method, temp_file = future.result()
                    print(f"{method.capitalize()} PDF downloaded successfully (parallel).")
                    temp_file.rename(output_path)
                    # Cancel remaining futures
                    for f in futures:
                        f.cancel()
                    return True
                except Exception as e:
                    tried.append(f"{method_name}:{type(e).__name__}")
                    print(f"{method_name.capitalize()} failed: {e}")
        
        print("All parallel legal sources failed.")

    # Title-based S2 OA PDF fallback (if parallel group failed)
    if doi:
        try:
            title = (meta.get("title") or "").strip()
            year = meta.get("year")
            if title:
                print("Trying Semantic Scholar title-based fallback...")
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
                        if tmp_pdf.stat().st_size > 50 * 1024:
                            _validate_pdf_file(tmp_pdf)
                            print("Semantic Scholar title-based Open Access PDF fetched.")
                            tmp_pdf.rename(output_path)
                            return True
        except Exception as e:
            print(f"S2 title-based fallback failed: {e}")

    # 5) International Sources (China, Russia, Iran, Korea, Spain, France, Brazil)
    title = (meta.get("title") or "").strip()
    if title:
        try:
            print("Trying international academic sources...")
            source = try_fetch_from_international_sources(title, doi, tmp_pdf)
            if source:
                print(f"International source ({source}) PDF downloaded successfully.")
                tmp_pdf.rename(output_path)
                return True
        except Exception as e:
            tried.append(f"international:{type(e).__name__}")
            print(f"International sources failed: {e}")

    # 6) Publisher URL Pattern Guessing (supplemental directories, etc.)
    article_url = meta.get("URL") or cr.get("URL")
    publisher = meta.get("publisher") or cr.get("publisher")
    
    # Skip if URL is just a DOI resolver
    if article_url and not article_url.startswith("https://doi.org/"):
        try:
            print("Trying publisher URL pattern guessing...")
            source = try_fetch_from_publisher_patterns(doi, article_url, tmp_pdf, publisher)
            if source:
                print(f"Publisher pattern PDF downloaded successfully.")
                tmp_pdf.rename(output_path)
                return True
        except Exception as e:
            tried.append(f"publisher_patterns:{type(e).__name__}")
            print(f"Publisher pattern guessing failed: {e}")

    # 7) Google Scholar + University Repositories
    if title:
        try:
            print("Trying Google Scholar and university repositories...")
            # Extract author from metadata
            authors = meta.get("author") or cr.get("author", [])
            author_name = None
            if authors and len(authors) > 0:
                first_author = authors[0]
                if isinstance(first_author, dict):
                    author_name = first_author.get("family", "")
                elif isinstance(first_author, str):
                    author_name = first_author
            
            source = try_fetch_from_google_scholar(title, doi, tmp_pdf, author_name, year)
            if source:
                print(f"Google Scholar PDF downloaded successfully.")
                tmp_pdf.rename(output_path)
                return True
        except Exception as e:
            tried.append(f"google_scholar:{type(e).__name__}")
            print(f"Google Scholar failed: {e}")

    # 8) Multi-language search (Chinese, Russian, Korean)
    if title:
        try:
            print("Trying multi-language search...")
            source = try_fetch_with_multilang(title, doi, tmp_pdf, languages=['zh-CN', 'ru', 'ko'])
            if source:
                print(f"Multi-language search PDF downloaded successfully.")
                tmp_pdf.rename(output_path)
                return True
        except Exception as e:
            tried.append(f"multilang:{type(e).__name__}")
            print(f"Multi-language search failed: {e}")

    # 9) Chinese academic sources (CNKI, Wanfang, VIP, Chinese universities)
    if title:
        try:
            print("Trying Chinese academic sources...")
            # Get translated title if available from previous step
            authors = meta.get("author") or cr.get("author", [])
            author_name = None
            if authors and len(authors) > 0:
                first_author = authors[0]
                if isinstance(first_author, dict):
                    author_name = f"{first_author.get('given', '')} {first_author.get('family', '')}".strip()
                elif isinstance(first_author, str):
                    author_name = first_author
            
            source = try_fetch_chinese_sources(title, doi, tmp_pdf, author_name)
            if source:
                print(f"Chinese sources PDF downloaded successfully.")
                tmp_pdf.rename(output_path)
                return True
        except Exception as e:
            tried.append(f"chinese:{type(e).__name__}")
            print(f"Chinese sources failed: {e}")

    # 10) Deep crawl (author pages, institutional repos)
    if title:
        try:
            print("Trying deep crawl of author pages...")
            # Pass full metadata for author extraction
            full_meta = {**cr, **meta} if cr and meta else (cr or meta or {})
            source = try_fetch_deep_crawl(title, doi, tmp_pdf, full_meta)
            if source:
                print(f"Deep crawl PDF downloaded successfully.")
                tmp_pdf.rename(output_path)
                return True
        except Exception as e:
            tried.append(f"deep_crawl:{type(e).__name__}")
            print(f"Deep crawl failed: {e}")

    # 11) PyPaperBot - multi-source aggregator
    if doi and _check_pypaperbot_available():
        try:
            print("Trying PyPaperBot (multi-source aggregator)...")
            _try_fetch_pypaperbot(doi, tmp_pdf)
            print("PyPaperBot PDF downloaded successfully.")
            tmp_pdf.rename(output_path)
            return True
        except Exception as e:
            tried.append(f"pypaperbot:{type(e).__name__}")
            print(f"PyPaperBot failed: {e}")
    elif doi:
        print("PyPaperBot not available (automatic installation failed).")

    # 12) Library Genesis (LibGen) - independent shadow library fallback
    if doi:
        if not _check_libgen_reachable():
            print("LibGen not reachable; skipping.")
            tried.append("libgen:unreachable")
        else:
            try:
                print("Trying Library Genesis (LibGen)...")
                _try_fetch_libgen(doi, tmp_pdf)
                print("LibGen PDF downloaded successfully.")
                tmp_pdf.rename(output_path)
                return True
            except Exception as e:
                tried.append(f"libgen:{type(e).__name__}")
                print(f"LibGen failed: {e}")

    # 13) arXiv - specialized for preprints
    if doi:
        try:
            print("Checking arXiv...")
            _try_fetch_arxiv_pdf(doi, tmp_pdf)
            print("arXiv PDF downloaded successfully.")
            tmp_pdf.rename(output_path)
            return True
        except Exception as e:
            tried.append(f"arxiv:{type(e).__name__}")
            print(f"arXiv failed: {e}")

    # 14) Crossref Direct Links - last-resort backup
    if doi:
        try:
            print("Trying Crossref direct links...")
            _try_fetch_crossref_links(doi, tmp_pdf)
            print("Crossref PDF downloaded successfully.")
            tmp_pdf.rename(output_path)
            return True
        except Exception as e:
            tried.append(f"crossref:{type(e).__name__}")
            print(f"Crossref direct failed: {e}")

    # Clean up temporary file
    try:
        tmp_pdf.unlink()
    except Exception:
        pass
    
    print(f"\nAll methods failed. Tried: {', '.join(tried)}")
    print("\nAdditional suggestions:")
    print("  • Check if the paper is very recent (it may not be indexed yet)")
    print("  • Try searching manually on Google Scholar")
    print("  • Contact your institution's library for access")
    return False

def interactive_doi_input() -> str:
    """Interactive terminal dialog to get DOI input"""
    print("=" * 60)
    print("PDF Fetcher - DOI to PDF Downloader")
    print("=" * 60)
    print()
    print("This tool will attempt to find and download a PDF for any given DOI.")
    print("It uses multiple sources including Open Access repositories, arXiv,")
    print("Semantic Scholar, and publisher websites.")
    print()
    
    while True:
        doi = input("Enter DOI (e.g., 10.1038/nature12373): ").strip()
        
        if not doi:
            print("Please enter a valid DOI.")
            continue
            
        # Basic DOI validation
        if not (doi.startswith("10.") or "doi.org" in doi.lower() or doi.lower().startswith("doi:")):
            print("This does not look like a valid DOI. Continue anyway? (y/n): ", end="")
            if input().lower() not in ['y', 'yes']:
                continue
        
        return normalize_doi(doi)

def main():
    parser = argparse.ArgumentParser(description="Download PDF by DOI or citation using comprehensive fallback methods")
    parser.add_argument("--doi", help="DOI or full citation to fetch (if not provided, will prompt interactively)")
    parser.add_argument("--output-dir", default=str(DEFAULT_OUTPUT_DIR), 
                       help=f"Output directory for downloaded PDFs (default: {DEFAULT_OUTPUT_DIR})")
    parser.add_argument("--filename", help="Custom filename for the PDF (without extension)")
    parser.add_argument("--install-deps", action="store_true", 
                       help="Install PyPaperBot and other optional dependencies")
    
    args = parser.parse_args()
    
    # Handle dependency installation
    if args.install_deps:
        print("🔧 Installing optional dependencies...")
        import subprocess
        deps = ["PyPaperBot", "beautifulsoup4", "requests"]
        for dep in deps:
            try:
                print(f"Installing {dep}...")
                subprocess.run([sys.executable, "-m", "pip", "install", dep], 
                             check=True, capture_output=True)
                print(f"✅ {dep} installed successfully")
            except subprocess.CalledProcessError as e:
                print(f"❌ Failed to install {dep}: {e}")
        print("🎉 Dependency installation complete!")
        return 0
    
    # Get input (DOI or citation)
    if args.doi:
        raw_input = args.doi.strip()
    else:
        raw_input = interactive_doi_input()

    # Clean input
    raw_input = clean_input(raw_input)

    # Try to extract DOI from text first
    extracted_doi = extract_doi_from_text(raw_input)
    if extracted_doi:
        doi = normalize_doi(extracted_doi)
        print(f"Extracted DOI from input: {doi}")
    elif looks_like_doi(raw_input):
        doi = normalize_doi(raw_input)
        print(f"Processing DOI: {doi}")
    else:
        print("Input does not look like a DOI. Trying to resolve it as a citation or title...")
        candidates = resolve_query_to_doi(raw_input, top_n=5)
        if not candidates:
            print("Could not resolve the input to a DOI. Please provide a DOI explicitly.")
            return 1
        
        # Auto-pick if top score is high and much better than second
        if len(candidates) == 1 or (candidates[0]["score"] > 50 and candidates[0]["score"] > candidates[1]["score"] * 1.5):
            doi = normalize_doi(candidates[0]["doi"])
            print(f"Resolved to DOI: {doi}")
            print(f"  Title: {candidates[0]['title']}")
            print(f"  Year: {candidates[0]['year']}")
        else:
            # Multiple candidates: show list and ask user
            print("\nMultiple possible matches found:")
            for i, cand in enumerate(candidates, 1):
                print(f"  {i}. {cand['title']} ({cand['year']}) - {cand['journal']}")
            print("\nEnter the number of the correct paper (or 'c' to cancel): ", end="")
            choice = input().strip().lower()
            if choice == 'c':
                print("Cancelled.")
                return 1
            try:
                idx = int(choice) - 1
                if 0 <= idx < len(candidates):
                    doi = normalize_doi(candidates[idx]["doi"])
                    print(f"Selected DOI: {doi}")
                else:
                    print("Invalid choice.")
                    return 1
            except ValueError:
                print("Invalid input.")
                return 1
    
    # Setup output directory
    output_dir = Path(args.output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)
    
    # Generate filename
    if args.filename:
        filename = f"{args.filename}.pdf"
    else:
        # Create safe filename from DOI
        safe_doi = doi.replace("/", "_").replace(".", "_")
        filename = f"{safe_doi}.pdf"
    
    output_path = output_dir / filename
    
    print(f"Output will be saved to: {output_path}")
    print()
    
    # Attempt to download
    success = download_pdf_with_fallbacks(doi, output_path)
    
    if success:
        print()
        print("Download completed successfully.")
        print(f"PDF saved to: {output_path}")
        print(f"File size: {output_path.stat().st_size / 1024:.1f} KB")
    else:
        print()
        print("Failed to download PDF from any source.")
        print("This could be because:")
        print("  • The paper is behind a paywall")
        print("  • The DOI is invalid or not found")
        print("  • Network connectivity issues")
        print("  • The paper is not available in digital format")
    
    return 0 if success else 1

if __name__ == "__main__":
    sys.exit(main())
