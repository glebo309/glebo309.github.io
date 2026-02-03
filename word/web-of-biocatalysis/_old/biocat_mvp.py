#!/usr/bin/env python3
import os, re, json, time, datetime, requests, argparse, traceback
from pathlib import Path
from pypdf import PdfReader

# ---------- CLI ----------
parser = argparse.ArgumentParser()
parser.add_argument("--papers", default="./papers", help="Folder with local PDFs")
parser.add_argument("--out", default="./output", help="Folder under _PROTOTYPE where results will be saved")
parser.add_argument("--model", default="qwen3:4b", help="Ollama model name (e.g. qwen3:4b, qwen2.5:7b, deepseek-r1:7b)")
parser.add_argument("--max_chars", type=int, default=6000, help="Max chars to send to model")
parser.add_argument("--pages", type=int, default=10, help="How many PDF pages to read")
parser.add_argument("--skip_existing", action="store_true", help="Skip PDFs that already have a note")
args = parser.parse_args()

# ---------- CONFIG ----------
PAPERS_DIR = Path(args.papers)
BASE_DIR   = Path(args.out)
PAPERS_OUT = BASE_DIR / "Papers"
TOPICS_OUT = BASE_DIR / "Topics"
NEWS_OUT   = BASE_DIR / "News"
MODEL      = args.model
MAX_CHARS  = args.max_chars
PAGES_READ = max(1, args.pages)
TIMEOUT_S  = 180

# Topic scaffold (word-boundary matching; no "adh" to avoid NADH false hits)
TOPICS = [
    {"name": "Transaminases", "keywords": ["transaminase","aminotransferase","ata","ec 2.6.1"]},
    {"name": "Ketoreductases", "keywords": ["ketoreductase","alcohol dehydrogenase"]},
    {"name": "Oxidases/Monooxygenases", "keywords": ["monooxygenase","p450","baeyer-villiger","oxidase"]},
    {"name": "Hydrolases", "keywords": ["lipase","esterase","amidase","protease"]},
    {"name": "Flow Biocatalysis", "keywords": ["flow","continuous","packed-bed","microreactor"]},
    {"name": "Immobilization", "keywords": ["immobilized","support","resin","carrier","agarose","boronic"]},
    {"name": "Cofactor Recycling", "keywords": ["nadh","nadph","atp regeneration","cofactor recycling"]},
    {"name": "Chemoenzymatic Cascades", "keywords": ["cascade","one-pot","tandem","dual catalysis"]},
    {"name": "Engineering & ML", "keywords": ["directed evolution","mutagenesis","machine learning","computational design","rosetta"]},
    {"name": "Photobiocatalysis/Electrobiocatalysis", "keywords": ["photoenzyme","light-driven","electroenzymatic","photobiocatalysis","electrobiocatalysis"]},
]

# ---------- Helpers ----------
def ensure_dirs():
    PAPERS_OUT.mkdir(parents=True, exist_ok=True)
    TOPICS_OUT.mkdir(parents=True, exist_ok=True)
    NEWS_OUT.mkdir(parents=True, exist_ok=True)

def read_pdf_text(path: Path) -> str:
    try:
        reader = PdfReader(str(path))
        texts = []
        for page in reader.pages[:PAGES_READ]:
            t = page.extract_text() or ""
            texts.append(t)
        return "\n".join(texts)
    except Exception as e:
        print(f"[warn] PDF read failed for {path.name}: {e}")
        return ""

def guess_title(pdf_text: str, fallback: str) -> str:
    for line in pdf_text.splitlines():
        s = line.strip()
        if len(s) >= 10 and not s.lower().startswith(("abstract","introduction","supplementary")):
            if not re.search(r"^\d+$", s) and len(s.split()) >= 3:
                return s
    name = Path(fallback).stem.replace("_"," ").replace("-"," ")
    return re.sub(r"\s+", " ", name).strip().title()

