#!/usr/bin/env python3
"""Make an isolated, hash-pinned diagnostic Image; not a production fix."""
import argparse
import hashlib
from pathlib import Path
import struct

parser = argparse.ArgumentParser(description=__doc__)
parser.add_argument("source", type=Path)
parser.add_argument("output", type=Path)
args = parser.parse_args()
data = bytearray(args.source.read_bytes())
expected = "716aef49389b25a0a3f4deac47de0bb69467a10f1057041cecd0f0621fbbf285"
if hashlib.sha256(data).hexdigest() != expected:
    parser.error("source is not the reviewed board Image")
offset = 0xb880f4
if struct.unpack_from("<I", data, offset)[0] != 0x00000013:
    parser.error("expected 32-bit NOP at discard drain site")
# CSRRS x0, vl, x0: no architectural register/state change; Ara waits for idle.
struct.pack_into("<I", data, offset, 0xc2002073)
with args.output.open("xb") as stream:
    stream.write(data)
print(hashlib.sha256(data).hexdigest(), args.output)
