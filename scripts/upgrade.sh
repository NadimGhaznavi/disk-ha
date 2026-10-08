#!/usr/bin/env bash
# Reuse installation while retaining configuration and saved data.
set -euo pipefail
cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.."
exec /usr/bin/python3 scripts/install.py upgrade "$@"