def _kw_hit(text: str, kw: str) -> bool:
    # Enable word-boundaries and allow hyphen/space variation inside kw
    pattern = r'\b' + re.escape(kw).replace(r'\-', r'[-\s]') + r'\b'
    return re.search(pattern, text, flags=re.I) is not None

def classify_topics(text: str) -> list:
    hits = []
    for t in TOPICS:
        if any(_kw_hit(text, kw) for kw in t["keywords"]):
            hits.append(t["name"])
    return hits[:2] or ["Unclassified"]

def slugify(name: str) -> str:
    s = re.sub(r"[^\w\s-]", "", name).strip().lower()
    s = re.sub(r"[\s_-]+", "-", s)
    return s[:80] if len(s)>80 else s

def ollama_summarize(text: str) -> dict:
    prompt = (
        "You are a biocatalysis expert. Using ONLY the text below, return STRICT JSON with keys:\n"
        "tldr: array(2-3 short bullets, total <= 40 words),\n"
        "what: string (3-5 sentences),\n"
        "why: string (2-3 sentences),\n"
        "limits: array(0-3 bullets).\n"
        "If info is missing, write 'Not stated'. Do not add any extra keys or commentary.\n\n"
        f"---TEXT START---\n{text[:MAX_CHARS]}\n---TEXT END---"
    )
    payload = {
        "model": MODEL,
        "prompt": prompt,
        "stream": False,
        "format": "json",
        "options": {"temperature": 0.1, "num_ctx": 3072, "num_predict": 320}
    }
    try:
        r = requests.post("http://localhost:11434/api/generate", json=payload, timeout=TIMEOUT_S)
        r.raise_for_status()
        raw = r.json().get("response", "").strip()
        data = json.loads(raw)
        return {
            "tldr": data.get("tldr", [])[:3],
            "what": (data.get("what") or "Not stated").strip(),
            "why": (data.get("why") or "Not stated").strip(),
            "limits": data.get("limits", [])[:3],
        }
    except Exception:
        # Fallback: try to salvage JSON from free-form output
        try:
            fallback_payload = dict(payload)
            fallback_payload.pop("format", None)
            rr = requests.post("http://localhost:11434/api/generate", json=fallback_payload, timeout=TIMEOUT_S)
            rr.raise_for_status()
            out = rr.json().get("response", "").strip()
            m = re.search(r"\{.*\}", out, re.S)
            if not m:
                return {"tldr":["Not stated"], "what":"Not stated", "why":"Not stated", "limits":[]}
            data = json.loads(m.group(0))
            return {
                "tldr": data.get("tldr", [])[:3],
                "what": (data.get("what") or "Not stated").strip(),
                "why": (data.get("why") or "Not stated").strip(),
                "limits": data.get("limits", [])[:3],
            }
        except Exception:
            return {"tldr":["Not stated"], "what":"Not stated", "why":"Not stated", "limits":[]}

def write_paper_md(title, topics, src_path: Path, summary: dict):
    date = datetime.date.today().isoformat()
    slug = slugify(title)
    md_path = PAPERS_OUT / f"{slug}.md"
    safe_title = title.replace('"', "'")
    yaml = [
        "---",
        f'title: "{safe_title}"',
        f'date: "{date}"',
        f'topics: {json.dumps(topics)}',
        f'source: "{src_path.as_posix()}"',
        "---",
        ""
    ]
    tldr_lines = "\n".join([f"- {b}" for b in summary.get("tldr",[])]) or "- —"
    limits = summary.get("limits",[])
    lim_lines = "\n".join([f"- {b}" for b in limits]) if limits else "- —"
    body = f"""### TL;DR
{tldr_lines}

### What they did
{summary.get("what","Not stated")}

### Why it matters
{summary.get("why","Not stated")}

### Limitations
{lim_lines}
"""
    md_path.write_text("\n".join(yaml) + body, encoding="utf-8")
    return md_path, slug, date

