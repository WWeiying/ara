#!/usr/bin/env python3
"""Transfer validated ELF and raw DDR data through the isolated J10 CDMA loader."""
import argparse
import json
from pathlib import Path
import secrets
import socket
import struct
import sys
import time

from eth_load import blocks, parse_load
from host_image import CAP_HOST, prepare_image


HEADER = struct.Struct("!4sIHHII")
MAGIC = b"AFLD"
CHUNK = 1380
DDR_START = 0x80000000
DDR_LIMIT = 0xFF000000
BEGIN = 1
DATA = 2
END = 3
REPLY = 0x8000


def validate_segments(segments):
    for segment in segments:
        if (segment.size <= 0 or segment.address < DDR_START or
                segment.address + segment.size > DDR_LIMIT):
            raise ValueError(f"Outside Ethernet loader DDR range: "
                             f"0x{segment.address:x}+0x{segment.size:x}")


def unpack_reply(packet, session, opcode):
    if len(packet) < HEADER.size:
        return None
    magic, observed_session, observed_opcode, status, arg0, arg1 = HEADER.unpack_from(packet)
    if magic != MAGIC or observed_session != session or observed_opcode != (opcode | REPLY):
        return None
    if status:
        raise RuntimeError(f"Board rejected opcode {opcode}: status={status}, "
                           f"arg0=0x{arg0:x}, arg1={arg1}")
    return arg0, arg1, packet[HEADER.size:]


def control(sock, session, opcode, arg0, arg1, retries, timeout):
    request = HEADER.pack(MAGIC, session, opcode, 0, arg0, arg1)
    for attempt in range(retries + 1):
        sock.send(request)
        deadline = time.monotonic() + timeout
        while True:
            remaining = deadline - time.monotonic()
            if remaining <= 0:
                break
            sock.settimeout(remaining)
            try:
                reply = sock.recv(1472)
            except socket.timeout:
                break
            result = unpack_reply(reply, session, opcode)
            if result is None:
                continue
            if result != (arg0, arg1, b""):
                raise ValueError(f"Malformed control reply for opcode {opcode}")
            return attempt
    raise TimeoutError(f"No board reply for opcode {opcode}")


def transfer_segment(sock, segment, session, window, retries, timeout):
    packets = (segment.size + CHUNK - 1) // CHUNK
    control_retries = control(sock, session, BEGIN, segment.address,
                              segment.size, retries, timeout)
    source = iter(blocks(segment, CHUNK))
    next_sequence = completed = data_retries = 0
    pending = {}
    while completed < packets:
        # Selective replies must not advance past an unacknowledged hole.
        base = min(pending, default=next_sequence)
        while next_sequence < packets and next_sequence < base + window:
            address, data = next(source)
            if address != segment.address + next_sequence * CHUNK or not data:
                raise ValueError("Noncontiguous source segment")
            packet = HEADER.pack(MAGIC, session, DATA, 0, next_sequence, len(data)) + data
            sock.send(packet)
            pending[next_sequence] = [packet, time.monotonic(), 0]
            next_sequence += 1
        sock.settimeout(min(timeout, 0.05))
        try:
            reply = sock.recv(1472)
        except socket.timeout:
            reply = None
        if reply is not None:
            result = unpack_reply(reply, session, DATA)
            if result is not None:
                sequence, size, readback = result
                if sequence in pending:
                    expected = pending[sequence][0]
                    if size != len(expected) - HEADER.size or readback != expected[HEADER.size:]:
                        raise ValueError(f"DDR readback mismatch at sequence {sequence}")
                    del pending[sequence]
                    completed += 1
        now = time.monotonic()
        for sequence, state in pending.items():
            if now - state[1] >= timeout:
                if state[2] >= retries:
                    raise TimeoutError(f"No DDR readback for sequence {sequence}")
                sock.send(state[0])
                state[1] = now
                state[2] += 1
                data_retries += 1
    control_retries += control(sock, session, END, packets, 0, retries, timeout)
    return {"address": segment.address, "bytes": segment.size, "packets": packets,
            "data_retries": data_retries, "control_retries": control_retries}


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--elf", required=True, type=Path)
    parser.add_argument("--load", action="append", type=parse_load, default=[])
    parser.add_argument("--host", default="192.168.1.10")
    parser.add_argument("--source", default="192.168.1.11")
    parser.add_argument("--port", type=int, default=49204)
    parser.add_argument("--window", type=int, default=8)
    parser.add_argument("--retry-seconds", type=float, default=0.1)
    parser.add_argument("--max-retries", type=int, default=10)
    parser.add_argument("--out", required=True, type=Path)
    args = parser.parse_args(argv)
    if not (1 <= args.port <= 65535 and 1 <= args.window <= 32 and
            args.retry_seconds > 0 and args.max_retries >= 0):
        parser.error("Invalid port/window/retry settings")
    args.out.mkdir(parents=True, exist_ok=False)
    report = {"state": "starting", "board_verified": False,
              "execution_started": False, "segments": []}
    try:
        image = prepare_image(args.elf, args.load, caps=CAP_HOST)
        validate_segments(image.segments)
        report["image"] = image.manifest()
        started = time.monotonic()
        with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as sock:
            sock.setsockopt(socket.SOL_SOCKET, socket.SO_RCVBUF, 1024 * 1024)
            sock.setsockopt(socket.SOL_SOCKET, socket.SO_SNDBUF, 1024 * 1024)
            sock.bind((args.source, 0))
            sock.connect((args.host, args.port))
            for segment in image.segments:
                session = secrets.randbits(32)
                report["segments"].append(transfer_segment(
                    sock, segment, session, args.window, args.max_retries,
                    args.retry_seconds))
        elapsed = time.monotonic() - started
        total = sum(row["bytes"] for row in report["segments"])
        report.update(state="transfer_verified_by_peer_not_execution",
                      payload_bytes=total, seconds=elapsed,
                      payload_bytes_per_second=total / elapsed)
    except (OSError, ValueError, RuntimeError, TimeoutError, StopIteration) as exc:
        report.update(state="failed", error=str(exc))
    (args.out / "report.json").write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    print(f"{report['state']}: {args.out}")
    if report["state"] == "failed":
        print(report["error"], file=sys.stderr)
        return 1
    print(f"{report['payload_bytes']} bytes, {report['seconds']:.3f} s, "
          f"{report['payload_bytes_per_second'] / 1e6:.3f} MB/s including DDR readback")
    return 0


if __name__ == "__main__":
    sys.exit(main())
