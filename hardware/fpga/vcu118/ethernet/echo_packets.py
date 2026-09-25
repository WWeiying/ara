#!/usr/bin/env python3
"""Send bounded raw Ethernet frames to the isolated VCU118 echo diagnostic."""
import argparse
from datetime import datetime, timezone
import json
from pathlib import Path
import queue
import secrets
import sys
import threading
import time


BOARD_MAC = bytes.fromhex("020000000118")
ETHERTYPE = 0x88B5
FRAME_SIZES = (60, 64, 512, 1514)


def mac_bytes(value):
    result = bytes.fromhex(value.replace(":", "").replace("-", ""))
    if len(result) != 6 or result == b"\0" * 6 or result[0] & 1:
        raise ValueError(f"Expected a nonzero unicast host MAC, got {value!r}")
    return result


def frame_pair(size, host_mac, nonce):
    if not 60 <= size <= 1514 or len(nonce) != 8:
        raise ValueError("Invalid diagnostic frame size or nonce")
    marker = b"ARA-ECHO" + nonce
    payload = (marker + bytes(range(256)) * 6)[: size - 14]
    header = ETHERTYPE.to_bytes(2, "big")
    return (BOARD_MAC + host_mac + header + payload,
            host_mac + BOARD_MAC + header + payload)


def select_interface(conf, description):
    matches = [interface for interface in conf.ifaces.values()
               if interface.description == description]
    if len(matches) != 1:
        raise RuntimeError(f"Expected one wired adapter named {description!r}; found {len(matches)}")
    interface = matches[0]
    mac = mac_bytes(interface.mac)
    return interface, mac


def exchange(interface, host_mac, timeout):
    from scapy.all import AsyncSniffer, Ether, sendp

    responses = queue.Queue()
    ready = threading.Event()
    sniffer = AsyncSniffer(
        iface=interface,
        filter="ether src 02:00:00:00:01:18 and ether proto 0x88b5",
        prn=lambda packet: responses.put(bytes(packet)),
        store=False,
        started_callback=ready.set,
    )
    sniffer.start()
    rows = []
    try:
        if not ready.wait(timeout):
            raise RuntimeError("Npcap capture did not start")
        for size in FRAME_SIZES:
            sent, expected = frame_pair(size, host_mac, secrets.token_bytes(8))
            start = time.monotonic()
            sendp(Ether(sent), iface=interface, verbose=False)
            deadline = start + timeout
            while True:
                remaining = deadline - time.monotonic()
                if remaining <= 0:
                    raise TimeoutError(f"No matching echo for {size}-byte frame")
                try:
                    received = responses.get(timeout=remaining)
                except queue.Empty as exc:
                    raise TimeoutError(f"No matching echo for {size}-byte frame") from exc
                if received == expected:
                    break
            rows.append({"frame_bytes_excluding_fcs": size,
                         "elapsed_ms": round((time.monotonic() - start) * 1000, 3),
                         "exact_echo": True})
            print(f"ECHO_PASS size={size} elapsed_ms={rows[-1]['elapsed_ms']}", flush=True)
    finally:
        sniffer.stop()
    return rows


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--out", type=Path, required=True)
    parser.add_argument("--iface-description", default="Realtek PCIe GbE Family Controller")
    parser.add_argument("--timeout", type=float, default=3.0)
    args = parser.parse_args(argv)
    if not 0 < args.timeout <= 30:
        parser.error("--timeout must be in (0, 30] seconds")
    args.out.mkdir(parents=True, exist_ok=False)
    report = {"state": "failed", "started_utc": datetime.now(timezone.utc).isoformat(),
              "board_mac": ":".join(f"{byte:02x}" for byte in BOARD_MAC), "rows": []}
    try:
        from scapy.all import conf
        conf.use_pcap = True
        interface, host_mac = select_interface(conf, args.iface_description)
        report["interface"] = interface.description
        report["host_mac"] = ":".join(f"{byte:02x}" for byte in host_mac)
        report["rows"] = exchange(interface, host_mac, args.timeout)
        report["state"] = "passed"
        return 0
    except (ImportError, OSError, RuntimeError, ValueError, TimeoutError) as exc:
        report["error"] = str(exc)
        print(f"ECHO_FAILED {exc}", file=sys.stderr, flush=True)
        return 1
    finally:
        report["completed_utc"] = datetime.now(timezone.utc).isoformat()
        (args.out / "echo_packets.json").write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
        print("EVIDENCE", args.out, flush=True)


if __name__ == "__main__":
    sys.exit(main())
