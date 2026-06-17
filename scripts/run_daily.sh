#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT_DIR"

if [[ ! -d .venv ]]; then
  ./scripts/bootstrap.sh
fi

source .venv/bin/activate

CONFIG_PATH="${1:-config.yaml}"
if [[ ! -f "$CONFIG_PATH" ]]; then
  CONFIG_PATH="example_config.yaml"
fi

portfolio-agent daily --config "$CONFIG_PATH" --out outputs
