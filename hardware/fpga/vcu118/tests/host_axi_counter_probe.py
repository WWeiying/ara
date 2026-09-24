#!/usr/bin/env python3
"""Compare DDR observer deltas around one FIXED and one INCR JTAG read."""
import argparse
from datetime import datetime
import json
from pathlib import Path
import sys
import tempfile

sys.path.insert(0, str(Path.cwd()))
from host_load import (COMMAND, FREEZE, RESUME, STATUS, WATCHDOG, capture_snapshot,
                       identity, read_debug, write_debug)
from host_transport import Operation, VivadoTransport


FIELDS = ("ar_count", "r_bytes", "last_ar_addr", "read_outstanding", "error_count")
ADDRESSES = {"FIXED": 0xa1010000, "INCR": 0xa1011000}


def counters(snapshot):
    return {name: snapshot["ddr1"][name] for name in FIELDS}


def collect(transport, report, resume_counters=False, include_spm=False):
    report["identity"] = identity(transport)
    if read_debug(transport, [STATUS])[0] & 15 != 7:
        raise RuntimeError("Board not ready; no memory access attempted")
    frozen, watchdog = read_debug(transport, [COMMAND, WATCHDOG])
    report["was_frozen"] = bool(frozen)
    report["watchdog_cycles"] = watchdog
    if watchdog:
        raise RuntimeError("Watchdog is enabled; no memory access attempted")
    if frozen and not resume_counters:
        raise RuntimeError("Counters are frozen; rerun with --resume-counters")
    resumed = False
    try:
        if frozen:
            write_debug(transport, [(COMMAND, RESUME)])
            resumed = True
            if read_debug(transport, [COMMAND])[0] != 0:
                raise RuntimeError("Counter resume did not take effect")
        previous = capture_snapshot(transport)
        if previous["watchdog_snapshot"]:
            raise RuntimeError("Watchdog snapshot; no memory access attempted")
        report["initial"] = counters(previous)
        idle = capture_snapshot(transport)
        report["idle"] = counters(idle)
        report["idle_ar_delta"] = idle["ddr1"]["ar_count"] - previous["ddr1"]["ar_count"]
        if report["idle_ar_delta"] != 0:
            raise RuntimeError("DDR AR counter changed while idle; no probe reads attempted")
        previous = idle
        cases = [(burst, ADDRESSES[burst], 0) for burst in ("FIXED", "INCR")]
        if include_spm:
            cases.extend((burst, 0x1401ff00, cache)
                         for burst in ("INCR", "FIXED") for cache in (0, 2))
        for burst, address, cache in cases:
            data = transport.exchange(
                [Operation("M", "READ", address, 2, burst=burst, cache=cache)])[0]
            current = capture_snapshot(transport)
            if (current["watchdog_snapshot"] or
                    current["snapshot_sequence"] <= previous["snapshot_sequence"]):
                raise RuntimeError("Fresh DDR snapshot unavailable")
            delta = {name: current["ddr1"][name] - previous["ddr1"][name]
                     for name in ("ar_count", "r_bytes", "error_count")}
            report["reads"].append({"burst": burst, "address": hex(address),
                                    "arcache": cache,
                                    "data": data.hex(), "delta": delta,
                                    "after": counters(current)})
            previous = current
        for row in report["reads"]:
            address = int(row["address"], 16)
            reads = [Operation("M", "READ", address + 8*i) for i in range(20)]
            before = transport.exchange(reads)
            after = transport.exchange(reads)
            row["neighbor_stable"] = before == after
            row["matches"] = [
                [hex(address + 8*i) for i, word in enumerate(before) if word == beat]
                for beat in (bytes.fromhex(row["data"])[:8], bytes.fromhex(row["data"])[8:])
            ]
    finally:
        if resumed:
            write_debug(transport, [(COMMAND, FREEZE)])
            report["restored_frozen"] = read_debug(transport, [COMMAND])[0] == 1
            if not report["restored_frozen"]:
                raise RuntimeError("Counter freeze was not restored")


def main(probes, output, vivado="vivado", resume_counters=False, include_spm=False):
    output = Path(output)
    output.mkdir(parents=True, exist_ok=False)
    report = {"diagnostic_only": True, "memory_writes": False,
              "debug_snapshot_writes": True, "reads": []}
    print(f"EVIDENCE {output.resolve()}", flush=True)
    try:
        with VivadoTransport(output / "transport", probes=Path(probes), vivado=vivado) as transport:
            collect(transport, report, resume_counters=resume_counters,
                    include_spm=include_spm)
    except BaseException as exc:
        report["error"] = str(exc)
        raise
    finally:
        (output / "counter_probe.json").write_text(json.dumps(report, indent=2) + "\n",
                                                     encoding="utf-8")
        print(json.dumps({key: report.get(key) for key in
                          ("was_frozen", "restored_frozen", "watchdog_cycles",
                           "idle_ar_delta", "reads", "error")},
                         indent=2), flush=True)
        print(f"EVIDENCE {output}", flush=True)


def cli(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("probes", type=Path)
    parser.add_argument("output", type=Path, nargs="?")
    parser.add_argument("--vivado", default="vivado")
    parser.add_argument("--resume-counters", action="store_true",
                        help="Temporarily resume frozen counters and restore freeze afterward")
    parser.add_argument("--include-spm", action="store_true",
                        help="Also count DDR handshakes around read-only SPM cache/burst cases")
    args = parser.parse_args(argv)
    if not args.probes.is_file():
        parser.error(f"Probes file does not exist: {args.probes}")
    output = args.output
    if output is None:
        parent = Path.cwd() / "burst_maps"
        parent.mkdir(parents=True, exist_ok=True)
        output = Path(tempfile.mkdtemp(prefix=datetime.now().strftime("%Y%m%d_%H%M%S_"),
                                       dir=parent)) / "counter"
    try:
        main(args.probes.resolve(), output.resolve(), vivado=args.vivado,
             resume_counters=args.resume_counters, include_spm=args.include_spm)
    except KeyboardInterrupt:
        return 130
    except Exception as exc:
        print(f"FAILED: {exc}; evidence: {output}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(cli())
