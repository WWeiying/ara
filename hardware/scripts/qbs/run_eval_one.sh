#!/usr/bin/env bash
set -u

if [[ $# -ne 3 ]]; then
  echo "usage: $0 <case> <run-dir> <app-bin>" >&2
  exit 2
fi

case_id=$1
run_dir=$(realpath "$2")
app_bin=$(realpath "$3")
script_dir=$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)
real_script_dir=$(cd -- "${script_dir}/../llama_qwen25_real" && pwd)

mkdir -p "${run_dir}"
cd "${run_dir}"

printf '%s\n' "$$" > worker_pid
date --iso-8601=seconds > started_at
set +e
./simv -no_save -l run.vcs.log \
  "+PRELOAD=${app_bin}" "+TESTCASE=llama_qwen25_${case_id}" \
  +NO_FSDB +QBS_PERF > console.log 2>&1
return_code=$?
set -e
printf '%s\n' "${return_code}" > exit_code
date --iso-8601=seconds > finished_at

perf_log="perf_report_llama_qwen25_${case_id}.log"
metrics_log="llm_perf_report_llama_qwen25_${case_id}.log"
status=FAIL
if [[ ${return_code} -eq 0 ]] &&
   grep -q "QBS_REAL_BENCH case=${case_id} result=PASS" run.vcs.log &&
   grep -q 'Core Test \*\*\* SUCCESS' run.vcs.log &&
   [[ -s "${perf_log}" ]] && [[ -s "${metrics_log}" ]]; then
  status=PASS
fi
printf '%s\n' "${status}" > status

: > summarize.log
if [[ -s "${perf_log}" ]]; then
  "${script_dir}/summarize_qbs_run.py" \
    --run-log run.vcs.log --perf-log "${perf_log}" --output result.csv \
    >> summarize.log 2>&1 || true
fi
if [[ -s "${metrics_log}" ]]; then
  "${real_script_dir}/summarize_llm_perf.py" \
    --metrics-log "${metrics_log}" --output metrics.csv \
    >> summarize.log 2>&1 || true
fi
if grep -q '^\[QBS_PERF\] ' run.vcs.log; then
  "${script_dir}/summarize_qbs_perf.py" \
    --log run.vcs.log --case "${case_id}" --output qbs_perf.csv \
    --commands-output qbs_commands.csv >> summarize.log 2>&1 || true
fi

if [[ "${status}" == PASS ]] &&
   [[ ! -s result.csv || ! -s metrics.csv || ! -s qbs_perf.csv ]]; then
  printf '%s\n' FAIL > status
  return_code=1
fi
exit "${return_code}"
