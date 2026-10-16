#!/usr/bin/env python3
"""Cold integrated Ethernet load, one-way DDR isolation, then JTAG launch."""
import argparse
import hashlib
import math
from pathlib import Path
import re
import secrets
import socket
import sys
import time

SOFTWARE = Path(__file__).resolve().parents[1] / "software"
if not (SOFTWARE / "eth_fast_load.py").is_file():
    SOFTWARE = Path(__file__).resolve().parents[2] / "ara_dsa_vcu118/software"
sys.path.insert(0, str(SOFTWARE))
import eth_fast_load as fast
import host_load as host
from host_image import CAP_HOST, CAP_DDR2, prepare_image
from host_transport import Operation, VivadoTransport

APP_LIMIT = 0xFEFF0000
ROM_BASE = 0x02000000
ROM_SOURCE = SOFTWARE.parent / "rtl/cheshire/hw/bootrom/cheshire_bootrom.sv"
REVIEWED_ROM_SHA256 = "89c227ce79391eaf5a3dd21670e0cd5782b7736183679a2f2ba442b0db4a60fc"


def require_host_profile(caps):
    if caps not in (CAP_HOST, CAP_HOST | CAP_DDR2):
        raise RuntimeError("Expected single- or dual-DDR host hardware")


def validate_image(image):
    fast.validate_segments(image.segments)
    if image.caps != CAP_HOST or any(s.address + s.size > APP_LIMIT for s in image.segments):
        raise ValueError("Image overlaps integrated diagnostic/loader reservation")


def loader_status(value, locked=False):
    if value & 0xFFFFFFFF != 0x45544831:
        raise RuntimeError("Wrong Ethernet hardware ABI")
    flags = (value >> 32) & 0xFFFFFFFF
    counts = [(value >> shift) & 0xFFFFFFFF for shift in (64, 96, 128, 160, 192)]
    if flags & ~3 or counts[4] or value >> 224:
        raise RuntimeError("Ethernet address/error/reserved status is nonzero")
    if locked:
        if flags != 3 or counts[0] != counts[1] or counts[2] != counts[3]:
            raise RuntimeError("Ethernet DDR admission not locked and drained")
    elif flags:
        raise RuntimeError("Loader already locked; full reset and reload required")
    return {"locked": bool(flags & 1), "isolated": bool(flags & 2),
            "aw": counts[0], "b": counts[1], "ar": counts[2],
            "rlast": counts[3], "errors": counts[4]}


def lock_and_drain(transport, seconds=10):
    transport.ethernet_status(lock=True)
    deadline = time.monotonic() + seconds
    while time.monotonic() < deadline:
        value = transport.ethernet_status()
        # Diagnose errors immediately; outstanding work is allowed while draining.
        flags = (value >> 32) & 0xFFFFFFFF
        if value & 0xFFFFFFFF != 0x45544831 or flags & ~3 or value >> 192:
            raise RuntimeError("Ethernet failure while draining")
        if value & (1 << 33):
            first = loader_status(value, locked=True)
            second = loader_status(transport.ethernet_status(), locked=True)
            if first != second:
                raise RuntimeError("Loader counters changed after isolation")
            return second
        time.sleep(0.02)
    raise TimeoutError("Loader did not drain; no program launch")


def firmware_identity(sock, timeout=1.0):
    session = secrets.randbits(32)
    request = fast.HEADER.pack(fast.MAGIC, session, 4, 0, 0, 0)
    for _ in range(3):
        sock.send(request)
        deadline = time.monotonic() + timeout
        while time.monotonic() < deadline:
            sock.settimeout(max(0.001, deadline - time.monotonic()))
            try:
                packet = sock.recv(1472)
            except socket.timeout:
                break
            reply = fast.unpack_reply(packet, session, 4)
            if reply is None:
                continue
            if reply != (fast.DDR_START, APP_LIMIT, b""):
                raise RuntimeError("Wrong firmware profile/address map; no payload sent")
            return {"application_start": reply[0], "application_end": reply[1]}
    raise TimeoutError("Integrated firmware identity unavailable; no payload sent")


