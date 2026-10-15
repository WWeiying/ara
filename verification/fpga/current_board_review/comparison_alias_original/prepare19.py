#!/usr/bin/env python3
"""Port exactly19 archived comparison-alias singles; preserve source oracle."""
import argparse
import difflib
import json
from pathlib import Path
import re
import shutil
import subprocess
import sys

sys.dont_write_bytecode = True
HERE = Path(__file__).resolve().parent
BASE = HERE.parent / "integration"
sys.path.insert(0, str(BASE))
import prepare

CAMP = Path("/home/wangwy/fpga_runs/ara_hw_campaign_20261007_01")
ARCH = CAMP / "rvv_small_masks02"
CC = Path("/home/wangwy/openproject/ara/install/riscv-gcc/bin/riscv64-unknown-elf-gcc")
SPIKE = Path("/home/wangwy/openproject/riscv-isa-sim-ara-dsa-vstart/build/spike")
FAIL = re.compile(r"RVV_MASK_(?:FAIL|FIRST|BIT|CAPACITY_FAIL)|BOARD_CASE_FAIL|"
                  r"BOARD_REPLAY_(?:TRAP|SERVICE_FAIL|VLEN_FAIL|MISMATCH)")
SELECTED = "rvv_small_masks_cmp_alias_restart_e16_m1"


def read(path):
    return json.loads(path.read_text())


def require(ok, message):
    if not ok:
        raise ValueError(message)


def oracle(entry, text):
    return not FAIL.search(text) and "SKIP" not in text and all(m in text for m in entry["pass_markers"])


def adapt(source, name):
    begin, end = source.index("static long syscall3("), source.index("static void text(")
    source = source[:begin] + "extern long replay_write(long,long,long,long);\n#define syscall3 replay_write\n" + source[end:]
    for old, new in (("void probe_main(void)", "int " + name + "_main(void)"),
                     ("syscall3(94,2,0,0);for(;;){}", "return 2;"),
                     ("syscall3(94,errors ? 1:0,0,0);for(;;){}", "return errors ? 1:0;"),
                     ("syscall3(29,1,0x5409,1);", "(void)0; /* Linux UART drain only. */")):
        require(source.count(old) == 1, "Wrapper boundary differs: " + old)
        source = source.replace(old, new)
    source, count = re.subn(r'__asm__\("\.global _start.*?\);\s*$', "", source, flags=re.S)
    require(count == 1 and "ecall" not in source and "syscall3(94" not in source, "Linux wrapper remains")
    return source


def command(argv, log, timeout=60):
    prepare.save(Path(str(log) + ".command.json"), list(map(str, argv)))
    with log.open("x") as stream:
        result = subprocess.run(list(map(str, argv)), stdout=stream, stderr=subprocess.STDOUT, timeout=timeout)
    require(result.returncode == 0, str(log) + ": process failed")


