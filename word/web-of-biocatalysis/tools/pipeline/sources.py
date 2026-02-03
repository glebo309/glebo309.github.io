import time, requests
from typing import Tuple, Dict, Any
from typing import Optional
from bs4 import BeautifulSoup
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry

UA_DEFAULT = "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124 Safari/537.36"

_SESSION: Optional[requests.Session] = None

def _get_session() -> requests.Session:
    global _SESSION
    if _SESSION is not None:
        return _SESSION
    s = requests.Session()
    s.headers.update({"User-Agent": UA_DEFAULT})
    retry = Retry(
        total=3,
        backoff_factor=1.0,
        status_forcelist=[429, 500, 502, 503, 504],
        allowed_methods=["GET", "HEAD"],
        raise_on_status=False,
    )
    adapter = HTTPAdapter(max_retries=retry)
    s.mount("http://", adapter)
    s.mount("https://", adapter)
    _SESSION = s
    return s

def fetch_crossref(doi: str, timeout=12) -> Dict[str, Any]:
    try:
        s = _get_session()
        r = s.get(f"https://api.crossref.org/works/{requests.utils.quote(doi)}", timeout=timeout)
        if r.ok:
            return r.json().get("message", {})
    except Exception:
        pass
    return {}

def fetch_semanticscholar(doi: str, timeout=12) -> Dict[str, Any]:
    try:
        url = f"https://api.semanticscholar.org/graph/v1/paper/DOI:{requests.utils.quote(doi)}"
        params = {"fields": "title,year,abstract,authors,name,journal,externalIds,publicationVenue,corpusId"}
        s = _get_session()
        r = s.get(url, params=params, timeout=timeout)
        if r.ok:
            return r.json()
    except Exception:
        pass
    return {}

def fetch_unpaywall(doi: str, email: str, timeout=12) -> Dict[str, Any]:
    try:
        s = _get_session()
        r = s.get(
            f"https://api.unpaywall.org/v2/{requests.utils.quote(doi)}",
            params={"email": email},
            timeout=timeout
        )
        if r.ok:
            return r.json()
    except Exception:
        pass
    return {}

def best_pdf_url_from_unpaywall(oa: Dict[str, Any]) -> Tuple[str, str]:
    """Return (pdf_url, license) or ("","")"""
    if not oa: return ("","")
    loc = oa.get("best_oa_location") or {}
    url = loc.get("url_for_pdf") or ""
    lic = loc.get("license") or ""
    return (url, lic)




def crossref_pdf_link(doi: str, timeout=12) -> str:
    """
    Ask Crossref for publisher-provided links and return a PDF URL if present.
    """
    try:
        s = _get_session()
        r = s.get(f"https://api.crossref.org/works/{requests.utils.quote(doi)}", timeout=timeout)
        if r.ok:
            msg = r.json().get("message", {})
            for link in msg.get("link", []) or []:
                if (link.get("content-type") or "").lower() == "application/pdf":
                    return link.get("URL") or ""
    except Exception:
        pass
    return ""

def find_pdf_on_landing(session: requests.Session, url: str, timeout=20) -> str:
    """
    Fetch landing page HTML and try to locate the PDF via common patterns:
    - <meta name="citation_pdf_url" content="...">
    - <link rel="alternate" type="application/pdf" href="...">
    - Obvious 'PDF' anchors
    """
    try:
        # Use provided session if available; otherwise use shared session
        s = session or _get_session()
        resp = s.get(url, timeout=timeout, allow_redirects=True)
        if not resp.ok:
            return ""
        html = resp.text
        soup = BeautifulSoup(html, "html.parser")

        # 1) citation_pdf_url
        m = soup.find("meta", attrs={"name": "citation_pdf_url"})
        if m and m.get("content"):
            return m["content"].strip()

        # 2) link rel="alternate" type="application/pdf"
        for link in soup.find_all("link"):
            if (link.get("rel") and "alternate" in [x.lower() for x in link.get("rel")]) and \
               (link.get("type","").lower() == "application/pdf") and link.get("href"):
                return link["href"].strip()

        # 3) obvious anchors
        for a in soup.find_all("a", href=True):
            href = a["href"]
            label = (a.get_text() or "").lower()
            if "pdf" in href.lower() or "pdf" in label:
                return requests.compat.urljoin(resp.url, href)
    except Exception:
        pass
    return ""
