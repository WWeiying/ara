#!/usr/bin/env python3
"""Four source-derived scalar-insert cases; sealed candidate02 only, jobs=1."""
import argparse
import csv
import json
import os
from pathlib import Path
import re
import shutil
import signal
import subprocess
import sys
import time
from types import SimpleNamespace

sys.dont_write_bytecode = True
HERE = Path(__file__).resolve().parent
BASE = HERE.parent / "integration"
sys.path.insert(0, str(BASE))
import prepare
import run as checked

CAMPAIGN = Path("/home/wangwy/fpga_runs/ara_hw_campaign_20261007_01")
NAME = "rvv_small_fp_move_restart_e16_m1_ops6"
SOURCE = CAMPAIGN / "rvv_small_fp_moves01" / NAME
IMAGE = Path("/home/wangwy/fpga_runs/current_board_memory_candidate02/campaign/image")
IMAGE_SHA = "384515b7365200942d08fc7b34275d10eee676cf6ce0574935043020e87c7810"
CC = Path("/home/wangwy/openproject/ara/install/riscv-gcc/bin/riscv64-unknown-elf-gcc")
SPIKE = Path("/home/wangwy/openproject/riscv-isa-sim-ara-dsa-vstart/build/spike")
CASES = {"fp_move_original": (2, 1), "fp_move_start0": (2, 0),
         "fp_move_start_eq_vl": (2, 2), "fp_move_vl0": (0, 1)}
MARKER = "RVV_FP_MOVE_PASS sew=16 cases=1 errors=0"
SYSTEM = "ara_tb.dut.i_ara_soc.i_system"
ARA = SYSTEM + ".i_ara"
LANE = ARA + ".gen_lanes[0].i_lane"
ALU = LANE + ".i_vfus.i_valu"


def inside(path):
    path = path.resolve()
    if not path.is_relative_to(HERE):
        raise ValueError("output must stay in fp_moves/")
    return path


def adapt(source, name, vl, start):
    first = source.index("static long syscall3(")
    last = source.index("static void text(", first)
    source = source[:first] + ("extern long replay_write(long,long,long,long);\n"
                              "#define syscall3 replay_write\n") + source[last:]
    for old, new, count in [
        ("void probe_main(void)", "int " + name + "_main(void)", 1),
        ("syscall3(94,2,0,0);for(;;){}", "return 2;", 2),
        ("syscall3(94,errors ? 1:0,0,0);for(;;){}", "return errors ? 1:0;", 1),
        ("syscall3(29,1,0x5409,1)", "0 /* Linux drain; unreachable for op6 */", 1),
        ("unsigned vl=2;", f"unsigned vl={vl};", 1),
        ("unsigned start=1;", f"unsigned start={start};", 1),
    ]:
        assert source.count(old) == count, old
        source = source.replace(old, new)
    source, n = re.subn(r'__asm__\("\.global _start.*?\);\s*$', "", source, flags=re.S)
    assert n == 1 and "ecall" not in source and "syscall3(94" not in source
    return source


