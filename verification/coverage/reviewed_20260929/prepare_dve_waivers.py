#!/usr/bin/env python3
"""Exact waivers for the reviewed FP16-repaired coverage image only."""
import argparse
import importlib.util
import re
from pathlib import Path

HERE = Path(__file__).resolve().parent
spec = importlib.util.spec_from_file_location("waiver_base", HERE / "waiver_base.py")
base = importlib.util.module_from_spec(spec)
spec.loader.exec_module(base)
base.HERE = HERE
base.APPROVED = {
    "59c11cb1ae975762be2d8b8df2b9e5c2bf713e5873a3ca71c0f4259d633a490e": "fp16-repaired-20260928-02",
}
base.SHAPES = {
    "fp16-repaired-20260928-02": "fcd7b464910ff702b9949bc7c33765203ffe658d95838aabcf34add92d7f1e25",
}
base.MONITORS = base.MONITORS | {"cva6_rvfi_probes"}
old_points = base.approved_points()
ROOT = "ara_tb.dut.i_ara_soc.i_system.i_ariane"
CONSTANT_POINTS = {(scope, "Toggle " + signal)
                   for scope in (ROOT, ROOT + ".csr_regfile_i")
                   for signal in ("ipi_i", "time_irq_i", "debug_req_i")}
base.approved_points = lambda: old_points | CONSTANT_POINTS
old_parser = base.exclusion_items


def exclusion_items(text):
    # Let the frozen parser validate all old directives. Only these three
    # additional scalar nets are accepted, then the exact scope set is checked.
    transformed, extra, path = [], set(), None
    for line in text.splitlines():
        if line.strip().startswith("INSTANCE:"):
            path = line.split(":", 1)[1].strip()
        if path in (ROOT, ROOT + ".csr_regfile_i") and re.match(r"\s*Toggle flush_i\b", line):
            raise ValueError("Unreviewed flush exclusion in scalar core")
        match = re.fullmatch(r'\s*Toggle (ipi_i|time_irq_i|debug_req_i)(?:\s+"[^"]*")?\s*', line)
        if match:
            point = (path, "Toggle " + match[1])
            if point not in CONSTANT_POINTS:
                raise ValueError("Constant-input exclusion in unreviewed scope")
            extra.add(point)
            transformed.append('Toggle flush_i "net flush_i"')
        else:
            transformed.append(line)
    parsed = old_parser("\n".join(transformed))
    for scope, _ in extra:
        parsed.discard((scope, "Toggle flush_i"))
    return parsed | extra


base.exclusion_items = exclusion_items

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--design", required=True, type=Path)
    parser.add_argument("--output", required=True, type=Path)
    parser.add_argument("--mode", choices=("auto", "off"), default="auto")
    parser.add_argument("--finalize", action="store_true")
    args = parser.parse_args()
    if args.finalize:
        base.finalize(args.design, args.output)
    else:
        print(base.prepare(args.design, args.output, args.mode)["status"])
