"""Reject private runtime material before publishing the static website.

Check the worktree before staging and use --staged before committing.
--quarantine preserves rejected files outside the site. Never print secret values.
"""
import argparse
import pathlib
import re
import shutil
import subprocess


TELEGRAM_HASH = re.compile(
    rb"(?i)\b(?:telegram_)?api_hash[\"']?\s*[:=]\s*[\"']?[0-9a-f]{32}\b"
)


def path_reason(name):
    path = pathlib.PurePosixPath(name)
    if any(part.startswith('PAPER_DOWNLOADER') for part in path.parts):
        return 'runtime downloader copy'
    if 'private' in path.parts:
        return 'private content'
    if path.name.endswith(('.session', '.session-journal', '.session-wal', '.session-shm')):
        return 'authentication session'
    if path.name in ('browser_state.json', 'storage_state.json', 'cookies.txt', 'cookies.json'):
        return 'browser authentication state'
    if path.name == '.env' or (path.name.startswith('.env.') and not path.name.endswith('.example')):
        return 'environment credentials'
    return None


def git(root, *args):
    return subprocess.check_output(['git', '-C', str(root), *args])


def findings(root, staged, revision=None):
    args = ['ls-tree', '-rz', '--name-only', revision] if revision else ['ls-files', '-z', '--cached']
    if not staged and not revision:
        args += ['--others', '--exclude-standard']
    for raw in sorted(set(git(root, *args).split(b'\0'))):
        if not raw:
            continue
        name = raw.decode('utf-8', errors='surrogateescape')
        path = root / name
        if not staged and not revision and not path.exists():
            continue
        reason = path_reason(name)
        if not reason:
            if revision:
                content = git(root, 'show', revision + ':' + name)
            else:
                content = git(root, 'show', ':' + name) if staged else path.read_bytes()
            if TELEGRAM_HASH.search(content):
                reason = 'populated Telegram API hash'
        if reason:
            yield name, reason


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('root', nargs='?', default='.')
    selection = parser.add_mutually_exclusive_group()
    selection.add_argument('--staged', action='store_true')
    selection.add_argument('--revision')
    parser.add_argument('--quarantine', type=pathlib.Path)
    args = parser.parse_args()
    root = pathlib.Path(args.root).resolve()
    if args.quarantine:
        destination = args.quarantine.resolve()
        if args.staged or args.revision or destination.is_relative_to(root):
            parser.error('Quarantine must be outside the site and cannot operate on the index.')
        destination.mkdir(parents=True, exist_ok=False, mode=0o700)
    rejected = list(findings(root, args.staged, args.revision))
    for name, reason in rejected:
        print(f'{name}: {reason}')
        if args.quarantine:
            target = destination / name
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.move(str(root / name), target)
    if args.quarantine:
        print(f'Quarantined {len(rejected)} files outside the publication tree.')
        return 0
    if rejected:
        print(f'Publication blocked: {len(rejected)} files require review.')
        return 1
    print('Publication safety check passed.')
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