def rom_bytes(path=ROM_SOURCE):
    text = Path(path).read_text()
    count = re.search(r"localparam unsigned NumWords = (\d+);", text)
    words = re.findall(r"(?m)^\s*(\d+): data_o = 32'h([0-9a-fA-F]{8})", text)
    if count is None or int(count[1]) != 2048 or len(words) != 2048:
        raise ValueError("Unreviewed ROM encoding/size")
    if [int(index) for index, _ in words] != list(range(2048)):
        raise ValueError("ROM word ordering changed")
    data = b"".join(int(word, 16).to_bytes(4, "little") for _, word in words)
    if hashlib.sha256(data).hexdigest() != REVIEWED_ROM_SHA256:
        raise ValueError("Boot ROM changed; repeat the cold-boot instruction audit")
    return data


def verify_rom(transport):
    expected = rom_bytes()
    observed = bytearray()
    for offset in range(0, len(expected), 1024):
        reads = [Operation("M", "READ", ROM_BASE + i)
                 for i in range(offset, min(offset + 1024, len(expected)), 8)]
        observed.extend(b"".join(transport.exchange(reads)))
    if observed != expected:
        raise RuntimeError("On-board boot ROM differs from the integration inputs")
    return hashlib.sha256(expected).hexdigest()


def cold_guard(transport):
    # COMMAND readback reports frozen, not the last command written.
    if host.read_debug(transport, [host.COMMAND, host.FLAGS]) != [0, 0]:
        raise RuntimeError("Cold guard requires continuous, unfrozen observation")
    host.check_passive_boot(transport)
    snapshot = host.capture_snapshot(transport)
    pc = snapshot["core"]["last_pc"]
    # Audited instructions at 0x0200083a..0x0200088b poll only scratch/UART.
    if not ROM_BASE + 0x83A <= pc < ROM_BASE + 0x88C or snapshot["core"]["trap_count"]:
        raise RuntimeError("CPU is not executing the cold passive ROM")
    registers = transport.exchange([Operation("M", "READ", 0x03000048),
                                    Operation("M", "READ", 0x03001000)])
    if registers[0][:4] != bytes(4) or int.from_bytes(registers[1][:4], "little") & 0xFF != 0xFF:
        raise RuntimeError("Unexpected platform ROM or LLC not in all-SPM mode")
    caps = snapshot["identity"]["caps"]
    require_host_profile(caps)
    for bank in (("ddr1", "ddr2") if caps & CAP_DDR2 else ("ddr1",)):
        for field in ("ar_count", "aw_count", "r_bytes", "w_bytes", "read_outstanding",
                      "write_outstanding", "error_count"):
            if snapshot[bank][field]:
                raise RuntimeError("Ara DDR activity violates cold-cache contract: " + bank + "." + field)
    return snapshot


