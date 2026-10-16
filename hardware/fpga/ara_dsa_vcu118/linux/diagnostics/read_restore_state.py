#!/usr/bin/env python3
"""Read saved vector context after the intentional kernel panic; no memory writes."""
import argparse
import hashlib
import json
from pathlib import Path
import struct
import sys


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--software", type=Path, required=True)
    parser.add_argument("--probes", type=Path, required=True)
    parser.add_argument("--vivado", required=True)
    parser.add_argument("--task-va", type=lambda s: int(s, 0), required=True)
    parser.add_argument("--data-va", type=lambda s: int(s, 0), required=True)
    parser.add_argument("--out", type=Path, required=True)
    args = parser.parse_args()
    sys.path.insert(0, str(args.software))
    from host_transport import Operation, VivadoTransport

    def physical(virtual):
        offset = virtual - 0xffffffd600000000
        if not 0 <= offset < 0x80000000:
            raise ValueError("not in this board kernel's reviewed direct-map range")
        return 0x80000000 + offset

    args.out.mkdir(parents=True, exist_ok=False)
    report = {"memory_writes": False, "task_va": hex(args.task_va),
              "data_va": hex(args.data_va), "requires_stopped_kernel": True}
    try:
        with VivadoTransport(args.out / "transport", vivado=args.vivado,
                             probes=args.probes) as transport:
            def read(address, count):
                result = bytearray()
                for offset in range(0, count, 512):
                    length = min(512, count - offset)
                    operations = [Operation("M", "READ", address + offset + i)
                                  for i in range(0, length, 8)]
                    result.extend(b"".join(transport.exchange(operations)))
                return bytes(result)

            metadata = read(physical(args.task_va) + 0xb80, 48)
            values = struct.unpack("<6Q", metadata)
            report["saved"] = dict(zip(("vstart", "vl", "vtype", "vcsr", "vlenb", "datap"),
                                       [hex(value) for value in values]))
            if values[4:] != (128, args.data_va):
                raise ValueError("context layout/direct-map validation failed")
            data = read(physical(args.data_va), 4096)
            report["stable"] = data == read(physical(args.data_va), 4096)
            report["sha256"] = hashlib.sha256(data).hexdigest()
            report["all_ff"] = data == b"\xff" * 4096
            (args.out / "context.bin").write_bytes(data)
    except Exception as exc:
        report["error"] = str(exc)
        raise
    finally:
        (args.out / "report.json").write_text(json.dumps(report, indent=2) + "\n")
        print(json.dumps(report, indent=2))


if __name__ == "__main__":
    main()
