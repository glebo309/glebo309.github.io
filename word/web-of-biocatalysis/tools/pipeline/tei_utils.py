from lxml import etree

NS = {"tei": "http://www.tei-c.org/ns/1.0"}

def parse_tei(tei_xml: str):
    return etree.fromstring(tei_xml.encode("utf-8"))

def get_title(root) -> str:
    t = root.xpath("//tei:fileDesc/tei:titleStmt/tei:title/text()", namespaces=NS)
    return " ".join(t).strip()

def get_abstract(root) -> str:
    parts = root.xpath("//tei:profileDesc/tei:abstract//text()", namespaces=NS)
    return " ".join(parts).strip()

def get_body_text(root, max_chars: int = 12000) -> str:
    chunks = root.xpath("//tei:text//tei:body//text()", namespaces=NS)
    text = " ".join(" ".join(chunks).split())
    return text[:max_chars]

def get_references(root, max_n: int = 50):
    bibs = root.xpath("//tei:listBibl//tei:biblStruct", namespaces=NS)
    out = []
    for b in bibs[:max_n]:
        doi = b.xpath(".//tei:idno[@type='DOI']/text()", namespaces=NS)
        title = b.xpath(".//tei:title/text()", namespaces=NS)
        year = b.xpath(".//tei:date/@when", namespaces=NS)
        out.append({
            "doi": (doi[0].lower() if doi else ""),
            "title": (title[0] if title else ""),
            "year": int(year[0][:4]) if year and year[0][:4].isdigit() else None
        })
    return out
