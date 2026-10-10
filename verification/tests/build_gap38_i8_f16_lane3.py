#!/usr/bin/env python3
"""Build one gap38 candidate, run Spike, and save a checked draft. Never run VCS."""
import argparse
import hashlib
import json
import os
from pathlib import Path
import re
import shlex
import struct
import subprocess
import sys
import time

sys.dont_write_bytecode = True
ROOT = Path(__file__).resolve().parents[2]
SCRIPT = Path(__file__).resolve()
NAME = "vgap38_i8_f16_lane3"
SOURCE = ROOT / "apps/riscv-tests/isa/rv64uv" / (NAME + ".c")
HISTORY = ROOT / "verification/out/gap38-queue-analysis-20261004-01"
BASELINE = ROOT / "verification/out/gap36-timeout-current-20261004-01"
PIN_PLAN = ROOT / "verification/out/repaired-aligned-600-20260930-01/plan.json"
CHECKS = 1274  # VLEN + 2*(7 CSR/setup + 512 element + 80 register + 36 guard) + 3 harness.
WORDS = {"gap38_signed_site": 0x4A859857, "gap38_unsigned_site": 0x4A851857}


def require(value, message):
    if not value:
        raise ValueError(message)


def read(path):
    return json.loads(Path(path).read_text())


def save(path, value):
    Path(path).write_text(json.dumps(value, indent=2, sort_keys=True) + "\n")


def sha(path):
    digest = hashlib.sha256()
    with Path(path).open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def pins(paths):
    return {str(p): sha(p) for p in sorted(set(map(Path, paths)))}


def verify(hashes):
    for path, digest in hashes.items():
        require(sha(path) == digest, "input drift: " + path)


def dependencies(path):
    text = path.read_text().replace("\\\n", " ").split(":", 1)[1]
    return {(ROOT / word).absolute() for word in shlex.split(text)}


def baseline_audit():
    checkpoint = read(BASELINE / "checkpoint.json")
    collection = read(BASELINE / "collection.json")
    require(checkpoint["coverage_status"] == "COMPLETE" and
            checkpoint["aggregate_passed"] == 638 and collection["status"] == "PASS" and
            collection["passed"] == 638, "638 baseline is not complete")
    verify(collection["reports"])
    rows = read(BASELINE / "all-passed-outcomes.json")
    bits = read(BASELINE / "combined-bits.json")
    design_db = Path((BASELINE / "combined-dve/inputs.txt").read_text().splitlines()[0])
    verify({str(design_db / "snps/coverage/db" / p): h for p, h in bits["design"].items()})
    inputs = (BASELINE / "combined-dve/inputs.txt").read_text().splitlines()
    require(len(rows) == 638 and bits["tests"] == inputs[1:] == [r["vdb"] for r in rows],
            "638 baseline membership differs")
    require(all(r["status"] == "PASS" and r["passed_only"] and r["vdb_valid"] for r in rows),
            "non-PASS baseline member")
    require(not any(r["name"] in (NAME, "rvv:" + NAME) for r in rows), "duplicate candidate")
    historical = read(HISTORY / "queue-audit.json")
    verify({str(ROOT / p): h for p, h in historical["source_pins"].items()})
    for scope, record in historical["instances"].items():
        for metric in ("branch", "line"):
            actual = bits["metrics"][metric][scope]
            prior = record["metrics"][metric]
            # Native shape supplies module identity for raw rows omitting chksum.
            require(actual["checksum"] in (None, prior["checksum"]) and
                    actual["width"] == prior["width"] and
                    format(int(actual["bits"], 16), f"0{actual['width']}b") == prior["bits638"],
                    "completed 638 differs from historical queue union")
    target = read(HISTORY / "path-classification.json")["candidate"]
    require(target["branch"]["raw_index"] == 41 == 31 + 46 - 1 - 35,
            "native branch-spec reversal differs")
    scope = target["scope"]
    require(historical["instances"][scope]["metrics"]["branch"]["bits638"][41] == "0" and
            all(historical["instances"][scope]["metrics"]["line"]["bits638"][i] == "0"
                for i in (120, 121)), "target no longer missing")
    return {"status": "PASS", "baseline": str(BASELINE), "passed": 638,
            "coverage_status": "COMPLETE", "queue_unions_matched": 36,
            "target": target, "measured_candidate_gain": None,
            "historical_records_unchanged": True, "waivers_applied": False,
            "note": "Historical pending-638 analysis retained verbatim; its raw queue union"
                    " now agrees with the completed official 638 aggregate. Structural A-queue,"
                    " child FIFO/LZC and observer classifications are review candidates only."}


