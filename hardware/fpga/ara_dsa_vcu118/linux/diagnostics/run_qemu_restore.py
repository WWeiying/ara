#!/usr/bin/env python3
"""Bounded GDB trace of the hash-pinned board Image on QEMU, no RTL changes."""
import argparse
import hashlib
from pathlib import Path
import subprocess
import time


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("image", type=Path)
    parser.add_argument("initramfs", type=Path)
    parser.add_argument("out", type=Path)
    parser.add_argument("--gdb-script", type=Path,
                        default=Path(__file__).with_name("qemu_restore.gdb"))
    args = parser.parse_args()
    if hashlib.sha256(args.image.read_bytes()).hexdigest() != "716aef49389b25a0a3f4deac47de0bb69467a10f1057041cecd0f0621fbbf285":
        parser.error("wrong kernel Image")
    sdk = Path("/home/wangwy/openproject/cva6/cva6-sdk")
    host = sdk / "buildroot/output/host/bin"
    args.out.mkdir(parents=True, exist_ok=False)
    command = [str(host / "qemu-system-riscv64"), "-machine", "virt",
               "-cpu", "rv64,v=true,vlen=1024,elen=64", "-smp", "1", "-m", "2G",
               "-no-reboot", "-display", "none", "-monitor", "none", "-serial", "stdio",
               "-bios", str(sdk / "install64_qemu/fw_dynamic.bin"),
               "-kernel", str(args.image), "-initrd", str(args.initramfs),
               "-append", "console=ttyS0,115200 earlycon=sbi loglevel=7 rdinit=/init unaligned_scalar_speed=unsupported unaligned_vector_speed=unsupported",
               "-S", "-gdb", "tcp:127.0.0.1:12347",
               "-D", str(args.out.resolve() / "tb.log")]
    with (args.out / "uart.log").open("w") as uart, (args.out / "gdb.log").open("w") as trace:
        process = subprocess.Popen(command, stdout=uart, stderr=subprocess.STDOUT)
        try:
            time.sleep(1)
            if process.poll() is not None:
                raise RuntimeError("QEMU failed to start; see uart.log")
            result = subprocess.run([str(host / "riscv64-buildroot-linux-gnu-gdb"),
                                     "-nx", "-batch", "-x", str(args.gdb_script.resolve())],
                                    stdout=trace, stderr=subprocess.STDOUT, timeout=60)
            return result.returncode
        finally:
            process.terminate()
            try:
                process.wait(timeout=5)
            except subprocess.TimeoutExpired:
                process.kill()
                process.wait()


if __name__ == "__main__":
    raise SystemExit(main())
