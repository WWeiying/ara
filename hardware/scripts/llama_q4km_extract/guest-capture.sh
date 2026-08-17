#!/bin/sh
set -eu

mount_dir=/mnt/llama-data
marker=${mount_dir}/q4km-capture.enabled
model=${mount_dir}/models/qwen2.5-1.5b-instruct-q4_k_m.gguf
output=${mount_dir}/captures/qwen2.5-1.5b-q4_k_m
replay_request=${mount_dir}/q4km-replay.request
replay_log=${mount_dir}/q4km-replay.log
generation_marker=${mount_dir}/qwen-generation.enabled
generation_log=${mount_dir}/qwen-generation.log

mkdir -p "${mount_dir}"
if ! mount -t ext4 /dev/vda "${mount_dir}"; then
    echo "q4km-capture: data disk is unavailable; skipping"
    exit 0
fi

if [ -f "${replay_request}" ]; then
    set -- $(cat "${replay_request}")
    if [ "$#" -ne 2 ]; then
        echo "q4km-replay: malformed request"
        exit 1
    fi
    level=$1
    case_path=${mount_dir}/$2
    if [ "${level}" = selftest ]; then
        command=/opt/ara-q4km/test-ara-q4k-repack-rvv
        echo "q4km-replay: running Ara Q4_Kx32 repack GEMV/GEMM self-test"
    else
        command="/opt/ara-q4km/llama-q4km-replay-rvv ${level} ${case_path}"
        echo "q4km-replay: running ${level} ${case_path}"
    fi
    set +e
    GGML_RISCV_REPACK_TRACE=1 ${command} > "${replay_log}" 2>&1
    status=$?
    set -e
    printf 'exit_status=%s\n' "${status}" >> "${replay_log}"
    rm -f "${replay_request}"
    sync
    umount "${mount_dir}"
    poweroff -f
    exit "${status}"
fi

if [ -f "${generation_marker}" ]; then
    if [ ! -f "${model}" ]; then
        echo "qwen-generation: missing model ${model}"
        exit 1
    fi

    generation_case=$(cat "${generation_marker}")
    case "${generation_case}" in
        large)
            set -- \
                -m "${model}" \
                -p "Explain how packed low-bit weights, vector-length-agnostic execution, output-row repacking, cache locality, and data reuse improve quantized transformer inference on a long-vector RISC-V processor." \
                -n 5 \
                -c 512 \
                -b 16 \
                -ub 16 \
                --temp 0 \
                -t 1 \
                -no-cnv \
                --load-mode none \
                --no-warmup
            ;;
        batch4)
            set -- \
                -m "${model}" \
                -p "Test packed vector matrix multiplication." \
                -n 3 \
                -c 128 \
                -b 4 \
                -ub 4 \
                --temp 0 \
                -t 1 \
                -no-cnv \
                --load-mode none \
                --no-warmup
            ;;
        *)
            generation_case=default
            set -- \
                -m "${model}" \
                -p "Explain why low-bit vector inference benefits from packed arithmetic and data reuse." \
                -n 2 \
                -c 64 \
                -t 1 \
                -no-cnv \
                --load-mode none \
                --no-warmup
            ;;
    esac

    echo "qwen-generation: starting ${generation_case} Qwen2.5-1.5B Q4_K_M prefill and decode"
    printf 'generation_case=%s\n' "${generation_case}" > "${generation_log}"
    set +e
    GGML_RISCV_REPACK_TRACE=1 /opt/ara-q4km/llama-completion-rvv "$@" \
        >> "${generation_log}" 2>&1
    status=$?
    set -e
    printf 'exit_status=%s\n' "${status}" >> "${generation_log}"
    rm -f "${generation_marker}"
    sync
    umount "${mount_dir}"
    poweroff -f
    exit "${status}"
fi

if [ ! -f "${marker}" ]; then
    echo "q4km-capture: marker is absent; skipping"
    umount "${mount_dir}"
    exit 0
fi

if [ ! -f "${model}" ]; then
    echo "q4km-capture: missing model ${model}"
    exit 1
fi

rm -rf "${output}"
mkdir -p "${output}"

export LLAMA_Q4KM_CAPTURE_DIR="${output}"
export LLAMA_Q4KM_CAPTURE_LAYER=0
export GGML_RISCV_REPACK_TRACE=1

echo "q4km-capture: starting Qwen2.5-1.5B Q4_K_M prefill and decode"
/opt/ara-q4km/llama-completion-rvv \
    -m "${model}" \
    -p "Explain why low-bit vector inference benefits from packed arithmetic and data reuse." \
    -n 2 \
    -c 64 \
    -t 1 \
    -no-cnv \
    --no-mmap \
    --load-mode none \
    --no-warmup \
    > "${output}/qemu-console.log" 2>&1

sync
echo "q4km-capture: complete; results are in ${output}"
rm -f "${marker}"
umount "${mount_dir}"
poweroff -f
