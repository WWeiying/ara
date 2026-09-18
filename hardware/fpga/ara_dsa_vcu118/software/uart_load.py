#!/usr/bin/env python3
"""Load DDR payloads using Cheshire's passive UART boot protocol."""
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
DDR_START = 0x80000000
DDR_END = 0x100000000
CHUNK_SIZE = 256
DEFAULT_BAUD = 115200


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
            if not (DDR_START <= addr < addr + size <= DDR_END):
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


def load_raw(path, address):
    data = path.read_bytes()
    if not data:
        raise ValueError(f"Raw payload is empty: {path}")
    if not (DDR_START <= address < address + len(data) <= DDR_END):
        raise ValueError(f"Raw payload is outside VCU118 DDR: 0x{address:x} {path}")
    return address, data, 0


def parse_raw_load(spec):
    try:
        address_text, path_text = spec.split(":", 1)
        address = int(address_text, 0)
    except ValueError as exc:
        raise argparse.ArgumentTypeError(
            "expected ADDRESS:PATH, for example 0x80200000:linux/out/Image"
        ) from exc
    return address, Path(path_text)


def write_and_verify(port, address, data, verify, chunk_size):
    for offset in range(0, len(data), chunk_size):
        chunk = data[offset:offset + chunk_size]
        chunk_address = address + offset
        port.write(b"\x12" + struct.pack("<QQ", chunk_address, len(chunk)))
        expect(port, ACK)
        port.write(chunk)
        expect(port, EOT)
        if verify:
            port.write(b"\x11" + struct.pack("<QQ", chunk_address, len(chunk)))
            expect(port, ACK)
            actual = exact(port, len(chunk))
            expect(port, EOT)
            if actual != chunk:
                raise RuntimeError(f"Load readback mismatch at 0x{chunk_address:x}")


def print_uart_chunk(chunk):
    try:
        print(chunk.decode("utf-8", errors="replace"), end="", flush=True)
    except UnicodeEncodeError:
        print(f"\n[UART non-UTF8] {chunk.hex(' ')}", flush=True)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--port", required=True, help="e.g. COM5 or /dev/ttyUSB0")
    parser.add_argument(
        "--baud", type=int, default=DEFAULT_BAUD,
        help=(
            f"UART baud rate (default: {DEFAULT_BAUD}); use 1562500 only with "
            "the matching fast-boot bitstream and the CP2105 enhanced port"
        ),
    )
    parser.add_argument(
        "--console-baud", type=int,
        help="switch the host UART to this rate immediately after EXEC is acknowledged",
    )
    parser.add_argument("--elf", type=Path, default=HERE / "smoke.elf")
    parser.add_argument(
        "--load", action="append", type=parse_raw_load, default=[],
        metavar="ADDRESS:PATH",
        help="load a raw file at a DDR address; repeat for Image/DTB/initramfs",
    )
    parser.add_argument(
        "--entry", type=lambda value: int(value, 0),
        help="override the ELF entry point, for example 0x80000000",
    )
    parser.add_argument(
        "--no-readback", action="store_true",
        help="skip per-chunk UART readback; useful for large Linux payloads",
    )
    parser.add_argument(
        "--chunk-size", type=int, default=CHUNK_SIZE,
        help=f"bytes per UART WRITE transaction (default: {CHUNK_SIZE})",
    )
    parser.add_argument("--seconds", type=float, default=30)
    args = parser.parse_args()
    if args.chunk_size <= 0:
        parser.error("--chunk-size must be positive")
    if args.baud <= 0:
        parser.error("--baud must be positive")
    if args.console_baud is not None and args.console_baud <= 0:
        parser.error("--console-baud must be positive")
    entry, segments = load_segments(args.elf)
    segments.extend(load_raw(path, address) for address, path in args.load)
    segments.sort()
    for left, right in zip(segments, segments[1:]):
        if left[0] + len(left[1]) > right[0]:
            raise ValueError("ELF and raw payloads overlap in DDR")
    if args.entry is not None:
        entry = args.entry
    if not any(addr <= entry < addr + len(data) and flags & 1
               for addr, data, flags in segments):
        raise ValueError("Entry point is not in an executable ELF load segment")
    with serial.Serial(args.port, args.baud, timeout=0.2, write_timeout=10,
                       rtscts=False, dsrdtr=False) as port:
        port.reset_input_buffer()
        port.write(ACK)
        expect(port, ACK)
        for addr, data, flags in segments:
            write_and_verify(port, addr, data, not args.no_readback, args.chunk_size)
            status = "loaded and verified" if not args.no_readback else "loaded"
            kind = "ELF" if flags else "raw"
            print(f"{status} {kind} {len(data)} bytes at 0x{addr:x}", flush=True)
        port.write(b"\x13" + struct.pack("<Q", entry))
        expect(port, ACK)
        print(f"Executing 0x{entry:x}; collecting UART for {args.seconds:g} seconds", flush=True)
        if args.console_baud is not None and args.console_baud != args.baud:
            port.baudrate = args.console_baud
            print(f"Switched host UART console to {args.console_baud} baud", flush=True)
        output = bytearray()
        end = time.monotonic() + args.seconds
        while time.monotonic() < end:
            chunk = port.read(256)
            output.extend(chunk)
            if chunk:
                print_uart_chunk(chunk)
        if args.elf.name == "smoke.elf" and not args.load and b"SMOKE PASS:" not in output:
            raise RuntimeError("Smoke pass marker not received; inspect UART output and VIO")


if __name__ == "__main__":
    main()