def build(out):
    out.mkdir(parents=True, exist_ok=False)
    manifest = json.loads((SOURCE.parent / "manifest.json").read_text())
    assert prepare.sha(SOURCE.parent / "manifest.json") == "e517533db5227820bbce08f6230f32b904d1d0a02169178e99d4f98221495d52"
    case = next(c for c in manifest["cases"] if c["name"] == NAME)
    for n, h in case["scenario_sources"].items():
        assert prepare.sha(SOURCE / n) == h
    assert prepare.sha(SOURCE.parent / "binaries" / NAME) == case["sha256"]
    prepared = out / "prepared"
    prepared.mkdir()
    for n in ("startup.S", "runtime.c", "replay.ld"):
        shutil.copyfile(BASE / n, prepared / n)
    entries = []
    host = out / "host"
    host.mkdir()
    host_results = []
    original = (SOURCE / "scenario.c").read_text()
    # The executable oracle block must remain byte-identical after wrapper adaptation.
    oracle = original[original.index("        unsigned long control="):original.index("        ++cases;")]
    for name, (vl, start) in CASES.items():
        dest = prepared / name / "original"
        dest.mkdir(parents=True)
        for n in case["scenario_sources"]:
            shutil.copyfile(SOURCE / n, dest / n)
        source = adapt(original, name, vl, start)
        assert oracle in source
        (dest.parent / "case.c").write_text(source)
        defines = ["SEW=16", "RESTART_MOVES=1", "DETAIL_MOVES=1", "MOVE_OP_MASK=64"]
        entries.append(dict(id=name, assembly="scenario.S", include_combined=True,
                            defines=defines, vl=vl, vstart=start))
        for mutation in (0, 1, 2):
            exe = host / (name + "_" + str(mutation))
            command = ["/usr/bin/gcc", "-O2", "-Wall", "-Wextra", "-Werror",
                       "-fno-tree-vectorize", *["-D" + x for x in defines],
                       "-DCASE_MAIN=" + name + "_main", "-DHOST_MUTATION=" + str(mutation),
                       "-I" + str(dest), str(dest.parent / "case.c"),
                       str(HERE / "host_fixture.c"), "-o", str(exe)]
            subprocess.run(command, check=True)
            result = subprocess.run([str(exe)], capture_output=True, text=True, timeout=5)
            expected = int(mutation == 2 or (mutation == 1 and start < vl))
            (host / (exe.name + ".log")).write_text(result.stdout + result.stderr)
            assert result.returncode == expected
            host_results.append(dict(name=name, mutation=mutation, returncode=result.returncode,
                                     expected=expected, command=command))
    prepare.save(out / "host.json", dict(status="PASS", checks=host_results,
        scope="Oracle sanity and mutation detection only, not hardware evidence"))
    provenance = dict(schema_version=1, cases=entries, original=case,
        scope="Original single source port plus three controls; not full Linux partition",
        source=str(SOURCE), full_oracle_unchanged=True, assembly_unchanged=True,
        script_sha256=prepare.sha(Path(__file__)),
        helper_sha256={n: prepare.sha(BASE / n) for n in ("prepare.py", "run.py")})
    provenance["files"] = {str(p.relative_to(prepared)): prepare.sha(p)
                           for p in prepared.rglob("*") if p.is_file()}
    prepare.save(prepared / "provenance.json", provenance)
    prepare.EXTENSIONS = list(CASES)
    prepare.ORACLE_MARKERS.update({n: MARKER for n in CASES})
    for backend in ("spike", "soc"):
        prepare.compile_programs(prepared, out / backend, CC, backend == "spike")
        ledger = json.loads((out / backend / "programs.json").read_text())
        ledger["programs"] = {n: ledger["programs"][n] for n in CASES}
        prepare.save(out / backend / "programs.json", ledger)
    maps, references = {}, []
    for name in CASES:
        maps[name] = {}
        for backend in ("spike", "soc"):
            elf = out / backend / (name + ".elf")
            dis = elf.with_suffix(".dis")
            pcs = re.findall(r"^\s*([0-9a-f]+):\s+42005c57\s+vfmv\.s\.f", dis.read_text(), re.M)
            assert len(pcs) == 1
            maps[name][backend] = dict(elf_sha256=prepare.sha(elf), target_pc="0x" + pcs[0],
                                       disassembly_sha256=prepare.sha(dis))
        elf = out / "spike" / (name + ".elf")
        nm = subprocess.check_output([str(CC.with_name(CC.name.removesuffix("gcc") + "nm")), str(elf)], text=True)
        symbols = {n: a for a, _, n in (line.split() for line in nm.splitlines())}
        debug = out / (name + ".cmd")
        debug.write_text("until pc 0 " + maps[name]["spike"]["target_pc"][2:] + "\n"
                         "pc 0\ninsn 0\nreg 0 vl\nreg 0 vstart\n"
                         "until pc 0 " + symbols["replay_exit"] + "\nreg 0 a0\nstr "
                         + symbols["replay_log"] + "\nrs\n")
        command = [str(SPIKE), "-d", "--debug-cmd=" + str(debug), "--isa=rv64gcv_zvfh_zvl1024b", "-m2", str(elf)]
        log = out / (name + ".spike.log")
        with log.open("w") as f:
            result = subprocess.run(command, stdout=f, stderr=subprocess.STDOUT, timeout=30)
        passed = result.returncode == 0 and MARKER in log.read_text() and "BOARD_REPLAY_PASS" in log.read_text()
        references.append(dict(name=name, passed=passed, returncode=result.returncode,
                               command=command, log_sha256=prepare.sha(log)))
    prepare.save(out / "address_map.json", dict(original_linux_target_pc="0x106f0",
        target_opcode="42005c57", programs=maps))
    prepare.save(out / "reference.json", dict(status="PASS" if all(r["passed"] for r in references) else "FAIL",
        results=references, spike_sha256=prepare.sha(SPIKE), address_map_sha256=prepare.sha(out / "address_map.json")))
    assert all(r["passed"] for r in references)
    print("HOST_12_PASS SPIKE_4_PASS", flush=True)


def resource_check():
    ps = subprocess.run(["/usr/bin/pgrep", "-a", "-x", "simv"], capture_output=True, text=True)
    assert ps.returncode in (0, 1)
    lines = ps.stdout.splitlines()
    reserve = max(0, 2 - sum("indexed_review" in x for x in lines))
    reserve += max(0, 1 - sum("mask_alias_original" in x for x in lines))
    memory = dict(line.split(":", 1) for line in Path("/proc/meminfo").read_text().splitlines())
    available = int(memory["MemAvailable"].split()[0]) * 1024
    assert len(lines) + reserve + 1 <= 24, "global simv cap; no launch"
    assert available >= 32 * 1024**3, "memory floor; no launch"
    return dict(simv_count=len(lines), reserved_unoccupied=reserve,
                available_bytes=available, processes=lines, jobs=1)


