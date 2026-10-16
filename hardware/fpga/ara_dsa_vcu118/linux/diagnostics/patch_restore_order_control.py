#!/usr/bin/env python3
"""Diagnostic only: move one NOP's space after v24 and insert FENCE rw,rw.

Same vector loads, operands, and scalar metadata reads. This changes ordering,
not the MMU; passing this control is not an RTL repair or hardware signoff.
"""
import argparse
import hashlib
import json
from pathlib import Path

SOURCE_SHA256 = "716aef49389b25a0a3f4deac47de0bb69467a10f1057041cecd0f0621fbbf285"
START, VECTOR, END = 0x15e80, 0x15e84, 0x15e9e


def patch_image(source):
    if hashlib.sha256(source).hexdigest() != SOURCE_SHA256:
        raise ValueError("Wrong original Image")
    if source[START:VECTOR] != bytes.fromhex("13000000"):
        raise ValueError("Expected spare NOP")
    if source[END-4:END] != bytes.fromhex("070c0702"):
        raise ValueError("Expected final vle8.v v24")
    result = bytearray(source)
    result[START:END] = source[VECTOR:END] + bytes.fromhex("0f003003")
    assert len(result) == len(source)
    assert result[:START] == source[:START] and result[END:] == source[END:]
    return bytes(result)


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("source", type=Path)
    p.add_argument("output", type=Path)
    a = p.parse_args()
    source = a.source.read_bytes()
    result = patch_image(source)
    with a.output.open("xb") as f:
        f.write(result)
    print(json.dumps({"diagnostic_only": True, "source_sha256": SOURCE_SHA256,
                      "output_sha256": hashlib.sha256(result).hexdigest(),
                      "extent": [hex(START), hex(END)],
                      "old": source[START:END].hex(), "new": result[START:END].hex()}))


if __name__ == "__main__":
    main()
