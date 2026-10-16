#!/usr/bin/env python3
"""Send a large GGUF file to the running Linux image over its UART console."""

import argparse
import binascii
from pathlib import Path
import struct
import sys
import time

HERE = Path(__file__).resolve().parent
for wheel in sorted((HERE / "vendor").glob("*.whl")):
    sys.path.insert(0, str(wheel))
import serial

READY = b"MODEL_RX_READY\n"
DONE = b"MODEL_RX_DONE"
ACK = b"\x06"
NAK = b"\x15"


def read_until(port, marker, timeout):
    data = bytearray()
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        chunk = port.read(256)
        if chunk:
            data.extend(chunk)
            if marker in data:
                return bytes(data)
            if len(data) > 64 * 1024:
                del data[:-len(marker)]
    raise RuntimeError(f"UART timeout waiting for {marker!r}; received {bytes(data[-256:])!r}")


def read_exact(port, size, timeout):
    data = bytearray()
    deadline = time.monotonic() + timeout
    while len(data) < size and time.monotonic() < deadline:
        data.extend(port.read(size - len(data)))
    if len(data) != size:
        raise RuntimeError(f"UART timeout: expected {size} bytes, received {len(data)}")
    return bytes(data)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--port", required=True, help="e.g. COM6 or /dev/ttyUSB0")
    parser.add_argument("--model", required=True, type=Path)
    parser.add_argument(
        "--target", default="/model/qwen2.5-1.5b-instruct-q4_k_m.gguf",
        help="target path in the Linux initramfs",
    )
    parser.add_argument("--baud", type=int, default=115200)
    parser.add_argument("--chunk-size", type=int, default=64 * 1024)
    parser.add_argument("--timeout", type=float, default=30.0)
    args = parser.parse_args()
    if args.chunk_size <= 0 or args.chunk_size > 64 * 1024:
        parser.error("--chunk-size must be between 1 and 65536")
    if args.baud <= 0:
        parser.error("--baud must be positive")

    model = args.model.resolve()
    size = model.stat().st_size
    if size <= 0:
        raise RuntimeError(f"empty model: {model}")
    print(f"model={model}")
    print(f"bytes={size} ({size / (1024 ** 3):.3f} GiB)")
    print(f"target={args.target}")
    print("waiting for the Linux shell to start model-rx ...", flush=True)

    with serial.Serial(args.port, args.baud, timeout=0.2, write_timeout=30,
                       rtscts=False, dsrdtr=False) as port:
        port.reset_input_buffer()
        command = f"model-rx {args.target} {size}\n".encode("ascii")
        port.write(command)
        read_until(port, READY, args.timeout)
        print("receiver ready; sending framed model", flush=True)

        sent = 0
        next_report = 0
        crc_source = 0
        with model.open("rb") as source:
            while sent < size:
                chunk = source.read(min(args.chunk_size, size - sent))
                if not chunk:
                    raise RuntimeError("model ended before stat size")
                crc = binascii.crc32(chunk) & 0xffffffff
                frame = struct.pack("<I", len(chunk)) + chunk + struct.pack("<I", crc)
                for attempt in range(5):
                    port.write(frame)
                    response = read_exact(port, 1, args.timeout)
                    if response == ACK:
                        break
                    if response != NAK:
                        raise RuntimeError(f"unexpected receiver response: {response.hex()}")
                    if attempt == 4:
                        raise RuntimeError(f"chunk at {sent} failed five CRC retries")
                sent += len(chunk)
                crc_source = binascii.crc32(chunk, crc_source) & 0xffffffff
                percent = sent * 100 // size
                if percent >= next_report:
                    print(f"{percent:3d}% ({sent}/{size})", flush=True)
                    next_report = percent + 1

        port.write(struct.pack("<I", 0))
        read_until(port, DONE, args.timeout)

    print(f"transfer complete; source crc32={crc_source:08x}")
    print("verify on the target with: sha256sum /model/qwen2.5-1.5b-instruct-q4_k_m.gguf")


if __name__ == "__main__":
    main()
