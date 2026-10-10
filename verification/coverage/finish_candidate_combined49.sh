#!/usr/bin/env bash
set -euo pipefail

root=$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/../.." && pwd)
base="${root}/verification/out/verilator-coverage-masked-indexed-2m-20260924-01"
python="${root}/verification/tools/soc-venv/bin/python"

for unit in \
  ara-dsa-masked-indexed-coverage-combined-20260924-01.service \
  ara-dsa-masked-indexed-focused-coverage-20260924-01.service; do
  while systemctl --user is-active --quiet "${unit}"; do
    sleep 60
  done
done

for group in combined_47case masked_indexed_2case/merged; do
  test "$(jq -r .status "${base}/${group}/independent_audit.json")" = PASS
  test "$(jq -r .status "${base}/${group}/signoff/signoff.json")" = PASS
done
"${python}" "${root}/verification/coverage/build_provenance.py" \
  --output "${base}/source_manifest.json" --check

results=()
while IFS= read -r name; do
  results+=("${base}/matrix_11case/${name}/result.json")
done < <(jq -r '.cases[].name' "${root}/verification/coverage/candidate_final_matrix_20260924.json")
while IFS= read -r name; do
  results+=("${base}/rvv_corners_35case/${name}/result.json")
done < <(jq -r '.[].artifact_dir | split("/")[-1]' \
  "${root}/verification/out/masked-indexed-latest-rvv-corners-run-20260924-02/summary.json")
results+=("${base}/akv_real/result.json")
results+=("${base}/masked_indexed_2case/rvv_vmasked_indexed_alignment/result.json")
results+=("${base}/masked_indexed_2case/rvv_vmasked_indexed_store_alignment/result.json")
test "${#results[@]}" -eq 49
test "$(printf '%s\n' "${results[@]}" | sort -u | wc -l)" -eq 49
for result in "${results[@]}"; do
  test -f "${result}"
  test "$(jq -r .status "${result}")" = PASS
done
test "$(jq -r .elf_sha256 "${results[@]}" | sort -u | wc -l)" -eq 49

out="${base}/combined_49case"
test ! -e "${out}"
cases=()
for result in "${results[@]}"; do
  cases+=(--case "${result}")
done
"${python}" "${root}/verification/coverage/merge_verilator_coverage.py" \
  "${cases[@]}" --output "${out}" \
  --verilator-coverage "${root}/install/verilator/bin/verilator_coverage" \
  --hierarchy-prefix ara_tb_verilator.dut.i_ara_soc \
  --include-path /hardware/src/ --include-path /hardware/deps/cva6/
"${python}" "${root}/verification/coverage/audit_merged.py" \
  --audit "${out}/audit.json" --minimum-cases 49 \
  --report "${out}/independent_audit.json"
"${python}" "${root}/verification/coverage/review_uncovered.py" \
  --audit "${out}/audit.json" --minimum-cases 49 \
  --output "${out}/review.json"
"${python}" "${root}/verification/run_signoff.py" \
  --stage coverage-integrity --coverage-merge-audit "${out}/audit.json" \
  --coverage-minimum-cases 49 --output "${out}/signoff"
