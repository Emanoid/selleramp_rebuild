#!/usr/bin/env bash
# Build the Mac .app bundle. Run from the repo root.
set -euo pipefail

cd "$(dirname "$0")/.."

if [ ! -d ".venv" ]; then
  python3 -m venv .venv
fi
source .venv/bin/activate

pip install --upgrade pip wheel >/dev/null
pip install -e . streamlit pyinstaller >/dev/null

rm -rf build/pyi_work dist/sa-rebuild dist/sa-rebuild.app
pyinstaller \
  --noconfirm \
  --workpath build/pyi_work \
  --distpath dist \
  sa-rebuild.spec

echo
echo "Built:"
ls -lah dist/
echo
echo "Distribute the .app bundle (or zip it):"
echo "  cd dist && zip -r sa-rebuild-mac.zip sa-rebuild.app"
