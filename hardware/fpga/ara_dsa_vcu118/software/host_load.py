#!/usr/bin/env python3
"""Independent JTAG AXI loader, debug snapshot collector and raw UART recorder."""
import argparse
import csv
from datetime import datetime, timezone
import hashlib
import json
import math
from pathlib import Path
import secrets
import struct
import sys
import time

from host_image import CAP_DDR2, CAP_HOST, check_range, prepare_image, sha256_file
from host_transport import Operation, VivadoTransport

MAGIC, ABI, FREQUENCY = 0x41524442, 1, 50000000
COMMAND, STATUS, SEQUENCE = 0x10, 0x14, 0x18
MARKER, RESULT, RUN_ID, WATCHDOG, FLAGS, DONE = 0x1C, 0x20, 0x24, 0x28, 0x2C, 0x30
CLEAR, SNAPSHOT, FREEZE, RESUME = 1, 2, 4, 8
SCRATCH = 0x03000000
AXI_PREFLIGHT_ADDRESS = 0xFFFF0000
SPM_PROBE_ADDRESS = 0x1401FF00
CORE_FIELDS = ("cycles", "retired", "last_pc", "head_pc", "last_trap_pc",
               "last_trap_cause", "last_trap_tval", "trap_count")
DDR_FIELDS = ("ar_count", "aw_count", "r_bytes", "w_bytes", "ar_stall", "aw_stall",
              "r_stall", "w_stall", "read_outstanding", "write_outstanding",
              "last_ar_addr", "last_aw_addr", "error_count", "reserved_error_addr",
              "last_error_info")
LIVE_FIELDS = {STATUS: "status", SEQUENCE: "snapshot_sequence", MARKER: "marker",
               RESULT: "result", RUN_ID: "run_id", WATCHDOG: "watchdog_cycles",
               FLAGS: "flags", DONE: "done"}


def now():
    return datetime.now(timezone.utc).isoformat()


def write_json(path, value):
    Path(path).write_text(json.dumps(value, indent=2) + "\n", encoding="utf-8")


def read_debug(transport, addresses):
    replies = transport.exchange([Operation("D", "READ", a) for a in addresses])
    return [int.from_bytes(data, "little") for data in replies]


def write_debug(transport, values):
    transport.exchange([Operation("D", "WRITE", a, data=struct.pack("<I", v))
                        for a, v in values])


def identity(transport):
    magic, abi, caps, frequency = read_debug(transport, [0, 4, 8, 12])
    if magic != MAGIC or abi != ABI or not caps & CAP_HOST or frequency != FREQUENCY:
        raise RuntimeError(f"Debug ABI/capability mismatch: {magic:08x}, {abi}, {caps}, {frequency}")
    return {"magic": magic, "abi": abi, "caps": caps, "frequency_hz": frequency}


def capture_snapshot(transport, freeze=False):
    ident = identity(transport)
    sequence, flags = read_debug(transport, [SEQUENCE, FLAGS])
    watchdog_snapshot = bool(flags & 1)
    if not watchdog_snapshot:
        if freeze:
            write_debug(transport, [(COMMAND, FREEZE)])
        write_debug(transport, [(COMMAND, SNAPSHOT)])
        deadline = time.monotonic() + 2
        while read_debug(transport, [SEQUENCE])[0] == sequence:
            if time.monotonic() >= deadline:
                raise RuntimeError("Snapshot sequence did not advance; no snapshot record")
            time.sleep(0.01)
    # A watchdog can replace the snapshot during collection. Retry the entire bank,
    # not individual high/low halves, and never overwrite a watchdog snapshot.
    blocks = [("core", 0x100, CORE_FIELDS), ("ddr1", 0x180, DDR_FIELDS)]
    if ident["caps"] & CAP_DDR2:
        blocks.append(("ddr2", 0x200, DDR_FIELDS))
    addresses = [base + 4 * i for _, base, fields in blocks for i in range(len(fields) * 2)]
    for _ in range(3):
        before = read_debug(transport, [SEQUENCE, FLAGS])
        words = read_debug(transport, addresses)
        live_values = read_debug(transport, list(LIVE_FIELDS))
        mailbox = read_debug(transport, list(range(0x40, 0x80, 4)))
        after = read_debug(transport, [SEQUENCE, FLAGS])
        if before != after or live_values[1] != before[0]:
            continue
        result = {"schema": "ara-fpga-debug-v1", "captured_utc": now(),
                  "identity": ident, "live": dict(zip(LIVE_FIELDS.values(), live_values)),
                  "snapshot_sequence": before[0], "watchdog_snapshot": bool(after[1] & 1),
                  "mailbox": mailbox,
                  "semantics": {"r_bytes": "8 per pre-width-converter R valid&&ready; bus occupancy, not narrow payload or PHY bytes",
                                "w_bytes": "popcount(WSTRB) per W valid&&ready",
                                "read_outstanding": "AR handshakes minus RLAST handshakes; transactions",
                                "write_outstanding": "AW handshakes minus B handshakes; transactions",
                                "reserved_error_addr": "reserved zero; no response-to-address attribution",
                                "last_ar_addr": "last accepted AR, NOT the failing address",
                                "last_aw_addr": "last accepted AW, NOT the failing address",
                                "watchdog": "no-retirement freeze+snapshot; does not abort execution",
                                "cycles": "software begin/finish window only when ELF uses those APIs; includes small boundary overhead; optional empty-window subtraction; helpers do not wait for accelerators"}}
        cursor = 0
        for name, _, fields in blocks:
            values = [words[cursor + 2 * i] | words[cursor + 2 * i + 1] << 32
                      for i in range(len(fields))]
            cursor += len(fields) * 2
            result[name] = dict(zip(fields, values))
            if name != "core":
                if result[name]["reserved_error_addr"] != 0:
                    raise RuntimeError("Reserved error-address field is nonzero (ABI mismatch)")
                info = result[name]["last_error_info"]
                result[name]["error_response"] = info & 3
                result[name]["error_channel"] = "B" if info & 4 else "R"
                result[name]["error_id"] = (info >> 8) & 255
        return result
    raise RuntimeError("Snapshot changed during all collection attempts")


