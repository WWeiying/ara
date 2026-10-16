#!/usr/bin/env python3
"""Diagnostic-only scalar usercopy control; does not disable user RVV."""
import argparse
import hashlib
from pathlib import Path
import struct


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("source", type=Path)
    parser.add_argument("output", type=Path)
    args = parser.parse_args()
    data = bytearray(args.source.read_bytes())
    if hashlib.sha256(data).hexdigest() != "716aef49389b25a0a3f4deac47de0bb69467a10f1057041cecd0f0621fbbf285":
        parser.error("wrong kernel Image")
    # Both actual Image AUIPC/LD pairs resolve to this data object.
    for offset, words in ((0xb874a0, (0x00e9d297, 0x1a02b283, 0x00566663)),
                          (0xb874d4, (0x00e9d297, 0x16c2b283, 0x00566663))):
        if struct.unpack_from("<3I", data, offset) != words:
            parser.error("usercopy threshold reference does not match")
    offset = 0x1a24640
    if struct.unpack_from("<Q", data, offset)[0] != 768:
        parser.error("unexpected usercopy threshold")
    struct.pack_into("<Q", data, offset, 0xffffffffffffffff)
    with args.output.open("xb") as stream:
        stream.write(data)
    print("DIAGNOSTIC_ONLY scalar usercopy; user RVV and vector restore unchanged")
    print(hashlib.sha256(data).hexdigest(), args.output)


if __name__ == "__main__":
    main()
