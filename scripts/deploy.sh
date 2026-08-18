#!/usr/bin/env bash
# Regenerate the HTML report and stage it for GitHub Pages deploy.
set -euo pipefail
cd "$(dirname "$0")/.."

.venv/bin/python -m consensus report-html
cp data/consensus/consensus.html index.html
echo "index.html updated — commit and push to deploy."