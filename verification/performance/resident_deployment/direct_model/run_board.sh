#!/bin/sh
set -eu

die() { printf '%s\n' "$*" >&2; exit 1; }
usage() {
    printf '%s\n' 'usage: sh run_board.sh rvv|native|resident MODEL NEW_OUTPUT [PROMPT [N_PREDICT]]'
}
if [ "${1:-}" = -h ] || [ "${1:-}" = --help ]; then usage; exit 0; fi
[ "$#" -ge 3 ] && [ "$#" -le 5 ] || { usage >&2; exit 1; }
mode=$1
case "$mode" in rvv|native|resident) ;; *) die 'mode must be rvv, native, or resident';; esac
model=$2
output=$3
prompt=${4:-Hello my name is}
predict=${5:-32}
diagnostic=${ARA_DIRECT_DIAGNOSTIC:-0}
case "$diagnostic" in 0|1) ;; *) die 'ARA_DIRECT_DIAGNOSTIC must be 0 or 1';; esac
case "$predict" in ''|*[!0-9]*) die 'N_PREDICT must be 1..4096';; esac
[ "${#predict}" -le 4 ] && [ "$predict" -ge 1 ] && [ "$predict" -le 4096 ] || die 'N_PREDICT must be 1..4096'
[ "${ARA_DIRECT_PREFLIGHT_ACK:-}" = kernel-v4-new-gate-single-worker ] ||
    die 'require ARA_DIRECT_PREFLIGHT_ACK=kernel-v4-new-gate-single-worker after manual installation and preflight'
[ "${ARA_DIRECT_SINGLE_WORKER:-}" = yes ] || die 'require ARA_DIRECT_SINGLE_WORKER=yes; no concurrent accelerator users'
[ "${ARA_DIRECT_MEMORY_ACK:-}" = normal-ram-no-mmio-immutable-model ] ||
    die 'require ARA_DIRECT_MEMORY_ACK=normal-ram-no-mmio-immutable-model after checking mappings and file stability'
[ "${ARA_DIRECT_POLICY_ACK:-}" = helper-owned-locks-no-external-policy ] ||
    die 'require ARA_DIRECT_POLICY_ACK=helper-owned-locks-no-external-policy; no foreign policy/mapping changes without invalidate'
case "${BOARD_ID:-}" in ''|*[!A-Za-z0-9._-]*) die 'require an ASCII BOARD_ID';; esac
case "${BOARD_CLOCK_HZ:-}" in ''|*[!0-9]*) die 'require measured/configuration-verified BOARD_CLOCK_HZ';; esac
[ "${#BOARD_CLOCK_HZ}" -le 12 ] && [ "$BOARD_CLOCK_HZ" -gt 0 ] || die 'invalid BOARD_CLOCK_HZ'
[ "${BOARD_HART:-}" = 0 ] || die 'require BOARD_HART=0 after verifying the single-hart configuration'
for digest in "${BITSTREAM_SHA256:-}" "${KERNEL_SHA256:-}"; do
    [ "${#digest}" -eq 64 ] || die 'require BITSTREAM_SHA256 and KERNEL_SHA256'
    case "$digest" in *[!0-9a-f]*) die 'image hashes must be lowercase SHA256';; esac
