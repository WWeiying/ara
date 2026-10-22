#!/usr/bin/env python3
"""Build an isolated Linux userspace smoke payload from a trusted base initramfs."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
from pathlib import Path
import shutil
import subprocess
import tempfile


REPO_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_CC = (
    "/home/wangwy/openproject/cva6/cva6-sdk/buildroot/output/host/bin/"
    "riscv64-buildroot-linux-gnu-gcc"
)
DEFAULT_BASE_INITRAMFS = (
    REPO_ROOT / "hardware/fpga/ara_dsa_vcu118/linux/artifacts/initramfs.cpio"
)
COMPILE_FLAGS = (
    "-static", "-O2", "-Wall", "-Wextra", "-Werror",
    "-fno-tree-vectorize", "-fno-tree-slp-vectorize",
    "-march=rv64gc", "-mabi=lp64d",
)
INIT_SCRIPT = """#!/bin/busybox sh
export PATH=/sbin:/bin:/usr/sbin:/usr/bin
echo 'Ara verification Linux init reached'
rc=0
/bin/busybox mkdir -p /proc /sys /dev || rc=1
/bin/busybox mount -t proc proc /proc || rc=1
/bin/busybox mount -t sysfs sysfs /sys || rc=1
/bin/busybox mount -t devtmpfs devtmpfs /dev || rc=1
if [ "$rc" -eq 0 ]; then
    /usr/bin/rvv_linux_smoke
    rc=$?
fi
if [ "$rc" -eq 0 ]; then
    echo 'ARA_LINUX_USERSPACE PASS'
else
    echo 'ARA_LINUX_USERSPACE FAIL'
