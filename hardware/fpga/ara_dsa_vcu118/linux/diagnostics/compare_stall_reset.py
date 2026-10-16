"""Compare bounded reset inventories; equality is not whole-design equivalence."""
import argparse
import json
from pathlib import Path
import tkinter


def read_inventory(path):
    parser = tkinter.Tcl()
    records = {}
    cells = set()
    count = None
    for line in Path(path).read_text().splitlines():
        fields = parser.splitlist(line)
        if not fields:
            continue
        kind = fields[0]
        if kind == "CELL":
            if len(fields) != 6 or fields[2] != "DEPTH" or fields[4] != "REF":
                raise ValueError("Malformed CELL")
            cells.add(fields[1])
            key, value = (kind, fields[1]), fields[5]
        elif kind == "PROPERTY":
            if len(fields) != 4:
                raise ValueError("Malformed PROPERTY")
            key, value = tuple(fields[:3]), fields[3]
        elif kind == "INPUT":
            if len(fields) != 4 or fields[2] != "DRIVERS":
                raise ValueError("Malformed INPUT")
            key = (kind, fields[1])
            value = tuple(sorted(parser.splitlist(fields[3])))
        elif kind == "MATCH":
            if len(fields) != 4 or fields[2] != "COUNT":
                raise ValueError("Malformed MATCH")
            key, value = tuple(fields[:2]), int(fields[3])
        elif kind == "TOTAL_CELLS":
            if count is not None or len(fields) != 2:
                raise ValueError("Malformed/duplicate completion count")
            count = int(fields[1])
            continue
        else:
            raise ValueError(f"Unknown record {kind}")
        if count is not None or key in records:
            raise ValueError("Duplicate record or data after completion")
        records[key] = value
    if not cells or count != len(cells):
        raise ValueError("Incomplete inventory")
    return records


def compare(original, observation):
    differences = []
    for key in sorted(original.keys() | observation.keys()):
        if key not in original or key not in observation or original[key] != observation[key]:
            differences.append({"key": key, "original": original.get(key),
                                "observation": observation.get(key)})
    return {"scope": "bounded_reset_inventory_only", "equivalence_proven": False,
            "identical_inventory": not differences, "differences": differences}


if __name__ == "__main__":
    args = argparse.ArgumentParser(description=__doc__)
    args.add_argument("original", type=Path)
    args.add_argument("observation", type=Path)
    options = args.parse_args()
    result = compare(read_inventory(options.original), read_inventory(options.observation))
    print(json.dumps(result, indent=2))
