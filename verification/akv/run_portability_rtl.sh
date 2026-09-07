#!/usr/bin/env bash
set -euo pipefail

root=$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/../.." && pwd)
tag=${AKV_PORTABLE_TAG:-$(date +%Y%m%d_%H%M%S)}
[[ ${tag} =~ ^[A-Za-z0-9_-]+$ ]] || exit 2
run=${root}/hardware/qbs_akv_portability_runs/${tag}
mkdir -p "$(dirname -- "${run}")"
mkdir "${run}"
exec > "${run}/job.log" 2>&1
printf '%s\n' "$$" > "${run}/pid"
date -Iseconds > "${run}/started_at"
trap 'rc=$?; printf "%s\n" "$rc" > "${run}/exit_code"; if (( rc != 0 )); then printf "FAIL\n" > "${run}/status"; fi; date -Iseconds > "${run}/finished_at"' EXIT
git -C "${root}" rev-parse HEAD > "${run}/git_head"
git -C "${root}" diff --binary HEAD > "${run}/tracked.patch"
tar -C "${root}" --exclude=build --exclude='rtl_*build' --exclude='*.o' --exclude='*.dump' \
  -czf "${run}/software_snapshot.tar.gz" software/akv software/qbs \
  apps/akv_portability_smoke apps/qbs_akv_handoff_smoke verification/akv

printf 'BUILDING\n' > "${run}/status"
make -C "${root}/apps" akv_portability_smoke qbs_akv_handoff_smoke \
  -W akv_portability_smoke/runtime.c sim_l2_mb=16 > "${run}/apps.log" 2>&1
cp "${root}/apps/bin/akv_portability_smoke" "${run}/portable.elf"
cp "${root}/apps/bin/qbs_akv_handoff_smoke" "${run}/handoff.elf"
if [[ -n ${AKV_PORTABLE_SIM_DIR:-} ]]; then
  test -x "${AKV_PORTABLE_SIM_DIR}/simv"
  bash "${root}/hardware/scripts/llama_q4km_extract/check-sim-l2.sh" \
    "${AKV_PORTABLE_SIM_DIR}" "${run}/portable.elf" akv_v2_portable > "${run}/sim-reuse.conf"
  ln -s "$(realpath "${AKV_PORTABLE_SIM_DIR}")" "${run}/sim"
else
  make -C "${root}/hardware" compile qbs=1 akv_v2=1 no_fsdb=1 \
    sim_l2_mb=16 nr_lanes=4 vlen=1024 \
    sim_dir="qbs_akv_portability_runs/${tag}/sim" \
    buildpath="${run}/build" > "${run}/compile.log" 2>&1
fi
sha256sum "${run}"/*.elf "${run}/sim/simv" \
  "${run}/sim/simulator.conf" > "${run}/binaries.sha256"

for name in portable handoff; do
  printf 'RUNNING_%s\n' "${name}" > "${run}/status"
  mkdir "${run}/${name}"
  set +e
  (
    cd "${run}/${name}"
    timeout --foreground "${AKV_PORTABLE_RTL_TIMEOUT:-1800}" "${run}/sim/simv" -no_save -l run.vcs.log \
      "+PRELOAD=${run}/${name}.elf" "+TESTCASE=akv_${name}" \
      +NO_FSDB +QBS_PERF +AKV_PERF
  ) > "${run}/${name}/console.log" 2>&1
  rc=$?
  set -e
  printf '%s\n' "${rc}" > "${run}/${name}/exit_code"
  marker='AKV native portability smoke: PASS'
  if [[ ${name} == handoff ]]; then marker='QBS/AKV handoff smoke: PASS traps=0'; fi
  log=${run}/${name}/run.vcs.log
  if [[ ${rc} -ne 0 ]] || ! grep -qF "${marker}" "${log}" ||
     ! grep -q 'Core Test \*\*\* SUCCESS' "${log}" ||
     grep -Eq 'Fatal:|Error:|^\[(QBS|AKV)_PERF\].*(success=0|fault=1)' "${log}"; then
    printf 'FAIL_%s\n' "${name}" > "${run}/status"
    exit 1
  fi
  if [[ ${name} == handoff ]]; then
    [[ $(grep -c '^\[QBS_PERF\] ' "${log}") -eq 4 ]]
    [[ $(grep -c '^\[AKV_PERF\] ' "${log}") -eq 10 ]]
  fi
  printf 'PASS\n' > "${run}/${name}/status"
done
printf 'PASS\n' > "${run}/status"
