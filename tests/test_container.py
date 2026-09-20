"""Exercise the built image without connecting to a real Cloudflare tunnel."""
from pathlib import Path
import subprocess
import sys
import tempfile
import time
import unittest
import uuid

IMAGE = sys.argv.pop(1) if len(sys.argv) > 1 else 'deeix-pro:ci'
MOCK = '''#!/bin/bash
set -eu
name=${0##*/}
printf '%s\\n' "$@" > "/test/$name.args"
trap 'echo stopped > "/test/$name.stopped"; exit 0' TERM INT
touch "/test/$name.ready"
while :; do
  if [[ -f "/test/$name.exit" ]]; then
    exit "$(cat "/test/$name.exit")"
  fi
  sleep 0.1 &
  wait "$!" || true
done
'''


def docker(*args, timeout=20):
    return subprocess.run(['docker', *args], capture_output=True, text=True, timeout=timeout, check=True).stdout.strip()


class ContainerTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix='deeix-container-')
        self.root = Path(self.temp.name)
        self.name = 'deeix-test-' + uuid.uuid4().hex
        for name in ['app', 'cloudflared']:
            path = self.root / name
            path.write_text(MOCK)
            path.chmod(0o755)

    def tearDown(self):
        subprocess.run(['docker', 'rm', '-f', '-v', self.name], capture_output=True)
        self.temp.cleanup()

    def ready(self, name):
        deadline = time.monotonic() + 10
        while time.monotonic() < deadline:
            if (self.root / f'{name}.ready').exists():
                return
            time.sleep(0.1)
        self.fail(f'{name} did not start: {docker("logs", self.name)}')

    def start(self, token=None):
        args = ['run', '-d', '--name', self.name, '--mount', f'type=bind,source={self.root},target=/test',
                '-e', 'PATH=/test:/usr/local/bin:/usr/bin:/bin']
        if token is not None:
            args += ['-e', f'CF_TOKEN={token}']
        docker(*args, IMAGE, '/test/app', 'argument with spaces')
        self.ready('app')
        if token:
            self.ready('cloudflared')

    def exit_code(self):
        return int(docker('wait', self.name))

    def test_real_cloudflared_binary(self):
        output = docker('run', '--rm', '--entrypoint', '/usr/local/bin/cloudflared', IMAGE, '--version')
        self.assertIn('cloudflared version', output)

    def test_without_token_runs_original_command_only(self):
        self.start()
        (self.root / 'app.exit').write_text('7')
        self.assertEqual(self.exit_code(), 7)
        self.assertFalse((self.root / 'cloudflared.ready').exists())
        self.assertEqual((self.root / 'app.args').read_text().splitlines(), ['argument with spaces'])

    def test_empty_token_disables_tunnel(self):
        self.start('')
        (self.root / 'app.exit').write_text('0')
        self.assertEqual(self.exit_code(), 0)
        self.assertFalse((self.root / 'cloudflared.ready').exists())

    def test_token_arguments_and_stop_signal(self):
        token = 'fake token with spaces'
        self.start(token)
        self.assertEqual((self.root / 'cloudflared.args').read_text().splitlines(),
                         ['--no-autoupdate', 'tunnel', 'run', '--token', token])
        docker('stop', '--time', '8', self.name)
        self.assertEqual(self.exit_code(), 143)
        for name in ['app', 'cloudflared']:
            self.assertTrue((self.root / f'{name}.stopped').exists())

    def test_application_exit_stops_tunnel(self):
        self.start('fake-token')
        (self.root / 'app.exit').write_text('9')
        self.assertEqual(self.exit_code(), 9)
        self.assertTrue((self.root / 'cloudflared.stopped').exists())

    def test_tunnel_failure_stops_application(self):
        self.start('fake-token')
        (self.root / 'cloudflared.exit').write_text('23')
        self.assertEqual(self.exit_code(), 23)
        self.assertTrue((self.root / 'app.stopped').exists())

    def test_tunnel_clean_exit_is_still_a_failure(self):
        self.start('fake-token')
        (self.root / 'cloudflared.exit').write_text('0')
        self.assertEqual(self.exit_code(), 1)
        self.assertTrue((self.root / 'app.stopped').exists())


if __name__ == '__main__':
    unittest.main()