def build(out):
    out.mkdir(parents=True, exist_ok=False)
    pins = {}

    def pin(path, expected=None):
        digest = prepare.sha(path)
        require(expected is None or expected == digest, "Identity drift: " + str(path))
        pins[str(path)] = digest

    pin(ARCH / "manifest.json", "eaafd63d14aa2a0d2019a49bb566d1983b2a1b94c15cbfbe17619185b9936ae8")
    manifest = read(ARCH / "manifest.json")
    symptoms_path = CAMP / "rvv_mask_symptoms02/symptoms.json"
    pin(symptoms_path, "1c7017790bd6953d6a6095ff793d1744d4a6c08a2ebca4d5d11a8cb7372f4409")
    symptoms = read(symptoms_path)
    for path, digest in ((ARCH / "prefix_board_report.json", symptoms["prefix_report_sha256"]),
                         (symptoms_path.parent / "sampled_report.json", symptoms["report_sha256"])):
        pin(path, digest)
    records = [c for c in manifest["cases"] if "masks_cmp_alias_restart" in c["name"]]
    require(len(records) == 19, "Expected19 genuine singles")
    records.sort(key=lambda c: (c["name"] != SELECTED, c["sew"], c["lmul"]))
    prepared = out / "prepared"
    prepared.mkdir()
    entries = []
    for n in ("startup.S", "runtime.c", "replay.ld"):
        pin(BASE / n)
        shutil.copyfile(BASE / n, prepared / n)
    for c in records:
        name = c["name"]
        symptom = next(x for x in symptoms["cases"] if x["name"] == name)
        require(symptom["confirmed"] and symptom["single_detail"] == symptom["prefix_detail"], "Unmatched historical failure")
        pin(ARCH / "binaries" / name, c["sha256"])
        pin(CAMP / "rvv_additions35/binaries" / c["original_name"], c["original_elf_sha256"])
        original = prepared / name / "original"
        original.mkdir(parents=True)
        for n, digest in c["scenario_sources"].items():
            pin(ARCH / name / n, digest)
            shutil.copyfile(ARCH / name / n, original / n)
        source = (original / "scenario.c").read_text()
        port = adapt(source, name)
        check = source[source.index("            unsigned long returned="):source.index("probe_done:\n")]
        require(check in port, "Scalar oracle changed")
        (original.parent / "case.c").write_text(port)
        (original.parent / "wrapper.diff").write_text("".join(difflib.unified_diff(
            source.splitlines(True), port.splitlines(True), fromfile="original/scenario.c", tofile="case.c")))
        defines = [f"SEW={c['sew']}", "SCALAR_FORMS=0", "ALIASES=0", "COMPARISON_ALIASES=1", "CARRY_FORMS=0", "RESTART_MASKS=1"]
        entries.append(dict(id=name, defines=defines, assembly="scenario.S", include_combined=False))
    for path in (Path(__file__), BASE / "prepare.py", BASE / "run.py", CC.resolve(), SPIKE):
        pin(path)
    prepare.save(out / "source_pins.json", pins)
    prepare.save(prepared / "provenance.json", dict(schema_version=1, cases=entries,
        records=records, scope="19 original archived singles, not4032-case parents or Linux ELF replay",
        files={str(p.relative_to(prepared)): prepare.sha(p) for p in prepared.rglob("*") if p.is_file()}))
    flags = ["-Os", "-march=rv64gcv", "-mabi=lp64d", "-mcmodel=medany", "-ffreestanding", "-fno-builtin",
             "-fno-stack-protector", "-fno-tree-vectorize", "-fno-tree-slp-vectorize", "-msmall-data-limit=0",
             "-ffunction-sections", "-fdata-sections", "-Wall", "-Wextra", "-Werror", "-nostdlib", "-static",
             "-Wl,--build-id=none", "-Wl,--gc-sections", "-T", prepared / "replay.ld"]
    maps, references = {}, []
    for backend in ("spike", "soc"):
        dest = out / backend
        dest.mkdir()
        programs = {}
        for c, entry in zip(records, entries):
            name, sew = c["name"], c["sew"]
            case = prepared / name
            main = dest / (name + "_main.c")
            main.write_text('extern void replay_text(const char *);\nextern int ' + name + '_main(void);\n'
                'int main(void) { unsigned long vb; __asm__ volatile("csrr %0,vlenb":"=r"(vb));\n'
                'if(vb!=128){replay_text("BOARD_REPLAY_VLEN_FAIL\\n");return 90;}\n'
                f'if({name}_main()){{replay_text("BOARD_CASE_FAIL {name}\\n");return 1;}}\n'
                f'replay_text("BOARD_CASE_PASS {name}\\nBOARD_REPLAY_PASS\\n");return 0;}}\n')
            elf = dest / (name + ".elf")
            defines = ["-D" + d for d in entry["defines"]]
            if backend == "spike":
                defines += ["-DSPIKE_REFERENCE=1"]
            command([CC, *flags, *defines, "-I" + str(case / "original"), case / "case.c",
                     case / "original/scenario.S", main, prepared / "startup.S", prepared / "runtime.c", "-lgcc", "-o", elf], dest / (name + ".compile.log"))
            dis = elf.with_suffix(".dis")
            command([CC.with_name(CC.name.removesuffix("gcc") + "objdump"), "-d", elf], dis)
            matches = re.findall(r"^\s*([0-9a-f]+):\s+60880457\s+vmseq\.vv\s+v8,v8,v16,v0.t", dis.read_text(), re.M)
            require(len(matches) == 1, "Missing/ambiguous op0 target")
            nm = subprocess.check_output([str(CC.with_name(CC.name.removesuffix("gcc") + "nm")), str(elf)], text=True)
            symbols = {n: a for a, _, n in (line.split() for line in nm.splitlines())}
            prepare.save(dest / (name + ".symbols.json"), symbols)
            maps.setdefault(name, {})[backend] = dict(target_pc="0x" + matches[0], opcode="60880457",
                elf_sha256=prepare.sha(elf), disassembly_sha256=prepare.sha(dis))
            markers = [f"RVV_MASK_PASS sew={sew} cases=1 errors=0", f"BOARD_CASE_PASS {name}", "BOARD_REPLAY_PASS"]
            programs[name] = dict(path=str(elf), sha256=prepare.sha(elf), cases=[name], pass_markers=markers)
            if backend == "spike":
                debug = dest / (name + ".cmd")
                debug.write_text("until pc 0 " + matches[0] + "\npc 0\ninsn 0\nreg 0 vl\nreg 0 vstart\n"
                    "until pc 0 " + symbols["replay_exit"] + "\nreg 0 a0\nstr " + symbols["replay_log"] + "\nrs\n")
                log = dest / (name + ".spike.log")
                command([SPIKE, "-d", "--debug-cmd=" + str(debug), "--isa=rv64gcv_zvl1024b", "-m2", elf], log, 30)
                require(oracle(programs[name], log.read_text()), "Spike original oracle not PASS: " + name)
                references.append(dict(name=name, status="PASS", log_sha256=prepare.sha(log)))
        prepare.save(dest / "programs.json", dict(schema_version=1, programs=programs, prepared=str(prepared),
            provenance_sha256=prepare.sha(prepared / "provenance.json"), backend="spike-htif" if backend == "spike" else "vcs-soc"))
    for path, digest in pins.items():
        require(prepare.sha(Path(path)) == digest, "Input drift: " + path)
    prepare.save(out / "address_map.json", maps)
    prepare.save(out / "reference.json", dict(status="SPIKE_19_PASS_NOT_DUT", results=references,
        source_pins_unchanged=True, full_original_scalar_oracle=True, assembly_unchanged=True))
    for token in ("RVV_MASK_FAIL", "RVV_MASK_FIRST", "RVV_MASK_BIT", "RVV_MASK_CAPACITY_FAIL", "BOARD_CASE_FAIL", "BOARD_REPLAY_TRAP"):
        require(not oracle(dict(pass_markers=["BOARD_REPLAY_PASS"]), "BOARD_REPLAY_PASS\n" + token), "Failure veto broken")
    print("SPIKE_19_PASS_NOT_DUT", flush=True)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--out", type=Path, required=True)
    args = parser.parse_args()
    out = args.out.resolve()
    require(out.is_relative_to(HERE) and out != HERE, "Owned output only")
    build(out)