def load_and_run(transport, sock, image, output, report, full_reset_confirmed=False,
                 run_id=1, seconds=30.0, launch_only=False):
    if not full_reset_confirmed:
        raise ValueError("Full reset before this load must be confirmed")
    if not 0 < run_id <= 0xFFFFFFFF or not math.isfinite(seconds) or seconds <= 0:
        raise ValueError("Invalid run ID or execution timeout")
    validate_image(image)
    report["identity"] = host.identity(transport)
    require_host_profile(report["identity"]["caps"])
    report["ethernet_before"] = loader_status(transport.ethernet_status())
    # Never clear historical DDR counters before establishing the cold contract.
    report["cold_before"] = cold_guard(transport)
    report["rom_sha256"] = verify_rom(transport)
    scratch3 = host.check_passive_boot(transport)
    report["firmware"] = firmware_identity(sock)
    report.update(state="loading", segments=[], image=image.manifest(), execution_started=False)
    host.write_json(Path(output) / "report.json", report)
    started = time.monotonic()
    for segment in image.segments:
        report["segments"].append(fast.transfer_segment(sock, segment, secrets.randbits(32), 8, 10, 0.1))
        host.write_json(Path(output) / "report.json", report)
    elapsed = time.monotonic() - started
    total = sum(s.size for s in image.segments)
    report["load_metrics"] = {"payload_bytes": total, "seconds": elapsed,
                              "bytes_per_second_including_readback": total / elapsed}
    report["ethernet_locked"] = lock_and_drain(transport)
    report["cold_after"] = cold_guard(transport)
    host.write_debug(transport, [(host.WATCHDOG, 0), (host.DONE, 0),
                                 (host.RESULT, 0xFFFFFFFF), (host.RUN_ID, run_id), (host.MARKER, 0)])

    def before_doorbell():
        loader_status(transport.ethernet_status(), locked=True)
        if host.check_passive_boot(transport) != scratch3:
            raise RuntimeError("Scratch registers changed during loading")
        cold_guard(transport)
        report["launch_attempted"] = True

    result = host._launch_verified(transport, image, output, report, scratch3,
                                   run_id, seconds, launch_only=launch_only,
                                   before_doorbell=before_doorbell)
    report["ethernet_after"] = loader_status(transport.ethernet_status(), locked=True)
    return result


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--elf", type=Path, required=True)
    parser.add_argument("--load", action="append", type=fast.parse_load, default=[])
    parser.add_argument("--probes", type=Path, required=True)
    parser.add_argument("--out", type=Path, required=True)
    parser.add_argument("--full-reset-confirmed", action="store_true", required=True)
    parser.add_argument("--host", default="192.168.1.10")
    parser.add_argument("--source", default="192.168.1.11")
    parser.add_argument("--vivado", default="vivado")
    parser.add_argument("--seconds", type=float)
    parser.add_argument("--linux", action="store_true", help="Wait for Linux init on UART instead of debug done")
    parser.add_argument("--port", help="UART console port for --linux")
    args = parser.parse_args(argv)
    if args.linux != bool(args.port):
        parser.error("--linux requires --port, and --port is only valid with --linux")
    seconds = args.seconds if args.seconds is not None else (180.0 if args.linux else 30.0)
    args.out.mkdir(parents=True, exist_ok=False)
    report = {"state": "starting", "passed": False, "execution_started": False}
    try:
        image = prepare_image(args.elf, args.load, caps=CAP_HOST,
                              allow_dynamic=args.linux)
        validate_image(image)
        with VivadoTransport(args.out / "transport", vivado=args.vivado, probes=args.probes) as transport:
            with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as sock:
                sock.setsockopt(socket.SOL_SOCKET, socket.SO_RCVBUF, 1024 * 1024)
                sock.setsockopt(socket.SOL_SOCKET, socket.SO_SNDBUF, 1024 * 1024)
                sock.bind((args.source, 0))
                sock.connect((args.host, 49204))
                run_id = secrets.randbelow(0xFFFFFFFF) + 1
                if args.linux:
                    report["uart_port"] = args.port
                    report["uart_baud"] = 115200
                    with host.serial_module().Serial(args.port, 115200, timeout=0.2,
                                                     rtscts=False, dsrdtr=False) as console:
                        report["uart"] = host.wait_linux_console(
                            console, args.out,
                            lambda: load_and_run(transport, sock, image, args.out, report,
                                                 args.full_reset_confirmed, run_id, seconds,
                                                 launch_only=True), seconds)
                    report.update(state="passed_linux_init_marker", passed=True,
                                  completed_utc=host.now())
                else:
                    load_and_run(transport, sock, image, args.out, report,
                                 args.full_reset_confirmed, run_id, seconds)
    except (OSError, ValueError, RuntimeError, StopIteration) as exc:
        report.update(state="failed", passed=False, error=str(exc))
    finally:
        host.write_json(args.out / "report.json", report)
    print(f"{report['state']}: {args.out}")
    if report.get("error"):
        print(report["error"], file=sys.stderr)
    return 0 if report["passed"] else 1


if __name__ == "__main__":
    sys.exit(main())
