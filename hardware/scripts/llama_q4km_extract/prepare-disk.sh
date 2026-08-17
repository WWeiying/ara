#!/usr/bin/env bash
set -euo pipefail

model=/home/wangwy/llama/models/qwen2.5-1.5b-instruct-q4_k_m.gguf
image=/home/wangwy/llama/platforms/cva6-qemu/images/qwen2.5-q4km-capture.ext4
staging=$(mktemp -d /home/wangwy/llama/.q4km-disk.XXXXXX)
trap 'rm -rf "${staging}"' EXIT

test -s "${model}"
mkdir -p "${staging}/models" "${staging}/captures"
ln "${model}" "${staging}/models/$(basename -- "${model}")"
touch "${staging}/q4km-capture.enabled"

truncate -s 3G "${image}"
mkfs.ext4 -q -F -L ara_q4km -d "${staging}" "${image}"
echo "Prepared ${image}"
