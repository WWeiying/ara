#!/usr/bin/env bash
set -euo pipefail
root=$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/../.." && pwd)
out=$(realpath -m -- "${1:?usage: divsqrt_multifmt_status_run.sh NEW_OUTPUT_DIR FULL_FILELIST [PLUSARGS...]}")
filelist=$(realpath -- "${2:?missing full filelist}")
shift 2
for arg in "$@"; do
  if [[ "$arg" == +EXPECT_OLD_BUG* ]]; then
    echo "historical bug reproduction is not a signoff pass mode" >&2
    exit 2
  fi
done
tb="${root}/verification/uvm/divsqrt_multifmt_status_tb.sv"
verify_root="${root}"
test ! -e "${out}"
mkdir -p "${out}"
cd "${out}"
cp -- "${filelist}" full_filelist.f
PYTHONPATH="${verify_root}/verification" python3 -m ara_verify.vcs_source_manifest \
  --filelist "${out}/full_filelist.f" --repo-root "${root}" --extra-source "${tb}" \
  --extra-source "${root}/verification/uvm/divsqrt_multifmt_status_run.sh" \
  --output "${out}/sources.json" > sources.capture.log
timeout --foreground --kill-after=10s 180s vcs \
  -full64 -sverilog -assert svaext -timescale=1ns/1ps \
  +define+SIMULATION +define+ARA_NO_FSDB \
  -top divsqrt_multifmt_status_tb -f full_filelist.f "${tb}" \
  -o simv -l compile.log > compile.console.log 2>&1
set +e
timeout --foreground --kill-after=10s 30s ./simv "$@" -l run.log > run.console.log 2>&1
run_rc=$?
set -e
printf '%s\n' "${run_rc}" > run.exitcode
sha256sum simv > binary.sha256
PYTHONPATH="${verify_root}/verification" python3 -m ara_verify.vcs_source_manifest \
  --output "${out}/sources.json" --check > sources.check.log
rg '^(CONFIG|RESULT|ARCH_FAIL|SUMMARY|REPRODUCED|PASS)' run.log || true
if (( run_rc != 0 )); then exit "${run_rc}"; fi
rg '^PASS divsqrt_multifmt_status$' run.log
if rg 'Error:|Fatal:|Error-|Fatal-|CHECK_FAIL|ARCH_FAIL|REPRODUCED|Assertion.*failed' compile.log run.log; then exit 1; fi