def update_news(slug: str, title: str, date_iso: str, topics: list):
    path = NEWS_OUT / "index.md"
    if not path.exists():
        path.write_text("# Biocatalysis — Latest\n\n", encoding="utf-8")
    txt = path.read_text(encoding="utf-8")

    # Remove any existing line for this slug (dedupe)
    txt = re.sub(rf"^- .*?\[\[Papers/{re.escape(slug)}\|.*?\]\].*$\n?", "", txt, flags=re.M)

    # Insert new entry after header
    entry = f"- {date_iso} — [[Papers/{slug}|{title}]] ({', '.join(topics[:2])})\n"
    if "# Biocatalysis — Latest" in txt:
        parts = txt.split("\n", 2)
        if len(parts) >= 2:
            txt = parts[0] + "\n" + parts[1] + "\n" + entry + (parts[2] if len(parts) == 3 else "")
    else:
        txt = "# Biocatalysis — Latest\n\n" + entry

    # Trim to ~200 lines to keep file small
    lines = txt.splitlines()
    txt = "\n".join(lines[:200]) + "\n"
    path.write_text(txt, encoding="utf-8")

def first_sentence(text: str) -> str:
    s = re.split(r"(?<=[.!?])\s+", (text or "").strip())
    return s[0][:180] if s else "—"

def append_topic_links(topics: list, slug: str, one_liner: str):
    for t in topics:
        path = TOPICS_OUT / f"{t}.md"
        if not path.exists():
            path.write_text(f"# {t}\n\n## New this week\n", encoding="utf-8")
        txt = path.read_text(encoding="utf-8")

        # Remove any previous line for this slug (dedupe even if one-liner changed)
        txt = re.sub(rf"^- \[\[Papers/{re.escape(slug)}\]\].*$\n?", "", txt, flags=re.M)

        if "## New this week" not in txt:
            txt += "\n## New this week\n"
        txt += f"- [[Papers/{slug}]] — {one_liner}\n"
        path.write_text(txt, encoding="utf-8")

def process_pdf(pdf_path: Path):
    txt = read_pdf_text(pdf_path)
    print(f"[debug] {pdf_path.name}: extracted {len(txt)} chars. Preview:\n{txt[:500]}\n---")

    if not txt.strip():
        print(f"[skip] No text: {pdf_path.name}")
        return

    title = guess_title(txt, pdf_path.name)
    slug  = slugify(title)

    if args.skip_existing and (PAPERS_OUT / f"{slug}.md").exists():
        print(f"[skip] Already processed: {slug}")
        return

    topics = classify_topics(txt)
    print(f"[+] {pdf_path.name} → '{title}' | topics: {topics}")

    summ = ollama_summarize(txt)
    print(f"  [debug] Summary obtained: tldr={len(summ.get('tldr',[]))} items")

    md_path, slug, date_iso = write_paper_md(title, topics, pdf_path, summ)
    print(f"  [debug] MD written to {md_path}")

    one_liner = first_sentence(summ.get("why") or summ.get("what") or title)
    append_topic_links(topics, slug, one_liner)
    print(f"  [debug] Topic links appended")

    update_news(slug, title, date_iso, topics)
    print(f"  [debug] News updated")
    print(f"    -> completed {md_path}")

def main():
    ensure_dirs()
    pdfs = sorted(PAPERS_DIR.glob("*.pdf"))
    if not pdfs:
        print(f"Put some PDFs into {PAPERS_DIR} and rerun.")
        return
    for p in pdfs:
        try:
            process_pdf(p)
            time.sleep(0.3)
        except requests.exceptions.ConnectionError:
            print("ERROR: Ollama not running? Start with `ollama serve &`")
            break
        except Exception as e:
            print(f"[err] {p.name}: {e}")
            traceback.print_exc()

if __name__ == "__main__":
    main()