def save_snapshot(output, snapshot):
    write_json(Path(output) / "snapshot.json", snapshot)
    flat = {"captured_utc": snapshot["captured_utc"],
            "snapshot_sequence": snapshot["snapshot_sequence"],
            "watchdog_snapshot": snapshot["watchdog_snapshot"]}
    for section in ("identity", "live", "core", "ddr1", "ddr2"):
        for key, value in snapshot.get(section, {}).items():
            flat[f"{section}.{key}"] = value
    for i, value in enumerate(snapshot["mailbox"]):
        flat[f"mailbox.{i}"] = value
    with (Path(output) / "snapshot.csv").open("w", newline="", encoding="ascii") as stream:
        writer = csv.DictWriter(stream, fieldnames=list(flat))
        writer.writeheader()
        writer.writerow(flat)


def preflight_axi_mapping(transport, caps, record):
    """After full reset/passive-boot checks, validate burst order independently.

    Use only 16 bytes in DDR1's last-64-KiB scratch reservation. Save/restore
    each address with single-beat transactions, never an unvalidated burst.
    A mirrored burst-write/burst-read bug must not establish address correctness.
    """
    address = AXI_PREFLIGHT_ADDRESS
    check_range(address, 16, caps)
    expected = [bytes.fromhex("0123456789abcdef"), bytes.fromhex("1032547698badcfe")]
    reads = [Operation("M", "READ", address + 8 * i) for i in range(2)]
    record.update(address=address, bytes=16, verified=False, restored=False,
                  expected_bytes_at_each_address=[word.hex() for word in expected],
                  method="two-beat write checked by two separately addressed one-beat reads; then validate burst-read packing")
    original = transport.exchange(reads)
    record["original_bytes_at_each_address"] = [word.hex() for word in original]
    try:
        transport.exchange([Operation("M", "WRITE", address, 2, b"".join(expected))])
        actual = transport.exchange(reads)
        record["observed_bytes_at_each_address"] = [word.hex() for word in actual]
        if actual != expected:
            raise RuntimeError("AXI burst mapping preflight readback mismatch at separately addressed "
                               f"0x{address:x}/0x{address + 8:x}; refusing load/launch (no auto-reordering)")
        record["burst_write_verified_by_single_reads"] = True
        # Memory contents are now independently anchored to their addresses.
        burst = transport.exchange([Operation("M", "READ", address, 2)])[0]
        record["observed_burst_read_bytes"] = burst.hex()
        if burst != b"".join(expected):
            raise RuntimeError("AXI burst-read mapping preflight readback mismatch; refusing load/launch")
        record["burst_read_verified"] = True
    except Exception as exc:
        record["error"] = str(exc)
        raise
    finally:
        try:
            transport.exchange([Operation("M", "WRITE", address + 8 * i, data=word)
                                for i, word in enumerate(original)])
            restored = transport.exchange(reads)
            record["restored"] = restored == original
            if not record["restored"]:
                raise RuntimeError("preflight scratch restore readback mismatch")
        except Exception as exc:
            record["restore_error"] = str(exc)
            raise RuntimeError(f"AXI mapping preflight scratch restoration failed: {exc}; "
                               f"original error: {record.get('error', 'none')}; refusing load/launch") from exc
    record["verified"] = True


