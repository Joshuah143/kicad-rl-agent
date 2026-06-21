#!/usr/bin/env bash
# Deploy the kicad-schematics HUD environment to the cloud, then sync the taskset.
#
# `hud deploy` only tarballs hud_env/, so we first VENDOR the main package
# (../src, ../tasks, ../pyproject.toml, ../README.md) into hud_env/_pkg/ — which
# the Dockerfile installs. _pkg/ is gitignored (it is a build artifact).
#
# Usage (run from hud_env/):
#   ./deploy.sh                 # lean cloud image (no KiCad; ERC skipped in cloud)
#   INSTALL_KICAD=1 ./deploy.sh # include KiCad for ERC in cloud rollouts (slow build)
#
# After this, train fully in the cloud with:  uv run python train.py --remote
set -euo pipefail
cd "$(dirname "$0")"

TASKSET="${TASKSET:-kicad-schematics}"
INSTALL_KICAD="${INSTALL_KICAD:-0}"

echo "==> Vendoring main package into _pkg/ ..."
rm -rf _pkg
mkdir -p _pkg
cp ../pyproject.toml ../README.md _pkg/
cp -R ../src _pkg/src
cp -R ../tasks _pkg/tasks
# drop caches so the tarball stays small
find _pkg -name __pycache__ -type d -prune -exec rm -rf {} + 2>/dev/null || true

echo "==> Deploying environment (INSTALL_KICAD=${INSTALL_KICAD}) ..."
uv run hud deploy . --build-arg "INSTALL_KICAD=${INSTALL_KICAD}"

echo "==> Syncing taskset '${TASKSET}' from tasks.py ..."
uv run hud sync tasks "${TASKSET}" tasks.py --yes

echo "==> Done. Launch cloud training with:  uv run python train.py --remote"
