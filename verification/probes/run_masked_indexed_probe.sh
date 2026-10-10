#!/usr/bin/env bash
set -euo pipefail

root=$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/../.." && pwd)
build_unit=ara-dsa-masked-indexed-probe-build-20260924-01.service
build=${root}/verification/out/rvv-masked-indexed-probe-image-20260924-01/_build/vcs/simv
source_elf=${1:-${root}/verification/out/rvv-masked-indexed-alignment-prefx-20260924-01/tests/rvv_vmasked_indexed_alignment/input.elf}
testcase=${2:-rv64uv-ara-vmasked_indexed_alignment}
out=${3:-${root}/verification/out/rvv-masked-indexed-probe-run-20260924-02}
expected=${4:-}

while :; do
  state=$(systemctl --user show "${build_unit}" -p ActiveState --value)
  case "${state}" in
    active|activating) sleep 60 ;;
    inactive|failed) break ;;
    *) printf 'unexpected build state: %s\n' "${state}" >&2; exit 1 ;;
  esac
done
test "$(systemctl --user show "${build_unit}" -p Result --value)" = success
test -x "${build}"
test ! -e "${out}"
mkdir -p "${out}"
cp -- "${build}" "${out}/simv"
cp -a --reflink=auto -- "${build}.daidir" "${out}/simv.daidir"
cp -- "${source_elf}" "${out}/input.elf"
(cd -- "${out}" && sha256sum simv input.elf > INPUT_SHA256SUMS)
(cd -- "${out}" && find simv.daidir -type f -print0 | sort -z |
  xargs -0 sha256sum >> INPUT_SHA256SUMS)
set +e
(cd -- "${out}" && timeout 120 ./simv -l run.vcs.log +ntb_random_seed=1 \
  +PRELOAD="${out}/input.elf" +TESTCASE="${testcase}" \
  +NO_FSDB +ARA_DEBUG_MASK_QUEUE_ALL \
  +COMMIT_TRACE="${out}/commit_trace.csv" > console.log 2>&1)
sim_status=$?
set -e
(cd -- "${out}" && sha256sum --status --check INPUT_SHA256SUMS)
rg '^\[MASKED_IDX_PROBE\]' "${out}/console.log" > "${out}/probe.log" || true
rg '^\[ARA_MASK_QUEUE_ALL\]' "${out}/console.log" > "${out}/mask_queue.log" || true
printf '%d\n' "${sim_status}" > "${out}/sim_exit_code.txt"
if [[ -n ${expected} ]]; then
  rg -q -- "${expected}" "${out}/console.log"
fi
printf 'sim exit=%d, focused cycle records=%s: %s\n' \
  "${sim_status}" "$(wc -l < "${out}/probe.log")" "${out}"
exit "${sim_status}"
