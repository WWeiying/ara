#!/usr/bin/env bash
set -euo pipefail
D=$(cd "$(dirname "$0")" && pwd)
OUT=${1:?new output directory required}
shift
for define in "$@"; do
  case "$define" in READ_PROBE|FAULT_PROBE|PRETOUCH|PATH_PROBE|NO_ZERO|MASK_PROBE|FORK_PROBE|MFPU_PROBE) ;; *) echo 'Unknown diagnostic define' >&2; exit 2;; esac
done
mkdir "$OUT"
OUT=$(cd "$OUT" && pwd)
CC=${CC:-/home/wangwy/openproject/cva6/cva6-sdk/buildroot/output/host/bin/riscv64-buildroot-linux-gnu-gcc}
defs=(-DINIT_PROBE)
for define in "$@"; do defs+=("-D$define"); done
"$CC" -march=rv64gcv -mabi=lp64d -nostdlib -static -Wl,--build-id=none \
  "${defs[@]}" "$D/rvv_context_check.S" -o "$OUT/init.elf"
mkdir -p "$OUT/root/dev"
install -m 755 "$OUT/init.elf" "$OUT/root/init"
(cd "$OUT/root"; printf 'dev\ninit\n' | cpio --quiet -o -H newc --owner=0:0) > "$OUT/initramfs.cpio"
test "$(stat -c %s "$OUT/initramfs.cpio")" -le 2432000
truncate -s 2432000 "$OUT/initramfs.cpio"
sha256sum "$D/rvv_context_check.S" "$OUT/init.elf" "$OUT/initramfs.cpio"
