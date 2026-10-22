#!/usr/bin/env bash
set -euo pipefail

root=$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/../.." && pwd)
out=${1:-"${root}/verification/out/masked-indexed-skip-probe-20260924-01"}
test ! -e "${out}"
mkdir -p "${out}/build" "${out}/sim" "${out}/load" "${out}/store"

make -C "${root}/hardware" compile \
  buildpath="${out}/build" sim_dir="${out}/sim" \
  qbs=1 akv=1 akv_v2=1 no_fsdb=1 \
  verify_extra_sources="${root}/verification/probes/masked_indexed_vlsu_probe.sv" \
  > "${out}/compile.log" 2>&1

load_elf="${root}/verification/out/masked-indexed-fix-load-20260924-02/tests/rvv_vmasked_indexed_alignment/input.elf"
store_elf="${root}/verification/out/masked-indexed-fix-store-20260924-01/tests/rvv_vmasked_indexed_store_alignment/input.elf"
sha256sum "${out}/sim/simv" "${load_elf}" "${store_elf}" \
  "${root}/verification/probes/masked_indexed_vlsu_probe.sv" \
  "${root}/hardware/src/vlsu/addrgen.sv" \
  "${root}/hardware/src/vlsu/vldu.sv" \
  "${root}/hardware/src/vlsu/vstu.sv" > "${out}/inputs.sha256"

for kind in load store; do
  if [[ ${kind} == load ]]; then
    elf=${load_elf}
    testcase=rv64uv-ara-vmasked_indexed_alignment
  else
    elf=${store_elf}
    testcase=rv64uv-ara-vmasked_indexed_store_alignment
  fi
  cp -- "${elf}" "${out}/${kind}/input.elf"
  (
    cd -- "${out}/${kind}"
    timeout 300 "${out}/sim/simv" -l run.vcs.log +ntb_random_seed=1 \
      "+PRELOAD=${out}/${kind}/input.elf" "+TESTCASE=${testcase}" \
      +NO_FSDB "+COMMIT_TRACE=${out}/${kind}/commit_trace.csv" \
      > console.log 2>&1
    rg -q '^PASSED:' run.vcs.log
    rg '^\[MASKED_IDX_PROBE\]' console.log > probe.log
    rg -q 'desc=1 skip=1' probe.log
  )
done

sha256sum --check "${out}/inputs.sha256" > "${out}/hash_check.log"
printf 'PASS: both directed cases completed with skip descriptors and no probe assertion\n' \
  > "${out}/result.txt"
