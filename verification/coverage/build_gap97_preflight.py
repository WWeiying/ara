"""Gap97 compile/Spike preflight only; no VCS, coverage admission, or waiver."""
import argparse
from collections import Counter
import hashlib
import json
from pathlib import Path
import struct
import subprocess

from inventory_operand_debug import Design
from closure_point_inventory import read_xml, definition, points
from run_gap75_operand_batch import SPIKE, parse_spike_commits
from ara_verify.random_rvv import _elf_symbol

ROOT = Path(__file__).resolve().parents[2]
OUT = ROOT / "verification/out"
BUILD = OUT / "repaired-aligned-build-20260930-01"
BASELINE = OUT / "gap96-offline-admitted-705-20261006-01"
LLVM = Path("/home/wangwy/openproject/ara/install/riscv-llvm/bin")
NAME = "vgap97_csr_large_avl"
APP = ROOT / "apps/riscv-tests/isa/rv64uv" / (NAME + ".c")
FROZEN_DISPATCHER = Path("/home/wangwy/openproject/ara_dsa/hardware/src/ara_dispatcher.sv")
DISPATCHER_SHA = "9af95c3eee6c63ecd9e60bf6d7c6474bdaaf1c5f96cef1bd653a6d51c6a2dd43"
SCOPE = "ara_tb.dut.i_ara_soc.i_system.i_ara.i_dispatcher"
TARGETS = {189: ("1736", "75", "10"), 576: ("4695", "246", "01"),
           588: ("4729", "251", "10"), 603: ("4804", "257", "01"),
           615: ("4843", "262", "10"), 616: ("4843", "262", "01")}
INITIAL = (4, 7, 2, 5, 6)
FUNCTIONS = (2, 3, 6, 7, 7)
OPERANDS = (1, 1, 1, 1, 2)


def require(value, message):
    if not value:
        raise ValueError(message)


def sha(path):
    h = hashlib.sha256()
    with Path(path).open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            h.update(block)
    return h.hexdigest()


def save(path, data):
    with path.open("x") as stream:
        json.dump(data, stream, indent=2)
        stream.write("\n")


def check(pins):
    for path, expected in pins.items():
        require(sha(path) == expected, "Pin drift: " + path)


def phase_oracle(phase):
    require(0 <= phase < 10, "Unknown phase")
    index = phase % 5
    initial, operand, funct = INITIAL[index], OPERANDS[index], FUNCTIONS[index]
    old = initial & 1 if phase < 5 else initial
    mask = 1 if phase < 5 else 7
    new = old | (operand & mask) if funct in (2, 6) else old & ~(operand & mask)
    vcsr = (initial & 6) | new if phase < 5 else new
    return [initial, initial & 1, initial >> 1, old, vcsr, vcsr & 1, vcsr >> 1]


def validate_targets(record, mapped):
    require(record["width"] == 1140 and record["checksum"] == "1370170966",
            "Dispatcher condition layout changed")
    require(0 <= int(record["bits"], 16) < (1 << record["width"]), "Bitmap overflow")
    selected = []
    for raw, (line, native, vector) in sorted(TARGETS.items()):
        matches = [p for p in mapped if p["raw_index"] == raw]
        require(len(matches) == 1, "Missing/duplicate target coordinate")
        point = matches[0]
        require((point["line"], point["native_id"], point["vector"]) == (line, native, vector),
                "Target identity differs")
        require(not int(record["bits"], 16) & (1 << (record["width"] - raw - 1)),
                "Target already hit in admitted705")
        selected.append(dict(scope=SCOPE, metric="cond", hit_before=False, point=point,
                             metric_checksum=record["checksum"], width=record["width"]))
    return selected


