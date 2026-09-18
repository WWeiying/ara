#!/usr/bin/env python3
"""Load and verify a DDR ELF using Cheshire's passive UART boot protocol."""
import argparse
from pathlib import Path
import struct
import sys
import time

HERE = Path(__file__).resolve().parent
for wheel in sorted((HERE / "vendor").glob("*.whl")):
    sys.path.insert(0, str(wheel))
import serial
from elftools.elf.elffile import ELFFile

ACK, EOT = b"\x06", b"\x04"


def exact(port, size):
    data = bytearray()
    deadline = time.monotonic() + 10 + size / 1000
    while len(data) < size and time.monotonic() < deadline:
        data.extend(port.read(size - len(data)))
    if len(data) != size:
        raise RuntimeError(f"UART timeout: expected {size} bytes, received {len(data)}")
    return bytes(data)


def expect(port, token):
    got = exact(port, 1)
    if got != token:
        raise RuntimeError(f"UART protocol mismatch: expected {token.hex()}, received {got.hex()}")


def load_segments(path):
    with path.open("rb") as source:
        elf = ELFFile(source)
        if elf.elfclass != 64 or not elf.little_endian or elf["e_machine"] != "EM_RISCV":
            raise ValueError("Expected a little-endian RV64 ELF")
        entry = int(elf["e_entry"])
        segments = []
        for segment in elf.iter_segments():
            if segment["p_type"] != "PT_LOAD" or segment["p_memsz"] == 0:
                continue
            addr, size = int(segment["p_paddr"]), int(segment["p_memsz"])
            if not (0x80000000 <= addr < addr + size <= 0x100000000):
                raise ValueError("Only physical VCU118 DDR addresses are accepted, not MMIO/ROM")
            if size > 64 * 1024 * 1024:
                raise ValueError("UART loader is for small bring-up payloads, not large model images")
            data = segment.data()
            if len(data) > size:
                raise ValueError("Invalid ELF segment size")
            segments.append((addr, data + bytes(size - len(data)), int(segment["p_flags"])))
    segments.sort()
    for left, right in zip(segments, segments[1:]):
        if left[0] + len(left[1]) > right[0]:
            raise ValueError("Overlapping ELF load segments")
    if not any(addr <= entry < addr + len(data) and flags & 1 for addr, data, flags in segments):
        raise ValueError("Entry point is not in an executable load segment")
    return entry, segments


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--port", required=True, help="e.g. COM5 or /dev/ttyUSB0")
    parser.add_argument("--elf", type=Path, default=HERE / "smoke.elf")
    parser.add_argument("--seconds", type=float, default=30)
    args = parser.parse_args()
    entry, segments = load_segments(args.elf)
    with serial.Serial(args.port, 115200, timeout=0.2, write_timeout=10,
                       rtscts=False, dsrdtr=False) as port:
        port.reset_input_buffer()
        port.write(ACK)
        expect(port, ACK)
        for addr, data, _ in segments:
            for offset in range(0, len(data), 256):
                chunk = data[offset:offset + 256]
                address = addr + offset
                port.write(b"\x12" + struct.pack("<QQ", address, len(chunk)))
                expect(port, ACK)
                port.write(chunk)
                expect(port, EOT)
                port.write(b"\x11" + struct.pack("<QQ", address, len(chunk)))
                expect(port, ACK)
                actual = exact(port, len(chunk))
                expect(port, EOT)
                if actual != chunk:
                    raise RuntimeError(f"Load readback mismatch at 0x{address:x}")
            print(f"Loaded and verified {len(data)} bytes at 0x{addr:x}", flush=True)
        port.write(b"\x13" + struct.pack("<Q", entry))
        expect(port, ACK)
        print(f"Executing 0x{entry:x}; collecting UART for {args.seconds:g} seconds", flush=True)
        output = bytearray()
        end = time.monotonic() + args.seconds
        while time.monotonic() < end:
            chunk = port.read(256)
            output.extend(chunk)
            if chunk:
                print(chunk.hex(" "), end="", flush=True)
        if args.elf.name == "smoke.elf" and b"SMOKE PASS:" not in output:
            raise RuntimeError("Smoke pass marker not received; inspect UART output and VIO")


if __name__ == "__main__":
    main()
