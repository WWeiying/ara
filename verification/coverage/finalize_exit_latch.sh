#!/usr/bin/env bash
set -euo pipefail

root=$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/../.." && pwd)
build_unit=ara-dsa-verilator-coverage-exit-latch-build-20260924-01.service
build=${root}/verification/out/verilator-coverage-exit-latch-20260924-01
out=${root}/verification/out/verilator-coverage-signoff-matrix-20260924-01

while :; do
  state=$(systemctl --user show "${build_unit}" -p ActiveState --value)
  case "${state}" in
    active|activating) sleep 60 ;;
    inactive|failed) break ;;
    *) printf 'unexpected build state: %s\n' "${state}" >&2; exit 1 ;;
  esac
done
test "$(systemctl --user show "${build_unit}" -p Result --value)" = success
test -f "${build}/source_manifest.json"
(cd -- "${build}" && sha256sum --status --check simv.sha256)

bash "${root}/verification/coverage/run_exit_latch_matrix.sh" \
  "${out}" "${build}/build/verilator/Vara_tb_verilator"
