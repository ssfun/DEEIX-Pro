#!/usr/bin/env python3
"""Apply DEEIX-Pro's reviewed patch set to a separate upstream checkout."""
import argparse
from pathlib import Path
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[1]


def apply(target: Path, check: bool = False) -> None:
    target = target.resolve()
    if not (target / 'backend/go.mod').is_file() or not (target / 'frontend/package.json').is_file():
        raise ValueError(f'Not a DEEIX-Chat source tree: {target}')
    patch = ROOT / 'patches/0001-subscription-day.patch'
    command = ['git', '-C', str(target), 'apply']
    result = subprocess.run(command + ['--check', str(patch)], capture_output=True, text=True)
    if result.returncode:
        reverse = subprocess.run(command + ['--reverse', '--check', str(patch)], capture_output=True, text=True)
        if reverse.returncode == 0:
            print('DEEIX-Pro: day subscription patch already applied')
            return
        raise ValueError('Upstream differs from the supported patch context, or is partially patched. '
                         'No changes applied.\n' + result.stderr)
    if check:
        print('DEEIX-Pro: day subscription patch can be applied')
    else:
        subprocess.run(command + [str(patch)], check=True)
        print('DEEIX-Pro: day subscription patch applied')


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('upstream', type=Path, help='DEEIX-Chat source directory')
    parser.add_argument('--check', action='store_true', help='Check compatibility without modifying files')
    args = parser.parse_args()
    try:
        apply(args.upstream, args.check)
    except (ValueError, subprocess.CalledProcessError) as error:
        print(error, file=sys.stderr)
        return 1
    return 0


if __name__ == '__main__':
    sys.exit(main())
