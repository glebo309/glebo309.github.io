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
                 'category': 'Workshop', 'location': 'Bern', 'bodyHtml': '<p>Bring your ideas.</p>'}
        self.write('content/events/editor-workshop.json', event)
        self.build()
        page = self.root / 'event-2030-02-14-editor-workshop.html'
        self.assertTrue(page.exists(), 'New editor entries must be published')
        self.assertIn('Editor workshop', (self.root / 'events.html').read_text())
        (self.root / 'content/events/editor-workshop.json').unlink()
        self.build()
        self.assertFalse(page.exists(), 'Deleted editor entries must not leave live pages')

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

if __name__ == '__main__':
    unittest.main()
