#!/usr/bin/env bash
set -euo pipefail
root=$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/../.." && pwd)
image=$(realpath -- "${1:?IMAGE_DIR MAIN_BATCH_DIR NEW_OUTPUT_DIR GOLDEN_BUNDLE}")
batch=$(realpath -- "${2:?missing main batch}")
out=$(realpath -m -- "${3:?missing new output directory}")
bundle=$(realpath -- "${4:?missing frozen golden bundle}")
test ! -e "$out"
test "$(jq -r .status "$bundle/manifest.json")" = PASS
names=(vec_fp_csr_order vfp_vstart_edges vfredosum vfwmacc)
for name in "${names[@]}"; do
  test -f "$bundle/inputs/$name.elf"
done
mkdir -p "$out/inputs"
for name in "${names[@]}"; do
  cp -p "$bundle/inputs/$name.elf" "$out/inputs/$name.elf"
  expected=$(jq -r --arg key "inputs/$name.elf" '.input_sha256[$key]' "$bundle/manifest.json")
  printf '%s  %s\n' "$expected" "$out/inputs/$name.elf" | sha256sum --check
done
cp -p "$bundle/manifest.json" "$out/golden_manifest.json"
sha256sum "$out"/inputs/*.elf > "$out/inputs.sha256"
printf 'WAITING_FOR_MAIN_BATCH\n' > "$out/status.txt"
# This is a background dependency gate, not an additional simulation worker.
# Do not exceed the main batch's five-worker budget by starting early.
deadline=$((SECONDS + 7200))
until [[ -f "$batch/accepted_completion.json" ]]; do
  if (( SECONDS >= deadline )); then
    printf 'INCOMPLETE_MAIN_BATCH\n' > "$out/status.txt"
    exit 1
  fi
  sleep 10
done
if [[ $(jq -r .status "$batch/accepted_completion.json") != PASS ]]; then
  printf 'BLOCKED_BY_MAIN_BATCH_FAILURE\n' > "$out/status.txt"
  exit 1
fi
test "$(jq -r .status "$image/uvm_result.json")" = PASS
printf 'RUNNING\n' > "$out/status.txt"
pids=()
for name in "${names[@]}"; do
  ARA_FOCUSED_TIMEOUT_SECONDS=900 ARA_FOCUSED_FP_CSR_TRACE=1 \
    bash "$root/verification/uvm/run_store_b_focused_case.sh" \
      "$image/sim/simv" "$out/inputs/$name.elf" "$out/$name" \
      > "$out/$name.driver.log" 2>&1 &
  pids+=("$!")
done
failed=0
for pid in "${pids[@]}"; do
  wait "$pid" || failed=1
done
sha256sum --check "$out/inputs.sha256" > "$out/input_check.txt" || failed=1
if (( failed )); then
  printf 'FAIL\n' > "$out/status.txt"
  exit 1
fi
printf 'PASS\n' > "$out/status.txt"
