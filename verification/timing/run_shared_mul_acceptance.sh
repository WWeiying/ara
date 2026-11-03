#!/usr/bin/env bash
# Run prebuilt local tests, then launch source-frozen DC only after acceptance.
set -euo pipefail
ROOT=$(realpath "$1")
TEST=$(realpath "$2")
PPA=$(realpath -m "$3")
STATE="$TEST/acceptance.status"
trap 'rc=$?; if ((rc != 0)); then printf "FAILED exit=%s\n" "$rc" > "$STATE"; fi' EXIT
cd "$ROOT"
sha256sum --quiet -c "$TEST/acceptance.sha256"
test ! -e "$PPA"
grep -q 'Shared MUL stream PASS' "$TEST/bank/run.log"
! grep -Eq 'Fatal:|Error:' "$TEST/bank/run.log"
printf 'VCS_RUNNING\n' > "$STATE"
run_case() {
    local name=$1 marker=$2
    cd "$TEST/$name"
    # Preserve the original 300-second run. Reuse its exact compiled image.
    timeout --foreground --kill-after=30s 1200 ./simv -l acceptance_run.log > acceptance_console.log 2>&1
    grep -q "$marker" acceptance_run.log
    ! grep -Eq 'Fatal:|Error:' acceptance_run.log
}
run_case product 'Shared signed product PASS checks=425280' &
product_pid=$!
run_case mul 'SIMD MUL equivalence PASS configurations=24' &
mul_pid=$!
wait "$product_pid"
wait "$mul_pid"
sha256sum --quiet -c "$TEST/acceptance.sha256"
printf 'VCS_PASS_DC_LAUNCHING\n' > "$STATE"
python3 "$ROOT/verification/timing/run_shared_mul_ppa.py" "$PPA"
cp "$ROOT/verification/timing/collect_shared_mul_ppa.py" "$PPA/collect_frozen.py"
systemd-run --user --unit="shared-mul-collect-$(basename "$PPA")" \
    --property="StandardOutput=append:$PPA/collector.log" \
    --property="StandardError=append:$PPA/collector.log" \
    /usr/bin/python3 "$PPA/collect_frozen.py" "$PPA" --wait
printf 'VCS_PASS_DC_DISPATCHED\n' > "$STATE"
