#!/usr/bin/env python3
"""Resolve the pinned upstream manifest for GitHub Actions."""
import json
from pathlib import Path
import re

manifest = json.loads((Path(__file__).resolve().parents[1] / 'upstream.json').read_text())
match = re.fullmatch(r'https://github\.com/([A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+)\.git', manifest['repository'])
if not match or not re.fullmatch(r'[0-9a-f]{40}', manifest['ref']):
    raise SystemExit('upstream.json must specify a GitHub repository and a full commit SHA')
print(f'repository={match.group(1)}')
print(f'sha={manifest["ref"]}')
