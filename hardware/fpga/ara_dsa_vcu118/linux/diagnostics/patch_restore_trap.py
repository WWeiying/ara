#!/usr/bin/env python3
"""Make a hash-pinned kernel breakpoint probe, never a production image."""
import argparse
import hashlib
from pathlib import Path
import struct


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("source", type=Path)
    parser.add_argument("output", type=Path)
    parser.add_argument("--site", choices=("entry", "third", "read"), default="third")
    args = parser.parse_args()
    data = bytearray(args.source.read_bytes())
    expected = "716aef49389b25a0a3f4deac47de0bb69467a10f1057041cecd0f0621fbbf285"
    if hashlib.sha256(data).hexdigest() != expected:
        parser.error("source is not the reviewed board Image")
    if args.site == "read":
        # a0 points to pt_regs; a7 is at byte 136. a2 is dead here and is
        # overwritten by the original vtype load before its next use.
        # Leave every vector instruction unchanged. These are NOP slots
        # for the standard-V (not XTheadVector) machines under investigation.
        patches = [(0x15e5e, 0x13, 0x08853603),
                   (0x15e74, 0x13, 0xfc160613),
                   (0x15e80, 0x13, 0x9002e211)]
    else:
        offset, instruction = {"entry": (0x15e80, 0x13),
                               "third": (0x15e94, 0x02070807)}[args.site]
        patches = [(offset, instruction, 0x00100073)]
    for offset, instruction, replacement in patches:
        if struct.unpack_from("<I", data, offset)[0] != instruction:
            parser.error("unexpected instruction at probe site")
        struct.pack_into("<I", data, offset, replacement)
    with args.output.open("xb") as stream:
        stream.write(data)
    print(f"INTENTIONAL_KERNEL_BREAKPOINT site={args.site}")
    print(hashlib.sha256(data).hexdigest(), args.output)


if __name__ == "__main__":
    main()
