#!/usr/bin/env bash
set -euo pipefail

root=$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/../.." && pwd)
out=$(realpath -m -- "${1:?usage: run_short_matrix.sh OUTPUT_ROOT SIMV}")
simv=$(realpath -e -- "${2:?usage: run_short_matrix.sh OUTPUT_ROOT SIMV}")
source_matrix=${root}/verification/out/rvv-waw-div-uvm-delay-image-20260924-01/matrix
reporter=${root}/install/verilator/bin/verilator_coverage

test -x "${simv}"
test -x "${reporter}"
test ! -e "${out}"
mkdir -p "${out}/inputs"

for name in rvv qbs akv-column; do
  source_case=${source_matrix}/${name}
  python3 - "${source_case}" <<'PY'
import hashlib
import json
import sys
from pathlib import Path

case = Path(sys.argv[1])
result = json.loads((case / "uvm_result.json").read_text())
elf = case / "work" / "input.elf"
if result.get("status") != "PASS" or not elf.is_file():
    raise SystemExit(f"VCS/UVM source case is not PASS: {case}")
actual = hashlib.sha256(elf.read_bytes()).hexdigest()
if actual != result.get("elf_sha256"):
    raise SystemExit(f"VCS/UVM source ELF hash differs: {case}")
PY
  cp -- "${source_case}/work/input.elf" "${out}/inputs/${name}.elf"
  test "$(sha256sum "${source_case}/work/input.elf" | cut -d ' ' -f 1)" = \
       "$(sha256sum "${out}/inputs/${name}.elf" | cut -d ' ' -f 1)"
done

cp -- "${root}/verification/out/verilator-coverage-waw-div-20260924-01/source_manifest_final.json" \
  "${out}/source_manifest.json"
python3 "${root}/verification/coverage/build_provenance.py" \
  --output "${out}/source_manifest.json" --check

"${root}/verification/tools/soc-venv/bin/python" \
  "${root}/verification/coverage/check_elf_fit.py" \
  --elf "${out}/inputs/rvv.elf" \
  --elf "${out}/inputs/qbs.elf" \
  --elf "${out}/inputs/akv-column.elf" \
  --ram-bytes 1048576 --ram-word-bytes 16 --output "${out}/elf_fit.json"

for name in rvv qbs akv-column; do
  python3 "${root}/verification/coverage/run_verilator_coverage.py" \
    --simv "${simv}" --elf "${out}/inputs/${name}.elf" \
    --output "${out}/${name}" --verilator-coverage "${reporter}" \
    --term-cycles 20000 --timeout 1200
done

python3 "${root}/verification/coverage/merge_verilator_coverage.py" \
  --case "${out}/rvv/result.json" \
  --case "${out}/qbs/result.json" \
  --case "${out}/akv-column/result.json" \
  --output "${out}/merged" --verilator-coverage "${reporter}" \
  --hierarchy-prefix ara_tb_verilator.dut.i_ara_soc \
  --include-path /hardware/src/ --include-path /hardware/deps/cva6/

python3 "${root}/verification/coverage/audit_merged.py" \
  --audit "${out}/merged/audit.json" --minimum-cases 3 \
  --report "${out}/merged/integrity_audit.json"

python3 "${root}/verification/coverage/review_uncovered.py" \
  --audit "${out}/merged/audit.json" --minimum-cases 3 \
  --output "${out}/merged/review.json"
