"""Load editor content and allow safe, portable article markup."""
from html import escape
from html.parser import HTMLParser
from pathlib import Path
from urllib.parse import urlsplit
import json
import re

def portable_url(value):
    value = str(value or '').strip()
    for prefix in ('/500ws/assets/', '/assets/'):
        if value.startswith(prefix):
            return 'assets/' + value[len(prefix):]
    return value

def safe_url(value):
    value = portable_url(value)
    compact = re.sub(r'[\x00-\x20\x7f]', '', value)
    return value if urlsplit(compact).scheme.lower() in ('', 'https', 'http', 'mailto', 'tel') else ''

class ArticleHTML(HTMLParser):
    tags = {'p','br','h2','h3','h4','h5','h6','strong','b','em','i','u','s','sup','sub',
            'ul','ol','li','blockquote','a','img','figure','figcaption','hr','table','thead',
            'tbody','tr','th','td','span','div','pre','code'}
    void = {'br','img','hr'}
    blocked = {'script','style','iframe','object','embed','svg','math','form'}

    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.output = []
        self.blocked_depth = 0

    def handle_starttag(self, tag, attrs):
        if tag in self.blocked:
            self.blocked_depth += 1
        if self.blocked_depth or tag not in self.tags:
            return
        clean = []
        for name, value in attrs:
            if name in ('href','src'):
                value = safe_url(value)
                if value:
                    clean.append((name,value))
            elif name in ('alt','title','colspan','rowspan'):
                clean.append((name,value or ''))
        attributes = ''.join(f' {k}="{escape(v, quote=True)}"' for k,v in clean)
        self.output.append(f'<{tag}{attributes}>')

    def handle_startendtag(self, tag, attrs):
        self.handle_starttag(tag, attrs)
        if tag not in self.void:
            self.handle_endtag(tag)

    def handle_endtag(self, tag):
        if tag in self.blocked:
            self.blocked_depth = max(0, self.blocked_depth - 1)
            return
        if not self.blocked_depth and tag in self.tags and tag not in self.void:
            self.output.append(f'</{tag}>')

    def handle_data(self, data):
        if not self.blocked_depth:
            self.output.append(escape(data))

def clean_html(value):
    parser = ArticleHTML()
    parser.feed(value or '')
    return ''.join(parser.output)

def load_content(root):
    root = Path(root)
    if not (root / 'content/site.json').exists():
        return json.loads((root / 'content.json').read_text())
    data = json.loads((root / 'content/site.json').read_text())
    for name in ('members','posts','events','news'):
        data[name] = []
        for path in sorted((root / 'content' / name).glob('*.json')):
            item = json.loads(path.read_text())
            for field in ('image','url'):
                if field in item:
                    item[field] = safe_url(item[field])
            data[name].append(item)
    def normalize(value):
        if isinstance(value, dict):
            return {key: normalize(item) for key, item in value.items()}
        if isinstance(value, list):
            return [normalize(item) for item in value]
        return portable_url(value) if isinstance(value, str) else value
    return normalize(data)
