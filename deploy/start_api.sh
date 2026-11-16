#!/usr/bin/env bash
set -eu
# This script lives under releases/<release>/deploy. Resolve the persistent root
# using the configured project environment, without depending on release names.
edge_root=${DNB_PROJECT_ROOT:?DNB_PROJECT_ROOT is required}
if [ -f /usr/local/Ascend/ascend-toolkit/set_env.sh ]; then
  set +u
  source /usr/local/Ascend/ascend-toolkit/set_env.sh
  set -u
fi
cd "$edge_root/current"
exec "$edge_root/.venv/bin/python" -m uvicorn backend.app:app --host 127.0.0.1 --port 8000 --workers 1 --timeout-graceful-shutdown 5
