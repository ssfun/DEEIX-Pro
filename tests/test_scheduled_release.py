#!/usr/bin/env python3
"""Run the actual workflow shell steps with a local GitHub CLI fixture.

Failure scenarios established before implementation:
- UTC cron does not correspond to 08:00 Asia/Shanghai.
- An already published version rebuilds, or a new version is skipped.
- A draft is mistaken for a completed release.
- An API failure is mistaken for a missing release.
- Manual/tag publication is accidentally skipped.
- Release creation loses the pinned Pro/upstream revisions or masks failure.

This checks workflow shell integration, not GitHub scheduling or Docker builds.
Usage: python3 tests/test_scheduled_release.py /tmp/scheduled-release-results.json
"""
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import textwrap

ROOT = Path(__file__).resolve().parents[1]
WORKFLOW = ROOT / '.github/workflows/publish-dockerhub.yml'


def shell_step(name):
    lines = WORKFLOW.read_text().splitlines()
    start = lines.index(f'      - name: {name}')
    run = next(i for i in range(start, len(lines)) if lines[i] == '        run: |')
    end = run + 1
    while end < len(lines) and (not lines[end].strip() or lines[end].startswith('          ')):
        end += 1
    return textwrap.dedent('\n'.join(lines[run + 1:end]))


def main():
    results = []
    workflow = WORKFLOW.read_text()
    assert "cron: '0 0 * * *'" in workflow
    assert 'needs: [resolve, publish]' in workflow
    assert "if: github.event_name == 'schedule'" in workflow
    results.append({'scenario': 'schedule and release dependency', 'passed': True})
    with tempfile.TemporaryDirectory() as temp:
        directory = Path(temp)
        gh = directory / 'gh'
        gh.write_text('''#!/usr/bin/env python3
import json, os, sys
from pathlib import Path
with Path(os.environ['CALLS']).open('a') as out:
    out.write(json.dumps(sys.argv[1:]) + '\\n')
if os.environ.get('FAIL') == 'true':
    sys.exit(1)
if sys.argv[1] == 'api':
    for release in json.loads(os.environ['RELEASES']):
        if not release['draft']:
            print(release['tag_name'])
''')
        gh.chmod(0o755)
        env = dict(os.environ, PATH=f'{directory}:{os.environ["PATH"]}',
                   GH_REPO='example/pro', TAG='v0.4.3', PRO_SHA='a' * 40,
                   UPSTREAM_SHA='b' * 40, UPSTREAM_REPOSITORY='DEEIX-AI/DEEIX-Chat',
                   IMAGE='example/pro', RUNNER_TEMP=temp,
                   GITHUB_STEP_SUMMARY=str(directory / 'summary'),
                   GITHUB_OUTPUT=str(directory / 'output'), CALLS=str(directory / 'calls'))
        scenarios = [
            ('new release', 'schedule', [], False, 'true'),
            ('published release', 'schedule', [{'tag_name': 'v0.4.3', 'draft': False}], False, 'false'),
            ('draft release', 'schedule', [{'tag_name': 'v0.4.3', 'draft': True}], False, 'true'),
            ('API failure', 'schedule', [], True, None),
            ('manual rebuild', 'workflow_dispatch', [{'tag_name': 'v0.4.3', 'draft': False}], False, 'true'),
            ('tag rebuild', 'push', [], False, 'true'),
        ]
        for name, event, releases, fail, expected in scenarios:
            (directory / 'output').write_text('')
            (directory / 'calls').write_text('')
            current = dict(env, EVENT_NAME=event, RELEASES=json.dumps(releases), FAIL=str(fail).lower())
            run = subprocess.run(['bash', '-e', '-o', 'pipefail', '-c', shell_step('Check whether publication is needed')], env=current, capture_output=True, text=True)
            output = (directory / 'output').read_text()
            assert (run.returncode != 0 and not output) if expected is None else (run.returncode == 0 and f'publish={expected}\n' in output), (name, run.stderr, output)
            if event != 'schedule':
                assert not (directory / 'calls').read_text()
            results.append({'scenario': name, 'passed': True})
        for fail in (False, True):
            (directory / 'calls').write_text('')
            run = subprocess.run(['bash', '-e', '-o', 'pipefail', '-c', shell_step('Create GitHub Release')], env=dict(env, FAIL=str(fail).lower()), capture_output=True, text=True)
            assert (run.returncode != 0) == fail, run.stderr
            args = json.loads((directory / 'calls').read_text().splitlines()[0])
            assert args[:3] == ['release', 'create', env['TAG']]
            assert args[args.index('--target') + 1] == env['PRO_SHA']
            notes = Path(args[args.index('--notes-file') + 1]).read_text()
            assert env['UPSTREAM_SHA'] in notes and env['PRO_SHA'] in notes
            results.append({'scenario': f'release creation fail={fail}', 'passed': True})
    artifact = Path(sys.argv[1])
    artifact.write_text(json.dumps(results, indent=2) + '\n')
    print(f'{len(results)} scenarios passed; artifact: {artifact}')


if __name__ == '__main__':
    main()
