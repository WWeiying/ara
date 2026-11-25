"""Compare the two cast RTL sources against the last completed DC inputs."""
import argparse
import re
import shutil
from pathlib import Path

from run_operand_ext import ROOT, command, read, save, sha, verify

RTL = Path("hardware/deps/fpnew/src")
FILES = ("fpnew_rounding", "fpnew_cast_multi")


def main():
    cli = argparse.ArgumentParser(description=__doc__)
    cli.add_argument("previous", type=Path, help="completed DC campaign with source-pins.json")
    cli.add_argument("out", type=Path)
    args = cli.parse_args()
    prev, out = args.previous.resolve(), args.out.resolve()
    pins = read(prev / "source-pins.json")
    assert read(prev / "status.json")["state"] == "SYNTHESIS_COMPLETE"
    src = out / "src"
    out.mkdir(parents=True, exist_ok=False)
    src.mkdir()
    shutil.copytree(ROOT / "hardware/deps/common_cells/include", out / "include")
    sources = []
    for rel in ("hardware/deps/common_cells/src/cf_math_pkg.sv",
                "hardware/deps/common_cells/src/lzc.sv", RTL / "fpnew_pkg.sv",
                RTL / "fpnew_classifier.sv", *(RTL / (n + ".sv") for n in FILES)):
        dest = src / Path(rel).name
        shutil.copy2(ROOT / rel, dest)
        sources.append(str(dest))
    changes = {}
    for name in FILES:
        rel = RTL / (name + ".sv")
        old, = (Path(p) for p in pins if Path(p).is_relative_to(prev / "dc/sources")
                and p.endswith("/" + str(rel)))
        assert sha(old) == pins[str(old)]
        text = old.read_text()
        for module in FILES:
            text = re.sub(r"\b" + module + r"\b", module + "_ref", text)
        ref = src / (name + "_ref.sv")
        ref.write_text(text)
        sources.append(str(ref))
        changes[str(rel)] = {"old": sha(old), "new": sha(src / rel.name)}
    bench = src / "cast_fused_equiv_tb.sv"
    shutil.copy2(Path(__file__).with_name(bench.name), bench)
    pins = {str(p): sha(p) for p in out.rglob("*") if p.is_file()}
    save(out / "source-pins.json", pins)
    cmd = ["vcs", "-full64", "-sverilog", "-top", "cast_fused_equiv_tb", "-timescale=1ns/1ps",
           "+incdir+include", *sources, str(bench), "-o", "simv"]
    save(out / "command.json", cmd)
    command(cmd, out, out / "compile.log", None)
    log = command(["./simv", "-no_save"], out, out / "run.log", "CAST_FUSED_EQUIV_PASS")
    rows = re.findall(r"CAST_PORT_PASS kind=(\d+) retired=(\d+) blocked=(\d+) cancelled=(\d+)", log)
    assert {r[0] for r in rows} == set("0123") and len(rows) == 4
    verify(out)
    save(out / "pass.json", {"state": "PASS", "changes": changes, "rows": rows,
                             "log_sha256": sha(out / "run.log")})
    print(log)


if __name__ == "__main__":
    main()
