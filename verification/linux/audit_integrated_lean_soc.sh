#!/usr/bin/env bash
set -euo pipefail

root=$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/../.." && pwd)
unit=ara-dsa-integrated-linux-lean-run-20260925-02.service
run="$root/verification/out/integrated-linux-lean-soc-20260925-02"

while systemctl --user is-active --quiet "$unit"; do
  sleep 30
done

"$root/verification/tools/soc-venv/bin/python" \
  "$root/verification/fpga/check_soc_linux.py" "$run" \
  --report "$run/independent_boot_audit.json"
