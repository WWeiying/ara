#!/usr/bin/env bash
set -euo pipefail
root=$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/../.." && pwd)
probe=$(realpath -m -- "${1:?usage: run_store_b_candidate_regression.sh PROBE_DIR NEW_OUTPUT_DIR}")
out=$(realpath -m -- "${2:?missing new output directory}")
test ! -e "$out"
mkdir -p "$out/inputs"
# Freeze the strengthened test before another software build can change it.
cp -p "$root/apps/bin/rv64uv-ara-vstore_lookahead" "$out/inputs/numeric.elf"
for name in fault handoff masked; do
  cp -p "$root/verification/out/store-lookahead-$name-20260925-01/work/input.elf" \
    "$out/inputs/$name.elf"
done
for ((attempt=0; attempt<180; attempt++)); do
  test ! -f "$probe/uvm_result.json" || break
  sleep 5
done
test "$(jq -r .status "$probe/uvm_result.json")" = PASS
test "$(jq -r .status "$probe/source_check.json")" = PASS
simv="$probe/sim/simv"
pids=()
for name in numeric fault handoff masked; do
  bash "$root/verification/uvm/run_store_b_focused_case.sh" \
    "$simv" "$out/inputs/$name.elf" "$out/$name" > "$out/$name.driver.log" 2>&1 &
  pids+=("$!")
done
failed=0
for pid in "${pids[@]}"; do
  wait "$pid" || failed=1
done
test "$failed" = 0
rg '^\[VSET_PREVIEW_FORWARD\]' "$out/numeric/work/run.vcs.log"
printf 'PASS: four directed DUT cases and numeric preview consumption\n'
