#!/usr/bin/env python3
"""Read-only board discriminator; run from the exported software directory."""
import argparse
from datetime import datetime
import json
from pathlib import Path
import sys
import tempfile

sys.path.insert(0, str(Path.cwd()))
from host_load import identity, read_debug, STATUS
from host_transport import Operation, VivadoTransport


def collect(transport, report, fixed_probe=False):
    for base in (0xffff0000, 0x1401ff00):
        print(f"Reading region {base:#x} (no memory writes)...", flush=True)
        reads = [Operation("M", "READ", base + 8*i) for i in range(32)]
        region = {"base": hex(base), "rows": [], "stable": None}
        report["regions"].append(region)
        before = transport.exchange(reads)
        region["before"] = [word.hex() for word in before]
        for offset, beats in ((0, 2), (8, 2), (0x38, 2), (0x40, 2), (0, 3), (0x38, 3), (0, 2)):
            data = transport.exchange([Operation("M", "READ", base + offset, beats)])[0]
            words = [data[i:i+8] for i in range(0, len(data), 8)]
            matches = [[hex(base + 8*i) for i, old in enumerate(before) if old == word]
                       for word in words]
            region["rows"].append({"address": hex(base + offset), "beats": beats,
                                   "data": data.hex(), "matches": matches})
        if fixed_probe:
            region["fixed_rows"] = []
            for offset, beats in ((0, 2), (0x38, 3)):
                data = transport.exchange(
                    [Operation("M", "READ", base + offset, beats, burst="FIXED")])[0]
                words = [data[i:i+8] for i in range(0, len(data), 8)]
                matches = [[hex(base + 8*i) for i, old in enumerate(before)
                            if old == word] for word in words]
                region["fixed_rows"].append({"address": hex(base + offset),
                                              "beats": beats, "data": data.hex(),
                                              "matches": matches})
        after = transport.exchange(reads)
        region["after"] = [word.hex() for word in after]
        region["stable"] = before == after


def main(probes, output, vivado="vivado", fixed_probe=False):
    output = Path(output)
    output.mkdir(parents=True, exist_ok=False)
    print(f"EVIDENCE {output.resolve()}", flush=True)
    print("Connecting to Vivado; diagnostic only, no reset or launch...", flush=True)
    report = {"diagnostic_only": True, "memory_writes": False, "regions": []}
    try:
        with VivadoTransport(output / "transport", probes=Path(probes), vivado=vivado) as transport:
            report["identity"] = identity(transport)
            if read_debug(transport, [STATUS])[0] & 15 != 7:
                raise RuntimeError("Board not ready; no memory access attempted")
            collect(transport, report, fixed_probe=fixed_probe)
    except BaseException as exc:
        report["error"] = str(exc)
        raise
    finally:
        (output / "map.json").write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
        for region in report["regions"]:
            print("REGION", region["base"], "STABLE", region["stable"])
            for row in region["rows"]:
                print(row["address"], "LEN", row["beats"], "MATCHES", row["matches"])
            for row in region.get("fixed_rows", []):
                print("FIXED", row["address"], "LEN", row["beats"], "MATCHES", row["matches"])
        print("EVIDENCE", output)


def cli(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("probes", type=Path, help="Matching .ltx file for the programmed design")
    parser.add_argument("output", type=Path, nargs="?", help="New output directory (default: automatic)")
    parser.add_argument("--vivado", default="vivado", help="Vivado executable or .bat path")
    parser.add_argument("--fixed-probe", action="store_true",
                        help="Compare two read-only FIXED bursts with INCR bursts")
    args = parser.parse_args(argv)
    if not args.probes.is_file():
        parser.error(f"Probes file does not exist: {args.probes}")
    output = args.output
    if output is None:
        stamp = datetime.now().strftime("%Y%m%d_%H%M%S_")
        parent = Path.cwd() / "burst_maps"
        parent.mkdir(parents=True, exist_ok=True)
        output = Path(tempfile.mkdtemp(prefix=stamp, dir=parent)) / "run"
    try:
        main(args.probes.resolve(), output.resolve(), vivado=args.vivado,
             fixed_probe=args.fixed_probe)
    except KeyboardInterrupt:
        print(f"CANCELLED: inspect {output}", file=sys.stderr)
        return 130
    except Exception as exc:
        print(f"FAILED: {exc}; evidence: {output}", file=sys.stderr)
        return 1
    print("Diagnostic collected; this is not a burst correctness pass.")
    return 0


if __name__ == "__main__":
    sys.exit(cli())
