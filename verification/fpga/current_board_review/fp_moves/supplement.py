#!/usr/bin/env python3
"""Seven scalar-insert derivatives; preserve the original full byte oracle."""
import argparse
import json
from pathlib import Path
import re
import shutil
import subprocess
import sys

sys.dont_write_bytecode = True
from focused import HERE, BASE, SOURCE, CC, SPIKE, MARKER, inside, prepare, adapt

CASES = {
    "int_plain_restart": (2, 1, True, 16),
    "int_plain_start0": (2, 0, True, 16),
    "fp_old64_restart": (18, 17, False, 64),
    "fp_old64_start0": (18, 0, False, 64),
    "fp_old64_empty": (18, 18, False, 64),
    "int_old8_restart": (2, 1, True, 8),
    "int_old8_start0": (2, 0, True, 8),
}


def assembly(original, integer, old_eew):
    first, last = original.index(".global op_6\n"), original.index(".global op_7\n")
    body = original[first:last]
    if old_eew != 16:
        # A full-register integer identity establishes stored EEW without new
        # memory-alignment assumptions or changing any original input bytes.
        shift = "srli t3,a4,2" if old_eew == 64 else "slli t3,a4,1"
        setup = ("vle16.v v24,(a2)\n" + shift + "\n"
                 f"vsetvli t0,t3,e{old_eew},m1,tu,mu\n"
                 "vor.vv v24,v24,v24\n"
                 "vsetvli t0,a4,e16,m1,tu,mu\n")
        assert body.count("vle16.v v24,(a2)\n") == 1
        body = body.replace("vle16.v v24,(a2)\n", setup)
    if integer:
        assert body.count("fld ft0,0(a1)") == body.count("vfmv.s.f v24,ft0") == 1
        body = body.replace("fld ft0,0(a1)", "ld t3,0(a1)")
        body = body.replace("vfmv.s.f v24,ft0", "vmv.s.x v24,t3")
    return original[:first] + body + original[last:]


