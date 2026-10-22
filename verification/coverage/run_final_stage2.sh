#!/usr/bin/env bash
set -euo pipefail

root=$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/../.." && pwd)
cd -- "${root}"
python="${root}/verification/tools/soc-venv/bin/python"
test -x "${python}"
out=${1:?usage: run_final_stage2.sh NEW_OUTPUT_DIR}
out=$(realpath -m -- "${out}")
case "${out}" in "${root}/verification/out/"*) ;; *) exit 2 ;; esac
test ! -e "${out}" || test -d "${out}"

stage1=${ARA_COVERAGE_STAGE1:-verification/out/integrated-final-stage1-20260925-02}
build=verification/out/integrated-verilator-coverage-20260925-01
simv="${build}/build/verilator/Vara_tb_verilator"
manifest="${ARA_COVERAGE_SOURCE_MANIFEST:-${build}/source_manifest_tohost.json}"
reporter=install/verilator/bin/verilator_coverage
test -x "${simv}"
"${python}" verification/coverage/build_provenance.py --output "${manifest}" --check
"${python}" verification/coverage/audit_merged.py \
  --audit "${stage1}/merged/audit.json" --minimum-cases 12
test "$(jq -r '.cases | length' "${stage1}/merged/audit.json")" -eq 12
test "$(jq -r .simv_sha256 "${stage1}/merged/audit.json")" = \
  "$(sha256sum "${simv}" | cut -d ' ' -f 1)"
image_sha=$(sha256sum "${simv}" | cut -d ' ' -f 1)
manifest_sha=$(sha256sum "${manifest}" | cut -d ' ' -f 1)
if [[ -f "${out}/merged/audit.json" ]]; then
  test "$(jq -r '.cases | length' "${out}/merged/audit.json")" -eq 76
  test "$(jq -r .simv_sha256 "${out}/merged/audit.json")" = "${image_sha}"
  jq -e --slurpfile first "${stage1}/merged/audit.json" \
    '(.cases | map(.result)) as $all |
     all($first[0].cases[]; .result as $result | $all | index($result) != null)' \
    "${out}/merged/audit.json" >/dev/null
  "${python}" verification/coverage/audit_merged.py \
    --audit "${out}/merged/audit.json" --minimum-cases 76 \
    --report "${out}/merged/independent_audit.json"
  "${python}" verification/coverage/review_uncovered.py \
    --audit "${out}/merged/audit.json" --minimum-cases 76 \
    --output "${out}/merged/review.json"
  exit 0
fi
if [[ -e "${out}/merged" ]]; then
  incomplete_index=1
  while [[ -e "${out}/merge_incomplete_${incomplete_index}" ]]; do
    ((incomplete_index += 1))
  done
  mv -- "${out}/merged" "${out}/merge_incomplete_${incomplete_index}"
fi

sources=(
  integrated-wred-m8-memory101-replay-20260925-01
  integrated-wred-m8-memory201-replay-20260925-01
  integrated-wred-m8-memory301-replay-20260925-01
  integrated-wred-m8-memory401-replay-20260925-01
  integrated-wred-m8-arithmetic10-replay-20260925-02
  integrated-wred-m8-loadstore10-replay-20260925-01
  integrated-wred-m8-fp32-10-replay-20260925-01
  integrated-wred-m8-fp64-10-replay-20260925-01
  integrated-wred-m8-vtype10-replay-20260925-01
)