class Build:
    def __init__(self, out):
        self.out, self.commands = out, []
        self.llvm = (ROOT / "install/riscv-llvm").resolve()
        self.cc = self.llvm / "bin/clang"
        self.host = Path("/usr/bin/cc").resolve()
        self.common = ROOT / "apps/common"
        self.sources = pins([SCRIPT, SOURCE])
        self.link_inputs = {}
        self.tools = pins([self.cc, self.host, sys.executable,
                          self.llvm / "bin/ld.lld", self.llvm / "bin/llvm-objdump",
                          self.llvm / "bin/llvm-readobj"])
        self.flags = ["--target=riscv64-unknown-elf", "-march=rv64gcv_zfh_zvfh", "-mabi=lp64d",
                      "-mcmodel=medany", "-mno-relax", "-O2", "-std=gnu11", "-fno-vectorize",
                      "-fno-slp-vectorize", "-fno-fast-math", "-ffp-contract=off",
                      "-mno-implicit-float", "-fno-common", "-fno-builtin-printf",
                      "-ffunction-sections", "-fdata-sections", "-DNR_LANES=4", "-DVLEN=1024"]
        self.inc = [f"-I{ROOT / p}" for p in ("apps/common", "apps/include",
                    "apps/riscv-tests/isa/macros/scalar", "apps/riscv-tests/isa/macros/vector")]

    def run(self, argv, label, timeout=120):
        argv = list(map(str, argv))
        log, err = self.out / (label + ".log"), self.out / (label + ".stderr.log")
        record = {"command": argv, "cwd": str(ROOT), "timeout_s": timeout,
                  "stdout": str(log), "stderr": str(err), "status": "STARTED"}
        self.commands.append(record)
        save(self.out / "commands.json", self.commands)
        start = time.monotonic()
        try:
            result = subprocess.run(argv, cwd=ROOT, capture_output=True, timeout=timeout,
                                    env={**os.environ, "PYTHONDONTWRITEBYTECODE": "1"})
        except subprocess.TimeoutExpired as error:
            log.write_bytes(error.stdout or b"")
            err.write_bytes(error.stderr or b"")
            record.update(status="TIMEOUT", seconds=time.monotonic() - start)
            save(self.out / "commands.json", self.commands)
            raise
        log.write_bytes(result.stdout)
        err.write_bytes(result.stderr)
        record.update(status="PASS" if result.returncode == 0 else "FAIL",
                      returncode=result.returncode, seconds=time.monotonic() - start,
                      log_hashes=pins([log, err]))
        save(self.out / "commands.json", self.commands)
        require(result.returncode == 0, f"{label} failed; see {err}")
        return result

    def bind_sources(self, paths):
        for path, digest in pins(paths).items():
            require(path not in self.sources or self.sources[path] == digest, "source drift: " + path)
            self.sources[path] = digest
        save(self.out / "source_hashes.json", self.sources)

    def compile(self, source, label, extra=(), host=False):
        obj, dep = self.out / (label + ".o"), self.out / (label + ".d")
        compiler = ([self.host, "-O2", "-std=gnu11", "-Wall", "-Wextra", "-Werror",
                     "-fno-fast-math", "-ffp-contract=off", "-DGAP38_ORACLE_HOST=1"] if host else
                    [self.cc, *self.flags, *self.inc])
        self.run([*compiler, *extra, "-M", "-MF", dep, source], label + ".dependencies")
        before = dependencies(dep)
        self.bind_sources(before)
        self.run([*compiler, *extra, "-MD", "-MF", dep, "-c", source, "-o", obj], label + ".compile")
        require(dependencies(dep) == before, "compile dependency set changed")
        verify(self.sources)
        return obj

    def link(self, argv, label):
        result = self.run([*argv, "-Wl,--trace"], label)
        for line in result.stdout.decode().splitlines():
            path = Path(line.split("(", 1)[0].strip())
            if path.is_file():
                self.link_inputs[str(path.absolute())] = sha(path)

    def metadata(self, elf, label):
        self.run([self.llvm / "bin/llvm-objdump", "-d", elf], label + ".disassembly")
        result = self.run([self.llvm / "bin/llvm-readobj", "--elf-output-style=JSON",
                           "--sections", "--symbols", "--program-headers", elf], label + ".metadata")
        metadata = json.loads(result.stdout)[0]
        symbols = {r["Symbol"]["Name"]["Name"]: r["Symbol"] for r in metadata["Symbols"]}
        blob, sites = elf.read_bytes(), {}
        for name, expected in WORDS.items():
            address = symbols[name]["Value"]
            matches = []
            for row in metadata["Sections"]:
                sec = row["Section"]
                if sec["Flags"]["Value"] & 4 and sec["Address"] <= address and \
                        address + 4 <= sec["Address"] + sec["Size"]:
                    offset = sec["Offset"] + address - sec["Address"]
                    matches.append(int.from_bytes(blob[offset:offset + 4], "little"))
            require(matches == [expected], "conversion instruction differs at " + name)
            sites[name] = {"pc": hex(address), "word": hex(expected)}
        return {"status": "PASS", "elf": str(elf), "elf_sha256": sha(elf), "sites": sites}


