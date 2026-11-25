#!/bin/sh
# Run only after board ownership, kernel/module and memory admission are checked.
set -eu
here=$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)
if [ "$#" -ne 1 ]; then
    echo "usage: sh run_board.sh NEW_RESULT_DIRECTORY" >&2
    exit 2
fi
: "${RESIDENT_PLATFORM_ACCEPTED:?Set to yes after checking the platform contract}"
: "${RESIDENT_BOARD_ID:?Record the board and bitstream identity}"
: "${RESIDENT_MODULE_SHA256:?Record the loaded module file SHA256}"
[ "$RESIDENT_PLATFORM_ACCEPTED" = yes ] || exit 2
[ "${RESIDENT_PHASE_STATS:-0}" = 0 ] || { echo 'Disable phase probes for the primary latency pair' >&2; exit 2; }
[ "$(uname -m)" = riscv64 ] || { echo 'Run on the RISC-V board' >&2; exit 2; }
[ -c /dev/ara-resident ] || { echo 'Resident device missing' >&2; exit 2; }
[ ! -e "$1" ] || { echo 'Output already exists' >&2; exit 2; }
(cd "$here" && sha256sum -c SHA256SUMS)
mkdir -- "$1"
out=$(CDPATH= cd -- "$1" && pwd)
printf '%s\n' RUNNING > "$out/status"
trap 'printf "%s\n" FAILED > "$out/status"' 0
trap 'exit 130' 2 15
cp "$here/manifest.json" "$here/SHA256SUMS" "$out/"
uname -a > "$out/uname.txt"
printf '%s\n' "$RESIDENT_BOARD_ID" > "$out/board_id.txt"
printf '%s\n' "$RESIDENT_MODULE_SHA256" > "$out/module_sha256.txt"
env | LC_ALL=C sort | awk '/^(GGML_|RESIDENT_|OMP_|OPENBLAS_|PATH=|LD_LIBRARY_PATH=)/' > "$out/environment.txt"
cat /proc/modules > "$out/modules.txt"
cat /proc/cpuinfo > "$out/cpuinfo.txt"
date -u > "$out/start.txt"
"$here/resident-ggml-pair" --probe > "$out/probe.log" 2>&1
for tokens in 65 128 137; do
    index=0
    for mode in native resident resident native; do
        stem="$out/t${tokens}_${index}_${mode}"
        rc=0
        "$here/resident-ggml-pair" "$mode" "$tokens" > "$stem.log" 2>&1 || rc=$?
        printf '%s\n' "$rc" > "$stem.rc"
        printf '%s\n' "tokens=$tokens index=$index mode=$mode exit=$rc"
        [ "$rc" -eq 0 ] || { echo "STOP: $stem.log" >&2; exit 1; }
        index=$((index + 1))
    done
done
date -u > "$out/end.txt"
printf '%s\n' COMPLETE > "$out/status"
trap - 0 2 15
echo "Complete: $out; analyze on the host with analyze.py"
