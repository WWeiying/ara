#!/usr/bin/env bash
set -euo pipefail

root=$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/../.." && pwd)
image="${root}/verification/out/final-mask-bundle-image-20260925-02/sim"
out="${root}/verification/out/final-mask-bundle-directed-20260925-02"
test ! -e "${out}"
PYTHONPATH="${root}/verification" python3 -m ara_verify.vcs_source_manifest \
  --output "${image}/vcs_source_manifest.json" --check
mkdir -p -- "${out}"
sha256sum "${image}/simv" \
  "${root}/apps/bin/rv64uv-ara-vmasked_indexed_alignment" \
  "${root}/apps/bin/rv64uv-ara-vmasked_indexed_store_alignment" \
  "${root}/apps/bin/rv64uv-ara-vindexed_fault_vstart" \
  "${root}/apps/bin/rv64uv-ara-vunit_vstart_edges" \
  "${root}/apps/bin/rv64uv-ara-vstore_mask_tail_edges" > "${out}/INPUT_SHA256SUMS"
PYTHONPATH="${root}/verification" python3 "${root}/verification/verify.py" run \
  --test rvv:vmasked_indexed_alignment \
  --test rvv:vmasked_indexed_store_alignment \
  --test rvv:vindexed_fault_vstart \
  --test rvv:vunit_vstart_edges --test rvv:vstore_mask_tail_edges \
  --output "${out}/run" --simv "${image}/simv" --skip-build \
  --commit-trace --jobs 3 --timeout 900
PYTHONPATH="${root}/verification" python3 "${root}/verification/verify.py" audit \
  --run "${out}/run" --require-trace \
  --output "${out}/independent_audit.json"
test "$(jq -r .status "${out}/independent_audit.json")" = PASS
test "$(jq '[.[] | select(.status == "PASS")] | length' "${out}/run/summary.json")" -eq 5
sha256sum -c --status "${out}/INPUT_SHA256SUMS"
PYTHONPATH="${root}/verification" python3 -m ara_verify.vcs_source_manifest \
  --output "${image}/vcs_source_manifest.json" --check
