#!/usr/bin/env bash
set -euo pipefail

root=$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/../.." && pwd)
image="${root}/verification/out/final-twofix-overlay-image-20260925-01/sim"
source="${root}/verification/out/masked-indexed-latest-rvv-corners-run-20260924-02"
out="${root}/verification/out/final-gather-overlay-regression-20260925-02"

test ! -e "${out}"
test -x "${image}/simv"
PYTHONPATH="${root}/verification" python3 -m ara_verify.vcs_source_manifest \
  --output "${image}/vcs_source_manifest.json" --check
mkdir -p -- "${out}"
sha256sum "${image}/simv" \
  "${source}/tests/rvv_vrgather_edges/input.elf" \
  "${source}/tests/rvv_vcompress_edges/input.elf" \
  "${root}/apps/bin/rv64uv-ara-vrgather_edges" \
  "${root}/apps/bin/rv64uv-ara-vcompress_edges" > "${out}/INPUT_SHA256SUMS"
PYTHONPATH="${root}/verification" python3 "${root}/verification/verify.py" \
  run --test rvv:vrgather_edges --test rvv:vcompress_edges \
  --output "${out}/run" --simv "${image}/simv" --skip-build \
  --commit-trace --jobs 2 --timeout 600
PYTHONPATH="${root}/verification" python3 "${root}/verification/verify.py" audit \
  --run "${out}/run" --require-trace \
  --output "${out}/independent_audit.json"
test "$(jq -r .status "${out}/independent_audit.json")" = PASS
test "$(jq '[.[] | select(.status == "PASS")] | length' "${out}/run/summary.json")" -eq 2
sha256sum -c --status "${out}/INPUT_SHA256SUMS"
PYTHONPATH="${root}/verification" python3 -m ara_verify.vcs_source_manifest \
  --output "${image}/vcs_source_manifest.json" --check
