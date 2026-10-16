#!/usr/bin/env python3
"""Measure isolated VCU118 UDP echo or DDR roundtrip diagnostic."""
import argparse
import json
from pathlib import Path
import socket
import struct
import sys
import time


HEADER = struct.Struct("!4sI")
MAGIC = b"AFSP"


def transfer(sock, byte_count, payload_size, window, retry_seconds, max_retries):
    block_size = payload_size - HEADER.size
    total_packets = (byte_count + block_size - 1) // block_size
    next_sequence = 0
    completed = 0
    retries = 0
    pending = {}
    started = time.monotonic()
    while completed < total_packets:
        while next_sequence < total_packets and len(pending) < window:
            take = min(block_size, byte_count - next_sequence * block_size)
            payload = HEADER.pack(MAGIC, next_sequence) + bytes([next_sequence & 255]) * take
            sock.send(payload)
            pending[next_sequence] = [payload, time.monotonic(), 0]
            next_sequence += 1
        try:
            payload = sock.recv(payload_size + 64)
        except socket.timeout:
            payload = None
        if payload is not None:
            if len(payload) < HEADER.size:
                raise ValueError("Short echoed payload")
            magic, sequence = HEADER.unpack_from(payload)
            if magic != MAGIC:
                raise ValueError("Unexpected echoed protocol")
            if sequence in pending:
                if payload != pending[sequence][0]:
                    raise ValueError(f"Echo mismatch at packet {sequence}")
                del pending[sequence]
                completed += 1
        now = time.monotonic()
        for sequence, state in pending.items():
            if now - state[1] >= retry_seconds:
                if state[2] >= max_retries:
                    raise TimeoutError(f"No echo for packet {sequence} after {max_retries} retries")
                sock.send(state[0])
                state[1] = now
                state[2] += 1
                retries += 1
    elapsed = time.monotonic() - started
    return {"data_bytes": byte_count, "packets": total_packets,
            "retries": retries, "seconds": elapsed,
            "data_bytes_per_second": byte_count / elapsed}


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--host", default="192.168.1.10")
    parser.add_argument("--source", default="192.168.1.11")
    parser.add_argument("--port", type=int, default=49201)
    parser.add_argument("--bytes", type=int, default=4 * 1024 * 1024)
    parser.add_argument("--payload", type=int, default=1400)
    parser.add_argument("--window", type=int, default=8)
    parser.add_argument("--retry-seconds", type=float, default=0.1)
    parser.add_argument("--max-retries", type=int, default=10)
    parser.add_argument("--out", required=True, type=Path)
    args = parser.parse_args(argv)
    if not (args.bytes > 0 and HEADER.size < args.payload <= 1472 and
            1 <= args.window <= 64 and args.retry_seconds > 0 and args.max_retries >= 0):
        parser.error("Invalid transfer size/window/retry settings")
    args.out.mkdir(parents=True, exist_ok=False)
    modes = {49201: "frame_echo", 49202: "cpu_ddr_roundtrip",
             49203: "cdma_ddr_roundtrip"}
    report = {"state": "starting", "board_verified": False,
              "port": args.port, "mode": modes.get(args.port, "unknown")}
    try:
        with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as sock:
            sock.setsockopt(socket.SOL_SOCKET, socket.SO_RCVBUF, 1024 * 1024)
            sock.setsockopt(socket.SOL_SOCKET, socket.SO_SNDBUF, 1024 * 1024)
            sock.bind((args.source, 0))
            sock.connect((args.host, args.port))
            sock.settimeout(min(args.retry_seconds, 0.05))
            report.update(transfer(sock, args.bytes, args.payload, args.window,
                                   args.retry_seconds, args.max_retries))
        report["state"] = "echo_verified_by_peer"
    except (OSError, ValueError, TimeoutError) as exc:
        report.update(state="failed", error=str(exc))
    (args.out / "report.json").write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    print(f"{report['state']}: {args.out}")
    if report["state"] == "failed":
        print(report["error"], file=sys.stderr)
        return 1
    print(f"{report['data_bytes']} bytes, {report['seconds']:.3f} s, "
          f"{report['data_bytes_per_second'] / 1e6:.3f} MB/s, {report['retries']} retries")
    return 0


if __name__ == "__main__":
    sys.exit(main())
