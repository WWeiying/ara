#!/usr/bin/env bash
set -euo pipefail

root=$(cd "$(dirname "$0")/../.." && pwd)
cd "$root"
build_service=ara-dsa-integrated-verilator-coverage-build-20260925-01.service
image=verification/out/integrated-verilator-coverage-20260925-01
source=verification/out/integrated-rvv-fast-integrity-20260925-01

for ((minute = 0; minute < 240; minute++)); do
    state=$(systemctl --user show "$build_service" -p ActiveState --value)
    [[ $state == active || $state == activating ]] || break
    sleep 60
done
[[ $(systemctl --user show "$build_service" -p ActiveState --value) == inactive ]]
[[ $(systemctl --user show "$build_service" -p Result --value) == success ]]
test -x "$image/build/verilator/Vara_tb_verilator"
python3 verification/coverage/build_provenance.py \
    --output "$image/source_manifest.json" --check
PYTHONPATH=verification verification/tools/soc-venv/bin/python \
    verification/coverage/run_directed_coverage.py \
    --summary "$source/summary.json" --audit "$source/independent_audit.json" \
    --simv "$image/build/verilator/Vara_tb_verilator" \
    --source-manifest "$image/source_manifest.json" \
    --ram-bytes 2097152 --jobs 2 --term-cycles 100000 --timeout 3600 \
    --output verification/out/integrated-coverage-directed-20260925-01
