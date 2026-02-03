import json, requests

def _ollama_generate(host: str, model: str, prompt: str, temperature: float = 0.0) -> str:
    url = f"{host.rstrip('/')}/api/generate"
    payload = {"model": model, "prompt": prompt, "stream": False, "options": {"temperature": temperature}}
    r = requests.post(url, json=payload, timeout=600)
    r.raise_for_status()
    j = r.json()
    return j.get("response","").strip()

def _pillar_hint_block(pillar: str) -> str:
    if not pillar: return ""
    return f"\nPILLAR CONTEXT: {pillar}\n"

def build_prompt(pillar: str, title: str, abstract: str, body_excerpt: str, max_chars: int) -> str:
    text = (title + "\n\n" + abstract + "\n\n" + body_excerpt)[:max_chars]
    schema = {
        "summary": "1-2 sentence plain-English take-away",
        "key_claims": ["short bullet points"],
        "process_signals": [
            {"name": "metric_name", "value": "number or string", "unit": "unit or ''", "context": "where/how measured"}
        ],
        "entities": {
            "enzymes": [],
            "reaction_types": [],
            "immobilization": [],
            "media": [],
            "reactor": []
        },
        "confidence": 0.0
    }
    prompt = f"""You are extracting structured, *process-relevant* information from a biocatalysis paper.
Return STRICT JSON only, matching this schema and field names exactly:
{json.dumps(schema, indent=2)}

Guidelines:
- Prefer claims with concrete numbers, conditions or comparisons.
- If no metric, return an empty list for process_signals.
- Populate entities when explicit (do not hallucinate).
- confidence in [0,1] reflecting how much the text supports the summary.

{_pillar_hint_block(pillar)}
TEXT:
\"\"\"{text}\"\"\"
JSON:"""
    return prompt

def run_extraction(ollama_host: str, model: str, pillar: str, title: str, abstract: str, body_excerpt: str, max_chars: int, temperature: float = 0.0):
    prompt = build_prompt(pillar, title, abstract, body_excerpt, max_chars)
    out = _ollama_generate(ollama_host, model, prompt, temperature=temperature)
    # best-effort json parse
    try:
        return json.loads(out)
    except Exception:
        # wrap if model printed junk
        try:
            s = out[out.index("{"):out.rindex("}")+1]
            return json.loads(s)
        except Exception:
            return {"summary": "", "key_claims": [], "process_signals": [], "entities": {}, "confidence": 0.0, "_raw": out[:2000]}
