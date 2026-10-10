#!/usr/bin/env bash
set -euo pipefail

root=$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/../.." && pwd)
out=$(realpath -m -- "${1:?usage: run_representative_matrix.sh OUTPUT_ROOT SIMV}")
simv=$(realpath -m -- "${2:?usage: run_representative_matrix.sh OUTPUT_ROOT SIMV}")
inputs=${out}/inputs
reporter=${root}/install/verilator/bin/verilator_coverage

test -x "${simv}"
test -x "${reporter}"
for elf in llama_qwen25_q4_0_decode_attn_q_rvv \
           llama_qwen25_q4_0_decode_attn_q_qbs akv_column_coverage_smoke; do
  test -f "${inputs}/${elf}"
done
(cd -- "${out}" && sha256sum --status --check \
  "${root}/verification/coverage/representative_inputs.sha256")

"${root}/verification/tools/soc-venv/bin/python" \
  "${root}/verification/coverage/check_elf_fit.py" \
  --elf "${inputs}/llama_qwen25_q4_0_decode_attn_q_rvv" \
  --elf "${inputs}/llama_qwen25_q4_0_decode_attn_q_qbs" \
  --elf "${inputs}/akv_column_coverage_smoke" \
  --ram-bytes 1048576 --ram-word-bytes 16 --output "${out}/elf_fit.json"

for entry in \
  rvv-q4-0:llama_qwen25_q4_0_decode_attn_q_rvv \
  qbs-q4-0:llama_qwen25_q4_0_decode_attn_q_qbs \
  akv-v2:akv_column_coverage_smoke; do
  name=${entry%%:*}
  elf=${entry#*:}
  python3 "${root}/verification/coverage/run_verilator_coverage.py" \
    --simv "${simv}" --elf "${inputs}/${elf}" \
    --output "${out}/${name}" --verilator-coverage "${reporter}" \
    --term-cycles 2000000 --timeout 900
done

python3 "${root}/verification/coverage/merge_verilator_coverage.py" \
  --case "${out}/rvv-q4-0/result.json" \
  --case "${out}/qbs-q4-0/result.json" \
  --case "${out}/akv-v2/result.json" \
  --output "${out}/merged" --verilator-coverage "${reporter}" \
  --hierarchy-prefix ara_tb_verilator.dut.i_ara_soc \
  --include-path /hardware/src/ --include-path /hardware/deps/cva6/

python3 "${root}/verification/coverage/audit_merged.py" \
  --audit "${out}/merged/audit.json" --minimum-cases 3 \
  --report "${out}/merged/integrity_audit.json"

python3 "${root}/verification/coverage/review_uncovered.py" \
  --audit "${out}/merged/audit.json" --minimum-cases 3 \
  --output "${out}/merged/review.json"