fi
/bin/busybox sync
/bin/busybox poweroff -f
while :; do /bin/busybox sleep 1; done
"""


def file_record(path: Path) -> dict:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return {"path": str(path), "sha256": digest.hexdigest()}


def find_tool(name: str) -> Path:
    found = shutil.which(name)
    if found is None:
        raise ValueError(f"executable not found: {name}")
    # Buildroot selects the compiler by argv[0]; do not resolve its wrapper symlink.
    return Path(os.path.abspath(found))


def install_file(source: Path, target: Path, rootfs: Path) -> None:
    if not target.parent.resolve().is_relative_to(rootfs):
        raise ValueError(f"install path escapes rootfs: {target}")
    missing = []
    parent = target.parent
    while not parent.exists():
        missing.append(parent)
        parent = parent.parent
    target.parent.mkdir(parents=True, exist_ok=True)
    for directory in missing:
        directory.chmod(0o755)
    # Replace archive entries without following a pre-existing symlink or hardlink.
    with tempfile.NamedTemporaryFile(dir=target.parent, delete=False) as stream:
        temporary = Path(stream.name)
        with source.open("rb") as incoming:
            shutil.copyfileobj(incoming, stream)
    temporary.chmod(0o755)
    temporary.replace(target)


def archive_names(rootfs: Path) -> list[str]:
    names = ["."]
    for directory, directories, files in os.walk(rootfs, followlinks=False):
        for name in directories + files:
            relative = (Path(directory) / name).relative_to(rootfs)
            names.append("./" + relative.as_posix())
    return sorted(names, key=os.fsencode)


def build_userspace(
    output: Path,
    cc: str = DEFAULT_CC,
    base_initramfs: Path = DEFAULT_BASE_INITRAMFS,
) -> dict:
    output = Path(output).expanduser()
    if output.is_symlink():
        raise ValueError(f"output must not be a symlink: {output}")
    output = output.resolve()
    if output.exists() and (not output.is_dir() or any(output.iterdir())):
        raise ValueError(f"output must be an empty directory: {output}")

    sources = [
        REPO_ROOT / "verification/linux/userspace/rvv_linux_smoke.c",
        REPO_ROOT / "verification/linux/userspace/rvv_linux_state.S",
        REPO_ROOT / "verification/linux/userspace/custom_caps.c",
    ]
    base_initramfs = Path(base_initramfs).expanduser().resolve()
    for path in [*sources, base_initramfs]:
        if not path.is_file():
            raise ValueError(f"missing input file: {path}")
    epoch = int(os.environ.get("SOURCE_DATE_EPOCH", "0"))
    if not 0 <= epoch <= 0xFFFFFFFF:
        raise ValueError("SOURCE_DATE_EPOCH must fit an unsigned 32-bit cpio timestamp")
    compiler = find_tool(str(cc))
    cpio = find_tool("cpio")
    objdump = None
    if compiler.name.endswith("gcc"):
        candidate = compiler.with_name(compiler.name[:-3] + "objdump")
        if candidate.is_file() and os.access(candidate, os.X_OK):
            objdump = candidate

    manifest = {
        "schema_version": 1,
        "status": "BUILT",
        "sources": {path.name: file_record(path) for path in sources},
        "inputs": {
            "base_initramfs": file_record(base_initramfs),
            "cc": file_record(compiler),
            "cpio": file_record(cpio),
        },
        "commands": [],
        "outputs": {},
    }
    manifest["sources"]["build_userspace.py"] = file_record(Path(__file__).resolve())
    if objdump is not None:
        manifest["inputs"]["objdump"] = file_record(objdump)

    output.mkdir(parents=True, exist_ok=True)
    rootfs = output / "rootfs"
    rootfs.mkdir(mode=0o755)
    rootfs.chmod(0o755)
    (output / "tmp").mkdir()
    environment = {
        "PATH": os.environ.get("PATH", os.defpath),
        "LC_ALL": "C",
        "TZ": "UTC",
        "SOURCE_DATE_EPOCH": str(epoch),
        "TMPDIR": str(output / "tmp"),
    }
    manifest["environment"] = environment
    log_path = output / "build.log"

    def run(argv: list[str], cwd: Path, stdin=None, stdout=None) -> None:
        manifest["commands"].append({
            "argv": argv,
            "cwd": str(cwd),
            "stdin": str(stdin.name) if stdin is not None else None,
            "stdout": str(stdout.name) if stdout is not None else str(log_path),
            "stderr": str(log_path),
        })
        with log_path.open("ab") as log:
            subprocess.run(
                argv, cwd=cwd, env=environment, check=True,
                stdin=stdin if stdin is not None else subprocess.DEVNULL,
                stdout=stdout if stdout is not None else log, stderr=log,
                umask=0o022,
            )

    # C stays scalar; the assembly enables V with .option arch,+v.
    run([
        str(compiler), *COMPILE_FLAGS, f"-ffile-prefix-map={REPO_ROOT}=.",
        *(str(path) for path in sources), "-o", "rvv_linux_smoke",
    ], output)
    binary = output / "rvv_linux_smoke"
    binary.chmod(0o755)
    artifacts = [binary]
    if objdump is not None:
        disassembly = output / "rvv_linux_smoke.objdump"
        with disassembly.open("wb") as stream:
            run([str(objdump), "-d", binary.name], output, stdout=stream)
        artifacts.append(disassembly)

    with base_initramfs.open("rb") as stream:
        run([
            str(cpio), "--extract", "--make-directories", "--preserve-modification-time",
            "--no-absolute-filenames", "--no-preserve-owner",
        ], rootfs, stdin=stream)

    # The SDK loader searches /lib64, while the baseline archive stores libs in /lib.
    lib64 = rootfs / "lib64"
    if not lib64.exists() and not lib64.is_symlink():
        lib64.symlink_to("lib")

    init = output / "init"
    init.write_text(INIT_SCRIPT, encoding="ascii")
    init.chmod(0o755)
    install_file(binary, rootfs / "usr/bin/rvv_linux_smoke", rootfs)
    install_file(init, rootfs / "init", rootfs)
    names = archive_names(rootfs)
    for name in names:
        os.utime(rootfs / name, (epoch, epoch), follow_symlinks=False)
    listing = output / "cpio-files.list"
    listing.write_bytes(b"".join(os.fsencode(name) + b"\0" for name in names))
    initramfs = output / "initramfs.cpio"
    with listing.open("rb") as incoming, initramfs.open("wb") as outgoing:
        run([
            str(cpio), "--null", "--create", "--format=newc",
            "--reproducible", "--owner=0:0",
        ], rootfs, stdin=incoming, stdout=outgoing)
    artifacts.extend([init, listing, initramfs, log_path])
    manifest["outputs"] = {path.name: file_record(path) for path in artifacts}
    (output / "manifest.json").write_text(
        json.dumps(manifest, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    return manifest


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--cc", default=DEFAULT_CC)
    parser.add_argument("--base-initramfs", type=Path, default=DEFAULT_BASE_INITRAMFS)
    args = parser.parse_args(argv)
    try:
        build_userspace(args.output, args.cc, args.base_initramfs)
    except (OSError, ValueError, subprocess.CalledProcessError) as error:
        print(f"error: {error}")
        return 1
    print(json.dumps({"status": "BUILT", "output": str(args.output.expanduser().resolve())}))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
