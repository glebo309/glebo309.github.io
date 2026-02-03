#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Combined pillar classification - Optimized version with externalized rules + per-paper master CSV
"""

import argparse, json, re, html, time
from pathlib import Path
from typing import Dict, List, Tuple, Optional
from collections import Counter, defaultdict
import pandas as pd
import requests
from concurrent.futures import ThreadPoolExecutor, as_completed
from requests.adapters import HTTPAdapter

# --------- Optional progress ----------
try:
    from tqdm import tqdm
    def PROG(it, **kw): return tqdm(it, **kw)
except Exception:
    def PROG(it, **kw): return it

# --------- Optional retry logic ----------
try:
    from urllib3.util.retry import Retry
except Exception:
    Retry = None

# --------- YAML (optional) ----------
try:
    import yaml
except Exception:
    yaml = None

WS = re.compile(r"\s+")
DOI_RE = re.compile(r'(10\.\d{4,9}/\S+)', re.I)

# Enhanced enzyme detection for biocatalysis filtering
ENZYME_RE = re.compile(
    r"\b(enzyme|enzymatic|biocatal\w+|lipase|transaminase|dehydrogenase|reductase|oxidase|"
    r"monooxygenase|peroxygenase|halogenase|P450|BVMO|OYE|nitrilase|nitrile hydratase|"
    r"aldolase|carboxylase|imine reductase|IRED|RedAm|AmDH|immobiliz|bioreactor|"
    r"ketoreductase|KRED|aminotransferase|ω-?TA)\b",
    re.I
)

# --- Default pillar names if parsing fails ---
DEFAULT_PILLARS_BY_NUM = {
    1: "Discovery & Sourcing of Biocatalysts",
    2: "Design & Engineering",
    3: "Biocatalyst Formats & Cellular Context",
    4: "Media & Microenvironment",
    5: "Immobilization & Materials",
    6: "Cofactor & Energy Management",
    7: "Cascade & Route Design",
    8: "Reactors, Flow & In-Line Operations",
    9: "Reaction Space & Enzyme Portfolios",
    10: "Sustainability, Metrics & Industrialization",
}

def _clean_text(s: str) -> str:
    return re.sub(r"\s+", " ", (s or "")).strip()

def strip_tags(s: str) -> str:
    if not s: return ""
    s = re.sub(r"<[^>]+>", " ", s)
    s = html.unescape(s)
    return WS.sub(" ", s).strip()

def normalize_doi(doi: str) -> str:
    if not doi: return ""
    s = re.sub(r'^https?://(dx\.)?doi\.org/', '', doi.strip(), flags=re.I)
    m = DOI_RE.search(s)
    doi = m.group(1).lower() if m else ""
    # collapse German vs Int. Ed. duplicates
    doi = re.sub(r"^10\.1002/ange\.", "10.1002/anie.", doi)
    return doi

def parse_pillars_from_md(md_path: Path):
    """Robust pillar parsing with multiple heading styles and fallback."""
    if not md_path.exists():
        print(f"[error] Pillar definition file not found: {md_path}")
        return []

    text = md_path.read_text(encoding="utf-8")
    lines = text.splitlines()

    head_res = [
        re.compile(r'^\s*#{1,6}\s*Pillar\s*(\d+)\s*[:\-–—]\s*(.+)$', re.I),
        re.compile(r'^\s*#{1,6}\s*(\d+)\s*[\)\.\-–—]\s*(.+)$', re.I),
        re.compile(r'^\s*(\d+)\s*[\)\.\-–—]\s*(.+)$', re.I),
        re.compile(r'^\s*Pillar\s*(\d+)\s*[:\-–—]\s*(.+)$', re.I),
    ]

    found = []
    for line in lines:
        L = line.rstrip()
        hit = None
        for rx in head_res:
            m = rx.match(L)
            if m:
                num = int(m.group(1))
                name = _clean_text(m.group(2))
                hit = (num, name)
                break
        if hit:
            found.append({"num": hit[0], "name": hit[1]})

    # Consolidate (handle duplicates; keep first)
    by_num = {}
    for rec in found:
        by_num.setdefault(rec["num"], rec["name"])

    # Build final list in numeric order
    pillars = [{"num": n, "name": by_num[n]} for n in sorted(by_num.keys())]

    if not pillars:
        print("[warn] No pillars parsed from Definition.md; falling back to defaults.")
        pillars = [{"num": n, "name": DEFAULT_PILLARS_BY_NUM[n]} for n in sorted(DEFAULT_PILLARS_BY_NUM)]

    print("[debug] Parsed pillars:")
    for p in pillars:
        print(f"  - {p['num']}: {p['name']}")

    return pillars

# ---------- Built-in rules (fallback) ----------
DEFAULT_RULES_BY_NUM = {
    1: [
        (r"\bgenome mining\b|\bmetagenom\w*\b|\bbioprospect\w*\b|\bbiopanning\b", 2.6),
        (r"\bhomolog (search|screen)\b|\b(ssn|sequence similarity network)\b|\bHMM\b|\bprofile[- ]?HMM\b", 2.2),
        (r"\b(biosynthetic gene cluster|BGCs?)\b|\bantiSMASH\b|\bgenomic context\b|\bsynten\w*", 1.9),
        (r"\bdegenerate primer\w*\b|\bPCR[- ]?based screen\w*\b|\benrichment culture\w*\b", 1.7),
    ],
    2: [
        (r"\bdirected evolution\b|error[- ]?prone PCR\b", 2.5),
        (r"\bsite[- ]saturation\b|saturation mutagenesis|CAST|ISM", 2.0),
        (r"\bconsensus\b|ancestral\b|ProSAR|DNA shuffling", 1.6),
    ],
    3: [
        (r"\bwhole[- ]cell\b|\bresting cell(s)?\b|\bpermeabiliz", 2.5),
        (r"\bcell[- ]free\b|\blysate\b|\bCFE\b|\bsurface display\b", 2.0),
        (r"\bchassis\b|\bco[- ]culture(s)?\b", 1.6),
    ],
    4: [
        (r"\borganic solvent(s)?\b|\bsolvent[- ]toleran\w*", 2.5),
        (r"\btwo[- ]liquid[- ]phase\b|\bbiphasic\b|\bmicro[- ]aqueous\b", 2.5),
        (r"\bionic liquid(s)?\b|\bILs?\b|\bdeep eutectic\b|\bDES\b", 2.5),
        (r"\bwater activity\b|\ba[_ ]?w\b|\bpH memory\b", 2.0),
    ],
    5: [
        (r"\bimmobiliz\w*", 3.0),
        (r"\bcarrier\b|\bsupport\b|\bresin\b|\bbead(s)?\b|\bagarose\b|\bglyoxyl\b|\bepoxy\b|\bboronic\b", 2.0),
        (r"\bCLEA(s)?\b|\bCLEC(s)?\b|\bsol[- ]gel\b|\bhydrogel(s)?\b|\bmesoporous\b|\bmagnetic\b", 2.0),
        (r"\bpreparation\b|\bimmobilized\b|\battached\b|\bbound\b|\bfixed\b", 1.5),
        (r"\breuse\b|\brecycl\w*\b|\bstabilit\w*\b|\boperational\b", 1.3),
    ],
    6: [
        (r"\bcofactor(s)?\b|\bNAD\+?\b|\bNADH\b|\bNADPH\b|\bflavin(s)?\b|\bFAD\b|\bFMN\b", 2.6),
        (r"\b(cofactor|NAD(P)H) regenerat\w*\b|\brecycling\b|\bcofactor[- ]?independent\b", 2.2),
        (r"\bFDH\b|\bformate dehydrogenase\b|\bGDH\b|\bglucose dehydrogenase\b|\bPTDH\b|\bphosphite dehydrogenase\b", 2.0),
        (r"\bATP regeneration\b|\bpolyphosphate\b|\bpolyP\b|\bPPK\b|\bSAM regeneration\b|\bCoA\b", 1.8),
        (r"\bhydrogen[- ]borrowing\b|\belectro(enzyme|chemical)\b|\bphotoenzyme\w*\b|\bphotoredox\b", 1.6),
    ],
    7: [
        (r"\b(cascade|multi[- ]enzym\w*)\b", 2.5),
        (r"\bone[- ]pot\b|\btandem\b|\bchemo[- ]?enzymatic\b", 2.0),
        (r"\bcompartment\w*\b|\b(retrosynthesis|CASP)\b", 1.6),
        (r"\bsequential\b|\bstepwise\b|\bone[- ]step\b|\btwo[- ]step\b", 1.3),
    ],
    8: [
        (r"\bflow\b|\bcontinuous\b|\bPFR\b|\bplug[- ]flow\b|\bCSTR\b", 2.5),
        (r"\bpacked[- ]bed\b|\bPBR\b|\bmicroreactor\b|\btube[- ]in[- ]tube\b|\bmembrane reactor\b|\bloop reactor\b", 2.1),
        (r"\bresidence[- ]?time\b|\bRTD\b|\bslug flow\b|\bchip reactor\b|\bmillifluidic\b", 1.8),
        (r"\bPAT\b|\bprocess analytical\b|\bin[- ]line\b|\bon[- ]line\b|\bquench\b|\bwork[- ]?up\b", 1.6),
    ],
    9: [
        (r"\bKRED\b|\bADH\b|\bketoreductase\b", 1.8),
        (r"\btransaminase\b|\baminotransferase\b|\bω-?TA\b|\bIRED\b|\bRedAm\b|\bAmDH\b", 1.8),
        (r"\bBVMO\b|\bOYE\b|\bmonooxygenase\b|\bperoxygenase\b|\bP450\b|\bhalogenase\b", 1.6),
        (r"\baldolase\b|\bDERA\b|\bFSA\b|\bHNL\b|\bThDP\b|\bcarboxylase\b|\bCAR\b", 1.6),
        (r"\bcyclase\b|\bSHC\b|\bterpene synthase\b|\bcarbene\b|\bnitrene\b|\bmetalloenzyme\b", 1.4),
    ],
    10:[
        (r"\bPMI\b|\bE[- ]factor\b|\bgreen (chemistry|metrics)\b", 2.0),
        (r"\bSTY\b|\bspace[- ]time yield\b|\btechno[- ]economic\b|\bTEA\b", 1.6),
        (r"\bLCA\b|\beco[- ]efficien", 1.6),
        (r"\bindustrial\b|\bscale\b|\bGMP\b", 1.4),
    ],
}
PRIORITY_ORDER_NUM_DEFAULT = [5,4,8,6,7,3,2,1,9,10]
PENALTIES_BY_NUM_DEFAULT = {
    9: [(r"directed evolution|site[- ]saturation|mutagenesis|CAST|ISM|library|screen(ing)?|engineer\w*", 1.8)],
    8: [(r"flow|continuous", 1.2)],
    10: [(r".*", 1.0)],
}

class CombinedClassifier:
    def __init__(self, pillar_md: Path, review_root: Path, out_dir: Path,
                 allow_multi: bool, conf_th: float, fetch_abstracts: bool,
                 limit_papers: int, limit_sections: int, cache_file: Path, 
                 section_chars: int, fetch_full_articles: bool, rules_yaml: Optional[Path]):
        self.pillar_md = pillar_md
        self.review_root = review_root
        self.out_dir = out_dir
        self.out_dir.mkdir(parents=True, exist_ok=True)
        self.allow_multi = allow_multi
        self.conf_th = conf_th
        self.fetch_abstracts = fetch_abstracts
        self.fetch_full_articles = fetch_full_articles
        self.limit_papers = max(0, limit_papers)
        self.limit_sections = max(0, limit_sections)
        self.section_chars = section_chars

        # Enhanced HTTP session with connection pooling and retries
        self.session = requests.Session()
        if Retry is not None:
            retry = Retry(total=3, connect=3, read=3, backoff_factor=0.3,
                         status_forcelist=[429, 502, 503, 504], raise_on_status=False)
            adapter = HTTPAdapter(max_retries=retry, pool_connections=64, pool_maxsize=64)
            self.session.mount("https://", adapter)
            self.session.mount("http://", adapter)

        # Cache policy
        self.max_cache_age_days = 180
        self.refresh_incomplete_cache = False

        # pillar parsing
        self.pillars = parse_pillars_from_md(self.pillar_md)
        self.pillar_by_num = {p["num"]: p["name"] for p in self.pillars}
        for n in range(1, 11):
            if n not in self.pillar_by_num:
                self.pillar_by_num[n] = DEFAULT_PILLARS_BY_NUM[n]
                self.pillars.append({"num": n, "name": self.pillar_by_num[n]})
        self.pillars = sorted(self.pillars, key=lambda x: x["num"])
        self.num_by_name = {p["name"]: p["num"] for p in self.pillars}

        # rules (YAML or fallback)
        self.rules_by_num, self.penalties_by_num, self.priority_order_nums = self._load_rules_yaml(rules_yaml)
        self.priority_order_names = [self.pillar_by_num[n] for n in self.priority_order_nums if n in self.pillar_by_num]

        # cache for metadata
        self.cache_path = cache_file
        self.cache = self._load_cache()

        # debug: collect rule hits for audit per paper key
        self.debug_hits: Dict[str, str] = {}

    # ---------- rules loading ----------
    def _load_rules_yaml(self, rules_yaml: Optional[Path]):
        if rules_yaml and rules_yaml.exists() and yaml is not None:
            try:
                data = yaml.safe_load(rules_yaml.read_text(encoding="utf-8"))
                pillars = data.get("pillars", {})
                rules_by_num = {}
                penalties_by_num = {}
                # allow pillar names override if present
                for k, v in pillars.items():
                    try:
                        num = int(k)
                    except Exception:
                        continue
                    pos = []
                    for item in (v.get("positive") or []):
                        pat = item.get("pattern", "")
                        w = float(item.get("weight", 1.0))
                        if pat:
                            pos.append((pat, w))
                    if pos:
                        rules_by_num[num] = pos

                    pens = []
                    for item in (v.get("penalties") or []):
                        pat = item.get("pattern", "")
                        w = float(item.get("weight", 1.0))
                        if pat:
                            pens.append((pat, w))
                    if pens:
                        penalties_by_num[num] = pens

                    # name override
                    if v.get("name"):
                        self.pillar_by_num[num] = v["name"]

                prio = data.get("priority_order") or PRIORITY_ORDER_NUM_DEFAULT

                # fill fallbacks
                if not rules_by_num:
                    rules_by_num = DEFAULT_RULES_BY_NUM
                else:
                    for n, lst in DEFAULT_RULES_BY_NUM.items():
                        rules_by_num.setdefault(n, lst)
                if not penalties_by_num:
                    penalties_by_num = PENALTIES_BY_NUM_DEFAULT
                else:
                    for n, lst in PENALTIES_BY_NUM_DEFAULT.items():
                        penalties_by_num.setdefault(n, lst)
                if not prio:
                    prio = PRIORITY_ORDER_NUM_DEFAULT

                print(f"[rules] Loaded external rules: {rules_yaml}")
                return rules_by_num, penalties_by_num, [int(x) for x in prio]
            except Exception as e:
                print(f"[rules] Failed to load YAML ({rules_yaml}): {e}. Using built-ins.")
        else:
            if rules_yaml and not rules_yaml.exists():
                print(f"[rules] No rules.yaml at {rules_yaml}. Using built-ins.")
            elif yaml is None and rules_yaml:
                print("[rules] PyYAML not installed; using built-ins.")

        return DEFAULT_RULES_BY_NUM, PENALTIES_BY_NUM_DEFAULT, PRIORITY_ORDER_NUM_DEFAULT

    # ---------- cache ----------
    def _load_cache(self):
        if self.cache_path.exists():
            try:
                return json.loads(self.cache_path.read_text(encoding="utf-8"))
            except Exception:
                return {}
        return {}

    def _save_cache(self):
        try:
            self.cache_path.write_text(json.dumps(self.cache, ensure_ascii=False, indent=2), encoding="utf-8")
        except Exception:
            pass

    # ---------- optional OA discovery ----------
    def fetch_full_article_content(self, doi: str) -> str:
        if not doi: return ""
        full_text = ""
        try:
            resp = self.session.get(
                f"https://api.unpaywall.org/v2/{requests.utils.quote(doi, safe='')}?email=researcher@example.com",
                timeout=10
            )
            if resp.ok:
                data = resp.json()
                if data.get("is_oa") and data.get("best_oa_location"):
                    pdf_url = data["best_oa_location"].get("url_for_pdf")
                    if pdf_url:
                        full_text = f"[Open Access PDF available: {pdf_url}]"
        except Exception:
            pass
        if "arxiv" in doi.lower():
            try:
                arxiv_id = doi.split("/")[-1]
                resp = self.session.get(f"http://export.arxiv.org/api/query?id_list={arxiv_id}", timeout=10)
                if resp.ok and resp.text:
                    full_text = f"[arXiv content available for {arxiv_id}]"
            except Exception:
                pass
        try:
            resp = self.session.get(
                f"https://www.ebi.ac.uk/europepmc/webservices/rest/search?query=DOI:{requests.utils.quote(doi, safe='')}&format=json&resultType=core",
                timeout=10
            )
            if resp.ok:
                data = resp.json()
                results = data.get("resultList", {}).get("result", [])
                if results and results[0].get("isOpenAccess") == "Y":
                    full_text = f"[Europe PMC open access content available]"
        except Exception:
            pass
        return full_text

    # ---------- metadata ----------
    def fetch_metadata(self, doi: str) -> Tuple[str, str, Optional[int], List[str], str, str]:
        if not doi:
            return ("", "", None, [], "", "")
        now = time.time()
        max_age = self.max_cache_age_days * 24 * 3600

        c = self.cache.get(doi, {})
        c_ts = c.get("ts", 0)
        fresh = (now - c_ts) < max_age if c_ts else False

        if self.fetch_abstracts:
            if fresh and (c.get("title") or not self.refresh_incomplete_cache):
                return (c.get("title",""), c.get("abstract",""), c.get("year"),
                        c.get("authors",[]) or [], c.get("journal","") or "", c.get("full_text",""))
        else:
            if c:
                return (c.get("title",""), c.get("abstract",""), c.get("year"),
                        c.get("authors",[]) or [], c.get("journal","") or "", c.get("full_text",""))

        title   = c.get("title","")
        abstract= c.get("abstract","")
        year    = c.get("year")
        authors = c.get("authors",[]) or []
        journal = c.get("journal","") or ""
        full_text = c.get("full_text","")

        # Crossref
        try:
            resp = self.session.get(
                f"https://api.crossref.org/works/{requests.utils.quote(doi, safe='')}",
                timeout=8
            )
            if resp.ok:
                msg = resp.json().get("message", {})
                if not title:
                    title = " ".join(msg.get("title") or []) or title
                cr_abs = msg.get("abstract")
                if cr_abs and not abstract:
                    abstract = strip_tags(cr_abs)
                y = (msg.get("issued") or {}).get("date-parts", [[None]])[0][0]
                if y and not year:
                    year = int(y)
                if not authors:
                    names = []
                    for a in (msg.get("author") or []):
                        given = (a.get("given") or "").strip()
                        family = (a.get("family") or "").strip()
                        nm = " ".join([given, family]).strip() or (a.get("name") or "").strip()
                        if nm:
                            names.append(WS.sub(" ", nm))
                    if names:
                        authors = names
                cont = msg.get("short-container-title") or msg.get("container-title") or []
                if not journal:
                    journal = (cont[0] if isinstance(cont, list) and cont else cont or "").strip()
        except Exception:
            pass

        # Semantic Scholar
        try:
            s2 = self.session.get(
                f"https://api.semanticscholar.org/graph/v1/paper/DOI:{requests.utils.quote(doi, safe='')}"
                "?fields=title,year,abstract,authors,name,journal",
                timeout=8
            )
            if s2.ok:
                j = s2.json()
                if not title:
                    title = j.get("title") or title
                if not abstract:
                    abstract = strip_tags(j.get("abstract") or "") or abstract
                if not year and j.get("year"):
                    year = int(j.get("year"))
                if not authors:
                    s2_auth = []
                    for a in j.get("authors") or []:
                        nm = (a.get("name") or "").strip()
                        if nm:
                            s2_auth.append(WS.sub(" ", nm))
                    if s2_auth:
                        authors = s2_auth
                if not journal:
                    jr = j.get("journal") or {}
                    journal = (jr.get("name") if isinstance(jr, dict) else jr or "").strip()
        except Exception:
            pass

        if self.fetch_full_articles and not full_text:
            full_text = self.fetch_full_article_content(doi)

        self.cache[doi] = {
            "title": title, "abstract": abstract, "year": year,
            "authors": authors, "journal": journal, "full_text": full_text, "ts": now
        }
        self._save_cache()
        return (title, abstract, year, authors, journal, full_text)

    def prefetch_metadata_batch(self, dois: List[str], workers: int = 12):
        to_fetch = []
        now = time.time()
        max_age = self.max_cache_age_days * 24 * 3600
        for d in set([normalize_doi(d) for d in dois if d]):
            c = self.cache.get(d, {})
            fresh = (now - c.get("ts", 0)) < max_age if c.get("ts") else False
            if not fresh:
                to_fetch.append(d)
        if not to_fetch:
            print(f"[cache] All {len(set(dois))} DOIs are fresh in cache")
            return
        print(f"[cache] Prefetching {len(to_fetch)} DOIs with {workers} workers...")
        def _task(doi_):
            try:
                self.fetch_metadata(doi_); return True
            except Exception:
                return False
        success_count = 0
        with ThreadPoolExecutor(max_workers=workers) as ex:
            futures = [ex.submit(_task, d) for d in to_fetch]
            for future in PROG(as_completed(futures), total=len(futures), desc="Fetching"):
                if future.result():
                    success_count += 1
        print(f"[cache] Successfully fetched {success_count}/{len(to_fetch)} papers")

    # ---------- data load ----------
    def load_bibliographies(self) -> pd.DataFrame:
        rows = []
        files = sorted((self.review_root/"json").glob("*.bibliography.json"))
        for jpath in files:
            data = json.loads(jpath.read_text(encoding="utf-8"))
            review_id = data.get("review_id") or jpath.stem.replace(".bibliography","")
            bib = data.get("bibliography", {})
            for _, rec in bib.items():
                doi = normalize_doi(rec.get("doi") or "")
                title = (rec.get("title") or "").strip()
                raw = (rec.get("raw_citation") or "").strip()

                authors = rec.get("authors", [])
                if isinstance(authors, str):
                    authors = [authors]
                elif not isinstance(authors, list):
                    authors = []
                authors = [str(a).strip() for a in authors if a]

                journal = (rec.get("journal") or rec.get("container") or 
                        rec.get("venue") or rec.get("booktitle") or "").strip()

                year = rec.get("year")
                if year is not None:
                    try:
                        if isinstance(year, (int, float)):
                            year = int(year)
                        else:
                            ys = re.sub(r"\D", "", str(year))
                            year = int(ys) if ys else None
                    except Exception:
                        year = None

                rows.append({
                    "review_id": review_id,
                    "doi": doi,
                    "title": title,
                    "authors": authors,
                    "journal": journal,
                    "year": year,
                    "raw_citation": raw
                })

        df = pd.DataFrame(rows)
        if df.empty:
            return df

        # robust dedupe with field merging
        df["key"] = df.apply(
            lambda r: r["doi"] if r["doi"] else WS.sub(" ", (r["raw_citation"] or "").strip().lower()), axis=1
        )
        grouped = []
        for key, g in df.groupby("key", dropna=False):
            doi   = next((x for x in g["doi"].dropna().unique() if x), "")
            title = next((x for x in g["title"].dropna().unique() if x), "")

            # merge authors lists
            all_authors = []
            for auth_list in g["authors"]:
                if isinstance(auth_list, list):
                    all_authors.extend(auth_list)
            authors = list(dict.fromkeys(all_authors))

            journal = next((x for x in g["journal"].dropna().unique() if x), "")

            years = [int(y) for y in g["year"].tolist() if pd.notna(y) and y is not None]
            year = Counter(years).most_common(1)[0][0] if years else None

            raw = next((x for x in g["raw_citation"].dropna().unique() if x), "")
            cited_by = sorted(set(g["review_id"].tolist()))

            grouped.append({
                "key": key, "doi": doi, "title": title, "authors": authors,
                "journal": journal, "year": year, "raw_citation": raw,
                "cited_by_reviews": ";".join(cited_by)
            })

        out = pd.DataFrame(grouped)
        if self.limit_papers > 0:
            out = out.head(self.limit_papers)
        return out

    # ---------- scoring helpers ----------
    def score_text(self, text: str) -> Dict[str, float]:
        txt = text or ""
        scores = {self.pillar_by_num[n]: 0.0 for n in self.rules_by_num if n in self.pillar_by_num}

        # Base scoring
        for num, pats in self.rules_by_num.items():
            name = self.pillar_by_num.get(num)
            if not name: continue
            for pat, w in pats:
                if re.search(pat, txt, flags=re.I):
                    scores[name] += w

        # Penalties (with gates)
        for num, pens in self.penalties_by_num.items():
            name = self.pillar_by_num.get(num)
            if not name: continue
            for pat, w in pens:
                if num == 8:
                    if re.search(pat, txt, re.I) and not re.search(r"enzyme|biocatal|lipase|transaminase|whole[- ]cell|bioreactor|immobiliz", txt, re.I):
                        scores[name] -= w
                elif num in (4, 5):
                    if re.search(pat, txt, re.I) and not ENZYME_RE.search(txt):
                        scores[name] -= w
                elif num == 10:
                    if not re.search(r"PMI|E[- ]?factor|LCA|TEA|space[- ]?time yield|STY|GMP|industrial|scale[- ]?up", txt, re.I):
                        scores[name] -= w
                else:
                    if re.search(pat, txt, re.I):
                        scores[name] -= w
        return scores

    def find_rule_hits(self, text: str, max_hits: int = 8) -> List[str]:
        """Return simple 'P<num>: <regex>' markers that matched (positive rules only)."""
        hits = []
        seen = set()
        for num, pats in self.rules_by_num.items():
            for pat, _w in pats:
                if re.search(pat, text or "", flags=re.I):
                    tag = f"P{num}:{pat}"
                    if tag not in seen:
                        hits.append(tag); seen.add(tag)
                        if len(hits) >= max_hits: return hits
        return hits

    def choose_from_scores(self, scores: Dict[str, float]) -> Tuple[List[str], float]:
        if not scores:
            return ([], 0.0)
        vals = sorted(scores.values(), reverse=True)
        best = vals[0]
        if best <= 0:
            return ([], 0.0)
        second = vals[1] if len(vals) > 1 else 0.0
        conf = best / (best + second + 1e-8)
        best_pillars = [p for p, s in scores.items() if abs(s - best) < 1e-6]
        if len(best_pillars) > 1:
            for pname in self.priority_order_names:
                if pname in best_pillars:
                    best_pillars = [pname]; break
        return (best_pillars, conf)

    # ---------- classifiers ----------
    def classify_by_sections(self) -> Dict[str, Dict]:
        results: Dict[str, Dict] = {}
        sec_files = sorted((self.review_root/"json").glob("*.sections.json"))
        if self.limit_sections > 0:
            sec_files = sec_files[:self.limit_sections]

        for sec_file in PROG(sec_files, desc="[sections]"):
            try:
                data = json.loads(sec_file.read_text(encoding="utf-8"))
                review_id = data.get("review_id") or sec_file.stem.replace(".sections","")
                sections = data.get("sections", [])
                cite_file = self.review_root / "json" / f"{review_id}.section_citations.csv"
                if not cite_file.exists():
                    continue
                cite_df = pd.read_csv(cite_file)
                def norm(s): return WS.sub(" ", (s or "").strip().lower())
                idx = {}
                for _, row in cite_df.iterrows():
                    idx.setdefault(norm(row.get("section_header","")), []).append(row)

                for s in sections:
                    header = strip_tags(s.get("header",""))
                    full_text = strip_tags(s.get("text",""))
                    if re.match(r"^\s*(references?|acknowledg|supporting|supplement)", header, re.I):
                        continue

                    # body sample
                    if len(full_text) > self.section_chars:
                        mid_point = len(full_text) // 2
                        start_chunk = full_text[:self.section_chars//2]
                        end_chunk = full_text[mid_point:mid_point + self.section_chars//2]
                        body_sample = start_chunk + " " + end_chunk
                    else:
                        body_sample = full_text

                    header_scores = self.score_text(header)
                    body_scores = self.score_text(body_sample)
                    combined_scores = {}
                    all_pillars = set(header_scores.keys()) | set(body_scores.keys())
                    for pillar in all_pillars:
                        combined_scores[pillar] = 0.2 * header_scores.get(pillar, 0.0) + 0.8 * body_scores.get(pillar, 0.0)
                    (best_list, conf_sec) = self.choose_from_scores(combined_scores)
                    if not best_list:
                        continue

                    sec_rows = idx.get(norm(header), [])
                    if not sec_rows:
                        q = norm(header)
                        hit = []
                        for k, rows in idx.items():
                            if q in k or k in q:
                                hit.extend(rows)
                        sec_rows = hit

                    for r in sec_rows:
                        doi = normalize_doi(str(r.get("doi") or ""))
                        raw = (r.get("raw_citation") or "").strip()
                        title = (r.get("title") or "").strip()
                        year = r.get("year")
                        try:
                            year = int(float(year)) if year not in (None, "") else None
                        except Exception:
                            year = None
                        key = doi if doi else WS.sub(" ", raw.strip().lower())
                        entry = results.setdefault(key, {"pillars": {}, "by": [], "sample": None})
                        for pname in best_list:
                            entry["pillars"][pname] = entry["pillars"].get(pname, 0.0) + conf_sec
                        if not entry["sample"] and (raw or title or doi):
                            entry["sample"] = {
                                "doi": doi, "raw_citation": raw, "title": title, "year": year,
                                "authors": r.get("authors", []), "journal": r.get("journal", "")
                            }
                        entry["by"].append({"review_id": review_id, "section": header, "conf": conf_sec})
            except Exception:
                continue

        # compress to final per paper
        final = {}
        for key, data in results.items():
            pill2score = data["pillars"]
            if not pill2score:
                continue
            items = sorted(pill2score.items(), key=lambda x: -x[1])
            best_score = items[0][1]
            keep = [items[0][0]]
            if self.allow_multi and len(items) > 1 and items[1][1] >= 0.8 * best_score:
                keep.append(items[1][0])
            total = sum(pill2score.values()) + 1e-8
            conf = best_score / total
            final[key] = {"pillars": keep, "confidence": float(conf), "sections_used": data["by"]}
        return final

    def classify_papers(self, df: pd.DataFrame) -> Dict[str, Dict]:
        out = {}
        for _, row in PROG(df.iterrows(), total=len(df), desc="[papers]"):
            key = row["key"]
            doi = row.get("doi") or ""
            title = row.get("title") or ""
            abstract = ""
            year = row.get("year")
            full_text = ""

            if doi and self.fetch_abstracts:
                t2, a2, y2, _authors2, _journal2, ft2 = self.fetch_metadata(doi)
                if not title or len(title) < 5:
                    title = t2 or title
                abstract = a2 or ""
                full_text = ft2 or ""
                if y2:
                    if (year is None) or (year < 1900 or year > (time.gmtime().tm_year + 1)) or (abs(y2 - (year or y2)) >= 5):
                        year = y2

            if abstract:
                title_scores = self.score_text(title)
                abstract_scores = self.score_text(abstract)
                if full_text and len(full_text) > 100:
                    full_text_sample = full_text[:1000]
                    full_scores = self.score_text(full_text_sample)
                    combined_scores = {}
                    all_pillars = set(title_scores.keys()) | set(abstract_scores.keys()) | set(full_scores.keys())
                    for pillar in all_pillars:
                        combined_scores[pillar] = (0.2 * title_scores.get(pillar, 0.0) + 
                                                   0.6 * abstract_scores.get(pillar, 0.0) + 
                                                   0.2 * full_scores.get(pillar, 0.0))
                else:
                    combined_scores = {}
                    all_pillars = set(title_scores.keys()) | set(abstract_scores.keys())
                    for pillar in all_pillars:
                        combined_scores[pillar] = (0.3 * title_scores.get(pillar, 0.0) + 
                                                   0.7 * abstract_scores.get(pillar, 0.0))
                scores = combined_scores
            else:
                scores = self.score_text(title)
                for pillar in scores:
                    scores[pillar] *= 0.8

            best_list, conf = self.choose_from_scores(scores)
            min_conf = 0.35 if abstract else 0.55
            if not best_list or conf < min_conf:
                # still store hits for audit visibility
                text_for_hits = (title or "") + " " + (abstract or "")
                if full_text:
                    text_for_hits += " " + full_text[:1000]
                self.debug_hits[key] = "; ".join(self.find_rule_hits(text_for_hits))
                continue

            keep = [best_list[0]]
            if self.allow_multi:
                sorted_items = sorted(scores.items(), key=lambda x: -x[1])
                if len(sorted_items) > 1 and sorted_items[1][1] >= 0.9 * sorted_items[0][1]:
                    keep.append(sorted_items[1][0])

            out[key] = {"pillars": keep, "confidence": float(conf)}

            # record rule hits for audit
            text_for_hits = (title or "") + " " + (abstract or "")
            if full_text:
                text_for_hits += " " + full_text[:1000]
            self.debug_hits[key] = "; ".join(self.find_rule_hits(text_for_hits))

        return out

    # ---------- reconcile ----------
    def combine(self, df: pd.DataFrame, sec_map: Dict[str, Dict], pap_map: Dict[str, Dict]) -> List[Dict]:
        def first_last_only(names: List[str]) -> List[str]:
            if not names:
                return []
            if len(names) == 1 or names[0] == names[-1]:
                return [names[0]]
            return [names[0], names[-1]]

        results = []
        keys = set(df["key"].tolist()) | set(sec_map.keys()) | set(pap_map.keys())
        cur_year = time.gmtime().tm_year

        for key in keys:
            s = sec_map.get(key)
            p = pap_map.get(key)

            row = df[df["key"] == key]
            row = row.iloc[0] if len(row) else None

            doi = (row["doi"] if row is not None else "") or ""
            title = ((row["title"] if row is not None else "") or "").strip()
            year = (row["year"] if row is not None else None)
            raw = ((row["raw_citation"] if row is not None else "") or "").strip()
            cited_by = (row["cited_by_reviews"] if row is not None else "") or ""

            # Fallback to section sample if bib row missing/empty
            if (not raw or not title) and s and s.get("sample"):
                samp = s["sample"]
                doi = doi or (samp.get("doi") or "")
                raw = raw or (samp.get("raw_citation") or "")
                title = title or (samp.get("title") or "")
                year = year if year not in (None, "") else samp.get("year")

            # Decide pillars + method + conf
            if s and p:
                agree = list(set(s["pillars"]) & set(p["pillars"]))
                if agree:
                    pillars = agree; method = "consensus"; conf = (s["confidence"] + p["confidence"]) / 2.0
                else:
                    if s["confidence"] + 0.10 >= p["confidence"]:
                        pillars = s["pillars"]; method = "section_priority"; conf = s["confidence"]
                    else:
                        pillars = p["pillars"]; method = "paper_priority"; conf = p["confidence"]

                    if self.allow_multi and s["confidence"] >= self.conf_th and p["confidence"] >= self.conf_th:
                        pillars = list(dict.fromkeys(s["pillars"] + p["pillars"]))
                        method = "union_strong"; conf = max(s["confidence"], p["confidence"])
            elif s:
                pillars = s["pillars"]; method = "section_only"; conf = s["confidence"]
            elif p:
                pillars = p["pillars"]; method = "paper_only"; conf = p["confidence"]
            else:
                continue

            # authors/journal
            authors_src = []
            if row is not None and isinstance(row.get("authors", []), list):
                authors_src = row.get("authors", []) or []
            elif s and s.get("sample") and isinstance(s["sample"].get("authors", []), list):
                authors_src = s["sample"]["authors"] or []

            journal = ""
            if row is not None and isinstance(row.get("journal", ""), str):
                journal = row.get("journal", "") or ""
            elif s and s.get("sample"):
                journal = s["sample"].get("journal", "") or ""

            # Enrich from metadata and reconcile YEAR
            if doi:
                try:
                    t2, a2, y2, auth2, jr2, _ft2 = self.fetch_metadata(doi)
                    if not title and t2:
                        title = t2
                    if y2:
                        if (year is None) or (year < 1900 or year > cur_year + 1) or (abs(int(y2) - int(year)) >= 5):
                            year = int(y2)
                    if not authors_src and auth2:
                        authors_src = auth2
                    if not journal and jr2:
                        journal = jr2
                except Exception:
                    pass

            # pre-1900 guard
            text_for_filter = f"{title} {raw}"
            if (year is not None and year < 1900) and not ENZYME_RE.search(text_for_filter):
                continue

            authors_pair = first_last_only([a for a in (authors_src or []) if a])

            for pname in pillars:
                results.append({
                    "key": key,
                    "pillar_num": self.num_by_name.get(pname, None),
                    "pillar": pname,
                    "method": method,
                    "confidence": round(float(conf), 3),
                    "doi": doi,
                    "title": title,
                    "year": year if pd.notna(year) else "",
                    "raw_citation": raw,
                    "cited_by_reviews": cited_by,
                    "authors": authors_pair,
                    "journal": journal or "",
                })

        return results

    # ---------- outputs ----------
    def _format_first_author(self, authors):
        if not authors: return ""
        if len(authors) == 1: return authors[0]
        return f"{authors[0]} … {authors[-1]}"

    def write_outputs(self, combined_rows: List[Dict]):
        df = pd.DataFrame(combined_rows)
        if df.empty:
            print("[warn] No combined rows to write.")
            return

        # -------- pillar MD & CSV (existing) --------
        df.sort_values(["pillar_num", "year", "title"], inplace=True, na_position="last")
        csv_path = self.out_dir / "combined_pillar_assignments.csv"
        df.to_csv(csv_path, index=False)

        md_path = self.out_dir / "pillar_papers_combined.md"
        with md_path.open("w", encoding="utf-8") as f:
            f.write("# Biocatalysis Literature by Pillar\n\n")

            for num in sorted(set(df["pillar_num"].dropna().astype(int).tolist())):
                name = self.pillar_by_num.get(int(num), f"Pillar {num}")
                f.write(f"## Pillar {int(num)}: {name}\n\n")

                sub = df[df["pillar_num"] == num].copy()

                method_rank = {
                    "union_strong": 6, "consensus": 5,
                    "paper_priority": 4, "paper_only": 4,
                    "section_priority": 3, "section_only": 2,
                }
                sub["has_authors"] = sub["authors"].apply(lambda x: isinstance(x, list) and len(x) > 0)
                sub["method_rank"] = sub["method"].map(method_rank).fillna(0)

                sub = sub.sort_values(
                    ["has_authors", "method_rank", "year", "title"],
                    ascending=[False, False, False, True],
                    na_position="last"
                )
                sub = sub.drop_duplicates(subset=["doi", "title"], keep="first").reset_index(drop=True)

                printed = 0

                for i, (_, row) in enumerate(sub.iterrows(), 1):
                    title = (row.get("title") or "").strip()
                    year = row.get("year")
                    try:
                        if pd.notna(year) and year != "":
                            year = int(float(year))
                        else:
                            year = None
                    except Exception:
                        year = None

                    doi = (row.get("doi") or "").strip()
                    raw = (row.get("raw_citation") or "").strip()
                    authors = row.get("authors", []) or []
                    journal = (row.get("journal") or "").strip()
                    method = row.get("method", "")
                    conf = row.get("confidence", "")

                    if not (title or doi or raw):
                        continue

                    def compact_authors(names: List[str]) -> str:
                        if not names: return ""
                        if len(names) == 1 or names[0] == names[-1]:
                            return names[0]
                        return f"{names[0]} … {names[-1]}"

                    if title:
                        line = f"{printed + 1}. **{title}**"
                    elif raw:
                        line = f"{printed + 1}. *{raw}*"
                    else:
                        line = f"{printed + 1}. *(Untitled)*"

                    a_str = compact_authors(authors)
                    if a_str:
                        line += f"\n   _{a_str}_"

                    pieces = []
                    if journal: pieces.append(journal)
                    if year: pieces.append(str(year))
                    if pieces: line += "\n   " + " ".join(pieces)
                    if doi: line += f"\n   DOI: [doi:{doi}](https://doi.org/{doi})"
                    line += f"\n   _Classification: {method}, confidence: {conf}_"
                    f.write(line + "\n\n")
                    printed += 1

                f.write(f"**Total papers: {printed}**\n\n")
                f.write("---\n\n")

        # -------- report (existing) --------
        rep = self.out_dir / "classification_report.md"
        with rep.open("w", encoding="utf-8") as f:
            f.write("# Combined Pillar Classification Report\n\n")
            f.write(f"- Output CSV: `{csv_path.name}`\n")
            f.write(f"- Output MD : `{md_path.name}`\n\n")
            f.write("## Counts by method\n")
            meth = df.groupby("method").size().to_dict()
            for k, v in meth.items():
                f.write(f"- {k}: {v}\n")
            f.write("\n## Counts by pillar\n")
            pil = df.groupby("pillar").size().to_dict()
            for k, v in pil.items():
                num = self.num_by_name.get(k, "?")
                f.write(f"- Pillar {num} — {k}: {v}\n")

        print(f"[ok] wrote: {csv_path}")
        print(f"[ok] wrote: {md_path}")
        print(f"[ok] wrote: {rep}")

        rescued = df[df["method"].eq("paper_only") & df["raw_citation"].eq("") & (df["doi"] != "")]
        if len(rescued):
            print(f"[info] rescued {len(rescued)} papers from section-only via metadata fetch")

        # ===== NEW: Per-paper master CSV =====
        method_rank = {
            "union_strong": 6, "consensus": 5,
            "paper_priority": 4, "paper_only": 4,
            "section_priority": 3, "section_only": 2,
        }
        per_rows = []
        grouped = df.groupby("key") if "key" in df.columns else df.groupby(["doi","title"])
        for key, g in grouped:
            gg = g.copy()
            gg["mrank"] = gg["method"].map(method_rank).fillna(0)
            gg = gg.sort_values(["confidence","mrank"], ascending=[False, False])
            best = gg.iloc[0]

            all_pillars = ";".join(sorted(set(gg["pillar"].tolist()), key=lambda x: self.num_by_name.get(x, 999)))
            methods_present = ";".join(sorted(set(gg["method"].tolist()), key=lambda x: -method_rank.get(x,0)))
            cited_all = set()
            for s in gg["cited_by_reviews"].fillna("").tolist():
                if s:
                    cited_all.update([x for x in s.split(";") if x])
            cited_by = ";".join(sorted(cited_all))

            k = key if isinstance(key, str) else (best.get("doi") or best.get("title"))
            per_rows.append({
                "key": k,
                "doi": best.get("doi",""),
                "title": best.get("title",""),
                "year": best.get("year",""),
                "journal": best.get("journal",""),
                "primary_pillar": best.get("pillar",""),
                "best_method": best.get("method",""),
                "confidence": float(best.get("confidence",0.0)),
                "all_pillars": all_pillars,
                "methods_present": methods_present,
                "cited_by_reviews": cited_by,
                "rule_hits": self.debug_hits.get(k, "")
            })
        per_df = pd.DataFrame(per_rows)
        per_csv = self.out_dir / "per_paper_primary_pillar.csv"
        per_df.to_csv(per_csv, index=False)
        print(f"[ok] wrote: {per_csv}")

        # ===== NEW: review × pillar coverage =====
        cover_counts = defaultdict(int)
        for _, row in df.iterrows():
            pillar = row.get("pillar","")
            cites = (row.get("cited_by_reviews") or "").split(";")
            for rv in cites:
                rv2 = rv.strip()
                if rv2:
                    cover_counts[(rv2, pillar)] += 1
        if cover_counts:
            rows = [{"review_id":rv, "pillar":pl, "count":ct} for (rv,pl), ct in cover_counts.items()]
            cov_df = pd.DataFrame(rows)
            cov_pivot = cov_df.pivot_table(index="review_id", columns="pillar", values="count", fill_value=0, aggfunc="sum")
            cov_csv = self.out_dir / "by_review_pillar_coverage.csv"
            cov_pivot.to_csv(cov_csv)
            print(f"[ok] wrote: {cov_csv}")

        # ===== NEW: audit sample (top 20 per primary pillar) =====
        audit_rows = []
        if not per_df.empty:
            for pname in sorted(set(per_df["primary_pillar"].dropna().tolist()),
                                key=lambda x: self.num_by_name.get(x, 999)):
                sub = per_df[per_df["primary_pillar"] == pname].sort_values("confidence", ascending=False).head(20)
                audit_rows.extend(sub.to_dict(orient="records"))
        if audit_rows:
            audit_df = pd.DataFrame(audit_rows)
            audit_csv = self.out_dir / "audit_sample.csv"
            audit_df.to_csv(audit_csv, index=False)
            print(f"[ok] wrote: {audit_csv}")

    # ---------- run ----------
    def run(self):
        print("[1/5] Loading bibliographies…")
        bib_df = self.load_bibliographies()
        if bib_df.empty:
            print("No bibliographies found. Abort.")
            return

        print(f"  -> {len(bib_df)} unique papers after dedupe")
        print("[2/5] Section-based classification…")
        sec_map = self.classify_by_sections()

        print("[3/5] Paper-level classification…")
        # Add section-only keys for enhanced scoring (FILTERED)
        extra_rows = []
        known_keys = set(bib_df["key"].tolist())
        for key, v in sec_map.items():
            if key in known_keys:
                continue
            samp = v.get("sample") or {}
            doi = normalize_doi(samp.get("doi") or "")
            if not doi or v.get("confidence", 0.0) < 0.70:
                continue
            extra_rows.append({
                "key": key,
                "doi": doi,
                "title": samp.get("title") or "",
                "authors": samp.get("authors", []) or [],
                "journal": samp.get("journal", "") or "",
                "year": samp.get("year"),
                "raw_citation": samp.get("raw_citation") or "",
                "cited_by_reviews": ";".join(sorted({x["review_id"] for x in v.get("sections_used", [])})) if v.get("sections_used") else ""
            })
        if extra_rows:
            extra_df = pd.DataFrame(extra_rows, columns=bib_df.columns)
            bib_df = pd.concat([bib_df, extra_df], ignore_index=True)
            print(f"  -> added {len(extra_rows)} high-confidence section-only papers for enhanced scoring")

        # Warm cache
        all_dois = [normalize_doi(d) for d in bib_df["doi"].tolist() if d]
        if all_dois:
            self.prefetch_metadata_batch(all_dois, workers=12)

        pap_map = self.classify_papers(bib_df)

        print("[4/5] Reconciling…")
        combined = self.combine(bib_df, sec_map, pap_map)

        print("[5/5] Writing outputs…")
        self.write_outputs(combined)
        print("✅ Done.")

def main():
    # Script dir (backbone)
    script_dir = Path(__file__).parent
    pillar_dir = script_dir / "pillars"
    backbone_dir = script_dir

    DEFAULT_CACHE = Path("/Users/glenn/Documents/SecondBrain/_PROTOTYPE/literature/core_output/metadata_cache.json")


    # Find definition
    definition_candidates = [
        pillar_dir / "definition.md",
        pillar_dir / "Definition.md", 
        pillar_dir / "DEFINITION.md"
    ]
    default_definition = next((c for c in definition_candidates if c.exists()), pillar_dir / "definition.md")

    # Find reviews
    review_candidates = [backbone_dir / "core_reviews", backbone_dir / "reviews"]
    default_reviews = next((c for c in review_candidates if c.exists()), backbone_dir / "core_reviews")

    # Rules YAML (optional)
    default_rules_yaml = pillar_dir / "rules.yaml"

    print(f"[debug] Script dir: {script_dir}")
    print(f"[debug] Pillar dir: {pillar_dir}")
    print(f"[debug] Using definition: {default_definition}")
    print(f"[debug] Using reviews: {default_reviews}")
    print(f"[debug] Rules YAML: {default_rules_yaml}")

    ap = argparse.ArgumentParser()
    ap.add_argument("--pillar-md", type=Path, default=default_definition)
    ap.add_argument("--review-root", type=Path, default=default_reviews)

    # Default output = ../literature/core_output relative to script
    default_output = (script_dir.parent / "literature/core_output").resolve()
    ap.add_argument("--output-dir", type=Path, default=default_output,
        help="Output directory for classifier results")



    ap.add_argument("--cache-file", type=Path, default=DEFAULT_CACHE,
        help="Path to JSON cache file for abstracts/metadata")
    ap.add_argument("--allow-multi", action="store_true", help="Allow up to 2 pillars per paper when close")
    ap.add_argument("--confidence-threshold", type=float, default=0.75, help="Strong-signal threshold")
    ap.add_argument("--fetch-abstracts", action="store_true", default=True,
        help="Fetch abstracts from Crossref/Semantic Scholar with caching")
    ap.add_argument("--no-abstracts", dest="fetch_abstracts", action="store_false",
        help="Disable abstract fetching (titles only)")
    ap.add_argument("--fetch-full-articles", action="store_true", default=False,
        help="Attempt to fetch full article content when available")
    ap.add_argument("--limit-papers", type=int, default=0, help="Limit #unique papers (0 = all)")
    ap.add_argument("--limit-sections", type=int, default=0, help="Limit #section files (0 = all)")
    ap.add_argument("--section-chars", type=int, default=2000,
        help="Number of characters from section body to use for scoring")
    ap.add_argument("--rules-yaml", type=Path, default=default_rules_yaml,
        help="Path to rules.yaml (optional). If absent, built-in rules are used.")
    args = ap.parse_args()

    args.output_dir.mkdir(parents=True, exist_ok=True)

    clf = CombinedClassifier(
        pillar_md=args.pillar_md,
        review_root=args.review_root,
        out_dir=args.output_dir,
        allow_multi=args.allow_multi,
        conf_th=args.confidence_threshold,
        fetch_abstracts=args.fetch_abstracts,
        limit_papers=args.limit_papers,
        limit_sections=args.limit_sections,
        cache_file=args.cache_file,
        section_chars=args.section_chars,
        fetch_full_articles=args.fetch_full_articles,
        rules_yaml=args.rules_yaml
    )
    clf.run()

if __name__ == "__main__":
    main()