def build(out):
    out.mkdir(parents=True, exist_ok=False)
    prepared, host = out / "prepared", out / "host"
    prepared.mkdir()
    host.mkdir()
    original = json.loads((SOURCE.parent / "manifest.json").read_text())
    case = next(c for c in original["cases"] if c["name"] == SOURCE.name)
    for n, digest in case["scenario_sources"].items():
        assert prepare.sha(SOURCE / n) == digest
    for n in ("startup.S", "runtime.c", "replay.ld"):
        shutil.copyfile(BASE / n, prepared / n)
    source = (SOURCE / "scenario.c").read_text()
    asm = (SOURCE / "scenario.S").read_text()
    oracle = source[source.index("        unsigned long control="):source.index("        ++cases;")]
    entries, tests = [], []
    for name, (vl, start, integer, old_eew) in CASES.items():
        dest = prepared / name / "original"
        dest.mkdir(parents=True)
        for n in ("inputs.h", "operations.h", "scenario.c"):
            shutil.copyfile(SOURCE / n, dest / n)
        (dest / "source.S").write_text(asm)
        (dest / "scenario.S").write_text(assembly(asm, integer, old_eew))
        adapted = adapt(source, name, vl, start)
        assert oracle in adapted
        (dest.parent / "case.c").write_text(adapted)
        defines = ["SEW=16", "RESTART_MOVES=1", "DETAIL_MOVES=1", "MOVE_OP_MASK=64"]
        entries.append(dict(id=name, assembly="scenario.S", include_combined=True, defines=defines,
                            vl=vl, vstart=start, integer=integer, stored_eew=old_eew))
        for mutation in (0, 1, 2):
            exe = host / (name + "_" + str(mutation))
            command = ["/usr/bin/gcc", "-O2", "-Wall", "-Wextra", "-Werror", "-fno-tree-vectorize",
                       *["-D" + x for x in defines], "-DCASE_MAIN=" + name + "_main",
                       "-DHOST_MUTATION=" + str(mutation), "-I" + str(dest),
                       str(dest.parent / "case.c"), str(HERE / "host_fixture.c"), "-o", str(exe)]
            subprocess.run(command, check=True)
            result = subprocess.run([str(exe)], capture_output=True, text=True, timeout=5)
            expected = int(mutation == 2 or (mutation == 1 and start < vl))
            (host / (exe.name + ".log")).write_text(result.stdout + result.stderr)
            assert result.returncode == expected
            tests.append(dict(name=name, mutation=mutation, expected=expected,
                              returncode=result.returncode, command=command))
    prepare.save(out / "host.json", dict(status="PASS", checks=tests, scope="Scalar oracle sanity only"))
    provenance = dict(schema_version=1, cases=entries, original_source_case=case,
        original_oracle_block_unchanged=True, source_identity_assembly_preserved="source.S",
        scope="Integer opcode/operand derivative and explicit stored-EEW identity setup; not original full partition",
        generator_sha256=prepare.sha(Path(__file__)), focused_helper_sha256=prepare.sha(HERE / "focused.py"))
    provenance["files"] = {str(p.relative_to(prepared)): prepare.sha(p)
                           for p in prepared.rglob("*") if p.is_file()}
    prepare.save(prepared / "provenance.json", provenance)
    prepare.EXTENSIONS = list(CASES)
    prepare.ORACLE_MARKERS.update({n: MARKER for n in CASES})
    for backend in ("soc", "spike"):
        prepare.compile_programs(prepared, out / backend, CC, backend == "spike")
        ledger = json.loads((out / backend / "programs.json").read_text())
        ledger["programs"] = {n: ledger["programs"][n] for n in CASES}
        prepare.save(out / backend / "programs.json", ledger)
    maps, refs = {}, []
    for name, (_, _, integer, _) in CASES.items():
        maps[name] = {}
        for backend in ("soc", "spike"):
            elf = out / backend / (name + ".elf")
            dis = elf.with_suffix(".dis")
            operation = r"vmv\.s\.x\s+v24,t3" if integer else r"vfmv\.s\.f\s+v24,ft0"
            matches = re.findall(r"^\s*([0-9a-f]+):\s+([0-9a-f]{8})\s+" + operation, dis.read_text(), re.M)
            assert len(matches) == 1, (name, matches)
            pc, opcode = matches[0]
            maps[name][backend] = dict(target_pc="0x" + pc, opcode=opcode,
                                       elf_sha256=prepare.sha(elf), disassembly_sha256=prepare.sha(dis))
        elf = out / "spike" / (name + ".elf")
        nm = subprocess.check_output([str(CC.with_name(CC.name.removesuffix("gcc") + "nm")), str(elf)], text=True)
        symbols = {n: a for a, _, n in (line.split() for line in nm.splitlines())}
        debug = out / (name + ".cmd")
        debug.write_text("until pc 0 " + maps[name]["spike"]["target_pc"][2:] + "\n"
                         "pc 0\ninsn 0\nreg 0 vl\nreg 0 vstart\n"
                         "until pc 0 " + symbols["replay_exit"] + "\nreg 0 a0\nstr " + symbols["replay_log"] + "\nrs\n")
        command = [str(SPIKE), "-d", "--debug-cmd=" + str(debug), "--isa=rv64gcv_zvfh_zvl1024b", "-m2", str(elf)]
        log = out / (name + ".spike.log")
        with log.open("w") as f:
            result = subprocess.run(command, stdout=f, stderr=subprocess.STDOUT, timeout=30)
        passed = result.returncode == 0 and MARKER in log.read_text() and "BOARD_REPLAY_PASS" in log.read_text()
        refs.append(dict(name=name, passed=passed, returncode=result.returncode,
                         command=command, log_sha256=prepare.sha(log)))
    prepare.save(out / "address_map.json", dict(programs=maps))
    prepare.save(out / "reference.json", dict(status="PASS" if all(x["passed"] for x in refs) else "FAIL",
        results=refs, spike_sha256=prepare.sha(SPIKE), address_map_sha256=prepare.sha(out / "address_map.json")))
    assert all(x["passed"] for x in refs)
    print("SUPPLEMENT_HOST_21_PASS SPIKE_7_PASS", flush=True)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--out", type=Path, required=True)
    args = parser.parse_args()
    build(inside(args.out))
