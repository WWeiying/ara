#!/usr/bin/env bash
set -euo pipefail

root=$(cd "$(dirname "$0")/../.." && pwd)
cd "$root"
build_service=ara-dsa-integrated-verilator-coverage-build-20260925-01.service
image=verification/out/integrated-verilator-coverage-20260925-01
simv="$image/build/verilator/Vara_tb_verilator"
manifest="$image/source_manifest.json"

# Wait in a detached service so the long build never blocks the verification driver.
for ((minute = 0; minute < 240; minute++)); do
    state=$(systemctl --user show "$build_service" -p ActiveState --value)
    [[ $state == active || $state == activating ]] || break
    sleep 60
done
[[ $(systemctl --user show "$build_service" -p ActiveState --value) == inactive ]]
[[ $(systemctl --user show "$build_service" -p Result --value) == success ]]
test -x "$simv"
python3 verification/coverage/build_provenance.py --output "$manifest" --check
verification/tools/soc-venv/bin/python verification/coverage/run_passed_matrix.py \
    --matrix verification/coverage/integrated_first_matrix_20260925.json \
    --simv "$simv" --source-manifest "$manifest" \
    --ram-bytes 2097152 --jobs 2 \
    --output verification/out/integrated-coverage-first-matrix-20260925-01
