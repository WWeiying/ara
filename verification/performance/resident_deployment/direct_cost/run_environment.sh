#!/bin/sh
set -eu

die() { printf '%s\n' "$*" >&2; exit 1; }
[ "$#" -eq 1 ] || die "usage: sh run_environment.sh NEW_OUTPUT_DIRECTORY"
[ "$(uname -m)" = riscv64 ] || die "run on the separately deployed RISC-V board"
case "${BOARD_ID:-}" in ''|*[!A-Za-z0-9._-]*) die "set BOARD_ID";; esac
for digest in "${BITSTREAM_SHA256:-}" "${KERNEL_SHA256:-}"; do
    [ "${#digest}" -eq 64 ] || die "set the actual BITSTREAM_SHA256 and KERNEL_SHA256"
    case "$digest" in *[!0-9a-f]*) die "image identities must be lowercase SHA256";; esac
done
bundle=$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)
[ -f "$bundle/kernel.sha256" ] || die "use the generated environment bundle"
[ "$KERNEL_SHA256" = "$(cat "$bundle/kernel.sha256")" ] || die "kernel differs from this bundle"
(cd "$bundle" && sha256sum -c SHA256SUMS) || die "environment bundle changed"
[ ! -e "$1" ] || die "output exists; no overwrite or automatic retry"
mkdir -- "$1"
out=$(CDPATH= cd -- "$1" && pwd)
printf 'RUNNING_SAFETY\n' > "$out/status"
finished=no
trap '[ "$finished" = yes ] || printf "FAILED\n" > "$out/status"' 0
trap 'exit 1' 1 2 15
cp -- "$bundle/safety/lease_smoke.elf" "$out/lease_smoke.elf"
cp -- "$bundle/safety/SHA256SUMS" "$out/safety-package.sha256"
cp -- "$bundle/run_environment.sh" "$out/run_environment.sh"
chmod u+x "$out/lease_smoke.elf"
uname -a > "$out/uname.txt"
printf '%s\n' "$BOARD_ID" > "$out/board-id.txt"
printf '%s\n' "$BITSTREAM_SHA256" > "$out/bitstream.sha256"
printf '%s\n' "$KERNEL_SHA256" > "$out/kernel.sha256"
rc=0
"$out/lease_smoke.elf" --new-gate-lease-smoke > "$out/safety.log" 2>&1 || rc=$?
printf '%s\n' "$rc" > "$out/safety.rc"
[ "$rc" -eq 0 ] || die "safety test failed; performance tests were not started"
[ "$(tail -n 1 "$out/safety.log")" = \
  'LEASE_SMOKE_DONE passed=11 total=11 errors=0 scope=bounded-safety-not-OS-proof' ] || \
  die "safety completion record missing"
[ "$(grep -c '^LEASE_SMOKE_WAIT .* forced=0 phases=1 pass=1$' "$out/safety.log")" -eq 11 ] || \
  die "safety case evidence incomplete"
printf 'RUNNING_SDK_PAIR\n' > "$out/status"
ARA_DIRECT_PLATFORM_ACCEPTED=yes BOARD_ID="$BOARD_ID" \
BITSTREAM_SHA256="$BITSTREAM_SHA256" KERNEL_SHA256="$KERNEL_SHA256" \
sh "$bundle/perf/run_board.sh" "$out/perf"
printf 'COMPLETE\n' > "$out/status"
finished=yes
printf 'Collected safety and SDK samples: %s\n' "$out"
printf 'Analyze off-board: python3 %s/perf/analyze.py %s/perf\n' "$out" "$out"
