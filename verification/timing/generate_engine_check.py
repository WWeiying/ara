#!/usr/bin/env python3
"""Bind cycle-accurate QBS/AKV engine references to real command testbenches."""
import argparse
from pathlib import Path
import re

ROOT = Path(__file__).resolve().parents[2]


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--before", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    args.output.mkdir(parents=True, exist_ok=False)
    for group in ("qbs", "akv"):
        name = group + "_engine"
        path = Path(f"hardware/src/vlsu/{group}/{name}.sv")
        old, new = (args.before / path).read_text(), (ROOT / path).read_text()
        header = new[new.index("module "):new.index(");") + 2]
        params = re.findall(r"\bparameter\s+[^=\n]+?\b(\w+)\s*=", header)
        ports = []
        for line in header.splitlines():
            match = re.fullmatch(r"\s*(input|output)\s+(.+?)\s+(\w+)(\s+\[[^]]+\])?\s*,?", line)
            if match:
                direction, kind, port, dims = match.groups()
                ports.append((direction, kind, port, dims or ""))
            elif re.match(r"\s*(input|output)\b", line):
                raise ValueError(f"unsupported port declaration: {line}")
        outputs = [p for p in ports if p[0] == "output"]
        if not outputs or not params:
            raise ValueError(f"no ports/parameters in {name}")
        mapping = ", ".join(f".{p}({p})" for p in params)
        checker = re.sub(r"\b" + name + r"\b", name + "_cycle_check", header, count=1)
        checker = re.sub(r"\boutput\b", "input", checker) + "\n"
        for _, kind, port, dims in outputs:
            checker += f"  {kind} ref_{port}{dims};\n"
        checker += f"  {name}_reference #({mapping}) reference (\n"
        checker += "".join(f"    .{p}(ref_{p}),\n" for _, _, p, _ in outputs) + "    .*\n  );\n"
        checker += "  always @(negedge clk_i) if (rst_ni) begin\n"
        for _, _, port, _ in outputs:
            condition = "1'b1"
            if port.startswith("ldu_result_") and port != "ldu_result_req_o":
                checker += (f"    for (int l=0;l<NrLanes;l++) if (ldu_result_req_o[l])\n"
                            f"      assert ({port}[l] === ref_{port}[l])\n"
                            f'        else $fatal(1,"{name} {port} lane=%0d cycle mismatch",l);\n')
                continue
            if port == "axi_ar_o":
                condition = "axi_ar_valid_o"
            if port in {"mmu_vaddr_o", "mmu_is_store_o"}:
                condition = "mmu_req_o"
            if port in {"physical_check_addr_o", "physical_check_bytes_o"}:
                condition = "physical_check_valid_o"
            checker += (f"    if ({condition}) assert ({port} === ref_{port})\n"
                        f'      else $fatal(1,"{name} {port} cycle mismatch");\n')
        checker += (f"  end\nendmodule\n"
                    f"bind {name} {name}_cycle_check #({mapping}) i_control_cycle_check (.*);\n")
        (args.output / f"{name}_reference.sv").write_text(
            re.sub(r"\b" + name + r"\b", name + "_reference", old))
        (args.output / f"{name}_check.sv").write_text(checker)
        print(f"{name}: {len(outputs)} cycle-checked outputs")


if __name__ == "__main__":
    main()
