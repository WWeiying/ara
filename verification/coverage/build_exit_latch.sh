#!/usr/bin/env bash
set -euo pipefail

root=$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/../.." && pwd)
source_build=${root}/verification/out/verilator-coverage-waw-div-20260924-01/build
out=$(realpath -m -- "${1:?usage: build_exit_latch.sh OUTPUT_ROOT}")
test -x "${source_build}/verilator/Vara_tb_verilator"
test ! -e "${out}"
mkdir -p "${out}"
cp -a --reflink=auto -- "${source_build}" "${out}/build"

make -C "${root}/hardware" verilate \
  buildpath="${out}/build" qbs=1 akv=1 akv_v2=1 \
  veril_coverage=1 veril_cxx_opt=-O0 veril_jobs=16

python3 "${root}/verification/coverage/build_provenance.py" \
  --filelist "${out}/build/verilator/bender_script_default" \
  --repo-root "${root}" --build-dir "${out}/build/verilator" \
  --output "${out}/source_manifest.json"
python3 "${root}/verification/coverage/build_provenance.py" \
  --output "${out}/source_manifest.json" --check
sha256sum "${out}/build/verilator/Vara_tb_verilator" > "${out}/simv.sha256"
