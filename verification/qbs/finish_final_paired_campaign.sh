#!/usr/bin/env bash
set -euo pipefail

root=$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/../.." && pwd)
source_root=/home/wangwy/openproject/ara_dsa_verification
image="${root}/verification/out/final-qbs-akv-16m-image-20260924-01"
output="${root}/verification/out/final-qbs-akv-pairs-20260924-01"
manifest="${source_root}/verification/qbs/paired_campaign_20260923_with_prefill.json"
runner="${source_root}/verification/qbs/rerun_paired_campaign.py"
unit=ara-dsa-final-qbs-akv-16m-compile-20260924-01.service

while systemctl --user is-active --quiet "${unit}"; do
  sleep 60
done

simv="${image}/sim/simv"
conf="${image}/sim/simulator.conf"
test -x "${simv}"
test -f "${conf}"
rg -q '^qbs=1$' "${conf}"
rg -q '^akv_v2=1$' "${conf}"
rg -q '^sim_l2_mb=16$' "${conf}"
PYTHONPATH="${root}/verification" python3 -m ara_verify.vcs_source_manifest \
  --output "${image}/sim/vcs_source_manifest.json" --check
test ! -e "${output}"

python3 "${runner}" --source-manifest "${manifest}" \
  --simv "${simv}" --output "${output}" --timeout-seconds 3600 \
  --jobs 3 --plan-only
python3 "${runner}" --source-manifest "${manifest}" \
  --simv "${simv}" --output "${output}" --timeout-seconds 3600 \
  --jobs 3 --resume

test "$(jq -r .status "${output}/plan.json")" = PASS
test "$(jq -r .status "${output}/audit.json")" = PASS
test "$(jq -r .image_match "${output}/audit.json")" = true
