"""Editor-controlled pages, section visibility and navigation."""
import json
import re
import unicodedata
from html import unescape
from urllib.parse import unquote, urlsplit

DEFAULT_SECTIONS = {
    'about': ('About', 'about.html', True),
    'members': ('Community', 'members.html', True),
    'events': ('Events', 'events.html', True),
    'stories': ('Stories', 'stories.html', True),
    'resources': ('Resources', 'resources.html', True),
    'news': ('News & letters', 'news.html', False),
    'archive': ('Newsletters & archive', 'archive.html', False),
    'contact': ('Contact', 'contact.html', False),
}


def address(value):
    value = unicodedata.normalize('NFKD', value).encode('ascii', 'ignore').decode().lower()
    return re.sub(r'[^a-z0-9]+', '-', value).strip('-')[:145]


class PageManager:
    def __init__(self, root):
        self.sections = {}
        self.owners = {'seri-letter.html': 'news', 'accreditation-initiative.html': 'archive'}
        for i, (name, (label, file, in_menu)) in enumerate(DEFAULT_SECTIONS.items(), 1):
            item = {'title': label, 'enabled': True, 'menuLabel': label, 'file': file,
                    'showInMenu': in_menu, 'showInFooter': name != 'contact', 'order': i * 10}
            source = root / 'content/sections' / (name + '.json')
            if source.exists():
                item.update(json.loads(source.read_text()))
            item['file'] = file
            self.sections[name] = item
            self.owners[file] = name
        self.pages = []
        self.published = set()
        addresses = set()
        for source in sorted((root / 'content/pages').glob('*.json')):
            item = json.loads(source.read_text())
            stem = address(source.stem)
            if not stem:
                raise ValueError('Page needs a readable filename: ' + source.name)
            file = 'page-' + stem + '.html'
            if file in addresses:
                raise ValueError('Duplicate page address: ' + file)
            addresses.add(file)
            item['file'] = file
            if item.get('published', False):
                if not str(item.get('title', '')).strip():
                    raise ValueError('Published page needs a title: ' + source.name)
                self.pages.append(item)
                self.published.add(file)

    def enabled(self, section):
        return self.sections[section]['enabled']

    def allows(self, file):
        file = unquote(urlsplit(file).path).removeprefix('/500ws/').removeprefix('./')
        if file.startswith('page-'):
            return file in self.published
        owner = self.owners.get(file)
        for prefix, section in [('member-', 'members'), ('event-', 'events'),
                                ('story-', 'stories'), ('news-', 'news')]:
            if file.startswith(prefix) and file.endswith('.html'):
                owner = section
        return self.enabled(owner) if owner else True

    def navigation(self, field):
        items = [item for item in self.sections.values() if item['enabled']] + self.pages
        items = [item for item in items if item.get(field, False)]
        items.sort(key=lambda item: (float(item['order']) if item.get('order') is not None else 100, item['file']))
        return [(item.get('menuLabel') or item['title'], item['file']) for item in items]

    def remove_unavailable_links(self, markup):
        def replace(match):
            opening, href, content = match.groups()
            parsed = urlsplit(unescape(href))
            if parsed.scheme or parsed.netloc or self.allows(href):
                return match.group(0)
            # Remove obsolete controls; keep historical prose readable without a dead link.
            if re.search(r'class="[^"]*\b(btn|text-link|filter|breadcrumb|round-link)\b', opening):
                return ''
            return content
        return re.sub(r'(<a\b[^>]*href="([^"]*)"[^>]*>)(.*?)</a>', replace, markup, flags=re.S)
