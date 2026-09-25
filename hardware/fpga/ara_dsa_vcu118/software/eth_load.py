#!/usr/bin/env python3
"""Candidate TCP image sender for the VCU118 Ethernet-to-DDR loader.

The board receiver is not implemented yet. This module is deliberately usable
against a test peer, but a successful exchange is not a board validation.
"""
import argparse
import json
from pathlib import Path
import socket
import struct
import sys
import time
import zlib

from host_image import CAP_HOST, prepare_image


MAGIC = b"ARAETH01"
HELLO = struct.Struct("<8sII")  # magic, capabilities, largest accepted data block
RECORD = struct.Struct("<4sQII")  # opcode, address/entry, byte count, CRC32
ACK = struct.Struct("<QII")  # address/entry, DDR readback CRC32, status
MAX_CHUNK = 65536


def receive_exact(stream, length):
    data = bytearray()
    while len(data) < length:
        part = stream.recv(length - len(data))
        if not part:
            raise ConnectionError(f"Peer closed after {len(data)}/{length} response bytes")
        data.extend(part)
    return bytes(data)


def hello(stream):
    stream.sendall(MAGIC)
    magic, caps, max_chunk = HELLO.unpack(receive_exact(stream, HELLO.size))
    if magic != MAGIC or not caps & CAP_HOST or not 1 <= max_chunk <= MAX_CHUNK:
        raise ValueError("Incompatible Ethernet loader identity/capabilities/chunk size")
    return caps, max_chunk


def blocks(segment, max_chunk):
    address = None
    block = bytearray()
    for current, data in segment.chunks():
        while data:
            if block and (current != address + len(block) or len(block) == max_chunk):
                yield address, bytes(block)
                block.clear()
                address = None
            if address is None:
                address = current
            take = min(len(data), max_chunk - len(block))
            block.extend(data[:take])
            current += take
            data = data[take:]
    if block:
        yield address, bytes(block)


def send_record(stream, opcode, address, data=b""):
    crc = zlib.crc32(data)
    stream.sendall(RECORD.pack(opcode, address, len(data), crc))
    if data:
        stream.sendall(data)
    observed_address, observed_crc, status = ACK.unpack(receive_exact(stream, ACK.size))
    if status or observed_address != address or observed_crc != crc:
        raise RuntimeError(f"DDR verification rejected at 0x{address:x}: "
                           f"status={status}, address=0x{observed_address:x}, "
                           f"readback_crc=0x{observed_crc:08x}, expected_crc=0x{crc:08x}")


def transfer(stream, image, max_chunk):
    if not 1 <= max_chunk <= MAX_CHUNK:
        raise ValueError("Invalid board maximum chunk size")
    count = 0
    total = 0
    for segment in image.segments:
        for address, data in blocks(segment, max_chunk):
            send_record(stream, b"DATA", address, data)
            count += 1
            total += len(data)
    send_record(stream, b"DONE", image.entry)
    return {"payload_bytes": total, "verified_blocks": count,
            "entry": image.entry, "execution_started": False}


def parse_load(value):
    address, separator, source = value.partition(":")
    if not separator or not source:
        raise argparse.ArgumentTypeError("--load must be ADDRESS:PATH")
    try:
        return int(address, 0), Path(source)
    except ValueError as exc:
        raise argparse.ArgumentTypeError("Invalid --load address") from exc


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--elf", required=True, type=Path)
    parser.add_argument("--load", action="append", type=parse_load, default=[])
    parser.add_argument("--host", help="Board IP; omit only with --plan-only")
    parser.add_argument("--port", type=int, default=49200)
    parser.add_argument("--timeout", type=float, default=30)
    parser.add_argument("--out", required=True, type=Path)
    parser.add_argument("--plan-only", action="store_true", help="Validate image without network access")
    args = parser.parse_args(argv)
    if not args.plan_only and not args.host:
        parser.error("--host is required unless --plan-only is set")
    if not 1 <= args.port <= 65535 or args.timeout <= 0:
        parser.error("Invalid port or timeout")
    report = {"state": "starting", "board_verified": False, "execution_started": False}
    created = False
    try:
        args.out.mkdir(parents=True, exist_ok=False)
        created = True
        if args.plan_only:
            image = prepare_image(args.elf, args.load)
            report.update(state="plan_only", image=image.manifest())
        else:
            with socket.create_connection((args.host, args.port), args.timeout) as stream:
                stream.settimeout(args.timeout)
                caps, max_chunk = hello(stream)
                image = prepare_image(args.elf, args.load, caps=caps)
                report.update(image=image.manifest(), board_capabilities=caps,
                              board_max_chunk=max_chunk)
                started = time.monotonic()
                report.update(transfer(stream, image, max_chunk))
                elapsed = time.monotonic() - started
                report["transfer_seconds_including_peer_readback"] = elapsed
                report["payload_bytes_per_second_including_peer_readback"] = (
                    report["payload_bytes"] / elapsed if elapsed > 0 else None)
                report["state"] = "transfer_verified_by_peer_not_execution"
                report["board_verified"] = False  # A peer can be a simulator.
    except (OSError, ValueError, RuntimeError, ConnectionError) as exc:
        report.update(state="failed", error=str(exc))
    finally:
        if created:
            (args.out / "report.json").write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    print(f"{report['state']}: {args.out}")
    if report["state"] == "failed":
        print(report["error"], file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
