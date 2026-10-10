#!/usr/bin/env bash
set -euo pipefail

root=$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/../.." && pwd)
out=$(realpath -m -- "${1:?usage: run_exit_latch_matrix.sh OUTPUT_ROOT SIMV}")
simv=$(realpath -e -- "${2:?usage: run_exit_latch_matrix.sh OUTPUT_ROOT SIMV}")
reporter=${root}/install/verilator/bin/verilator_coverage
build=${root}/verification/out/verilator-coverage-exit-latch-20260924-01
test -x "${simv}"
test -x "${reporter}"
test ! -e "${out}"
mkdir -p "${out}/inputs"

source_rvv=${root}/verification/out/rvv-waw-div-uvm-delay-image-20260924-01/matrix/rvv
source_qbs=${root}/verification/out/coverage-smoke-qbs-vcs-20260924-01
source_akv=${root}/verification/out/coverage-smoke-akv-minimal-vcs-20260924-01
expected_vcs_image=""
for entry in "rvv:${source_rvv}" "qbs:${source_qbs}" "akv:${source_akv}"; do
  name=${entry%%:*}
  source_case=${entry#*:}
  (cd -- "${source_case}" && sha256sum --status --check INPUT_SHA256SUMS &&
    sha256sum --status --check RUN_SHA256SUMS)
  image=$(python3 - "${source_case}" <<'PY'
import hashlib
import json
import sys
from pathlib import Path

case = Path(sys.argv[1])
record = json.loads((case / "uvm_result.json").read_text())
elf = case / "work" / "input.elf"
if record.get("status") != "PASS" or not elf.is_file():
    raise SystemExit(f"VCS/UVM source case is not PASS: {case}")
if hashlib.sha256(elf.read_bytes()).hexdigest() != record.get("elf_sha256"):
    raise SystemExit(f"VCS/UVM source ELF hash differs: {case}")
print(record["simv_sha256"])
PY
  )
  if [[ -n ${expected_vcs_image} && ${image} != "${expected_vcs_image}" ]]; then
    printf 'VCS cases use different images: %s\n' "${source_case}" >&2
    exit 1
  fi
  expected_vcs_image=${image}
  cp -- "${source_case}/work/input.elf" "${out}/inputs/${name}.elf"
  cp -- "${source_case}/uvm_result.json" "${out}/inputs/${name}.uvm_result.json"
  test "$(sha256sum "${source_case}/work/input.elf" | cut -d ' ' -f 1)" = \
       "$(sha256sum "${out}/inputs/${name}.elf" | cut -d ' ' -f 1)"
done

cp -- "${build}/source_manifest.json" "${out}/source_manifest.json"
python3 "${root}/verification/coverage/build_provenance.py" \
  --output "${out}/source_manifest.json" --check
"${root}/verification/tools/soc-venv/bin/python" \
  "${root}/verification/coverage/check_elf_fit.py" \
  --elf "${out}/inputs/rvv.elf" \
  --elf "${out}/inputs/qbs.elf" \
  --elf "${out}/inputs/akv.elf" \
  --ram-bytes 1048576 --ram-word-bytes 16 --output "${out}/elf_fit.json"

for name in rvv qbs akv; do
  python3 "${root}/verification/coverage/run_verilator_coverage.py" \
    --simv "${simv}" --elf "${out}/inputs/${name}.elf" \
    --output "${out}/${name}" --verilator-coverage "${reporter}" \
    --term-cycles 20000 --timeout 1200
done

python3 "${root}/verification/coverage/merge_verilator_coverage.py" \
  --case "${out}/rvv/result.json" \
  --case "${out}/qbs/result.json" \
  --case "${out}/akv/result.json" \
  --output "${out}/merged" --verilator-coverage "${reporter}" \
  --hierarchy-prefix ara_tb_verilator.dut.i_ara_soc \
  --include-path /hardware/src/ --include-path /hardware/deps/cva6/
python3 "${root}/verification/coverage/audit_merged.py" \
  --audit "${out}/merged/audit.json" --minimum-cases 3 \
  --report "${out}/merged/integrity_audit.json"
python3 "${root}/verification/coverage/review_uncovered.py" \
  --audit "${out}/merged/audit.json" --minimum-cases 3 \
  --output "${out}/merged/review.json"
