#!/usr/bin/env bash
set -euo pipefail

root=$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/../.." && pwd)
base="${root}/verification/out/verilator-coverage-masked-indexed-2m-20260924-01"
python="${root}/verification/tools/soc-venv/bin/python"
units=(
  ara-dsa-masked-indexed-coverage-matrix-20260924-01.service
  ara-dsa-masked-indexed-real-akv-coverage-20260924-01.service
  ara-dsa-masked-indexed-rvv-corners-coverage-20260924-01.service
)

for unit in "${units[@]}"; do
  while systemctl --user is-active --quiet "${unit}"; do
    sleep 60
  done
done

for group in matrix_11case rvv_corners_35case; do
  test "$(jq -r .status "${base}/${group}/merged/independent_audit.json")" = PASS
  test "$(jq -r .status "${base}/${group}/merged/signoff/signoff.json")" = PASS
done
test "$(jq -r .status "${base}/akv_real/result.json")" = PASS
"${python}" "${root}/verification/coverage/build_provenance.py" \
  --output "${base}/source_manifest.json" --check

cases=()
while IFS= read -r name; do
  cases+=(--case "${base}/matrix_11case/${name}/result.json")
done < <(jq -r '.cases[].name' "${root}/verification/coverage/candidate_final_matrix_20260924.json")
while IFS= read -r path; do
  cases+=(--case "${base}/rvv_corners_35case/${path}/result.json")
done < <(jq -r '.[].artifact_dir | split("/")[-1]' \
  "${root}/verification/out/masked-indexed-latest-rvv-corners-run-20260924-02/summary.json")
cases+=(--case "${base}/akv_real/result.json")
test "${#cases[@]}" -eq 94

out="${base}/combined_47case"
test ! -e "${out}"
"${python}" "${root}/verification/coverage/merge_verilator_coverage.py" \
  "${cases[@]}" --output "${out}" \
  --verilator-coverage "${root}/install/verilator/bin/verilator_coverage" \
  --hierarchy-prefix ara_tb_verilator.dut.i_ara_soc \
  --include-path /hardware/src/ --include-path /hardware/deps/cva6/
"${python}" "${root}/verification/coverage/audit_merged.py" \
  --audit "${out}/audit.json" --minimum-cases 47 \
  --report "${out}/independent_audit.json"
"${python}" "${root}/verification/coverage/review_uncovered.py" \
  --audit "${out}/audit.json" --minimum-cases 47 \
  --output "${out}/review.json"
"${python}" "${root}/verification/run_signoff.py" \
  --stage coverage-integrity --coverage-merge-audit "${out}/audit.json" \
  --coverage-minimum-cases 47 --output "${out}/signoff"