def target_evidence(pins):
    def pin(path, expected=None):
        path = Path(path).absolute()
        actual = sha(path)
        require(expected is None or expected == actual, "Evidence mismatch: " + str(path))
        pins[str(path)] = actual
        return path
    sourcefile = pin(BUILD / "build-source-pins.json")
    sources = json.loads(sourcefile.read_bytes())
    compiled_source = ROOT / "hardware/src/ara_dispatcher.sv"
    require(sources[str(compiled_source)] == DISPATCHER_SHA, "Old dispatcher pin differs")
    pin(FROZEN_DISPATCHER, DISPATCHER_SHA)
    bitmap_path, state_path = pin(BASELINE / "combined-bits.json"), pin(BASELINE / "status.json")
    bitmap, state = json.loads(bitmap_path.read_bytes()), json.loads(state_path.read_bytes())
    require(state["status"] == "PASS_RAW_UNION_HISTORICAL_ONLY" and state["aggregate_passed"] == 705,
            "Not admitted705")
    require(len(bitmap["tests"]) == 705 and len(set(bitmap["tests"])) == 705,
            "Population is not exact705")
    design = Design(BUILD / "sim/simv.vdb")
    for relative, expected in bitmap["design"].items():
        pin(design.db / relative, expected)
    source_info = pin(design.db / "auxiliary/verilog.sourceinfo.xml")
    shape_file = pin(design.db / "shape/cond.verilog.shape.xml")
    info_file = pin(design.db / "shape/cond.verilog.info.xml")
    binding = design.source(SCOPE)
    require(binding["resolved_path"] == str(compiled_source) and
            binding["definition_checksum"] == "1448229316", "Compiled source owner differs")
    source_record = design.sources[binding["file_id"]]
    info = [n for n in read_xml(info_file).iter("instance_data") if n.get("name") == SCOPE]
    record = bitmap["metrics"]["cond"][SCOPE]
    require(len(info) == 1 and info[0].get("chksum") == record["checksum"], "Metric checksum differs")
    node = definition(read_xml(shape_file), design.hierarchy[SCOPE], record["checksum"])
    targets = validate_targets(record, points("cond", node, record["width"]))
    param = design.definition(SCOPE, "tgl").get("param", "")
    fields = dict(field.split("=", 1) for field in param.split(","))
    require(all(fields.get(k) == v for k, v in
                dict(NrLanes="4", VLEN="1024", VLENB="128", FixPtSupport="1").items()),
            "Compiled configuration differs")
    compile_path = pin(BUILD / "compile.command.json")
    plan_path = pin(OUT / "repaired-aligned-600-20260930-01/plan.json")
    plan = json.loads(plan_path.read_bytes())
    require(plan["design_vdb"] == str(BUILD / "sim/simv.vdb") and
            plan["simv"] == str(BUILD / "sim/simv"), "Wrong old-image plan")
    return dict(status="GAP97_EXACT705_SIX_TARGETS_NOT_MEASURED", baseline_tests=705,
                baseline=str(bitmap_path), baseline_sha256=pins[str(bitmap_path)],
                design=bitmap["design"], compiled_source=binding, source_record=source_record,
                recovered_source=str(FROZEN_DISPATCHER), recovered_source_sha256=DISPATCHER_SHA,
                source_info=str(source_info), compiled_parameters=param,
                original_compile=json.loads(compile_path.read_bytes()),
                configuration_changed=False, targets=targets, target_unhit_count=6,
                old_image_plan=str(plan_path), expected_old_image_hashes=plan["image"],
                image_execution_verified=False, exclusions_generated=False)


def validate_probe(instruction, phase, registers):
    funct, csr, rd, rs1 = ((instruction >> 12) & 7, instruction >> 20,
                          (instruction >> 7) & 31, (instruction >> 15) & 31)
    require(instruction & 127 == 0x73 and funct == FUNCTIONS[phase % 5] and
            csr == (9 if phase < 5 else 15) and rd != 0, "Probe encoding differs")
    operand = registers.get(rs1) if funct < 4 else rs1
    require(rs1 != 0 and operand == OPERANDS[phase % 5], "Probe operand differs")
    return rd


