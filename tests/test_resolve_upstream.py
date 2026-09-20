import importlib.util
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

spec = importlib.util.spec_from_file_location('resolve_upstream', Path(__file__).resolve().parents[1] / 'scripts/resolve_upstream.py')
resolver = importlib.util.module_from_spec(spec)
spec.loader.exec_module(resolver)


class ResolveTests(unittest.TestCase):
    manifest = {'repository': 'https://github.com/DEEIX-AI/DEEIX-Chat.git', 'ref': 'a' * 40, 'version': '0.4.2'}

    def test_baseline_needs_no_api(self):
        with patch.object(resolver, 'api') as api:
            result = resolver.resolve(self.manifest)
        api.assert_not_called()
        self.assertEqual((result['sha'], result['tag']), ('a' * 40, 'v0.4.2'))

    def test_latest_resolves_tag_not_moving_target_branch(self):
        with patch.object(resolver, 'api', side_effect=[
            {'tag_name': 'v0.5.0', 'target_commitish': 'main', 'draft': False, 'prerelease': False},
            {'sha': 'b' * 40},
        ]) as api:
            result = resolver.resolve(self.manifest, latest=True)
        self.assertEqual(result['tag'], 'v0.5.0')
        self.assertEqual(result['version'], '0.5.0')
        self.assertEqual(result['sha'], 'b' * 40)
        self.assertEqual(api.call_args_list[1].args, ('repos/DEEIX-AI/DEEIX-Chat/commits/v0.5.0',))

    def test_resolved_snapshot_does_not_query_latest_again(self):
        with patch.object(resolver, 'api') as api:
            result = resolver.resolve(self.manifest, sha='b' * 40, tag='v0.5.0')
        api.assert_not_called()
        self.assertEqual(result['sha'], 'b' * 40)

    def test_rejects_draft_or_prerelease(self):
        for field in ['draft', 'prerelease']:
            with patch.object(resolver, 'api', return_value={'tag_name': 'v0.5.0', field: True}):
                with self.assertRaises(ValueError):
                    resolver.resolve(self.manifest, latest=True)

    def test_rejects_invalid_or_partial_snapshot(self):
        for sha, tag in [('main', 'v0.5.0'), ('a'*40, 'latest'), ('a'*40, 'v0.5.0\nother=value'), ('a'*40, ''), ('', 'v0.5.0')]:
            with self.subTest(sha=sha, tag=tag), self.assertRaises(ValueError):
                resolver.resolve(self.manifest, sha=sha, tag=tag)

    def test_missing_release_fails_without_baseline_fallback(self):
        with patch.object(resolver, 'api', side_effect=resolver.subprocess.CalledProcessError(1, 'gh')):
            with self.assertRaises(resolver.subprocess.CalledProcessError):
                resolver.resolve(self.manifest, latest=True)

    def test_checked_out_version_and_sha_must_match(self):
        result = resolver.resolve(self.manifest)
        with tempfile.TemporaryDirectory() as directory:
            tree = Path(directory)
            (tree / 'VERSION').write_text('0.4.2\n')
            with patch.object(resolver.subprocess, 'check_output', return_value='a'*40 + '\n'):
                resolver.verify_tree(tree, result)
                (tree / 'VERSION').write_text('0.4.3\n')
                with self.assertRaises(ValueError):
                    resolver.verify_tree(tree, result)
            (tree / 'VERSION').write_text('0.4.2\n')
            with patch.object(resolver.subprocess, 'check_output', return_value='b'*40 + '\n'):
                with self.assertRaises(ValueError):
                    resolver.verify_tree(tree, result)


if __name__ == '__main__':
    unittest.main()
