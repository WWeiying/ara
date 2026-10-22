#!/usr/bin/env bash
set -euo pipefail

usage() {
    echo "usage: $0 --output DIR [--configure-only | --build-only] [--jobs N] [--memory-model sparse|flat] [--lean-init] [--minimal-boot] [--single-hart-fast]" >&2
    exit 2
}

output=""
mode=all
jobs=16
memory_model=sparse
lean_init=0
minimal_boot=0
single_hart_fast=0
while (($#)); do
    case "$1" in
        --output) (($# >= 2)) || usage; output=$2; shift 2 ;;
        --configure-only) [[ $mode == all ]] || usage; mode=configure; shift ;;
        --build-only) [[ $mode == all ]] || usage; mode=build; shift ;;
        --jobs) (($# >= 2)) || usage; jobs=$2; shift 2 ;;
        --memory-model) (($# >= 2)) || usage; memory_model=$2; shift 2 ;;
        --lean-init) lean_init=1; shift ;;
        --minimal-boot) minimal_boot=1; shift ;;
        --single-hart-fast) single_hart_fast=1; shift ;;
        *) usage ;;
    esac
done
[[ -n $output && $jobs =~ ^[0-9]+$ && $jobs -ge 1 && $jobs -le 32 &&
   ( $memory_model == sparse || $memory_model == flat ) ]] || usage

sdk=${SDK:-/home/wangwy/openproject/cva6/cva6-sdk}
config_source=${KERNEL_CONFIG_SOURCE:-$sdk/buildroot/output/build/linux-6.19.6/.config}
source_tar=${KERNEL_SOURCE_TAR:-$sdk/buildroot/dl/linux/linux-6.19.6.tar.xz}
cross_compile=${CROSS_COMPILE:-$sdk/buildroot/output/host/bin/riscv64-buildroot-linux-gnu-}
output=$(realpath -m "$output")
sdk=$(realpath -e "$sdk")
[[ $output != "$sdk" && $output != "$sdk"/* ]] || {
    echo "output must be outside the SDK tree" >&2
    exit 2
}
[[ -f $config_source && -f $source_tar && -x ${cross_compile}gcc ]] || {
    echo "missing source config, kernel source tarball, or cross-compiler" >&2
    exit 2
}

source_dir=$output/source
build_dir=$output/build

if [[ $mode != build ]]; then
    [[ ! -e $output ]] || { echo "output already exists: $output" >&2; exit 2; }
    mkdir -p "$source_dir" "$build_dir"
    tar -xJf "$source_tar" -C "$source_dir" --strip-components=1
    cp "$config_source" "$build_dir/.config"
    "$source_dir/scripts/config" --file "$build_dir/.config" --disable JUMP_LABEL
    if [[ $memory_model == flat ]]; then
        "$source_dir/scripts/config" --file "$build_dir/.config" \
            --enable FLATMEM_MANUAL --disable SPARSEMEM_MANUAL --disable SPARSEMEM_VMEMMAP
    fi
    if ((lean_init)); then
        "$source_dir/scripts/config" --file "$build_dir/.config" \
            --disable FTRACE --disable EVENT_TRACING --disable BPF_EVENTS
    fi
    if ((minimal_boot)); then
        "$source_dir/scripts/config" --file "$build_dir/.config" \
            --disable NET --disable ACPI --disable PCI --disable USB_SUPPORT \
            --disable ATA --disable SCSI --disable SOUND --disable MEDIA_SUPPORT \
            --disable DRM --disable MODULES --disable RAID6_PQ_BENCHMARK
    fi
    if ((single_hart_fast)); then
        "$source_dir/scripts/config" --file "$build_dir/.config" \
            --disable SMP --set-val NR_CPUS 1 --disable DEBUG_KERNEL
    fi
    make -C "$source_dir" O="$build_dir" ARCH=riscv CROSS_COMPILE="$cross_compile" olddefconfig
fi

config=$build_dir/.config
[[ -f $config ]] || { echo "missing configured kernel: $config" >&2; exit 2; }
for required in '# CONFIG_JUMP_LABEL is not set' 'CONFIG_RISCV_ISA_V=y' \
                'CONFIG_MMU=y' 'CONFIG_64BIT=y'; do
    rg -F -x -q "$required" "$config" || {
        echo "kernel configuration requirement failed: $required" >&2
        exit 1
    }
done
if [[ $memory_model == flat ]]; then
    rg -F -x -q 'CONFIG_FLATMEM=y' "$config" || {
        echo 'kernel configuration requirement failed: CONFIG_FLATMEM=y' >&2
        exit 1
    }
fi
if ((lean_init)); then
    rg -F -x -q '# CONFIG_FTRACE is not set' "$config" || {
        echo 'kernel configuration requirement failed: CONFIG_FTRACE=n' >&2
        exit 1
    }
    for disabled in EVENT_TRACING BPF_EVENTS; do
        if rg -F -x -q "CONFIG_${disabled}=y" "$config"; then
            echo "kernel configuration requirement failed: CONFIG_${disabled}=y" >&2
            exit 1
        fi
    done
fi
if ((minimal_boot)); then
    for disabled in NET ACPI PCI USB_SUPPORT ATA SCSI SOUND MEDIA_SUPPORT DRM MODULES; do
        rg -F -x -q "# CONFIG_${disabled} is not set" "$config" || {
            echo "kernel configuration requirement failed: CONFIG_${disabled}=n" >&2
            exit 1
        }
    done
    for required in CONFIG_BLK_DEV_INITRD CONFIG_DEVTMPFS CONFIG_TMPFS \
                    CONFIG_PROC_FS CONFIG_SYSFS CONFIG_SERIAL_8250 \
                    CONFIG_RISCV_ISA_V CONFIG_MMU; do
        rg -F -x -q "${required}=y" "$config" || {
            echo "kernel configuration requirement failed: ${required}=y" >&2
            exit 1
        }
    done
    rg -F -x -q '# CONFIG_RAID6_PQ_BENCHMARK is not set' "$config" || {
        echo 'kernel configuration requirement failed: CONFIG_RAID6_PQ_BENCHMARK=n' >&2
        exit 1
    }
fi
if ((single_hart_fast)); then
    for disabled in SMP DEBUG_KERNEL; do
        rg -F -x -q "# CONFIG_${disabled} is not set" "$config" || {
            echo "kernel configuration requirement failed: CONFIG_${disabled}=n" >&2
            exit 1
        }
    done
fi
if [[ $mode != configure ]]; then
    image=$build_dir/arch/riscv/boot/Image
    [[ ! -e $image ]] || { echo "Image already exists: $image" >&2; exit 2; }
    make -C "$source_dir" O="$build_dir" ARCH=riscv CROSS_COMPILE="$cross_compile" \
        -j "$jobs" Image
    [[ -s $image ]] || { echo "kernel Image missing or empty: $image" >&2; exit 1; }
    sha256sum "$config" "$image" "$source_tar" > "$output/SHA256SUMS"
    echo "verification-only Image: $image"
fi