# Stage 1 used the first case in memory101 and each 10-seed batch. Other
# memory batches were not replayed there.
expected=(4 5 5 5 9 9 9 9 9)
results=()
declare -A seen_cases=()
declare -A seen_elf_hashes=()
check_provenance() {
  local directory=$1 source_run=$2
  test -f "${directory}/provenance.json" || return 1
  jq -e --arg image "${image_sha}" --arg manifest "${manifest_sha}" \
    --arg summary "$(sha256sum "${source_run}/summary.json" | cut -d ' ' -f 1)" \
    --arg audit "$(sha256sum "${source_run}/independent_audit.json" | cut -d ' ' -f 1)" \
    '.simv_sha256 == $image and .source_manifest_sha256 == $manifest and
     .summary_sha256 == $summary and .audit_sha256 == $audit' \
    "${directory}/provenance.json" >/dev/null
}
for i in "${!sources[@]}"; do
  source=${sources[i]}
  run="verification/out/${source}"
  test "$(jq -r .status "${run}/independent_audit.json")" = PASS
  mapfile -t all_names < <(jq -r '.[].artifact_dir | split("/")[-1]' \
    "${run}/summary.json")
  if (( i == 0 || i >= 4 )); then
    first=${all_names[0]}
    # A stage-1 case can refer to an audited preflight outside stage1's tree.
    first_result=$(jq -er --arg name "${first}" \
      '.cases[] | select(.name == $name and .status == "PASS") | .result' \
      "${stage1}/${source}/case_replay.json")
    jq -e --arg path "${first_result}" 'any(.cases[]; .result == $path)' \
      "${stage1}/merged/audit.json" >/dev/null
    names=("${all_names[@]:1}")
  else
    names=("${all_names[@]}")
  fi
  test "${#names[@]}" -eq "${expected[i]}"
  args=()
  for name in "${names[@]}"; do
    key="${source}/${name}"
    test -z "${seen_cases[${key}]+present}"
    seen_cases["${key}"]=1
    elf="${run}/tests/${name}/input.elf"
    test -f "${elf}"
    elf_sha=$(sha256sum "${elf}" | cut -d ' ' -f 1)
    test -z "${seen_elf_hashes[${elf_sha}]+present}"
    seen_elf_hashes["${elf_sha}"]=1
    args+=(--case-name "${name}")
  done
  target="${out}/${source}"
  if [[ ! -e "${target}" ]]; then
    "${python}" verification/coverage/run_directed_coverage.py \
      --random-source --summary "${run}/summary.json" \
      --audit "${run}/independent_audit.json" "${args[@]}" \
      --simv "${simv}" --source-manifest "${manifest}" \
      --verilator-coverage "${reporter}" --ram-bytes 2097152 \
      --jobs 4 --term-cycles 250000 --timeout 3600 --output "${target}"
  fi
  roots=()
  if [[ -f "${target}/provenance.json" ]]; then
    check_provenance "${target}" "${run}"
    roots+=("${target}")
  fi
  for retry in "${target}"/retry_*; do
    [[ -d "${retry}" ]] || continue
    if [[ -f "${retry}/provenance.json" ]]; then
      check_provenance "${retry}" "${run}"
      roots+=("${retry}")
    fi
  done
  missing=()
  for name in "${names[@]}"; do
    passed=""
    for root_dir in "${roots[@]}"; do
      candidate="${root_dir}/${name}/result.json"
      [[ -f "${candidate}" ]] || continue
      if jq -e --arg image "${image_sha}" \
        '.status == "PASS" and .simv_sha256 == $image' "${candidate}" >/dev/null; then
        passed="${candidate}"
        break
      fi
      echo "coverage case failed; diagnose before retrying: ${candidate}" >&2
      exit 1
    done
    if [[ -n ${passed} ]]; then
      results+=("${passed}")
    else
      missing+=("${name}")
    fi
  done
  if (( ${#missing[@]} > 0 )); then
    retry_index=1
    while [[ -e "${target}/retry_${retry_index}" ]]; do
      ((retry_index += 1))
    done
    retry_args=()
    for name in "${missing[@]}"; do retry_args+=(--case-name "${name}"); done
    retry="${target}/retry_${retry_index}"
    "${python}" verification/coverage/run_directed_coverage.py \
      --random-source --summary "${run}/summary.json" \
      --audit "${run}/independent_audit.json" "${retry_args[@]}" \
      --simv "${simv}" --source-manifest "${manifest}" \
      --verilator-coverage "${reporter}" --ram-bytes 2097152 \
      --jobs 4 --term-cycles 250000 --timeout 3600 --output "${retry}"
    for name in "${missing[@]}"; do
      results+=("${retry}/${name}/result.json")
    done
  fi
done
test "${#results[@]}" -eq 64

merge=("${python}" verification/coverage/merge_verilator_coverage.py \
  --extend-audit "${stage1}/merged/audit.json")
for result in "${results[@]}"; do merge+=(--case "${result}"); done
"${merge[@]}" --output "${out}/merged" --verilator-coverage "${reporter}" \
  --report-timeout 600
"${python}" verification/coverage/audit_merged.py \
  --audit "${out}/merged/audit.json" --minimum-cases 76 \
  --report "${out}/merged/independent_audit.json"
"${python}" verification/coverage/review_uncovered.py \
  --audit "${out}/merged/audit.json" --minimum-cases 76 \
  --output "${out}/merged/review.json"
