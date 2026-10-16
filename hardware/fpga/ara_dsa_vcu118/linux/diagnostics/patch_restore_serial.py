#!/usr/bin/env python3
"""Serialize actual restore loads in a separate hash-pinned diagnostic Image."""
import argparse
import hashlib
from pathlib import Path
import subprocess
import tempfile

p = argparse.ArgumentParser(description=__doc__)
p.add_argument("source", type=Path)
p.add_argument("output", type=Path)
args = p.parse_args()
data = bytearray(args.source.read_bytes())
if hashlib.sha256(data).hexdigest() != "716aef49389b25a0a3f4deac47de0bb69467a10f1057041cecd0f0621fbbf285":
    p.error("Wrong original kernel Image")
prefix = "/home/wangwy/openproject/cva6/cva6-sdk/buildroot/output/host/bin/riscv64-buildroot-linux-gnu-"
with tempfile.TemporaryDirectory() as temp:
    elf, binary = Path(temp) / "fragment.elf", Path(temp) / "fragment.bin"
    subprocess.run([prefix + "gcc", "-march=rv64gcv", "-mabi=lp64d", "-nostdlib", "-static",
                    "-Wl,--no-relax,--build-id=none,-Ttext=0x15e4c",
                    str(Path(__file__).with_name("restore_serial_fragment.S")), "-o", str(elf)], check=True)
    subprocess.run([prefix + "objcopy", "-O", "binary", "-j", ".text", str(elf), str(binary)], check=True)
    fragment = binary.read_bytes()[0x12:]
if len(fragment) != 0x58:
    raise SystemExit("Wrong replacement extent")
data[0x15e5e:0x15eb6] = fragment
with args.output.open("xb") as output:
    output.write(data)
print("DIAGNOSTIC_ONLY serialized restore; not a production repair")
print(hashlib.sha256(data).hexdigest(), args.output)
