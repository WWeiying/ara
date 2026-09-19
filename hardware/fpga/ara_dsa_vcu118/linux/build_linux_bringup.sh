#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR=$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)
OUT=${OUT:-"$SCRIPT_DIR/out"}
SDK=${SDK:-/home/wangwy/openproject/cva6/cva6-sdk}
CROSS_COMPILE=${CROSS_COMPILE:-"$SDK/buildroot/output/host/bin/riscv64-buildroot-linux-gnu-"}
CC=${CC:-"${CROSS_COMPILE}gcc"}
READELF=${READELF:-"${CROSS_COMPILE}readelf"}
STRIP=${STRIP:-"${CROSS_COMPILE}strip"}
KERNEL_IMAGE=${KERNEL_IMAGE:-"$SDK/install64_qemu/Image"}
OPENSBI_SRC=${OPENSBI_SRC:-"$SDK/buildroot/output/build/opensbi-1.7"}
TARGET_ROOTFS=${TARGET_ROOTFS:-"$SDK/buildroot/output/target"}
BUSYBOX=${BUSYBOX:-"$TARGET_ROOTFS/bin/busybox"}
DTC=${DTC:-dtc}

FW_ADDR=0x80000000
DTB_ADDR=0x80100000
KERNEL_ADDR=0x80200000
INITRD_ADDR=0x88000000

die() {
    printf 'error: %s\n' "$*" >&2
    exit 1
}

command -v "$CC" >/dev/null 2>&1 || die "missing RISC-V compiler: $CC"
command -v "$READELF" >/dev/null 2>&1 || die "missing RISC-V readelf: $READELF"
command -v "$STRIP" >/dev/null 2>&1 || die "missing RISC-V strip: $STRIP"
command -v "$DTC" >/dev/null 2>&1 || die "missing device-tree compiler: $DTC"
command -v cpio >/dev/null 2>&1 || die "missing cpio"
[[ -f "$KERNEL_IMAGE" ]] || die "kernel Image not found: $KERNEL_IMAGE"
[[ -f "$OPENSBI_SRC/Makefile" ]] || die "OpenSBI source not found: $OPENSBI_SRC"
[[ -x "$BUSYBOX" ]] || die "BusyBox not found or not executable: $BUSYBOX"
[[ -f "$TARGET_ROOTFS/lib/ld-linux-riscv64-lp64d.so.1" ]] || die "RISC-V dynamic loader not found: $TARGET_ROOTFS/lib"
[[ -f "$TARGET_ROOTFS/lib/libc.so.6" ]] || die "RISC-V libc not found: $TARGET_ROOTFS/lib"
[[ -f "$TARGET_ROOTFS/lib/libresolv.so.2" ]] || die "RISC-V libresolv not found: $TARGET_ROOTFS/lib"
[[ -f "$SCRIPT_DIR/rootfs/init" ]] || die "initramfs init not found: $SCRIPT_DIR/rootfs/init"

mkdir -p "$OUT"
rm -rf "$OUT/initramfs" "$OUT/opensbi-fw-jump"
mkdir -p "$OUT/initramfs"/{bin,sbin,usr/bin,usr/sbin,lib,dev,proc,sys,dev/pts,dev/shm,etc,root,run,tmp}

# Package only BusyBox, its runtime libraries, and applet symlinks so the
# interactive initramfs remains small enough for the UART bring-up path.
cp -a "$BUSYBOX" "$OUT/initramfs/bin/busybox"
for library in ld-linux-riscv64-lp64d.so.1 libc.so.6 libresolv.so.2; do
    cp -a "$TARGET_ROOTFS/lib/$library" "$OUT/initramfs/lib/$library"
