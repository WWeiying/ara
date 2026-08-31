#!/usr/bin/env bash
set -euo pipefail

if [[ $# -lt 2 || $# -gt 3 ]]; then
  echo "usage: $0 MODEL.gguf OUTPUT.ext4 [GUEST_BASENAME]" >&2
  exit 2
fi

model=$(realpath -- "$1")
output=$(realpath -m -- "$2")
guest_basename=${3:-$(basename -- "${model}")}
[[ ${guest_basename} =~ ^[A-Za-z0-9._-]+$ ]] || {
  echo "invalid guest model basename: ${guest_basename}" >&2
  exit 2
}
test -s "${model}"
command -v mkfs.ext4 >/dev/null
command -v debugfs >/dev/null

model_bytes=$(stat -c %s -- "${model}")
reserve_bytes=$((256 * 1024 * 1024))
alignment=$((64 * 1024 * 1024))
disk_bytes=$((model_bytes + reserve_bytes))
disk_bytes=$((((disk_bytes + alignment - 1) / alignment) * alignment))

mkdir -p "$(dirname -- "${output}")"
temporary=${output}.tmp.$$
trap 'rm -f -- "${temporary}"' EXIT
truncate -s "${disk_bytes}" "${temporary}"
mkfs.ext4 -q -F -m 0 "${temporary}"
debugfs -w -R 'mkdir /models' "${temporary}" >/dev/null 2>&1
debugfs -w -R "write ${model} /models/${guest_basename}" \
  "${temporary}" >/dev/null 2>&1
debugfs -R "stat /models/${guest_basename}" "${temporary}" \
  > "${output}.stat.tmp"
mv -- "${temporary}" "${output}"
trap - EXIT
mv -- "${output}.stat.tmp" "${output}.stat"

{
  printf 'MODEL_SOURCE=%s\n' "${model}"
  printf 'MODEL_SOURCE_BYTES=%s\n' "${model_bytes}"
  printf 'MODEL_SOURCE_SHA256=%s\n' "$(sha256sum -- "${model}" | awk '{print $1}')"
  printf 'MODEL_GUEST_PATH=/model/models/%s\n' "${guest_basename}"
  printf 'DISK_BYTES=%s\n' "${disk_bytes}"
  printf 'DISK_SHA256=%s\n' "$(sha256sum -- "${output}" | awk '{print $1}')"
} > "${output}.manifest"

echo "model disk: ${output}"
echo "guest path: /model/models/${guest_basename}"
