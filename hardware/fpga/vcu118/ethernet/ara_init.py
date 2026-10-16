#!/usr/bin/env python3
"""Initialize matching MicroBlaze firmware after fresh integrated programming only."""
import argparse
import hashlib
from pathlib import Path
import socket
import struct
import subprocess
import time

import ara_load as load


def validate_firmware(data, expected):
    if hashlib.sha256(data).hexdigest() != expected.lower():
        raise ValueError("Firmware SHA256 mismatch")
    if len(data) < 52 or data[:7] != b"\x7fELF\x01\x01\x01":
        raise ValueError("Expected ELF32 little-endian firmware")
    fields = struct.unpack_from("<HHIIIIIHHHHHH", data, 16)
    kind, machine, version, entry, offset = fields[:5]
    if (kind, machine, version, entry, fields[8]) != (2, 189, 1, 0, 32):
        raise ValueError("Unexpected MicroBlaze ELF header")
    count = fields[9]
    if not count or offset + 32 * count > len(data):
        raise ValueError("Truncated program headers")
    regions = []
    for index in range(count):
        typ, pos, va, pa, size, memory, flags, _ = struct.unpack_from("<8I", data, offset + 32 * index)
        if typ != 1:
            continue
        if size > memory or pos + size > len(data) or va != pa or not memory:
            raise ValueError("Invalid firmware segment")
        end = pa + memory
        bram = 0 <= pa < end <= 0x80000
        private = 0xFF000000 <= pa < end <= 0x100000000 and not flags & 1
        if not (bram or private):
            raise ValueError("Firmware segment touches application memory")
        if any(pa < old_end and old_start < end for old_start, old_end in regions):
            raise ValueError("Overlapping firmware segments")
        regions.append((pa, end))
    if not any(start == 0 and end > 0 for start, end in regions):
        raise ValueError("Missing reset vector")
    return regions


def fresh_guard(transport):
    identity = load.host.identity(transport)
    load.require_host_profile(identity["caps"])
    status = load.loader_status(transport.ethernet_status())
    if any(status[name] for name in ("aw", "b", "ar", "rlast")):
        raise RuntimeError("Loader already accessed DDR; refuse processor reset/download")
    return {"identity": identity, "loader": status,
            "cold": load.cold_guard(transport), "rom_sha256": load.verify_rom(transport)}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--elf", type=Path, required=True)
    parser.add_argument("--sha256", required=True)
    parser.add_argument("--probes", type=Path, required=True)
    parser.add_argument("--out", type=Path, required=True)
    parser.add_argument("--fresh-bitstream-confirmed", action="store_true", required=True)
    parser.add_argument("--vivado", default="vivado")
    parser.add_argument("--xsct", default="xsct")
    parser.add_argument("--server", default="tcp:localhost:3121")
    parser.add_argument("--host", default="192.168.1.10")
    parser.add_argument("--source", default="192.168.1.11")
    parser.add_argument("--prepare-phy-clock", action="store_true",
                        help="Enable VCU118 six-wire PHY clock before firmware DMA/PCS initialization")
    args = parser.parse_args()
    args.out.mkdir(parents=True, exist_ok=False)
    report = {"state": "starting", "passed": False, "program_launched": False,
              "phy_clock_preparation_requested": args.prepare_phy_clock}
    try:
        data = args.elf.read_bytes()
        report["segments"] = validate_firmware(data, args.sha256)
        # Use this checked snapshot even if another process rebuilds the source ELF.
        elf = (args.out / "firmware.elf").resolve()
        elf.write_bytes(data)
        report["elf_sha256"] = hashlib.sha256(data).hexdigest()
        with load.VivadoTransport(args.out / "precheck", vivado=args.vivado, probes=args.probes) as transport:
            report["precheck"] = fresh_guard(transport)
        report["state"] = "firmware_download"
        load.host.write_json(args.out / "report.json", report)
        with (args.out / "xsct.log").open("w") as log:
            command = [args.xsct, str(Path(__file__).with_name("ara_mb_download.tcl")),
                       str(elf), args.server]
            if args.prepare_phy_clock:
                command.append("--prepare-phy-clock")
            subprocess.run(command, stdout=log, stderr=subprocess.STDOUT,
                           timeout=120, check=True)
        report["phy_clock_prepared"] = args.prepare_phy_clock
        with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as sock:
            sock.bind((args.source, 0))
            sock.connect((args.host, 49204))
            deadline = time.monotonic() + 20
            while True:
                try:
                    report["firmware"] = load.firmware_identity(sock)
                    break
                except TimeoutError:
                    if time.monotonic() >= deadline:
                        raise
        report.update(state="firmware_ready", passed=True)
    except (OSError, ValueError, RuntimeError, subprocess.SubprocessError) as exc:
        report.update(state="failed", error=str(exc))
    finally:
        load.host.write_json(args.out / "report.json", report)
    print(f"{report['state']}: {args.out}")
    return 0 if report["passed"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
