#!/usr/bin/env bash
set -euo pipefail
root="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
target="$(cd "${1:?Usage: scripts/validate.sh /path/to/DEEIX-Chat}" && pwd)"
python3 "$root/scripts/apply_upstream_patches.py" "$target"
python3 "$root/scripts/apply_upstream_patches.py" --check "$target"
(
  cd "$target/backend"
  go test ./internal/domain/billing ./internal/application/billing ./internal/transport/http/billing ./internal/infra/persistence/postgres/billing
)
(
  cd "$target"
  node packages/api-contract/scripts/generate.mjs --check
  cd frontend
  node node_modules/typescript/bin/tsc --noEmit --pretty false
)
