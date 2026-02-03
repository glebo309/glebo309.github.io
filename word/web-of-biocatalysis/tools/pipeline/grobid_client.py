import requests
from pathlib import Path
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry

def grobid_process_pdf(pdf_path: Path, grobid_url: str, params: dict, timeout_sec: int = 120) -> str:
    """
    Returns TEI XML as string. Raises on error.
    """
    endpoint = f"{grobid_url.rstrip('/')}/api/processFulltextDocument"

    # Quick health check
    try:
        alive = requests.get(f"{grobid_url.rstrip('/')}/api/isalive", timeout=5)
        if alive.status_code != 200:
            raise RuntimeError(f"GROBID not healthy (status {alive.status_code})")
    except Exception as e:
        raise RuntimeError(f"Unable to reach GROBID at {grobid_url}: {e}")

    # Prepare form fields
    form = {
        "consolidateHeader": str(params.get("consolidate_header", 1)),
        "consolidateCitations": str(params.get("consolidate_citations", 1)),
        "includeRawCitations": str(params.get("include_raw_citations", 1)),
        "teiCoordinates": str(params.get("tei_coordinates", 1)),
    }

    # Session with retries
    retry = Retry(
        total=2,
        backoff_factor=1.0,
        status_forcelist=[500, 502, 503, 504],
        allowed_methods=["POST"],
        raise_on_status=False,
    )
    adapter = HTTPAdapter(max_retries=retry)
    s = requests.Session()
    s.mount("http://", adapter)
    s.mount("https://", adapter)

    # Stream the file to avoid loading completely into memory
    with pdf_path.open("rb") as f:
        files = {"input": (pdf_path.name, f, "application/pdf")}
        resp = s.post(endpoint, data=form, files=files, timeout=timeout_sec)

    # Raise with more context on failure
    try:
        resp.raise_for_status()
    except requests.HTTPError as e:
        snippet = resp.text[:800] if resp is not None else ""
        raise RuntimeError(f"GROBID error {resp.status_code}: {snippet}") from e

    return resp.text