done
for applet_dir in bin sbin usr/bin usr/sbin; do
    source_dir="$TARGET_ROOTFS/$applet_dir"
    destination_dir="$OUT/initramfs/$applet_dir"
    while IFS= read -r -d '' applet; do
        applet_name=${applet#"$source_dir/"}
        ln -s "$(readlink "$applet")" "$destination_dir/$applet_name"
    done < <(find "$source_dir" -maxdepth 1 -type l -lname '*busybox*' -print0)
done
cp "$SCRIPT_DIR/rootfs/init" "$OUT/initramfs/init"
chmod 0755 "$OUT/initramfs/init"
cat > "$OUT/initramfs/etc/passwd" <<'EOF'
root:x:0:0:root:/root:/bin/sh
EOF
cat > "$OUT/initramfs/etc/group" <<'EOF'
root:x:0:
EOF
cat > "$OUT/initramfs/etc/profile" <<'EOF'
export PATH=/sbin:/bin:/usr/sbin:/usr/bin
export HOME=/root
export TERM=vt100
PS1='ara-vcu118:\w# '
EOF
cat > "$OUT/initramfs/etc/hostname" <<'EOF'
ara-vcu118
EOF
(
    cd "$OUT/initramfs"
    find . -print0 | cpio --null -o --format=newc > "$OUT/initramfs.cpio"
)

initrd_size=$(stat -c '%s' "$OUT/initramfs.cpio")
initrd_end=$(printf '0x%x' $((INITRD_ADDR + initrd_size)))
sed \
    -e "s/__INITRD_START__/$INITRD_ADDR/g" \
    -e "s/__INITRD_END__/$initrd_end/g" \
    "$SCRIPT_DIR/ara_vcu118.dts.in" > "$OUT/ara_vcu118.dts"
"$DTC" -I dts -O dtb -o "$OUT/ara_vcu118.dtb" "$OUT/ara_vcu118.dts"

make -C "$OPENSBI_SRC" O="$OUT/opensbi-fw-jump" \
    PLATFORM=generic PLATFORM_RISCV_XLEN=64 \
    CROSS_COMPILE="$CROSS_COMPILE" \
    FW_TEXT_START="$FW_ADDR" FW_FDT_PATH="$OUT/ara_vcu118.dtb" \
    FW_JUMP=y FW_DYNAMIC=n FW_PAYLOAD=n \
    FW_JUMP_ADDR="$KERNEL_ADDR" FW_JUMP_FDT_ADDR="$DTB_ADDR"

cp "$KERNEL_IMAGE" "$OUT/Image"
cp "$OUT/opensbi-fw-jump/platform/generic/firmware/fw_jump.elf" "$OUT/fw_jump.elf"
"$STRIP" --strip-debug "$OUT/fw_jump.elf"

if ! "$READELF" -lW "$OUT/fw_jump.elf" | awk '
    /^[[:space:]]*LOAD[[:space:]]/ {
        p = tolower($4)
        sub(/^0x/, "", p)
        if (p ~ /^0*80000000$/)
            found = 1
    }
    END { exit(found ? 0 : 1) }
'; then
    die "fw_jump.elf is not linked at 0x80000000"
fi

sha256sum "$OUT/fw_jump.elf" "$OUT/Image" "$OUT/ara_vcu118.dtb" \
    "$OUT/initramfs.cpio" > "$OUT/SHA256SUMS"
cat > "$OUT/LOAD_LAYOUT.txt" <<EOF
fw_jump.elf  @ $FW_ADDR
ara_vcu118.dtb @ $DTB_ADDR
Image        @ $KERNEL_ADDR
initramfs.cpio @ $INITRD_ADDR
EOF

printf '\nLinux bring-up artifacts generated in %s\n' "$OUT"
cat "$OUT/LOAD_LAYOUT.txt"
printf '\nWindows loader command:\n'
printf 'py software/uart_load.py --port COM6 --elf linux/out/fw_jump.elf '
printf -- '--load 0x%s:linux/out/Image ' "${KERNEL_ADDR#0x}"
printf -- '--load 0x%s:linux/out/ara_vcu118.dtb ' "${DTB_ADDR#0x}"
printf -- '--load 0x%s:linux/out/initramfs.cpio --no-readback --chunk-size 65536 --interactive\n' "${INITRD_ADDR#0x}"