def host_oracle(b):
    obj = b.compile(SOURCE, "host-oracle", host=True)
    exe = b.out / "host-oracle"
    b.link([b.host, obj, "-o", exe], "host-oracle.link")
    result = b.run([exe], "host-oracle.results", timeout=30)
    rows = result.stdout.decode().splitlines()
    require(len(rows) == 512, "host oracle input set differs")
    for n, line in enumerate(rows):
        uns, byte, actual = line.split()
        uns, byte = int(uns), int(byte)
        require((uns, byte) == divmod(n, 256), "host oracle order differs")
        value = byte if uns or byte < 128 else byte - 256
        expected = int.from_bytes(struct.pack(">e", value), "big")
        require(int(actual, 16) == expected, "independent IEEE binary16 oracle mismatch")
    save(b.out / "oracle-check.json", {"status": "PASS", "inputs": 512,
         "reference": "Python struct.pack('>e', integer); all int8/uint8 inputs exactly representable",
         "implementation": "Same C bitwise integer_half used by both DUT and Spike test bodies",
         "binary": str(exe), "binary_sha256": sha(exe),
         "log": str(b.out / "host-oracle.results.log"),
         "log_sha256": sha(b.out / "host-oracle.results.log")})


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", required=True, type=Path)
    args = parser.parse_args()
    require(ROOT == Path("/home/wangwy/openproject/ara_dsa_signoff_integration"), "wrong worktree")
    out = args.output.resolve()
    require(out.parent == ROOT / "verification/out" and out.name.startswith("gap38-") and
            not out.exists(), "require a NEW verification/out/gap38-* directory")
    audit = baseline_audit()
    protected_paths = list(HISTORY.rglob("*")) + [SOURCE.with_name("vgap35_common.h"), PIN_PLAN,
        ROOT / "verification/coverage/coverage_evidence.py",
        ROOT / "verification/coverage/reviewed_20261004/audit_readonly.py"]
    protected_paths += [ROOT / p for p in read(HISTORY / "queue-audit.json")["source_pins"]]
    protected_paths += list(map(Path, read(BASELINE / "collection.json")["reports"]))
    protected_paths += [BASELINE / "checkpoint.json", BASELINE / "collection.json"]
    protected = pins(p for p in protected_paths if p.is_file())
    oracle = next(c for c in read(PIN_PLAN)["cases"] if c.get("spike"))
    spike = Path(oracle["spike"])
    require(sha(spike) == oracle["spike_sha256"], "pinned Spike differs")
    out.mkdir()
    save(out / "638-completion-note.json", audit)
    save(out / "protected-inputs.json", protected)
    b = Build(out)
    b.tools.update(pins([spike, ROOT / "verification/tools/soc-venv/bin/python"]))
    save(out / "tool_hashes.json", b.tools)
    print("Complete638 queue union matched; building one candidate", flush=True)
    host_oracle(b)
    objects = [b.compile(b.common / n, "dut-" + n) for n in
               ("crt0.S", "printf.c", "string.c", "serial.c", "util.c", "print_trap_cause.c")]
    objects.insert(0, b.compile(SOURCE, NAME, ["-Wall", "-Wextra", "-Wno-unused-function"]))
    elf = out / (NAME + ".elf")
    b.bind_sources([b.common / "link.ld"])
    b.link([b.cc, *b.flags, "-fuse-ld=lld", "-static", "-nostartfiles", "-Wl,--gc-sections",
            f"-Wl,-Map={out / (NAME + '.map')}", f"-T{b.common / 'link.ld'}", *objects, "-lm",
            f"-L{b.llvm / 'lib/generic'}", "-lclang_rt.builtins-riscv64", "-o", elf], NAME + ".link")
    fit_checker = ROOT / "verification/coverage/check_elf_fit.py"
    b.bind_sources([fit_checker])
    b.run([ROOT / "verification/tools/soc-venv/bin/python", fit_checker, "--elf", elf,
           "--ram-bytes", "0x200000", "--output", out / "elf-fit.json"], "elf-fit")
    dut_proof = b.metadata(elf, NAME)
    runtime = ROOT / "apps/riscv-tests/benchmarks/common"
    extra = ["-D__SPIKE__=1", "-DPREALLOCATE=1", f"-I{runtime}",
             f"-I{ROOT / 'apps/riscv-tests/env'}", "-fno-function-sections", "-fno-data-sections"]
    objects = [b.compile(src, label, extra) for src, label in
               [(runtime / "crt.S", "spike-crt"), (runtime / "syscalls.c", "spike-syscalls"),
                (SOURCE, "spike-test")]]
    spike_elf = out / (NAME + ".spike")
    b.bind_sources([runtime / "test.ld"])
    b.link([b.cc, *b.flags, "-fuse-ld=lld", "-static", "-nostdlib", f"-T{runtime / 'test.ld'}",
            *objects, "-o", spike_elf], NAME + ".spike-link")
    spike_proof = b.metadata(spike_elf, NAME + ".spike")
    command = [spike, "--isa=rv64gcv_zfh_zvfh_zvl1024b", "-l", "--log-commits", spike_elf]
    result = b.run(command, NAME + ".spike", timeout=30)
    log, trace = result.stdout.decode(), result.stderr.decode()
    require(re.findall(r"^gap35 checks=(\d+) failures=0$", log, re.M) == [str(CHECKS)] and
            log.splitlines().count("PASSED: " + str(SOURCE) + "!") == 1 and
            not re.search(r"(?im)^\s*(?:FAIL(?:ED)?\b|Fatal:|Error:)", log), "Spike selfcheck failed")
    commits = [(int(m[1]), int(m[2], 16), int(m[3], 16)) for m in re.finditer(
        r"(?m)^core\s+\d+:\s+([0-3])\s+0x([0-9a-f]+)\s+\(0x([0-9a-f]+)\)", trace)]
    for name, site in spike_proof["sites"].items():
        seen = [(mode, word) for mode, pc, word in commits if pc == int(site["pc"], 16)]
        require(seen == [(3, WORDS[name])], "conversion commit missing/duplicated: " + name)
    require(sum(word in WORDS.values() for _, _, word in commits) == 2 and
            not re.search(r"exception |trap_illegal_instruction|trap_load|trap_store", trace),
            "unexpected conversion or trap")
    proof = {"status": "PASS", "dut": dut_proof, "spike": spike_proof,
             "conversion_commits": 2, "retired_log_entries": len(commits), "unexpected_traps": 0,
             "checks": CHECKS, "vl": 36, "tail_halfwords_per_operation": 92,
             "source_bytes_per_operation": 128, "register_guards": [7, 9, 15, 18],
             "memory_guard_bytes_per_operation": 288, "fflags": 8, "frm": 0, "vstart": 0,
             "scope": "Spike-only, not RTL. Separate immutable CRT/I/O/link runtimes and ELFs;"
                      " Spike main is M-mode, DUT main U-mode. Conversion/check body uses only"
                      " unprivileged vector/FP CSRs; existing startup enables FS/VS in each runtime.",
             "vcs_timeout_s": 300, "vcs_runtime_measured": False, "vcs_launched": False}
    save(out / "execution-proof.json", proof)
    sys.path.insert(0, str(ROOT / "verification/coverage"))
    import coverage_evidence
    b.bind_sources([Path(m.__file__).resolve() for m in tuple(sys.modules.values())
                    if getattr(m, "__file__", None) and
                    str(Path(m.__file__).resolve()).startswith(str(ROOT / "verification"))])
    verify(b.sources)
    verify(b.tools)
    verify(b.link_inputs)
    verify(protected)
    save(out / "source_hashes.json", b.sources)
    save(out / "tool_hashes.json", b.tools)
    save(out / "link-inputs.json", b.link_inputs)
    row = {"test": "rvv:" + NAME, "status": "PASS", "returncode": 0,
           "command": list(map(str, command)), "seconds": b.commands[-1]["seconds"],
           "binary": str(elf), "binary_sha256": sha(elf), "spike_binary": str(spike_elf),
           "spike_sha256": sha(spike_elf), "spike_tool_sha256": sha(spike),
           "log": str(out / (NAME + ".spike.log")),
           "trace_log": str(out / (NAME + ".spike.stderr.log")),
           "source_hashes": b.sources, "tool_hashes": b.tools, "link_inputs": b.link_inputs,
           "checks": CHECKS, "vcs_launched": False, "measured_coverage_gain": None}
    row["log_sha256"], row["trace_sha256"] = sha(row["log"]), sha(row["trace_log"])
    save(out / "spike_results.json", [row])
    artifacts = pins(p for p in out.iterdir() if p.is_file())
    save(out / "artifact_hashes.json", artifacts)
    item = {"name": "rvv:" + NAME, "binary": str(elf), "binary_sha256": sha(elf),
            "sources": sorted(b.sources), "source_hashes": b.sources,
            "evidence": sorted([*artifacts, str(out / "artifact_hashes.json")]),
            "source_audit": "Same bitwise integer-to-half oracle host-validated against independent"
                            " IEEE packing for all 512 inputs. Two VL36 conversions, all 128 destination"
                            " halfwords including 92 tail elements, all 128 source bytes, full v7/v9/"
                            "v15/v18 guards and both guards on all nine buffers, immediate flags/CSRs."
                            " Unmodified gap35 selfcheck/PASS-path contract; no carry/slide/restart.",
            "targets": [audit["target"]["scope"]], "timeout_s": 300,
            "rationale": "Lane3 MFPU-B Branch5(35) raw41 and line Block116/117 raw120/121 remain"
                         " zero in COMPLETE638. VL36 gives each lane nine int8 source elements."
                         " Expected +1 branch/+2 line positions only; no measured gain or A-queue claim.",
            "precheck": {"format": "rvv-spike-v1", "record": str(out / "spike_results.json"),
                         "log": row["log"]}}
    selection = {"status": "CHECKED_DRAFT_SPIKE_ONLY_NOT_SUBMITTED", "baseline": str(BASELINE),
                 "baseline_bits": str(BASELINE / "combined-bits.json"), "cases": [item],
                 "vcs_launched": False, "waivers_applied": False, "measured_candidate_gain": None}
    selection_path = out / "selection.checked-draft.json"
    save(selection_path, selection)
    evidence = coverage_evidence.Evidence()
    evidence.pin(selection_path)
    for bound in (b.tools, b.link_inputs, protected, artifacts):
        evidence.hashes(bound)
    checked = coverage_evidence.precheck(read(selection_path)["cases"][0], evidence)
    verify(protected)
    save(out / "checked-precheck.json", {"status": "PASS", "result": checked,
         "checked_files": evidence.files, "entrypoint": "coverage_evidence.precheck(item, Evidence())",
         "read_only_validation": True, "baseline_full_reaudit_performed": False,
         "vcs_launched": False, "waivers_applied": False})
    save(out / "draft.sha256.json", pins([selection_path, out / "checked-precheck.json",
                                          out / "artifact_hashes.json"]))
    print(f"PASS: host oracle 512 inputs; genuine Spike {CHECKS} checks; two conversion commits", flush=True)
    print("PASS: read-only rvv-spike-v1 precheck; no VCS or waiver changes", flush=True)
    print(selection_path, flush=True)


if __name__ == "__main__":
    main()
