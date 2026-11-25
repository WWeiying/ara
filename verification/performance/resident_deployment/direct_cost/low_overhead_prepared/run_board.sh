#!/bin/sh
set -eu

# This script measures an already-deployed, operator-identified gate image.
# It never installs a driver, changes the kernel, or programs the board.
die() { printf '%s\n' "$*" >&2; exit 1; }
[ "$#" -eq 1 ] || die "usage: sh run_board.sh NEW_OUTPUT_DIRECTORY"
[ "${ARA_DIRECT_PLATFORM_ACCEPTED:-}" = yes ] || die "require ARA_DIRECT_PLATFORM_ACCEPTED=yes"
case "${BOARD_ID:-}" in ''|*[!A-Za-z0-9._-]*) die "require an ASCII BOARD_ID";; esac
for digest in "${BITSTREAM_SHA256:-}" "${KERNEL_SHA256:-}"; do
    [ "${#digest}" -eq 64 ] || die "require BITSTREAM_SHA256 and KERNEL_SHA256"
    case "$digest" in *[!0-9a-f]*) die "image hashes must be lowercase SHA256";; esac
done
[ -z "${LD_PRELOAD:-}${LD_LIBRARY_PATH:-}${LD_AUDIT:-}" ] || die "loader overrides forbidden"
[ -z "${AKV_QK_PANEL4+x}${AKV_PAIR_HEADS+x}${AKV_PREFILL_PAIR_PV+x}" ] || die "SDK policy overrides forbidden"
[ "$(uname -m)" = riscv64 ] || die "not a riscv64 board"
[ "$(cat /sys/devices/system/cpu/online)" = 0 ] || die "require exactly CPU0 online"
[ -c /dev/ara-akv-direct ] || die "missing built-in direct lease device; old image unsupported"

bundle=$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)
for name in resident-direct-pair analyze.py README.md source-pins.json goldens.json SHA256SUMS; do
    [ -f "$bundle/$name" ] || die "missing frozen bundle file: $name"
done
(cd "$bundle" && sha256sum -c SHA256SUMS) || die "bundle identity mismatch"
[ ! -e "$1" ] || die "output exists; no retry/overwrite"
mkdir -- "$1"
out=$(CDPATH= cd -- "$1" && pwd)
printf 'RUNNING\n' > "$out/status"
finished=no
trap '[ "$finished" = yes ] || printf "FAILED\n" > "$out/status"' 0
trap 'exit 1' 1 2 15
for name in resident-direct-pair run_board.sh analyze.py README.md source-pins.json goldens.json SHA256SUMS; do
    cp -- "$bundle/$name" "$out/$name"
done
(cd "$out" && sha256sum -c SHA256SUMS) > "$out/package-check.log" 2>&1 || die "copied bundle mismatch"
chmod u+x "$out/resident-direct-pair"
uname -a > "$out/uname.txt"
cat /proc/cpuinfo > "$out/cpuinfo.txt"
cat /proc/modules > "$out/modules.txt"
date -u '+%Y-%m-%dT%H:%M:%SZ' > "$out/started.txt"
printf '{"schema":1,"operator_accepted":true,"board_id":"%s","bitstream_sha256":"%s","kernel_sha256":"%s","machine":"riscv64","online_cpus":"0"}\n' \
    "$BOARD_ID" "$BITSTREAM_SHA256" "$KERNEL_SHA256" > "$out/platform.json"

run() {
    label=$1
    argument=$2
    rc=0
    "$out/resident-direct-pair" "$argument" > "$out/$label.log" 2>&1 || rc=$?
    printf '%s\n' "$rc" > "$out/$label.rc"
    [ "$rc" -eq 0 ] || die "$label failed, stopped without retry; inspect $out/$label.log"
}
run probe --probe
for tokens in 65 128 137; do run "t$tokens" "$tokens"; done
date -u '+%Y-%m-%dT%H:%M:%SZ' > "$out/finished.txt"
printf 'COMPLETE\n' > "$out/status"
finished=yes
printf 'Direct SDK samples complete: %s\n' "$out"
printf 'Analyze off-board: python3 %s/analyze.py %s\n' "$out" "$out"


