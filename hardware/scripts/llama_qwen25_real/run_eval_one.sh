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

mkdir -p "${run_dir}"
cd "${run_dir}"

printf '%s\n' "$$" > worker_pid
date --iso-8601=seconds > started_at
set +e
./simv -no_save -l run.vcs.log \
  "+PRELOAD=${app_bin}" "+TESTCASE=llama_qwen25_${case_id}" +NO_FSDB \
  > console.log 2>&1
return_code=$?
set -e
printf '%s\n' "${return_code}" > exit_code
date --iso-8601=seconds > finished_at

perf_log="perf_report_llama_qwen25_${case_id}.log"
metrics_log="llm_perf_report_llama_qwen25_${case_id}.log"
status=FAIL
if [[ ${return_code} -eq 0 ]] &&
   grep -q "REAL_BENCH case=${case_id} result=PASS" run.vcs.log &&
   grep -q 'Core Test \*\*\* SUCCESS' run.vcs.log &&
   [[ -s "${perf_log}" ]] && [[ -s "${metrics_log}" ]]; then
  status=PASS
fi
printf '%s\n' "${status}" > status

if [[ -s "${perf_log}" ]]; then
  "${script_dir}/summarize.py" \
    --run-log run.vcs.log --perf-log "${perf_log}" --output result.csv \
    > summarize.log 2>&1 || true
fi
if [[ -s "${metrics_log}" ]]; then
  "${script_dir}/summarize_llm_perf.py" \
    --metrics-log "${metrics_log}" --output metrics.csv \
    >> summarize.log 2>&1 || true
fi

exit "${return_code}"
