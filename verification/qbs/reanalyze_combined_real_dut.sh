#!/usr/bin/env bash
set -euo pipefail

root=$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/../.." && pwd)
out=$(realpath -- "${1:?usage: reanalyze_combined_real_dut.sh EXISTING_OUTPUT_DIR}")
checker="${root}/verification/qbs/check_combined_real_evidence.py"
if [[ ! -f ${out}/INPUT_SHA256SUMS || ! -f ${out}/uvm_result.json ||
      ! -f ${out}/work/run.vcs.log || ! -f ${out}/work/vector_trace.csv ]]; then
  printf 'incomplete original VCS evidence: %s\n' "${out}" >&2
  exit 2
fi

# The original checker expected an optional AKV summary. Verify every frozen
# simulation input while recording the corrected checker as a new analysis.
awk -v checker="${checker}" '$2 != checker {print}' \
  "${out}/INPUT_SHA256SUMS" | (cd -- "${out}" && sha256sum -c --status)
python3 "${checker}" --log "${out}/work/run.vcs.log" \
  --output "${out}/combined_result.json"
(
  cd -- "${out}"
  sha256sum -- "${checker}" work/run.vcs.log work/vector_trace.csv \
    work/console.log work/input.elf uvm_result.json combined_result.json \
    INPUT_SHA256SUMS > POSTPROCESS_SHA256SUMS
  sha256sum -c --status POSTPROCESS_SHA256SUMS
)
printf 'reanalysis sealed: %s\n' "${out}/POSTPROCESS_SHA256SUMS"
