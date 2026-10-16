#!/usr/bin/env python3
"""Strict candidate-to-LTX name audit; mismatches require routed alias review."""
import argparse
import json
from pathlib import Path


def audit(bindings, ltx):
    cores = [c for s in ltx["ltx_root"]["ltx_data"] for c in s["debug_cores"]
             if c["name"] == "i_stall_ila"]
    if len(cores) != 1:
        raise ValueError("Expected one stall ILA")
    actual = {}
    for pin in cores[0]["pins"]:
        if pin["portIndex"] != 0:
            raise ValueError("Unexpected probe port")
        low, high = pin["leftIndex"], pin["rightIndex"]
        if low > high:
            raise ValueError("Unsupported LTX index direction; review explicitly")
        leaves = []
        for net in pin["nets"]:
            leaves.extend(n["name"] for n in net["subnets"]) if net.get("isBus") else leaves.append(net["name"])
        if len(leaves) != high-low+1:
            raise ValueError("LTX bus width mismatch")
        # Vivado 2020.1 emits bus subnets MSB-first, probe range start-first.
        for bit, net in zip(range(low, high+1), reversed(leaves)):
            if bit in actual:
                raise ValueError("Overlapping LTX probe bits")
            actual[bit] = net
    expected = bindings["physical_nets"]
    if set(actual) != set(range(len(expected))):
        raise ValueError("LTX does not cover the expected physical bits")
    mismatches = [dict(bit=i, expected=net, actual=actual[i])
                  for i, net in enumerate(expected) if net != actual[i]]
    return dict(width=len(expected), exact_name_match=not mismatches,
                mismatches=mismatches, routed_connectivity_proven=False,
                hardware_validated=False)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("bindings", type=Path)
    parser.add_argument("ltx", type=Path)
    parser.add_argument("output", type=Path)
    args = parser.parse_args()
    report = audit(json.loads(args.bindings.read_text()), json.loads(args.ltx.read_text()))
    with args.output.open("x") as stream:
        json.dump(report, stream, indent=2)
        stream.write("\n")
    print(f"WIDTH={report['width']} NAME_MISMATCHES={len(report['mismatches'])}; not a connectivity proof")
    return 0 if report["exact_name_match"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