done
[ -z "${LD_PRELOAD:-}${LD_LIBRARY_PATH:-}${LD_AUDIT:-}" ] || die 'loader overrides forbidden'
[ "$(uname -m)" = riscv64 ] || die 'not a riscv64 board'
[ "$(id -u)" = 0 ] || die 'controlled candidate requires root'
[ "$(cat /sys/devices/system/cpu/online)" = 0 ] || die 'require exactly CPU0 online'
[ -c /dev/ara-akv-direct ] || die 'missing Direct-U device; old images unsupported'
[ -f "$model" ] && [ -r "$model" ] || die 'model is not a readable regular file'
case "$model" in /*) ;; *) model=$(pwd)/$model;; esac
[ ! -e "$output" ] && [ ! -L "$output" ] || die 'output exists; no retry/overwrite'
bundle=$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)
for name in llama-simple run_board.sh README.md candidate.json freeze.json source-pins.json symbol-audit.json candidate-contract.json candidate-contract.sha256 kernel-image.sha256 SHA256SUMS; do
    [ -f "$bundle/$name" ] && [ ! -L "$bundle/$name" ] || die "missing regular bundle file: $name"
done
(cd "$bundle" && sha256sum -c SHA256SUMS) || die 'bundle identity mismatch'
contract=$(sha256sum "$bundle/candidate-contract.json")
contract=${contract%% *}
[ "$contract" = "$(cat "$bundle/candidate-contract.sha256")" ] || die 'contract digest mismatch'
[ "${ARA_DIRECT_CONTRACT_SHA256:-}" = "$contract" ] || die 'require explicit ARA_DIRECT_CONTRACT_SHA256 for this candidate'
[ "$KERNEL_SHA256" = "$(cat "$bundle/kernel-image.sha256")" ] || die 'kernel hash differs from the pinned v4 Image'
# Serialize this launcher; operator acknowledgement still covers other clients.
lock=/tmp/ara-direct-model.lock
mkdir "$lock" 2>/dev/null || die 'another runner or stale lock exists; inspect before removing /tmp/ara-direct-model.lock'
finished=no
out=
cleanup() {
    if [ "$finished" != yes ] && [ -n "$out" ]; then printf 'FAILED\n' > "$out/status"; fi
    rmdir "$lock"
}
trap cleanup 0
trap 'exit 1' 1 2 15
mkdir -- "$output"
out=$(CDPATH= cd -- "$output" && pwd)
printf 'RUNNING\n' > "$out/status"
cp -- "$bundle/llama-simple" "$out/llama-simple"
cmp -s "$bundle/llama-simple" "$out/llama-simple" || die 'copied ELF identity mismatch'
chmod u+x "$out/llama-simple"
sha256sum -- "$model" > "$out/model.sha256"
sha256sum -- "$bundle/llama-simple" "$out/llama-simple" > "$out/elf.sha256"
uname -a > "$out/uname.txt"
cat /proc/cpuinfo > "$out/cpuinfo.txt"
date -u '+%Y-%m-%dT%H:%M:%SZ' > "$out/started.txt"
printf '%s\n' "$prompt" > "$out/prompt.txt"
printf 'mode=%s\nboard_id=%s\nbitstream_sha256=%s\nkernel_sha256=%s\npreflight_ack=%s\nworkers=1\nnormal_memory=0\nhardware_accepted=false\n' \
    "$mode" "$BOARD_ID" "$BITSTREAM_SHA256" "$KERNEL_SHA256" "$ARA_DIRECT_PREFLIGHT_ACK" > "$out/operator-preflight.txt"
printf 'contract_sha256=%s\nmemory_ack=%s\nprovenance_attests_running_board=false\n' \
    "$contract" "$ARA_DIRECT_MEMORY_ACK" >> "$out/operator-preflight.txt"
printf 'clock_hz=%s\nhart=%s\ndiagnostic=%s\n' "$BOARD_CLOCK_HZ" "$BOARD_HART" "$diagnostic" >> "$out/operator-preflight.txt"
printf 'policy_ack=%s\n' "$ARA_DIRECT_POLICY_ACK" >> "$out/operator-preflight.txt"
cp -- "$bundle/candidate-contract.json" "$out/candidate-contract.json"
ulimit -l > "$out/memlock-before.txt"
ulimit -l unlimited || die 'cannot raise memlock limit; Direct-U mlockall admission would decline'
ulimit -l > "$out/memlock-after.txt"
[ "$(cat "$out/memlock-after.txt")" = unlimited ] || die 'memlock limit is not unlimited'

# A clean environment excludes inherited emulation, policy, teacher-force and
# memory-authority overrides. NORMAL_MEMORY is not inferred from board identity.
auto=0
qbs=0
akv=0
resident=0
case "$mode" in native) auto=1; qbs=1; akv=1;; resident) auto=1; qbs=1; akv=1; resident=1;; esac
run_clean() {
    if [ "$diagnostic" = 1 ]; then
        set -- "LLAMA_SIMPLE_LOGITS_FILE=$out/logits.bin" "$@"
    fi
    env -i PATH=/usr/bin:/bin LC_ALL=C OMP_NUM_THREADS=1 OPENBLAS_NUM_THREADS=1 \
        GGML_RISCV_ACCEL_AUTO="$auto" GGML_RISCV_QBS="$qbs" GGML_RISCV_AKV="$akv" \
        GGML_RISCV_AKV_RESIDENT="$resident" GGML_RISCV_AKV_KERNEL=auto \
        GGML_RISCV_QBS_EMULATE=0 GGML_RISCV_AKV_EMULATE=0 \
        GGML_RISCV_AKV_TRACE="$diagnostic" GGML_RISCV_QBS_TRACE="$diagnostic" \
        GGML_RISCV_AKV_QUANT_KV_NORMAL_MEMORY=0 GGML_RISCV_AKV_GROUPED_PV=0 \
        "$@"
}
# examples/simple returns 1 after printing usage when no model was supplied.
help_rc=0
run_clean "$out/llama-simple" -h > "$out/help.txt" 2>&1 || help_rc=$?
printf '%s\n' "$help_rc" > "$out/help.rc"
[ "$help_rc" -eq 0 ] || [ "$help_rc" -eq 1 ] || die 'llama-simple -h failed unexpectedly'
for option in '-m ' '-n ' '-ngl ' '-t ' '-fa ' '--kv-type '; do
    grep -F -- "$option" "$out/help.txt" >/dev/null || die "CLI mismatch: missing $option in -h"
done
printf '%s\n' "$out/llama-simple" -m "$model" -n "$predict" -ngl 0 -t 1 -fa on --kv-type f16 "$prompt" > "$out/argv.txt"
run_clean /usr/bin/env > "$out/runtime-environment.txt"
rc=0
run_clean "$out/llama-simple" -m "$model" -n "$predict" -ngl 0 -t 1 -fa on --kv-type f16 "$prompt" \
    > "$out/stdout.txt" 2> "$out/stderr.txt" || rc=$?
printf '%s\n' "$rc" > "$out/exit-code.txt"
if [ "$diagnostic" = 1 ]; then
    grep -E '^(GGML_AKV_DIRECT_COVERAGE|GGML_AKV_DIRECT_PREP|GGML_RISCV_AKV_COVERAGE|GGML_RISCV_AKV_RESIDENT_V1|GGML_RISCV_QBS_(COVERAGE|EXEC)) ' \
        "$out/stderr.txt" > "$out/counters.txt" || :
fi
[ "$rc" -eq 0 ] || die 'model execution failed; stopped without retry'
if [ "$diagnostic" = 1 ]; then
    [ -s "$out/logits.bin" ] || die 'diagnostic run did not produce logits'
    sha256sum "$out/logits.bin" > "$out/logits.sha256"
fi
sha256sum -c "$out/model.sha256" > "$out/model-post-check.txt" || die 'model identity drift'
date -u '+%Y-%m-%dT%H:%M:%SZ' > "$out/finished.txt"
printf 'EXECUTED_UNVERIFIED\n' > "$out/status"
finished=yes
printf 'Execution captured at %s; correctness, path admission and performance remain unverified.\n' "$out"
