#!/usr/bin/env bash
set -euo pipefail

script_dir=$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)
repo_root=$(cd -- "${script_dir}/../../.." && pwd)

qemu_version=10.2.0
archive_sha256=9e30ad1b8b9f7b4463001582d1ab297f39cfccea5d08540c0ca6d6672785883a
work_root=${QBS_QEMU_BUILD_ROOT:-${script_dir}/build}
archive=${QBS_QEMU_ARCHIVE:-${work_root}/qemu-${qemu_version}.tar.xz}
source_dir=${work_root}/qemu-${qemu_version}
build_dir=${work_root}/qemu-${qemu_version}-build
patch_file=${script_dir}/qemu-${qemu_version}-xaraqbs.patch

mkdir -p "${work_root}"
if [[ ! -f "${archive}" ]]; then
    curl -fL --retry 3 \
        -o "${archive}" "https://download.qemu.org/qemu-${qemu_version}.tar.xz"
fi
printf '%s  %s\n' "${archive_sha256}" "${archive}" | sha256sum -c -

fingerprint=$(
    sha256sum \
        "${patch_file}" \
        "${repo_root}/apps/common/qbs_abi.h" \
        "${repo_root}/verification/qbs/qbs_ref.h" \
        "${repo_root}/verification/qbs/qbs_ref.c" |
        sha256sum | awk '{print $1}'
)
current_fingerprint=
if [[ -f "${source_dir}/.xaraqbs-source" ]]; then
    read -r current_fingerprint < "${source_dir}/.xaraqbs-source"
fi

if [[ "${current_fingerprint}" != "${fingerprint}" ]]; then
    rm -rf "${source_dir}" "${build_dir}"
    tar -xf "${archive}" -C "${work_root}"
    patch -d "${source_dir}" -p1 < "${patch_file}"
    if [[ $(tail -n 1 "${source_dir}/target/riscv/qbs_helper.c") != '}' ]]; then
        printf 'error: QBS QEMU patch produced a truncated qbs_helper.c\n' >&2
        exit 1
    fi
    cp "${repo_root}/apps/common/qbs_abi.h" \
       "${source_dir}/target/riscv/qbs_abi.h"
    cp "${repo_root}/verification/qbs/qbs_ref.c" \
       "${source_dir}/target/riscv/qbs_ref.c"
    sed 's|#include "../../apps/common/qbs_abi.h"|#include "qbs_abi.h"|' \
        "${repo_root}/verification/qbs/qbs_ref.h" \
        > "${source_dir}/target/riscv/qbs_ref.h"
    printf '%s\n' "${fingerprint}" > "${source_dir}/.xaraqbs-source"
fi

if [[ ! -f "${build_dir}/config-host.mak" ]]; then
    mkdir -p "${build_dir}"
    (
        cd "${build_dir}"
        "${source_dir}/configure" \
            --target-list=riscv64-softmmu \
            --disable-docs \
            --disable-werror \
            --disable-plugins \
            --disable-linux-user \
            --disable-guest-agent \
            --disable-sdl \
            --disable-gtk \
            --disable-vnc \
            --disable-curses \
            --disable-opengl \
            --disable-slirp
    )
fi

ninja -C "${build_dir}" -j"${QBS_QEMU_JOBS:-$(nproc)}" qemu-system-riscv64
printf 'QBS_QEMU=%s\n' "${build_dir}/qemu-system-riscv64"
