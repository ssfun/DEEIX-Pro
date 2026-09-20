#!/usr/bin/env python3
"""Resolve a baseline or latest upstream release to an immutable source SHA."""
import argparse
import json
from pathlib import Path
import re
import subprocess
from urllib.parse import quote

ROOT = Path(__file__).resolve().parents[1]


def api(path):
    return json.loads(subprocess.check_output(['gh', 'api', path], text=True))


def resolve(manifest, latest=False, sha=None, tag=None):
    match = re.fullmatch(r'https://github\.com/([A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+)\.git', manifest['repository'])
    if not match:
        raise ValueError('upstream.json must specify a GitHub repository')
    repository = match.group(1)
    if latest:
        release = api(f'repos/{repository}/releases/latest')
        if release.get('draft') or release.get('prerelease'):
            raise ValueError('Expected a published stable release')
        tag = release['tag_name']
        # Resolve the actual tag, not target_commitish (which may be a moving branch).
        sha = api(f'repos/{repository}/commits/{quote(tag, safe="")}')['sha']
    elif bool(sha) != bool(tag):
        raise ValueError('Provide both upstream SHA and release tag')
    elif not sha:
        sha, tag = manifest['ref'], f'v{manifest["version"]}'
    if not re.fullmatch(r'[0-9a-f]{40}', sha):
        raise ValueError('Expected a full upstream commit SHA')
    version = re.fullmatch(r'v?([0-9]+\.[0-9]+\.[0-9]+(?:-[0-9A-Za-z.-]+)?)', tag)
    if not version or len(tag) > 128:
        raise ValueError('Upstream release tag must be a Docker-compatible version')
    return {'repository': repository, 'sha': sha, 'tag': tag, 'version': version.group(1)}


def verify_tree(tree, resolved):
    actual_sha = subprocess.check_output(['git', '-C', str(tree), 'rev-parse', 'HEAD'], text=True).strip()
    actual_version = (tree / 'VERSION').read_text().strip()
    if actual_sha != resolved['sha'] or actual_version != resolved['version']:
        raise ValueError('Checked-out SHA or VERSION does not match the resolved upstream release')


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--latest', action='store_true')
    parser.add_argument('--sha', default='')
    parser.add_argument('--tag', default='')
    parser.add_argument('--verify-tree', type=Path)
    args = parser.parse_args()
    if args.latest and (args.sha or args.tag):
        parser.error('--latest cannot be combined with --sha or --tag')
    try:
        result = resolve(json.loads((ROOT / 'upstream.json').read_text()), args.latest, args.sha, args.tag)
        if args.verify_tree:
            verify_tree(args.verify_tree, result)
    except (ValueError, KeyError, OSError, subprocess.CalledProcessError) as error:
        parser.exit(1, f'Cannot resolve upstream: {error}\n')
    for name, value in result.items():
        print(f'{name}={value}')


if __name__ == '__main__':
    main()
