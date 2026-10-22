#!/usr/bin/env python3
"""New-directory gap44 compiler/Spike precheck; no simulator scheduler or VCS."""
import argparse
import hashlib
import json
from pathlib import Path
import subprocess
import sys
import time

sys.dont_write_bytecode = True
ROOT = Path(__file__).resolve().parents[2]
LLVM = ROOT / "install/riscv-llvm"
SPIKE = ROOT / "install/riscv-isa-sim/bin/spike"
COMMON = ROOT / "apps/common"
RUNTIME = ROOT / "apps/riscv-tests/benchmarks/common"
FLAGS = ["-march=rv64gcv_zfh_zvfh", "-mabi=lp64d", "--target=riscv64-unknown-elf",
         "-mcmodel=medany", "-mno-relax", "-O2", "-std=gnu99", "-fno-vectorize",
         "-fno-slp-vectorize", "-mno-implicit-float", "-fno-common", "-fno-builtin-printf",
         "-DNR_LANES=4", "-DVLEN=1024"]
INCLUDES = ["-I" + str(ROOT / p) for p in ("apps/include", "apps/common",
    "apps/riscv-tests/isa/macros/scalar", "apps/riscv-tests/isa/macros/vector",
    "apps/riscv-tests/env", "apps/riscv-tests/benchmarks/common")]
BASE = ROOT / "verification/out/gap37-control-current-20261004-01"
SCOPE = "ara_tb.dut.i_ara_soc.i_system.i_ariane.csr_regfile_i"


