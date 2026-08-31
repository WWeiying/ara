#!/usr/bin/env bash
set -euo pipefail

script_dir=$(cd -- "$(dirname -- "$0")" && pwd)
export AKV_MODEL_MODE=combined
exec "${script_dir}/run-qemu-model-check.sh" "$@"
