#!/bin/sh
# Does not load/unload modules, change the bitstream or start a model.
set -eu
here=$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)
[ "$#" -eq 1 ] || { echo 'usage: sh run_board.sh NEW_RESULT_DIRECTORY' >&2; exit 2; }
: "${RESIDENT_PLATFORM_ACCEPTED:?Check coherent memory, one CPU and exclusive execution}"
: "${RESIDENT_BOARD_ID:?Record the board and bitstream identity}"
: "${RESIDENT_MODULE_SHA256:?Record the actually loaded module SHA256}"
[ "$RESIDENT_PLATFORM_ACCEPTED" = yes ]
[ "${RESIDENT_PHASE_STATS:-0}" = 0 ]
[ "$(uname -m)" = riscv64 ]
[ "$(cat /sys/devices/system/cpu/online)" = 0 ]
[ "$(cat /sys/module/ara_resident/parameters/profile)" = N ]
[ -c /dev/ara-resident ]
[ ! -e "$1" ]
(cd "$here" && sha256sum -c SHA256SUMS)
[ "$(sha256sum "$here/ara_resident.ko" | awk '{print $1}')" = "$RESIDENT_MODULE_SHA256" ]
mkdir -- "$1"
out=$(CDPATH= cd -- "$1" && pwd)
printf '%s\n' RUNNING > "$out/status"
trap 'printf "%s\n" FAILED > "$out/status"' 0
trap 'exit 130' 2 15
cp "$here/manifest.json" "$here/SHA256SUMS" "$out/"
uname -a > "$out/uname.txt"
printf '%s\n' "$RESIDENT_BOARD_ID" > "$out/board_id.txt"
printf '%s\n' "$RESIDENT_MODULE_SHA256" > "$out/module_sha256.txt"
env | LC_ALL=C sort | awk '/^(GGML_|RESIDENT_|OMP_|PATH=|LD_LIBRARY_PATH=)/' > "$out/environment.txt"
cat /proc/modules > "$out/modules.txt"
cat /proc/cpuinfo > "$out/cpuinfo.txt"
date -u > "$out/start.txt"
"$here/resident-ggml-pair" --probe > "$out/probe.log" 2>&1
for kv in 1 4; do
    for tokens in 65 128 137 stream; do
        index=0
        for mode in native session views views session native; do
            stem="$out/k${kv}_t${tokens}_${index}_${mode}"
            rc=0
            "$here/resident-ggml-pair" "$mode" "$tokens" "$kv" > "$stem.log" 2>&1 || rc=$?
            printf '%s\n' "$rc" > "$stem.rc"
            [ "$rc" -eq 0 ] || { echo "STOP: $stem.log" >&2; exit 1; }
            index=$((index + 1))
        done
    done
done
date -u > "$out/end.txt"
printf '%s\n' COMPLETE > "$out/status"
trap - 0 2 15
echo "Complete: $out; analyze.py runs on the host"