def probe_axi_single_beat(transport, caps, record):
    """Discriminate an address-specific single-beat failure from a burst failure."""
    address = AXI_PREFLIGHT_ADDRESS
    check_range(address, 16, caps)
    reads = [Operation("M", "READ", address + 8 * i) for i in range(2)]
    record.update(address=address, bytes=16, target_address=address + 8,
                  verified=False, restored=False,
                  method="one-beat write at +8, separately read +0/+8, then restore both")
    original = transport.exchange(reads)
    record["original_bytes_at_each_address"] = [word.hex() for word in original]
    pattern = bytes.fromhex("deadc0de88776655")
    if pattern == original[1]:
        pattern = bytes(b ^ 0xff for b in pattern)
    record["written_bytes_at_target"] = pattern.hex()
    try:
        transport.exchange([Operation("M", "WRITE", address + 8, data=pattern)])
        actual = transport.exchange(reads)
        record["observed_bytes_at_each_address"] = [word.hex() for word in actual]
        if actual != [original[0], pattern]:
            raise RuntimeError("AXI single-beat write/read at 0xffff0008 failed or changed adjacent word")
    except Exception as exc:
        record["error"] = str(exc)
        raise
    finally:
        try:
            # Restore +8 first: if that address aliases +0, the final +0 write
            # still restores its original value.
            transport.exchange([Operation("M", "WRITE", address + 8, data=original[1]),
                                Operation("M", "WRITE", address, data=original[0])])
            restored = transport.exchange(reads)
            record["restored"] = restored == original
            if not record["restored"]:
                raise RuntimeError("single-beat scratch restore readback mismatch")
        except Exception as exc:
            record["restore_error"] = str(exc)
            raise RuntimeError(f"AXI probe scratch restoration failed: {exc}; "
                               f"original error: {record.get('error', 'none')}") from exc
    record["verified"] = True


def probe_axi_separated_burst(transport, caps, record):
    """Test read bursts and the manual's word-separated write syntax in scratch."""
    address = AXI_PREFLIGHT_ADDRESS
    check_range(address, 16, caps)
    reads = [Operation("M", "READ", address + 8 * i) for i in range(2)]
    record.update(address=address, bytes=16, burst_read_verified=False,
                  separated_write_verified=False, write_attempted=False, restored=True,
                  method="two-beat read compared with two single reads; word-separated two-beat write checked by single reads; restore")
    original = transport.exchange(reads)
    record["original_bytes_at_each_address"] = [word.hex() for word in original]
    burst = transport.exchange([Operation("M", "READ", address, 2)])[0]
    record["observed_burst_read_bytes"] = burst.hex()
    record["burst_read_verified"] = burst == b"".join(original)
    if not record["burst_read_verified"]:
        check_range(address, 80, caps)
        record["repeated_burst_read_bytes"] = transport.exchange(
            [Operation("M", "READ", address, 2)])[0].hex()
        neighbors = transport.exchange(
            [Operation("M", "READ", address + 8 * i) for i in range(10)])
        record["neighbor_single_bytes"] = [word.hex() for word in neighbors]
        record["shifted_burst_read_bytes"] = transport.exchange(
            [Operation("M", "READ", address + 8, 2)])[0].hex()
        record["post_single_bytes"] = [word.hex() for word in transport.exchange(reads)]
        raise RuntimeError("AXI two-beat read differs from separately addressed reads; no write attempted")

    expected = [bytes.fromhex("0011223344556677"), bytes.fromhex("8899aabbccddeeff")]
    expected = [bytes(b ^ 0xff for b in word) if word == old else word
                for word, old in zip(expected, original)]
    record["expected_bytes_at_each_address"] = [word.hex() for word in expected]
    record["write_attempted"] = True
    record["restored"] = False
    try:
        transport.exchange([Operation("M", "WRITE", address, 2, b"".join(expected),
                                      separate_words=True)])
        actual = transport.exchange(reads)
        record["observed_bytes_at_each_address"] = [word.hex() for word in actual]
        if actual != expected:
            raise RuntimeError("AXI word-separated two-beat write did not update both addresses")
    except Exception as exc:
        record["error"] = str(exc)
        raise
    finally:
        try:
            transport.exchange([Operation("M", "WRITE", address + 8, data=original[1]),
                                Operation("M", "WRITE", address, data=original[0])])
            record["restored"] = transport.exchange(reads) == original
            if not record["restored"]:
                raise RuntimeError("separated burst scratch restore readback mismatch")
        except Exception as exc:
            record["restore_error"] = str(exc)
            raise RuntimeError(f"AXI separated burst scratch restoration failed: {exc}; "
                               f"original error: {record.get('error', 'none')}") from exc
    record["separated_write_verified"] = True