def validate_spike(commits, symbols):
    registers, writes, probes = {0: 0}, {}, Counter()
    order, terminal_writes = [], []
    for commit in commits:
        require(commit.pc != symbols["trap_fail"], "Spike entered trap handler")
        for phase in range(10):
            if commit.pc == symbols["gap97_probe%d" % phase]:
                rd = validate_probe(commit.instruction, phase, registers)
                require(commit.gpr_writes.get(rd) == phase_oracle(phase)[3], "CSR returned wrong old value")
                probes[phase] += 1
                order.append(phase)
        if commit.pc == symbols["gap97_large_avl"]:
            insn = commit.instruction
            rd, rs1 = (insn >> 7) & 31, (insn >> 15) & 31
            require(insn & 127 == 0x57 and (insn >> 12) & 7 == 7 and insn >> 20 == 0 and
                    rd != 0 and rs1 != 0 and registers.get(rs1) == 1 << 20,
                    "Large AVL encoding/operand differs")
            require(commit.gpr_writes.get(rd) == 128, "Large AVL returned wrong VL")
            probes["avl"] += 1
            order.append("avl")
        for address, value in commit.memory_accesses:
            if value is not None:
                writes[address] = value
                if address == symbols["tohost"]:
                    terminal_writes.append(value)
        registers.update(commit.gpr_writes)
        registers[0] = 0
    require(probes == Counter({**{i: 1 for i in range(10)}, "avl": 1}), "Incomplete/duplicate probes")
    require(order == list(range(10)) + ["avl"], "Probe ordering differs")
    require(terminal_writes == [1], "Missing/duplicate/failed tohost terminal write")
    expected = {symbols["tohost"]: 1, symbols["g75_result"]: 75,
                symbols["g75_result"] + 4: 0, symbols["num_failed"]: 0}
    for phase in range(10):
        for column, value in enumerate(phase_oracle(phase)):
            expected[symbols["g97_observed"] + phase * 56 + column * 8] = value
    for column, value in enumerate((128, 128, 0, 128, 0)):
        expected[symbols["g97_avl"] + column * 8] = value
    for offset in (0, 8, 16):
        expected[symbols["g75_trap"] + offset] = 0
    require(all(writes.get(a) == v for a, v in expected.items()), "Incomplete/wrong exact signature")
    return dict(checks=75, csr_phases=10, exact_observed_bytes=600, probe_counts=dict(probes),
                scalar_commits=len(commits), expected_final_memory={hex(a): v for a, v in expected.items()})


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, required=True)
    out = parser.parse_args().output.absolute()
    require(out.parent == OUT and out.resolve() == out and not out.exists(), "Fresh direct output required")
    pins = {}
    evidence = target_evidence(pins)
    startup, linker = ROOT / "verification/tests/gap75_start.S", ROOT / "verification/tests/gap75.ld"
    paths = [Path(__file__).resolve(), Path(__file__).with_name("test_build_gap97_preflight.py"),
             APP, startup, linker, LLVM / "clang", LLVM / "llvm-readelf", LLVM / "llvm-objdump", SPIKE]
    paths += [p for p in (ROOT / "apps/riscv-tests/isa/macros").rglob("*") if p.is_file()]
    paths += [p for p in (ROOT / "verification/ara_verify").glob("*.py")]
    paths += [ROOT / "verification/coverage" / name for name in
              ("run_gap75_operand_batch.py", "inventory_operand_debug.py", "closure_point_inventory.py",
               "closure_scorecard.py", "reviewed_20261004/audit_readonly.py")]
    for path in paths:
        pins[str(path.resolve())] = sha(path)
    check(pins)
    out.mkdir()
    save(out / "target-before.json", evidence)
    try:
        with (out / "frozen-ara_dispatcher.sv").open("xb") as stream:
            stream.write(FROZEN_DISPATCHER.read_bytes())
        require(sha(out / "frozen-ara_dispatcher.sv") == DISPATCHER_SHA, "Archived source differs")
        elf = out / "input.elf"
        command = [str(LLVM / "clang"), "--target=riscv64-unknown-elf", "-march=rv64gcv_zfh_zvfh",
                   "-mabi=lp64d", "-mcmodel=medany", "-mno-relax", "-msmall-data-limit=0", "-O2",
                   "-fno-vectorize", "-fno-slp-vectorize", "-ffreestanding", "-DG75_NO_PRINT",
                   "-D__SPIKE__", "-DVLEN=1024", "-DNR_LANES=4",
                   "-I" + str(ROOT / "apps/riscv-tests/isa/macros/vector"),
                   "-I" + str(ROOT / "apps/riscv-tests/env"), "-I" + str(ROOT / "apps/common"),
                   "-fuse-ld=lld", "-nostdlib", "-T" + str(linker), str(startup), str(APP), "-o", str(elf)]
        save(out / "compile-command.json", command)
        with (out / "compile.log").open("x") as log:
            subprocess.run(command, stdout=log, stderr=subprocess.STDOUT, timeout=120, check=True)
        data = elf.read_bytes()
        require(struct.unpack_from("<Q", data, 24)[0] == 0x80000000, "Wrong ELF entry")
        phoff = struct.unpack_from("<Q", data, 32)[0]
        phsize, phnum = struct.unpack_from("<HH", data, 54)
        for i in range(phnum):
            segment = struct.unpack_from("<IIQQQQQQ", data, phoff + i * phsize)
            require(not (segment[0] == 1 and segment[5] and segment[4] % 128), "Unaligned ELF preload")
        keys = ("tohost", "g75_result", "g75_trap", "num_failed", "g97_observed", "g97_avl",
                "trap_fail", "gap97_large_avl") + tuple("gap97_probe%d" % i for i in range(10))
        symbols = {key: _elf_symbol(elf, LLVM / "llvm-readelf", key) for key in keys}
        with (out / "input.objdump").open("x") as log:
            subprocess.run([str(LLVM / "llvm-objdump"), "-d", str(elf)], stdout=log,
                           stderr=subprocess.STDOUT, timeout=30, check=True)
        command = [str(SPIKE), "--isa=rv64gcv_zfh_zvfh_zvl1024b", "--priv=msu",
                   "--pmpregions=0", "-l", "--log-commits", str(elf)]
        save(out / "spike-command.json", command)
        with (out / "spike.stdout").open("x") as stdout, (out / "spike.trace").open("x") as trace:
            subprocess.run(command, stdout=stdout, stderr=trace, timeout=120, check=True)
        diagnostic = validate_spike(parse_spike_commits(out / "spike.trace"), symbols)
        save(out / "spike-validation.json", diagnostic)
        check(pins)
        for path in out.iterdir():
            if path.is_file():
                pins[str(path)] = sha(path)
        manifest = dict(status="GAP97_SPIKE_PREFLIGHT_PASS_NOT_VCS", case=NAME, pins=pins,
                        baseline_tests=705, target_unhit_count=6, symbols=symbols, checks=75,
                        expected_vector_data_requests=0, expected_vector_data_bytes=0,
                        expected_vsetvli=1, measured_raw_increment=None, coverage_admitted=False,
                        rtl_changed=False, new_RTL_signoff=False, spike_validation=diagnostic)
        save(out / "preflight-manifest.json", manifest)
        print(json.dumps(dict(output=str(out), seal=sha(out / "preflight-manifest.json"),
                              elf_sha=sha(elf), checks=75, target_unhit_count=6)))
    except Exception as error:
        save(out / "failure.json", dict(status="PREFLIGHT_FAILED", reason=str(error), pins=pins))
        raise


if __name__ == "__main__":
    main()
