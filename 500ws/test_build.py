"""Publishing regressions, using temporary copies of the real website."""
import json
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import unittest

ROOT = Path(__file__).resolve().parent
COLLECTIONS = ('members', 'posts', 'events', 'news')

class PublishingTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        for source in ROOT.glob('*.py'):
            shutil.copy(source, self.root / source.name)
        (self.root / 'assets').mkdir()
        if (ROOT / 'content').exists():
            shutil.copytree(ROOT / 'content', self.root / 'content')
            # Each test controls visibility and custom pages independently of live edits.
            for name in ('sections', 'pages'):
                shutil.rmtree(self.root / 'content' / name, ignore_errors=True)
        else:
            data = json.loads((ROOT / 'content.json').read_text())
            shutil.copy(ROOT / 'content.json', self.root / 'content.json')
            for name in COLLECTIONS:
                for i, item in enumerate(data.pop(name)):
                    self.write(f'content/{name}/{i}.json', item)
            self.write('content/site.json', data)

    def write(self, path, data):
        path = self.root / path
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(data))

    def build(self):
        subprocess.run([sys.executable, str(self.root / 'build.py')], check=True, capture_output=True)

    def test_editor_adds_and_removes_event_without_stale_page(self):
        event = {'title': 'Editor workshop', 'slug': 'editor-workshop', 'date': '2030-02-14',
                 'category': 'Workshop', 'location': 'Bern', 'bodyHtml': '<p>Bring your ideas.</p>',
                 'source': 'https://www.500womenscientistsfribourgbern.ch/upcoming-events/editor-workshop'}
        self.write('content/events/editor-workshop.json', event)
        self.build()
        page = self.root / 'event-2030-02-14-editor-workshop.html'
        self.assertTrue(page.exists(), 'New editor entries must be published')
        self.assertIn('Editor workshop', (self.root / 'events.html').read_text())
        (self.root / 'content/events/editor-workshop.json').unlink()
        self.build()
        self.assertFalse(page.exists(), 'Deleted editor entries must not leave live pages')
        self.assertFalse((self.root / 'upcoming-events/editor-workshop/index.html').exists(),
                         'Deleted entries must not leave redirects to missing pages')

    def test_editor_changes_about_copy_and_normalizes_uploaded_image(self):
        site_path = self.root / 'content/site.json'
        data = json.loads(site_path.read_text())
        data['pageContent']['aboutHtml'] = '<p>A changed introduction from the board.</p>'
        self.write('content/site.json', data)
        self.write('content/posts/new-story.json', {'title': 'New story', 'slug': 'new-story',
            'date': '2026-11-07', 'author': 'The board', 'image': '/500ws/assets/photo.webp',
            'bodyHtml': '<p>A new story.</p><img src="/500ws/assets/second.webp" alt="A gathering">'})
        self.build()
        self.assertIn('A changed introduction from the board.', (self.root / 'about.html').read_text())
        story = (self.root / 'story-new-story.html').read_text()
        self.assertIn('src="assets/photo.webp"', story)
        self.assertIn('src="assets/second.webp"', story)

    def test_formatted_content_cannot_embed_scripts_or_unsafe_links(self):
        self.write('content/posts/security.json', {'title': 'Safe article', 'slug': 'security',
            'date': '2026-11-07', 'author': 'The board', 'bodyHtml':
            '<p>Keep this text.</p><script>alert(123)</script><img src="assets/photo.webp" onerror="alert(456)">'
            '<a href="javascript:alert(789)">Unsafe link</a><a href="https://example.org/">Useful link</a>'})
        self.build()
        story = (self.root / 'story-security.html').read_text()
        self.assertIn('Keep this text.', story)
        self.assertIn('https://example.org/', story)
        self.assertNotIn('alert(', story)
        self.assertNotIn('onerror=', story)

    def test_custom_pages_publish_reorder_unpublish_and_delete(self):
        item = {'title': 'Our projects', 'introduction': 'Research together.',
                'bodyHtml': '<p>Project details.</p><script>alert(1)</script>',
                'image': '/500ws/assets/projects.webp', 'imageAlt': 'Working together',
                'published': True, 'showInMenu': True, 'showInFooter': True,
                'menuLabel': 'Projects', 'order': 5}
        self.write('content/pages/projects.json', item)
        self.build()
        target = self.root / 'page-projects.html'
        self.assertTrue(target.exists())
        self.assertIn('Project details.', target.read_text())
        self.assertIn('src="assets/projects.webp"', target.read_text())
        self.assertNotIn('alert(1)', target.read_text())
        home = (self.root / 'index.html').read_text()
        self.assertLess(home.index('href="page-projects.html"'), home.index('href="about.html"'))
        self.assertIn('Projects</a>', home)
        item['title'] = 'Projects and partnerships'
        self.write('content/pages/projects.json', item)
        self.build()
        self.assertIn('Projects and partnerships', target.read_text())
        item['published'] = False
        self.write('content/pages/projects.json', item)
        self.build()
        self.assertFalse(target.exists())
        self.assertNotIn('href="page-projects.html"', (self.root / 'index.html').read_text())
        item['published'] = True
        self.write('content/pages/projects.json', item)
        self.build()
        (self.root / 'content/pages/projects.json').unlink()
        self.build()
        self.assertFalse(target.exists())

    def test_section_switch_removes_pages_links_and_redirects_then_restores(self):
        self.write('content/events/section-check.json', {'title': 'Section check', 'date': '2030-03-01',
            'category': 'Workshop', 'bodyHtml': '<p>Community workshop.</p>'})
        self.build()
        original_events = sorted(self.root.glob('event-*.html'))
        self.assertTrue(original_events)
        self.write('content/sections/events.json', {'enabled': False})
        self.build()
        self.assertFalse((self.root / 'events.html').exists())
        self.assertFalse(list(self.root.glob('event-*.html')))
        self.assertFalse((self.root / 'events/index.html').exists())
        self.assertTrue(list((self.root / 'content/events').glob('*.json')))
        home = (self.root / 'index.html').read_text()
        self.assertNotIn('Explore our events', home)
        for page in self.root.glob('*.html'):
            self.assertNotIn('href="events.html', page.read_text(), page.name)
            self.assertNotIn('href="event-', page.read_text(), page.name)
        self.write('content/sections/events.json', {'enabled': True, 'menuLabel': 'Gatherings',
                                                  'showInMenu': True, 'order': 1})
        self.build()
        self.assertTrue((self.root / 'events.html').exists())
        self.assertEqual(len(original_events), len(list(self.root.glob('event-*.html'))))
        self.assertIn('Gatherings</a>', (self.root / 'index.html').read_text())

    def test_all_optional_sections_can_be_hidden(self):
        for name in ('about', 'members', 'events', 'stories', 'news', 'resources', 'archive', 'contact'):
            self.write(f'content/sections/{name}.json', {'enabled': False})
        self.build()
        self.assertEqual({'index.html', '404.html'}, {p.name for p in self.root.glob('*.html')})
        home = (self.root / 'index.html').read_text()
        self.assertIn('mailto:500wsbern@gmail.com', home)
        self.assertNotIn('Voices from our community.', home)

    def test_colliding_custom_addresses_fail_before_changing_public_pages(self):
        self.build()
        before = (self.root / 'index.html').read_text()
        self.write('content/pages/project one.json', {'title': 'One', 'published': True})
        self.write('content/pages/project-one.json', {'title': 'Two', 'published': True})
        result = subprocess.run([sys.executable, str(self.root / 'build.py')], capture_output=True)
        self.assertNotEqual(0, result.returncode)
        self.assertIn('Duplicate page address', result.stderr.decode())
        self.assertEqual(before, (self.root / 'index.html').read_text())

    def test_menu_order_zero_comes_first(self):
        self.write('content/sections/events.json', {'enabled': True, 'order': 0})
        self.build()
        home = (self.root / 'index.html').read_text()
        self.assertLess(home.index('href="events.html"'), home.index('href="about.html"'))

if __name__ == '__main__':
    unittest.main()
