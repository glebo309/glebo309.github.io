import pathlib
import subprocess
import sys
import tempfile
import unittest


CHECK = pathlib.Path(__file__).with_name('publication_safety.py')


class PublicationSafetyTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = pathlib.Path(self.temp.name) / 'site'
        self.root.mkdir()
        subprocess.run(['git', 'init', '-q', str(self.root)], check=True)

    def put(self, name, content=b'public content'):
        path = self.root / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(content)
        return path

    def run_check(self, *args):
        return subprocess.run([sys.executable, str(CHECK), str(self.root), *args],
                              capture_output=True, text=True)

    def test_rejects_runtime_and_authentication_files(self):
        for name in ['word/web-of-biocatalysis/PAPER_DOWNLOADER/config.yaml',
                     'word/web-of-biocatalysis/PAPER_DOWNLOADER-copy/src/tool.py',
                     'elsewhere/login.session', 'elsewhere/login.session-journal',
                     'browser_state.json', '.env.production', 'private/draft.html']:
            with self.subTest(name=name):
                path = self.put(name)
                result = self.run_check()
                self.assertEqual(result.returncode, 1, result.stderr)
                self.assertIn(name, result.stdout)
                path.unlink()

    def test_allows_public_assets_and_placeholder_configuration(self):
        self.put('index.html', b'<h1>Glecko</h1>')
        self.put('word/article.html')
        self.put('config.yaml.example', b'api_hash: YOUR_API_HASH')
        self.assertEqual(self.run_check().returncode, 0)

    def test_checks_staged_content_and_never_prints_credential(self):
        secret = 'a' * 32
        path = self.put('settings.yaml', ('api_hash: ' + secret).encode())
        subprocess.run(['git', '-C', str(self.root), 'add', 'settings.yaml'], check=True)
        path.write_text('api_hash: YOUR_API_HASH')
        result = self.run_check('--staged')
        self.assertEqual(result.returncode, 1, result.stderr)
        self.assertIn('settings.yaml', result.stdout)
        self.assertNotIn(secret, result.stdout + result.stderr)

    def test_quarantine_preserves_original_and_leaves_public_content(self):
        original = self.put('cache/login.session', b'private-session-bytes')
        self.put('index.html', b'public')
        destination = pathlib.Path(self.temp.name) / 'quarantine'
        result = self.run_check('--quarantine', str(destination))
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertFalse(original.exists())
        self.assertEqual((destination / 'cache/login.session').read_bytes(), b'private-session-bytes')
        self.assertTrue((self.root / 'index.html').exists())

    def test_checks_pushed_commit_even_when_index_has_removed_the_file(self):
        self.put('login.session')
        subprocess.run(['git', '-C', str(self.root), 'add', 'login.session'], check=True)
        subprocess.run(['git', '-C', str(self.root), '-c', 'user.name=Test',
                        '-c', 'user.email=test@example.invalid', 'commit', '-qm', 'Fixture'], check=True)
        subprocess.run(['git', '-C', str(self.root), 'rm', '-q', 'login.session'], check=True)
        result = self.run_check('--revision', 'HEAD')
        self.assertEqual(result.returncode, 1, result.stderr)
        self.assertIn('login.session', result.stdout)


if __name__ == '__main__':
    unittest.main()
