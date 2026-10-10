#!/usr/bin/env bash
set -euo pipefail

root=$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/../.." && pwd)
cd "$root"

unit=ara-dsa-integrated-rvv-fast-integrity-traced-20260925-01.service
source=verification/out/integrated-rvv-fast-integrity-traced-20260925-01
image=verification/out/integrated-verilator-coverage-20260925-01

while systemctl --user is-active --quiet "$unit"; do
  sleep 30
done
jq -e 'length == 6 and all(.[]; .status == "PASS")' "$source/summary.json" >/dev/null
python3 verification/verify.py audit --run "$source" --require-trace \
  --output "$source/independent_audit.json"
jq -e '.status == "PASS" and .case_count == 6 and .passed_cases == 6' \
  "$source/independent_audit.json" >/dev/null
test -x "$image/build/verilator/Vara_tb_verilator"
python3 verification/coverage/build_provenance.py \
  --output "$image/source_manifest.json" --check
PYTHONPATH=verification verification/tools/soc-venv/bin/python \
  verification/coverage/run_directed_coverage.py \
  --summary "$source/summary.json" --audit "$source/independent_audit.json" \
  --simv "$image/build/verilator/Vara_tb_verilator" \
  --source-manifest "$image/source_manifest.json" \
  --ram-bytes 2097152 --jobs 2 --term-cycles 100000 --timeout 3600 \
  --output verification/out/integrated-coverage-directed-20260925-02