def digest(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def save(path, value):
    with Path(path).open("x") as stream:
        json.dump(value, stream, indent=2)
        stream.write("\n")


class Build:
    def __init__(self, out):
        self.out = out.resolve()
        if self.out.parent != ROOT / "verification/out" or not self.out.name.startswith("gap44-"):
            raise ValueError("use a NEW local verification/out/gap44-* directory")
        self.out.mkdir(exist_ok=False)
        self.commands, self.inputs, self.tools = [], {}, {}

    def pin(self, path, tool=False):
        path = Path(path).absolute()
        target = self.tools if tool else self.inputs
        sha = digest(path)
        if str(path) in target and target[str(path)] != sha:
            raise ValueError("input changed during build: " + str(path))
        target[str(path)] = sha
        return path

    def command(self, argv, filename, timeout=60):
        argv = list(map(str, argv))
        self.pin(argv[0], tool=True)
        log = self.out / filename
        entry = dict(argv=argv, cwd=str(ROOT), timeout_s=timeout, log=str(log))
        self.commands.append(entry)
        start = time.monotonic()
        try:
            result = subprocess.run(argv, cwd=ROOT, capture_output=True, timeout=timeout)
            data = result.stdout + result.stderr
            entry["returncode"] = result.returncode
        except subprocess.TimeoutExpired as exc:
            data = (exc.stdout or b"") + (exc.stderr or b"")
            entry["returncode"] = "TIMEOUT"
            with log.open("xb") as stream:
                stream.write(data)
            raise
        entry["elapsed_s"] = round(time.monotonic() - start, 6)
        with log.open("xb") as stream:
            stream.write(data)
        if result.returncode:
            raise RuntimeError("command failed; retained " + str(log))
        return data.decode()

    def binary(self, source, stem, spike):
        opts = FLAGS + (["-D__SPIKE__=1", "-DPREALLOCATE=1", "-DG35_TRACE=1"] if spike else [])
        runtime = RUNTIME if spike else COMMON
        names = ("crt.S", "syscalls.c") if spike else ("crt0.S", "printf.c", "string.c", "serial.c", "util.c", "print_trap_cause.c")
        objects = []
        for name in names:
            src = self.pin(runtime / name)
            obj = self.out / (stem + "_" + name + ".o")
            dep = Path(str(obj) + ".d")
            self.command([LLVM / "bin/clang", *opts, *INCLUDES, "-MD", "-MF", dep,
                          "-c", src, "-o", obj], obj.name + ".build.log")
            self.dependencies(dep)
            objects.append(obj)
        source = self.pin(source)
        obj = self.out / (stem + ".o")
        dep = Path(str(obj) + ".d")
        self.command([LLVM / "bin/clang", *opts, *INCLUDES, "-Wall", "-Wextra", "-Werror",
                      "-MD", "-MF", dep, "-c", source, "-o", obj], obj.name + ".build.log")
        self.dependencies(dep)
        link = self.pin(runtime / ("test.ld" if spike else "link.ld"))
        libraries = [] if spike else ["-lm", f"-L{LLVM.resolve() / 'lib/generic'}", "-lclang_rt.builtins-riscv64"]
        if not spike:
            self.pin(LLVM / "lib/generic/libclang_rt.builtins-riscv64.a", tool=True)
            self.pin(LLVM / "riscv64-unknown-elf/lib/libm.a", tool=True)
        self.pin(LLVM / "bin/ld.lld", tool=True)
        binary = self.out / stem
        self.command([LLVM / "bin/clang", *opts, "-fuse-ld=lld", "-static", "-nostdlib",
                      f"-T{link}", obj, *objects, *libraries, "-o", binary], stem + ".link.log")
        for tool, flags, suffix in (("llvm-nm", [], ".nm"), ("llvm-objdump", ["-d"], ".dis"),
                                    ("llvm-readelf", ["-lWs"], ".readelf")):
            self.command([LLVM / "bin" / tool, *flags, binary], stem + suffix)
        return binary

    def dependencies(self, path):
        # Clang Make dependencies; project paths contain no whitespace/escapes.
        text = path.read_text().replace("\\\n", "")
        for word in text.split(":", 1)[1].split():
            if "\\" in word:
                raise ValueError("unsupported escaped dependency path")
            self.pin(Path(word) if Path(word).is_absolute() else ROOT / word)

    def run_spike(self, binary):
        return self.command([SPIKE, "--isa=rv64gcv_zfh", "--pmpregions=0",
            "--varch=vlen:1024,elen:64", binary], binary.name + ".log")

    def finish(self):
        for path, sha in {**self.inputs, **self.tools}.items():
            if digest(path) != sha:
                raise ValueError("build input drift: " + path)
        save(self.out / "commands.json", self.commands)
        save(self.out / "source-hashes.json", self.inputs)
        save(self.out / "tool-hashes.json", self.tools)


def source_audit(build):
    review = ROOT / "verification/out/gap39-csr-waiver-review-20261004-01"
    pins = json.loads(build.pin(review / "proof-checks.json").read_text())["source_pins"]
    manifest = build.pin(ROOT / "verification/out/repaired-aligned-build-20260930-01/sim/vcs_source_manifest.json")
    compiled = {p["path"]: p["sha256"] for p in json.loads(manifest.read_text())["files"]}
    for name in ("hardware/deps/cva6/core/perf_counters.sv", "hardware/deps/cva6/core/include/ariane_pkg.sv",
                 "hardware/deps/cva6/core/decoder.sv"):
        path = str(ROOT / name)
        pins[path] = compiled[path]
    for path, sha in pins.items():
        if compiled[path] != sha or digest(build.pin(path)) != sha:
            raise ValueError("compiled RTL mismatch: " + path)
    pairs = json.loads(build.pin(review / "retained-coordinates.json").read_text())["access_pairs"]
    targets = [p for p in pairs if p["proof_id"].startswith("H_CSR_SUCCESS:") or
               p["proof_id"] in ("RV32_SUCCESS:806", "RV32_SUCCESS:875", "RV32_SUCCESS:1850")]
    collection = json.loads(build.pin(BASE / "collection.json").read_text())
    if collection["status"] != "PASS" or collection["passed"] != 640:
        raise ValueError("reviewed 640 baseline is not complete")
    bits_path = build.pin(BASE / "combined-bits.json")
    if digest(bits_path) != collection["reports"][str(bits_path)]:
        raise ValueError("baseline bitmap hash differs")
    row = json.loads(bits_path.read_text())["metrics"]["branch"][SCOPE]
    if row["width"] != 626 or row["checksum"] != "3035350189":
        raise ValueError("CSR branch shape differs")
    raw = format(int(row["bits"], 16), "0626b")
    if len(targets) != 50 or any(raw[p["retained"]["raw_index"]] != "0" for p in targets):
        raise ValueError("targets are no longer exactly 50 missing vectors")
    result = dict(scope=SCOPE, baseline=str(BASE), baseline_passed=640,
        compiled_manifest=str(manifest), compiled_manifest_sha256=digest(manifest), rtl_sources=pins,
        targets=[dict(proof_id=p["proof_id"], native=p["retained"]["native"],
                      raw_index=p["retained"]["raw_index"]) for p in targets],
        hypothesis="M privilege passes CSR address/counteren gating; RVH=0 or XLEN=64 then rejects inside read/write decode.",
        hpm="PerfCounterEn=1, MHPMCounterNum=6: counter3 implemented; event=0 is stable; two nonzero DUT seeds mandatory, no mcountinhibit.",
        runtime_budget_s=300, runtime_measured=False, coverage_gain_claimed=False)
    filename = build.out / "source-audit.json"
    save(filename, result)
    build.pin(filename)
    return result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", required=True, type=Path)
    parser.add_argument("--capability-only", action="store_true")
    args = parser.parse_args()
    build = Build(args.output)
    build.pin(__file__)
    record = None
    try:
        if args.capability_only:
            elf = build.binary(Path(__file__).with_name("gap44_hpm_capability.c"), "hpm-capability.spike", True)
            print(build.run_spike(elf), end="")
        else:
            sys.path.insert(0, str(ROOT / "verification/coverage"))
            import gap44_csr_oracle as oracle
            build.pin(oracle.__file__)
            audit = source_audit(build)
            capability_elf = build.binary(Path(__file__).with_name("gap44_hpm_capability.c"), "hpm-capability.spike", True)
            capability = oracle.validate_capability(build.run_spike(capability_elf))
            source = ROOT / "apps/riscv-tests/isa/rv64uv" / (oracle.NAME + ".c")
            elf = build.binary(source, oracle.NAME + ".elf", False)
            spike_elf = build.binary(source, oracle.NAME + ".spike", True)
            stub = oracle.stub_address(spike_elf.read_bytes())
            log = build.run_spike(spike_elf)
            validated = oracle.validate_log(log, spike=True, stub=stub)
            record = dict(status="SPIKE_PASS_ONLY", format=oracle.FORMAT, name=oracle.TEST,
                returncode=0, vcs_launched=False, binary=str(elf), elf_sha256=digest(elf),
                spike_elf=str(spike_elf), spike_elf_sha256=digest(spike_elf),
                log=str(build.out / (spike_elf.name + ".log")),
                stub=stub, dut_stub=oracle.stub_address(elf.read_bytes()), validated=validated,
                capability=capability, runtime_budget_s=300, runtime_measured=False,
                missing_branch_targets=audit["targets"],
                limitation="Spike HPM3 is RAZ/WI; nonzero writable-counter preservation remains a mandatory DUT-only assertion, NOT proved by Spike.")
    except Exception as exc:
        save(build.out / "failure.json", dict(error=type(exc).__name__, reason=str(exc), vcs_launched=False))
        raise
    finally:
        build.finish()
    if record is not None:
        record["files"] = {str(p): digest(p) for p in sorted(build.out.iterdir()) if p.is_file()}
        save(build.out / "evidence.json", record)
        print(json.dumps({k: record[k] for k in ("status", "name", "capability", "runtime_budget_s", "runtime_measured")}))
        print("PASS: 52 exact ELF-bound probes, 50 illegal, 1290 checks; no VCS")


if __name__ == "__main__":
    main()
