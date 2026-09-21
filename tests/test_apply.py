"""Validate application on a clean upstream archive, idempotency and drift refusal."""
import hashlib
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
UPSTREAM = Path(sys.argv.pop(1)).resolve() if len(sys.argv) > 1 else None


class ApplyTests(unittest.TestCase):
    def test_clean_repeat_and_drift(self):
        self.assertIsNotNone(UPSTREAM, 'Pass a clean upstream git checkout as the first argument')
        with tempfile.TemporaryDirectory(prefix='deeix-patch-test-') as directory:
            target = Path(directory)
            archive = subprocess.run(['git', '-C', str(UPSTREAM), 'archive', 'HEAD'], check=True, capture_output=True).stdout
            subprocess.run(['tar', '-x', '-C', directory], input=archive, check=True)
            subprocess.run(['git', 'init', '-q', directory], check=True)
            def snapshot():
                return {str(p.relative_to(target)): hashlib.sha256(p.read_bytes()).hexdigest()
                        for p in target.rglob('*') if p.is_file() and '.git' not in p.relative_to(target).parts}
            def run(*args):
                return subprocess.run([sys.executable, str(ROOT / 'scripts/apply_upstream_patches.py'), directory, *args], capture_output=True, text=True)
            before = snapshot()
            self.assertEqual(run('--check').returncode, 0)
            self.assertEqual(snapshot(), before)
            result = run()
            self.assertEqual(result.returncode, 0, result.stderr)
            patched = snapshot()
            self.assertNotEqual(before, patched)
            self.assertEqual(run().returncode, 0)
            self.assertEqual(snapshot(), patched)
            subprocess.run(['git', '-C', directory, 'apply', '--reverse', *[str(p) for p in sorted((ROOT / 'patches').glob('*.patch'), reverse=True)]], check=True)
            self.assertEqual(snapshot(), before)
            # Upgrade an existing checkout that only has the quota refresh patch.
            subprocess.run(['git', '-C', directory, 'apply', str(ROOT / 'patches/0001-quota-refresh.patch')], check=True)
            quota_only = snapshot()
            self.assertEqual(run('--check').returncode, 0)
            self.assertEqual(snapshot(), quota_only)
            self.assertEqual(run().returncode, 0)
            self.assertEqual(snapshot(), patched)
            subprocess.run(['git', '-C', directory, 'apply', '--reverse', *[str(p) for p in sorted((ROOT / 'patches').glob('*.patch'), reverse=True)]], check=True)
            source = target / 'Dockerfile'
            source.write_text(source.read_text().replace('CMD ["/app/deeix-chat"]', 'CMD ["/app/changed-upstream"]'))
            drifted = snapshot()
            self.assertNotEqual(run().returncode, 0)
            self.assertEqual(snapshot(), drifted)


if __name__ == '__main__':
    unittest.main()
