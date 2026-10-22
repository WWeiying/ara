#!/usr/bin/env python3
"""Structural LZC reachability evidence, never a native coverage exclusion."""
import argparse
import hashlib
import json
from pathlib import Path


SOURCE_SHA256 = "f31989be4369ea7c4809c0c3d61df28581e9ac7666005fde6e476a975d1acd07"


def prove(width):
    if type(width) is not int or width < 2:
        raise ValueError("WIDTH must be an integer >= 2")
    levels = (width - 1).bit_length()
    nodes = []
    for level in range(levels - 1):
        span = 1 << (levels - level)
        for index in range(1 << level):
            start = index * span
            middle = start + span // 2
            end = start + span
            left = list(range(start, min(middle, width)))
            right = list(range(middle, min(end, width)))
            # Children are ORs of disjoint real input bits; padding is constant 0.
            possibilities = [str(a) + str(b)
                             for a in ([0, 1] if left else [0])
                             for b in ([0, 1] if right else [0])]
            witnesses = {}
            for vector in possibilities:
                value = 0
                if vector[0] == "1":
                    value |= 1 << left[0]
                if vector[1] == "1":
                    value |= 1 << right[0]
                witnesses[vector] = hex(value)
            nodes.append(dict(level=level, index=index,
                              left_real_bits=left, right_real_bits=right,
                              reachable_child_vectors=possibilities,
                              unreachable_child_vectors=[v for v in ("00", "01", "10", "11")
                                                         if v not in possibilities],
                              reachable_selector_values=([0, 1] if left else [0]),
                              witnesses_in_tmp=witnesses))
    return dict(width=width, levels=levels,
                scope="g_not_last_level internal OR and left-child selector only",
                excluded="g_last_level g_reduce/g_base/g_out_of_range leaf assignments",
                nodes=nodes)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source", type=Path, required=True)
    parser.add_argument("--width", type=int, action="append", required=True)
    args = parser.parse_args()
    digest = hashlib.sha256(args.source.read_bytes()).hexdigest()
    if digest != SOURCE_SHA256:
        parser.error("LZC source differs from reviewed implementation")
    print(json.dumps(dict(schema="lzc-padding-proof-v1", source=str(args.source.resolve()),
                          source_sha256=digest,
                          status="STRUCTURAL_EVIDENCE_ONLY_NOT_NATIVE_WAIVER",
                          assumptions=["two-state input values", "WIDTH >= 2",
                                       "MODE only permutes real input bits",
                                       "all real input bit patterns permitted"],
                          limitations=["does not map DVE condition vectors or native leaf IDs",
                                       "does not authorize exclusion of any coverage point",
                                       "four-state initialization behavior not proved"],
                          proofs=[prove(width) for width in args.width]), indent=2))


if __name__ == "__main__":
    main()