def probe_axi_spm_burst(transport, record):
    """Compare single and two-beat reads in the host profile's uncached SPM."""
    address = SPM_PROBE_ADDRESS
    reads = [Operation("M", "READ", address + 8 * i) for i in range(2)]
    record.update(address=address, bytes=16, region="uncached_llc_spm",
                  verified=False, restored=False, write_attempted=False,
                  single_beat_verified=False,
                  method="single-beat save/write/read, two-beat read, single-beat restore/read")
    original = transport.exchange(reads)
    record["original_bytes_at_each_address"] = [word.hex() for word in original]
    expected = [bytes.fromhex("0123456789abcdef"), bytes.fromhex("fedcba9876543210")]
    expected = [bytes(b ^ 0xff for b in word) if word == old else word
                for word, old in zip(expected, original)]
    record["expected_bytes_at_each_address"] = [word.hex() for word in expected]
    try:
        record["write_attempted"] = True
        transport.exchange([Operation("M", "WRITE", address + 8 * i, data=word)
                            for i, word in enumerate(expected)])
        actual = transport.exchange(reads)
        record["observed_single_bytes"] = [word.hex() for word in actual]
        record["single_beat_verified"] = actual == expected
        if not record["single_beat_verified"]:
            raise RuntimeError("SPM single-beat write/read mismatch; burst not attempted")
        burst = transport.exchange([Operation("M", "READ", address, 2)])[0]
        record["observed_burst_read_bytes"] = burst.hex()
        if burst != b"".join(expected):
            raise RuntimeError("SPM two-beat read differs from separately addressed reads")
    except Exception as exc:
        record["error"] = str(exc)
        raise
    finally:
        try:
            transport.exchange([Operation("M", "WRITE", address + 8, data=original[1]),
                                Operation("M", "WRITE", address, data=original[0])])
            record["restored"] = transport.exchange(reads) == original
            if not record["restored"]:
                raise RuntimeError("SPM scratch restore readback mismatch")
        except Exception as exc:
            record["restore_error"] = str(exc)
            raise RuntimeError(f"SPM scratch restoration failed: {exc}; "
                               f"original error: {record.get('error', 'none')}") from exc
    record["verified"] = True


def load_chunks(segment, single_beat):
    for address, data in segment.chunks():
        if not single_beat:
            yield address, data
            continue
        offset = 0
        while offset < len(data):
            current = address + offset
            length = min(len(data) - offset, 8 - (current & 7))
            yield current, data[offset:offset + length]
            offset += length