def profile():
    names = ["ara_tb.clk", SYSTEM + ".i_ara_commit_monitor.cycle_q"]
    names += [ARA + ".i_dispatcher." + n for n in (
        "acc_req_i", "acc_resp_o", "csr_vl_q", "csr_vstart_q", "ara_req_o",
        "ara_req_valid_o", "ara_req_ready_i")]
    names += [LANE + ".i_lane_sequencer." + n for n in (
        "pe_req", "pe_req_valid", "pe_req_ready", "vfu_operation_d", "vfu_operation_valid_d")]
    names += [ALU + "." + n for n in (
        "vfu_operation_i", "vfu_operation_valid_i", "alu_ready_o", "vinsn_issue_q",
        "vinsn_issue_valid", "issue_cnt_q", "valu_valid", "valu_result", "result_write",
        "alu_result_req_o", "alu_result_gnt_i", "alu_result_id_o", "alu_result_addr_o",
        "alu_result_be_o", "alu_result_wdata_o", "alu_vinsn_done_o")]
    return names


def replay(build_dir, out):
    assert json.loads((build_dir / "reference.json").read_text())["status"] == "PASS"
    assert prepare.sha(IMAGE / "image.json") == IMAGE_SHA
    out.mkdir(parents=True, exist_ok=False)
    checked.run_programs(SimpleNamespace(image=IMAGE, programs=build_dir / "soc",
        case=list(CASES), jobs=1, timeout=180, execute=False, out=out / "preflight"))
    image = json.loads((IMAGE / "image.json").read_text())
    programs = json.loads((build_dir / "soc/programs.json").read_text())["programs"]
    pins = dict(image["files"])
    for p in [IMAGE / "image.json", build_dir / "reference.json", build_dir / "address_map.json",
              build_dir / "host.json", build_dir / "soc/programs.json", Path(__file__)]:
        pins[str(p)] = prepare.sha(p)
    prepare.save(out / "pins.json", pins)
    prepare.save(out / "profile.json", dict(signals=profile(), window_ns=[0, 50000]))
    results = []
    for name, entry in programs.items():
        directory = out / name
        directory.mkdir()
        prepare.save(directory / "resources.json", resource_check())
        assert prepare.sha(Path(entry["path"])) == entry["sha256"]
        shutil.copyfile(entry["path"], directory / "input.elf")
        command = ["/usr/bin/nice", "-n", "10", image["simv"], "-no_save",
                   "-l", "run.vcs.log", "+ntb_random_seed=1", "+PRELOAD=" + str(directory / "input.elf"),
                   "+TESTCASE=" + name, "+NO_FSDB", "+COMMIT_TRACE=" + str(directory / "commit_trace.csv")]
        if name == "fp_move_original":
            tcl = ["onerror {quit}", "set fid [dump -file selected.fsdb -type FSDB]"]
            tcl += ["dump -add {" + n + "} -aggregates -fid $fid" for n in profile()]
            tcl += ["run -absolute 50000ns", "dump -disable -fid $fid", "dump -flush $fid", "run", "quit"]
            (directory / "capture.tcl").write_text("\n".join(tcl) + "\n")
            command += ["-ucli", "-do", str(directory / "capture.tcl")]
        prepare.save(directory / "command.json", dict(command=command, timeout_s=180,
            elf_sha256=entry["sha256"], image_sha256=IMAGE_SHA))
        began = time.monotonic()
        timeout = False
        with (directory / "console.log").open("w") as log:
            process = subprocess.Popen(command, cwd=directory, env=checked.environment(),
                                       stdout=log, stderr=subprocess.STDOUT, start_new_session=True)
            prepare.save(directory / "launch.json", dict(pid=process.pid, started=time.time()))
            try:
                rc = process.wait(timeout=180)
            except subprocess.TimeoutExpired:
                timeout = True
                os.killpg(process.pid, signal.SIGTERM)
                try:
                    rc = process.wait(timeout=5)
                except subprocess.TimeoutExpired:
                    os.killpg(process.pid, signal.SIGKILL)
                    rc = process.wait()
        text = (directory / "console.log").read_text()
        passed = rc == 0 and all(m in text for m in entry["pass_markers"]) and "Core Test *** SUCCESS *** (tohost = 0)" in text
        result = dict(name=name, status="TIMEOUT" if timeout else "PASS" if passed else "FAIL",
            returncode=rc, elapsed_s=time.monotonic()-began,
            oracle_lines=[s for s in text.splitlines() if "RVV_FP_MOVE_" in s or "BOARD_CASE_" in s],
            console_sha256=prepare.sha(directory / "console.log"))
        prepare.save(directory / "status.json", result)
        results.append(result)
        print(json.dumps(result), flush=True)
        if timeout or (not passed and "RVV_FP_MOVE_FAIL sew=16 cases=1 errors=" not in text):
            break
    for path, digest in pins.items():
        assert prepare.sha(Path(path)) == digest, path
    prepare.save(out / "complete.json", dict(status="MEASURED", results=results,
        pins_unchanged=True, image_sha256=IMAGE_SHA, no_rtl_build=True, jobs=1))


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("mode", choices=("build", "replay"))
    parser.add_argument("--out", type=Path, required=True)
    parser.add_argument("--build", type=Path)
    args = parser.parse_args()
    if args.mode == "build":
        build(inside(args.out))
    else:
        replay(inside(args.build), inside(args.out))
