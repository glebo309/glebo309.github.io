import json, re
from pathlib import Path
from datetime import datetime, timedelta

SAFE = re.compile(r"[^a-zA-Z0-9._-]+")

def doi_to_slug(doi: str) -> str:
    doi = (doi or "").strip().lower()
    doi = doi.replace("/", "_")
    doi = SAFE.sub("_", doi)
    return doi[:200]

class Store:
    def __init__(self, base_dir: Path):
        self.base = base_dir
        self.lib = self.base / "library"
        self.tmp = self.base / "tmp"
        self.idx = self.base / "index"
        self.cache = self.base / "cache"
        self.lib.mkdir(parents=True, exist_ok=True)
        self.tmp.mkdir(parents=True, exist_ok=True)
        self.idx.mkdir(parents=True, exist_ok=True)
        self.cache.mkdir(parents=True, exist_ok=True)

    def paper_dir(self, doi: str) -> Path:
        return self.lib / doi_to_slug(doi)

    def meta_path(self, doi: str) -> Path:
        return self.paper_dir(doi) / "meta.json"

    def tei_path(self, doi: str) -> Path:
        return self.paper_dir(doi) / "tei.xml"

    def extracted_path(self, doi: str) -> Path:
        return self.paper_dir(doi) / "extracted.json"

    def log_path(self, doi: str) -> Path:
        return self.paper_dir(doi) / "logs.txt"

    def index_csv(self) -> Path:
        return self.idx / "papers.csv"

    def write_json(self, path: Path, obj):
        path.parent.mkdir(parents=True, exist_ok=True)
        with path.open("w", encoding="utf-8") as f:
            json.dump(obj, f, ensure_ascii=False, indent=2)

    def append_log(self, doi: str, msg: str):
        p = self.log_path(doi)
        p.parent.mkdir(parents=True, exist_ok=True)
        with p.open("a", encoding="utf-8") as f:
            f.write(f"[{datetime.utcnow().isoformat()}Z] {msg}\n")

    # --- Simple on-disk API cache ---
    def _cache_key_to_path(self, namespace: str, key: str) -> Path:
        ns = SAFE.sub("_", (namespace or "").strip().lower()) or "default"
        slug_key = doi_to_slug(key)
        return self.cache / ns / f"{slug_key}.json"

    def read_cache_json(self, namespace: str, key: str, max_age_hours: int | None = None):
        """
        Read a cached JSON object. If max_age_hours is provided, return None when expired.
        """
        p = self._cache_key_to_path(namespace, key)
        if not p.exists():
            return None
        if max_age_hours is not None:
            try:
                mtime = datetime.utcfromtimestamp(p.stat().st_mtime)
                if datetime.utcnow() - mtime > timedelta(hours=max_age_hours):
                    return None
            except Exception:
                return None
        try:
            return json.loads(p.read_text(encoding="utf-8"))
        except Exception:
            return None

    def write_cache_json(self, namespace: str, key: str, obj) -> None:
        p = self._cache_key_to_path(namespace, key)
        p.parent.mkdir(parents=True, exist_ok=True)
        try:
            with p.open("w", encoding="utf-8") as f:
                json.dump(obj, f, ensure_ascii=False)
        except Exception:
            pass
