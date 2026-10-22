#!/usr/bin/env bash
set -euo pipefail
root=$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/../.." && pwd)
image=$(realpath -- "${1:?IMAGE BATCH DIV_BUNDLE NEW_OUTPUT}")
batch=$(realpath -- "${2:?missing batch}")
bundle=$(realpath -- "${3:?missing DIV golden bundle}")
out=$(realpath -m -- "${4:?missing output}")
test ! -e "$out"
test "$(jq -r .status "$bundle/manifest.json")" = PASS
mkdir -p "$out"
printf 'WAITING_FOR_BATCH\n' > "$out/status.txt"
# Wait in the background controller, without occupying a VCS worker.
deadline=$((SECONDS + 7200))
until [[ -f "$batch/completion.json" ]]; do
  if (( SECONDS >= deadline )); then
    printf 'INCOMPLETE_BATCH\n' > "$out/status.txt"
    exit 1
  fi
  sleep 15
done
if [[ $(jq -r .status "$batch/completion.json") != PASS ]]; then
  printf 'BLOCKED_BY_BATCH_FAILURE\n' > "$out/status.txt"
  exit 1
fi
elf="$bundle/$(jq -r .elf "$bundle/manifest.json")"
expected=$(jq -r .elf_sha256 "$bundle/manifest.json")
printf '%s  %s\n' "$expected" "$elf" | sha256sum --check > "$out/input_check.txt"
cp -p "$bundle/manifest.json" "$out/golden_manifest.json"
printf 'RUNNING\n' > "$out/status.txt"
if ! ARA_FOCUSED_TIMEOUT_SECONDS=900 bash "$root/verification/uvm/run_store_b_focused_case.sh" \
    "$image/sim/simv" "$elf" "$out/div_mask" > "$out/div_mask.driver.log" 2>&1; then
  printf 'FAIL\n' > "$out/status.txt"
  exit 1
fi
summary=$(jq -r .summary "$bundle/manifest.json")
if ! grep -Fx "$summary" "$out/div_mask/work/run.vcs.log" > "$out/count_check.txt"; then
  printf 'INCOMPLETE_DIV_CHECKS\n' > "$out/status.txt"
  exit 1
fi
printf 'PASS\n' > "$out/status.txt"
