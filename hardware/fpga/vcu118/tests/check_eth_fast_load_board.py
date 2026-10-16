#!/usr/bin/env python3
"""Controlled protocol acceptance for the isolated Ethernet CDMA loader."""
import argparse
import json
from pathlib import Path
import secrets
import socket
import sys
from types import SimpleNamespace

sys.path.insert(0, str(Path(__file__).resolve().parents[2] /
                       "ara_dsa_vcu118" / "software"))
import eth_fast_load as loader


def exchange(sock, session, opcode, arg0, arg1, data=b"", expected_status=0):
    request = loader.HEADER.pack(loader.MAGIC, session, opcode, 0, arg0, arg1) + data
    sock.send(request)
    reply = sock.recv(1472)
    expected = loader.HEADER.pack(loader.MAGIC, session, opcode | loader.REPLY,
                                  expected_status, arg0, arg1) + data
    if reply != expected:
        raise ValueError(f"Unexpected reply for opcode {opcode}, arg0={arg0}, "
                         f"expected status={expected_status}")


def check(sock):
    session = secrets.randbits(32)
    address = 0x85000FF8
    length = 2 * loader.CHUNK + 7
    checks = []
    exchange(sock, session, loader.BEGIN, loader.DDR_LIMIT, 8, expected_status=1)
    checks.append("reserved_range_rejected")
    exchange(sock, session, loader.BEGIN, address, length)
    data = [bytes((i * 37 + sequence * 19) & 255 for i in range(size))
            for sequence, size in enumerate((loader.CHUNK, loader.CHUNK, 7))]
    exchange(sock, session, loader.DATA, 1, len(data[1]), data[1])
    exchange(sock, session, loader.END, 3, 0, expected_status=4)
    checks.append("incomplete_end_rejected")
    for sequence in (1, 0, 2):
        exchange(sock, session, loader.DATA, sequence, len(data[sequence]), data[sequence])
    exchange(sock, session, loader.END, 3, 0)
    checks.append("reordered_duplicate_and_unaligned_ddr_readback")
    exchange(sock, session, loader.DATA, 0, len(data[0]), data[0], expected_status=2)
    checks.append("finished_session_write_rejected")

    class DropOneSocket:
        def __init__(self):
            self.dropped = False

        def send(self, packet):
            fields = loader.HEADER.unpack_from(packet)
            if fields[2] == loader.DATA and fields[4] == 1 and not self.dropped:
                self.dropped = True
                return len(packet)
            return sock.send(packet)

        def recv(self, size):
            return sock.recv(size)

        def settimeout(self, timeout):
            sock.settimeout(timeout)

    loss_data = bytes((i * 17 + (i >> 8)) & 255 for i in range(80 * loader.CHUNK))
    loss_address = 0x86000FF8
    segment = SimpleNamespace(address=loss_address, size=len(loss_data),
                              chunks=lambda: iter(((loss_address, loss_data),)))
    loss_result = loader.transfer_segment(DropOneSocket(), segment,
                                           secrets.randbits(32), 8, 10, 0.1)
    if loss_result["data_retries"] < 1:
        raise ValueError("Injected lost packet was not retransmitted")
    checks.append("lost_early_packet_retried_without_window_overrun")
    return {"checks": checks, "address": address, "bytes": length,
            "loss_injection_transfer": loss_result, "execution_started": False}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--host", default="192.168.1.10")
    parser.add_argument("--source", default="192.168.1.11")
    parser.add_argument("--out", required=True, type=Path)
    args = parser.parse_args()
    args.out.mkdir(parents=True, exist_ok=False)
    report = {"state": "failed", "board_verified": False}
    try:
        with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as sock:
            sock.bind((args.source, 0))
            sock.connect((args.host, 49204))
            sock.settimeout(2)
            report.update(check(sock), state="protocol_peer_checks_passed")
    except (OSError, ValueError) as exc:
        report["error"] = str(exc)
    (args.out / "report.json").write_text(json.dumps(report, indent=2) + "\n",
                                          encoding="utf-8")
    print(json.dumps(report, indent=2))
    return int(report["state"] == "failed")


if __name__ == "__main__":
    sys.exit(main())
