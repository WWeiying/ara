#!/usr/bin/env bash
set -euo pipefail

script_dir=$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)
repo_root=$(cd -- "${script_dir}/../.." && pwd)
simv=${QBS_AKV_SIMV:?set QBS_AKV_SIMV to a QBS+AKV-v2 top-level simv}
sim_l2_mb=${QBS_AKV_SIM_L2_MB:-16}
run_timeout=${QBS_AKV_TIMEOUT:-600}
run_root=${QBS_AKV_RUN_ROOT:-${repo_root}/hardware/qbs_akv_current_runs/handoff}
stamp=$(date +%Y%m%d_%H%M%S)
run_dir=${run_root}/qbs_akv_handoff_${stamp}
elf=${repo_root}/apps/bin/qbs_akv_handoff_smoke
sim_dir=$(cd -- "$(dirname -- "${simv}")" && pwd)
simv=${sim_dir}/$(basename -- "${simv}")
sim_config=${sim_dir}/simulator.conf

test -x "${simv}"
test -f "${sim_config}"
grep -qx 'nr_lanes=4' "${sim_config}"
grep -qx 'vlen=1024' "${sim_config}"
grep -qx 'qbs=1' "${sim_config}"
grep -qx 'akv_v2=1' "${sim_config}"

make -C "${repo_root}/apps" qbs_akv_handoff_smoke \
  sim_l2_mb="${sim_l2_mb}"
test -s "${elf}"

mkdir -p "${run_dir}"
{
  printf 'schema_version=1\n'
  printf 'test=qbs_akv_handoff_smoke\n'
  printf 'git_head=%s\n' "$(git -C "${repo_root}" rev-parse HEAD)"
  printf 'simv=%s\n' "${simv}"
  printf 'simv_sha256=%s\n' "$(sha256sum "${simv}" | awk '{print $1}')"
  printf 'simulator_config_sha256=%s\n' \
    "$(sha256sum "${sim_config}" | awk '{print $1}')"
  printf 'elf=%s\n' "${elf}"
  printf 'elf_sha256=%s\n' "$(sha256sum "${elf}" | awk '{print $1}')"
  printf 'timeout_seconds=%s\n' "${run_timeout}"
} > "${run_dir}/run.conf"
cp "${sim_config}" "${run_dir}/simulator.conf"

set +e
(
  cd "${run_dir}"
  timeout --foreground "${run_timeout}" "${simv}" -no_save \
    -l run.vcs.log "+PRELOAD=${elf}" +TESTCASE=qbs_akv_handoff_smoke \
    +NO_FSDB +QBS_PERF +AKV_PERF
) > "${run_dir}/console.log" 2>&1
rc=$?
set -e
printf '%s\n' "${rc}" > "${run_dir}/exit_code"

log=${run_dir}/run.vcs.log
qbs_commands=$(grep -c '^\[QBS_PERF\] ' "${log}" || true)
akv_commands=$(grep -c '^\[AKV_PERF\] ' "${log}" || true)
status=FAIL
if [[ ${rc} -eq 0 && ${qbs_commands} -eq 4 && ${akv_commands} -eq 10 ]] &&
   grep -q '^QBS/AKV handoff smoke: PASS traps=0$' "${log}" &&
   grep -q 'Core Test \*\*\* SUCCESS' "${log}" &&
   ! grep -Eq '^\[(QBS|AKV)_PERF\].*(success=0|fault=1)' "${log}" &&
   ! grep -Eq 'Fatal:|Error:' "${log}"; then
  status=PASS
fi

{
  printf 'status=%s\n' "${status}"
  printf 'qbs_commands=%s\n' "${qbs_commands}"
  printf 'akv_commands=%s\n' "${akv_commands}"
} > "${run_dir}/summary.txt"
printf '%s\n' "${status}" > "${run_dir}/status"
ln -sfn "$(basename -- "${run_dir}")" "${run_root}/latest"

printf 'QBS/AKV integration handoff: %s\n' "${status}"
printf '  run: %s\n' "${run_dir}"
printf '  commands: QBS=%s AKV=%s\n' "${qbs_commands}" "${akv_commands}"
[[ ${status} == PASS ]]
