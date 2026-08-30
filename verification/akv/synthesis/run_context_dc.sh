#!/usr/bin/env bash
set -euo pipefail

script_dir=$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)
cd "$script_dir"

status_file=akv_context_dc.status
log_file=akv_context_dc.log
printf 'RUNNING\n' > "$status_file"

if dc_shell -f akv_context_dc.tcl > "$log_file" 2>&1; then
  printf 'PASS\n' > "$status_file"
else
  status=$?
  printf 'FAIL %d\n' "$status" > "$status_file"
  exit "$status"
fi
