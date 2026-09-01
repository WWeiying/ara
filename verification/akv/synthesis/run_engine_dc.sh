#!/usr/bin/env bash
set -euo pipefail

script_dir=$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)
ara_root=$(cd -- "$script_dir/../../.." && pwd)
cd "$script_dir"

status_file=akv_engine_dc.status
log_file=akv_engine_dc.log
printf 'PREFLIGHT\n' > "$status_file"

make -C "$ara_root/verification/akv" synth-preflight

printf 'RUNNING\n' > "$status_file"
if dc_shell -f akv_engine_dc.tcl > "$log_file" 2>&1; then
  if python3 "$ara_root/hardware/scripts/akv/collect-synthesis-results.py" \
      --mode standalone; then
    printf 'PASS\n' > "$status_file"
  else
    status=$?
    printf 'FAIL %d\n' "$status" > "$status_file"
    exit "$status"
  fi
else
  status=$?
  printf 'FAIL %d\n' "$status" > "$status_file"
  exit "$status"
fi