def verified_load(transport, image, batch_chunks=16, single_beat=False):
    if not 1 <= batch_chunks <= 128:
        raise ValueError("batch_chunks must be 1..128")
    records = []
    for segment in image.segments:
        digest = hashlib.sha256()
        pending = []

        def flush():
            operations = []
            for address, data, _, _ in pending:
                operations.extend([Operation("M", "WRITE", address, len(data) // 8, data),
                                   Operation("M", "READ", address, len(data) // 8)])
            replies = transport.exchange(operations)
            for i, (address, expected, prefix, length) in enumerate(pending):
                actual = replies[2 * i + 1]
                if actual != expected:
                    raise RuntimeError(f"DDR readback mismatch at 0x{address:x}")
                digest.update(actual[prefix:prefix + length])
            pending.clear()

        for address, data in load_chunks(segment, single_beat):
            aligned = address & ~7
            prefix = address - aligned
            size = (prefix + len(data) + 7) & ~7
            if prefix or size != len(data):
                # Preserve bytes outside the image; flush earlier writes before RMW.
                if pending:
                    flush()
                old = transport.exchange([Operation("M", "READ", aligned, size // 8)])[0]
                block = bytearray(old)
                block[prefix:prefix + len(data)] = data
            else:
                block = data
            pending.append((aligned, bytes(block), prefix, len(data)))
            if len(pending) == batch_chunks:
                flush()
        if pending:
            flush()
        if digest.hexdigest() != segment.sha256:
            raise RuntimeError("Image changed since preparation; refusing to boot")
        records.append({"address": segment.address, "bytes": segment.size,
                        "readback_sha256": digest.hexdigest(), "verified": True})
    return records


def measured_verified_load(transport, image, report, batch_chunks=16, single_beat=False):
    """Wall time of verified_load ONLY, not preparation, launch or collection.

    This is payload throughput INCLUDING all readback, hashing, Tcl and refresh
    overhead. It is not wire throughput or an accelerator performance metric.
    Stage-2 hardware benchmarking is still required; no throughput is promised.
    """
    payload_bytes = sum(segment.size for segment in image.segments)
    metrics = {"clock": "time.monotonic", "scope": "verified_load_only",
               "memory_transaction_mode": "single_beat" if single_beat else "burst",
               "complete": False, "payload_bytes_including_bss": payload_bytes,
               "payload_bytes_per_second_including_readback": None,
               "uart_115200_theoretical_bytes_per_second": 11520,
               "ratio_to_uart_theoretical_not_measured_speedup": None,
               "comparison": "115200 baud / 10 bits per 8N1 byte; theoretical UART ceiling, NOT measured speedup",
               "limitations": "Tcl per-burst and refresh overhead may dominate; benchmark stage 2 on hardware; no throughput promise"}
    report["load_metrics"] = metrics
    start = time.monotonic()
    try:
        records = verified_load(transport, image, batch_chunks, single_beat=single_beat)
    except BaseException:
        metrics["elapsed_seconds"] = time.monotonic() - start
        raise
    elapsed = time.monotonic() - start
    metrics.update(complete=True, elapsed_seconds=elapsed)
    if elapsed > 0:
        throughput = payload_bytes / elapsed
        metrics["payload_bytes_per_second_including_readback"] = throughput
        metrics["ratio_to_uart_theoretical_not_measured_speedup"] = throughput / 11520
    return records


def validate_result(snapshot, run_id):
    live = snapshot["live"]
    if live["run_id"] != run_id:
        raise RuntimeError("Run ID mismatch; refusing stale results")
    if not live["done"]:
        raise RuntimeError("No done record; execution timed out or legacy ELF lacks debug reporting")
    if live["result"] != 0:
        raise RuntimeError(f"Software failed: result=0x{live['result']:08x}")
    if live["flags"] & 1:
        raise RuntimeError("Watchdog hit (freeze/snapshot only, not an execution abort)")
    if live["status"] & 15 != 7:
        raise RuntimeError("Board lost ready/reset state during execution")
    if not snapshot["core"]["retired"]:
        raise RuntimeError("No retirement measurement record")
    if snapshot["core"]["trap_count"]:
        raise RuntimeError("Trap recorded during execution")
    if any(snapshot.get(name, {}).get("error_count", 0) for name in ("ddr1", "ddr2")):
        raise RuntimeError("DDR AXI error recorded during execution")


def check_passive_boot(transport):
    if read_debug(transport, [STATUS])[0] & 15 != 7:
        raise RuntimeError("SoC/DDR not ready; no memory access attempted")
    boot = transport.exchange([Operation("M", "READ", SCRATCH + 0x40),
                               Operation("M", "READ", SCRATCH + 8)])
    if int.from_bytes(boot[0][:4], "little") != 0 or boot[1][:4] != bytes(4):
        raise RuntimeError("Expected passive boot mode and reset scratch[2]=0")
    return boot[1][4:]


def load_and_run(transport, image, output, report, full_reset_confirmed=False,
                 run_id=1, seconds=30.0, watchdog_cycles=0, batch_chunks=16,
                 single_beat=False):
    if not full_reset_confirmed:
        raise ValueError("Explicit --full-reset-confirmed is required before each load")
    if (not 0 < run_id <= 0xFFFFFFFF or not 0 <= watchdog_cycles <= 0xFFFFFFFF or
            not math.isfinite(seconds) or seconds <= 0):
        raise ValueError("Invalid run ID, watchdog or execution timeout")
    ident = identity(transport)
    report["memory_transaction_mode"] = "single_beat" if single_beat else "burst"
    if ident["caps"] != image.caps:
        raise RuntimeError("Capabilities changed since preparation")
    # The 64-bit memory IP has no narrow transfers. Read paired 32-bit registers.
    scratch3 = check_passive_boot(transport)
    write_debug(transport, [(WATCHDOG, 0), (COMMAND, CLEAR), (COMMAND, RESUME), (DONE, 0),
                            (RESULT, 0xFFFFFFFF), (RUN_ID, run_id), (MARKER, 0)])
    preflight_name = "axi_single_beat_preflight" if single_beat else "axi_mapping_preflight"
    report["state"] = preflight_name
    report[preflight_name] = {}
    timings = report.setdefault("other_timings_seconds", {})
    write_json(Path(output) / "report.json", report)
    start = time.monotonic()
    try:
        if single_beat:
            probe_axi_single_beat(transport, image.caps, report[preflight_name])
        else:
            preflight_axi_mapping(transport, image.caps, report[preflight_name])
    finally:
        timings[preflight_name] = time.monotonic() - start
        write_json(Path(output) / "report.json", report)
    report["state"] = "loading"
    write_json(Path(output) / "report.json", report)
    report["readback"] = measured_verified_load(transport, image, report, batch_chunks,
                                                 single_beat=single_beat)
    start = time.monotonic()
    loading_snapshot = capture_snapshot(transport, freeze=True)
    write_json(Path(output) / "load_snapshot.json", loading_snapshot)
    timings["load_snapshot_collection"] = time.monotonic() - start
    if any(loading_snapshot.get(name, {}).get("error_count", 0) for name in ("ddr1", "ddr2")):
        raise RuntimeError("DDR AXI error recorded while loading; refusing launch")
    # Publish the entry as one 64-bit pair, then the doorbell LAST. Do not read
    # back scratch[2] after launch: ROM may already have consumed/cleared it.
    start = time.monotonic()
    entry_data = struct.pack("<Q", image.entry)
    replies = transport.exchange([Operation("M", "WRITE", SCRATCH, data=entry_data),
                                  Operation("M", "READ", SCRATCH)])
    if replies[1] != entry_data:
        raise RuntimeError("Boot entry readback mismatch")
    if read_debug(transport, [STATUS])[0] & 15 != 7:
        raise RuntimeError("Board no longer ready; refusing launch")
    write_debug(transport, [(COMMAND, CLEAR), (WATCHDOG, watchdog_cycles), (COMMAND, RESUME)])
    check = read_debug(transport, [DONE, RUN_ID, RESULT, FLAGS])
    if check != [0, run_id, 0xFFFFFFFF, 0]:
        raise RuntimeError("Debug run controls did not initialize")
    report.update(state="launching", run_id=run_id, launched_utc=now())
    write_json(Path(output) / "report.json", report)
    transport.exchange([Operation("M", "WRITE", SCRATCH + 8,
                                  data=struct.pack("<I", 2) + scratch3)])
    timings["boot_control_and_launch"] = time.monotonic() - start
    report["state"] = "running"
    start = time.monotonic()
    deadline = start + seconds
    while time.monotonic() < deadline:
        done, flags, observed_id = read_debug(transport, [DONE, FLAGS, RUN_ID])
        if done or flags & 1 or observed_id != run_id:
            break
        time.sleep(min(0.1, max(0, deadline - time.monotonic())))
    timings["execution_wait_including_polling_not_cpu_time"] = time.monotonic() - start
    start = time.monotonic()
    snapshot = capture_snapshot(transport, freeze=True)
    save_snapshot(output, snapshot)
    timings["result_snapshot_collection"] = time.monotonic() - start
    validate_result(snapshot, run_id)
    report.update(state="passed", passed=True, completed_utc=now())
    return snapshot


def parse_load(value):
    try:
        address, name = value.split(":", 1)
        return int(address, 0), Path(name)
    except ValueError as exc:
        raise argparse.ArgumentTypeError("Expected ADDRESS:PATH") from exc


def provenance():
    here = Path(__file__).resolve().parent
    paths = sorted(here.glob("host_*.py")) + [here / "host_vivado.tcl", here / "fpga_debug.h"]
    return {"python": sys.version, "host_sha256": {p.name: sha256_file(p) for p in paths}}


def collect_uart(args):
    here = Path(__file__).resolve().parent
    for directory in (here / "vendor", here.parents[1] / "ara_dsa_vcu118/software/vendor"):
        for wheel in directory.glob("pyserial-*.whl"):
            sys.path.insert(0, str(wheel))
    import serial
    count = 0
    with serial.Serial(args.port, args.baud, timeout=0.2, rtscts=False, dsrdtr=False) as port:
        with (args.out / "uart.bin").open("wb") as stream:
            deadline = time.monotonic() + args.seconds
            while time.monotonic() < deadline:
                data = port.read(4096)
                stream.write(data)
                stream.flush()
                count += len(data)
    write_json(args.out / "uart.json", {"bytes": count, "port": args.port, "baud": args.baud,
                                       "sha256": sha256_file(args.out / "uart.bin"),
                                       "meaning": "raw UART capture, not execution success"})
    if count == 0:
        raise RuntimeError("No UART bytes captured")


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest="command", required=True)
    for name in ("prepare", "load", "snapshot", "uart", "ddr-test", "axi-probe", "axi-burst-probe", "axi-spm-probe"):
        sub = commands.add_parser(name)
        sub.add_argument("--out", type=Path, required=True, help="new evidence directory")
        if name in ("prepare", "load"):
            sub.add_argument("--elf", type=Path, required=True)
            sub.add_argument("--load", action="append", type=parse_load, default=[])
        if name == "prepare":
            sub.add_argument("--caps", type=lambda s: int(s, 0), default=CAP_HOST)
        if name in ("load", "snapshot", "ddr-test", "axi-probe", "axi-burst-probe", "axi-spm-probe"):
            sub.add_argument("--vivado", default="vivado")
            sub.add_argument("--server", default="localhost:3121")
            sub.add_argument("--probes", type=Path, help="matching debug probes .ltx file")
            sub.add_argument("--target", default="-")
            sub.add_argument("--device", default="-")
            sub.add_argument("--mem-cell", default="gen_host.i_host_bridge.i_jtag_mem")
            sub.add_argument("--debug-cell", default="gen_host.i_host_bridge.i_jtag_debug")
            sub.add_argument("--transaction-timeout", type=float, default=30)
            sub.add_argument("--startup-timeout", type=float, default=120)
        if name in ("load", "ddr-test", "axi-probe", "axi-burst-probe", "axi-spm-probe"):
            sub.add_argument("--full-reset-confirmed", action="store_true")
        if name == "axi-spm-probe":
            sub.add_argument("--destructive-spm-test-confirmed", action="store_true")
            sub.add_argument("--reset-jtag-axi", action="store_true")
        if name == "ddr-test":
            sub.add_argument("--destructive-ddr-test-confirmed", action="store_true")
        if name == "load":
            sub.add_argument("--run-id", type=lambda s: int(s, 0), default=None)
            sub.add_argument("--watchdog-cycles", type=lambda s: int(s, 0), default=0)
            sub.add_argument("--batch-chunks", type=int, default=16)
            sub.add_argument("--single-beat", action="store_true",
                             help="use only single-beat memory transactions; slower, burst hardware remains unverified")
        if name in ("load", "uart"):
            sub.add_argument("--seconds", type=float, default=30)
        if name == "uart":
            sub.add_argument("--port", required=True)
            sub.add_argument("--baud", type=int, default=115200)
    args = parser.parse_args(argv)
    if args.command in ("load", "ddr-test", "axi-probe", "axi-burst-probe", "axi-spm-probe") and not args.full_reset_confirmed:
        parser.error("Perform a full VIO reset first, then explicitly pass --full-reset-confirmed")
    if args.command == "axi-spm-probe" and not args.destructive_spm_test_confirmed:
        parser.error("--destructive-spm-test-confirmed is required; 16 SPM bytes WILL be overwritten then restored")
    if args.command == "ddr-test" and not args.destructive_ddr_test_confirmed:
        parser.error("--destructive-ddr-test-confirmed is required; last 64 KiB per bank WILL be overwritten")
    for key in ("seconds", "transaction_timeout", "startup_timeout", "baud"):
        if hasattr(args, key) and (not math.isfinite(getattr(args, key)) or getattr(args, key) <= 0):
            parser.error(f"--{key.replace('_', '-')} must be finite and positive")
    if args.command == "load":
        if not 0 <= args.watchdog_cycles <= 0xFFFFFFFF or not 1 <= args.batch_chunks <= 128:
            parser.error("Watchdog must fit uint32; batch chunks must be 1..128")
        args.run_id = args.run_id if args.run_id is not None else secrets.randbelow(0xFFFFFFFF) + 1
        if not 0 < args.run_id <= 0xFFFFFFFF:
            parser.error("Run ID must be a nonzero uint32")
    if args.command in ("load", "snapshot", "ddr-test", "axi-probe", "axi-burst-probe", "axi-spm-probe") and args.probes is not None:
        if not args.probes.is_file():
            parser.error(f"Debug probes file not found: {args.probes}")
        args.probes = args.probes.resolve()
    args.out = args.out.resolve()
    args.out.mkdir(parents=True, exist_ok=False)
    report = {"command": args.command, "started_utc": now(), "state": "starting", "passed": False,
              "arguments": {k: str(v) for k, v in vars(args).items()}, "provenance": provenance(),
              "other_timings_seconds": {}, "compile_time": "external/not measured; never included in load time"}

    def connect(name):
        return VivadoTransport(args.out / name, vivado=args.vivado, server=args.server,
                               target=args.target, device=args.device, mem_cell=args.mem_cell,
                               debug_cell=args.debug_cell, timeout=args.transaction_timeout,
                               startup_timeout=args.startup_timeout, probes=args.probes)

    try:
        if args.command == "prepare":
            start = time.monotonic()
            image = prepare_image(args.elf, args.load, args.caps)
            report["other_timings_seconds"]["image_preparation"] = time.monotonic() - start
            write_json(args.out / "image.json", image.manifest())
            report["state"] = "prepared_not_executed"
        elif args.command == "uart":
            collect_uart(args)
            report["state"] = "uart_collected_not_verified"
        elif args.command == "snapshot":
            with connect("debug") as transport:
                save_snapshot(args.out, capture_snapshot(transport))
            report["state"] = "snapshot_collected_not_execution_verification"
        elif args.command == "axi-probe":
            with connect("axi_probe") as transport:
                ident = identity(transport)
                report["identity"] = ident
                check_passive_boot(transport)
                report["axi_single_beat_probe"] = {}
                try:
                    probe_axi_single_beat(transport, ident["caps"], report["axi_single_beat_probe"])
                finally:
                    write_json(args.out / "report.json", report)
            report.update(state="passed_axi_single_beat_only", passed=True)
        elif args.command == "axi-burst-probe":
            with connect("axi_burst_probe") as transport:
                ident = identity(transport)
                report["identity"] = ident
                check_passive_boot(transport)
                report["axi_burst_probe"] = {}
                try:
                    probe_axi_separated_burst(transport, ident["caps"], report["axi_burst_probe"])
                finally:
                    write_json(args.out / "report.json", report)
            report.update(state="passed_axi_separated_burst_only", passed=True)
        elif args.command == "axi-spm-probe":
            with connect("axi_spm_probe") as transport:
                ident = identity(transport)
                report["identity"] = ident
                report["jtag_axi_reset_before_probe"] = False
                if args.reset_jtag_axi:
                    transport.reset_memory_axi()
                    report["jtag_axi_reset_before_probe"] = True
                check_passive_boot(transport)
                report["axi_spm_probe"] = {}
                try:
                    probe_axi_spm_burst(transport, report["axi_spm_probe"])
                finally:
                    write_json(args.out / "report.json", report)
            report.update(state="passed_axi_spm_burst_only", passed=True)
        elif args.command == "ddr-test":
            from host_ddr_test import test_memory, plan
            with connect("ddr_test") as transport:
                ident = identity(transport)
                report["identity"] = ident
                write_json(args.out / "ddr_plan.json", plan(ident["caps"]))
                check_passive_boot(transport)
                write_debug(transport, [(WATCHDOG, 0), (COMMAND, CLEAR), (COMMAND, RESUME)])
                report["ddr_test"] = test_memory(transport, ident["caps"], True, True)
                snapshot = capture_snapshot(transport, freeze=True)
                save_snapshot(args.out, snapshot)
                if any(snapshot.get(name, {}).get("error_count", 0) for name in ("ddr1", "ddr2")):
                    raise RuntimeError("DDR AXI error recorded during scratch test")
            report.update(state="passed_small_ddr_scratch_test", passed=True)
        else:
            with connect("load") as transport:
                ident = identity(transport)
                report["identity"] = ident
                start = time.monotonic()
                image = prepare_image(args.elf, args.load, ident["caps"])
                report["other_timings_seconds"]["image_preparation"] = time.monotonic() - start
                write_json(args.out / "image.json", image.manifest())
                load_and_run(transport, image, args.out, report, args.full_reset_confirmed,
                             args.run_id, args.seconds, args.watchdog_cycles, args.batch_chunks,
                             args.single_beat)
        write_json(args.out / "report.json", report)
        print(f"{report['state']}: {args.out}")
        metrics = report.get("load_metrics", {})
        rate = metrics.get("payload_bytes_per_second_including_readback")
        if rate is not None:
            print(f"Verified load only: {metrics['payload_bytes_including_bss']} payload bytes (BSS included), "
                  f"{metrics['elapsed_seconds']:.6f} s, {rate:.3f} payload B/s INCLUDING readback")
            print(f"Ratio to theoretical UART115200 8N1 ceiling (11520 B/s): "
                  f"{metrics['ratio_to_uart_theoretical_not_measured_speedup']:.6f}; NOT measured speedup")
        return 0
    except Exception as exc:
        report.update(state="failed", passed=False, error=str(exc), completed_utc=now())
        write_json(args.out / "report.json", report)
        if args.command in ("load", "ddr-test", "axi-probe", "axi-burst-probe", "axi-spm-probe") and not (args.out / "snapshot.json").exists():
            # A timed-out memory transaction must not prevent independent diagnosis.
            try:
                with connect("recovery_debug") as transport:
                    save_snapshot(args.out, capture_snapshot(transport, freeze=True))
            except Exception as diagnostic_error:
                report["diagnostic_error"] = str(diagnostic_error)
        write_json(args.out / "report.json", report)
        print(f"FAILED: {exc}; evidence: {args.out}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main())
