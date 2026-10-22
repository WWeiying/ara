#!/usr/bin/env python3
"""New-output-only software builder and host/ELF preflight; never starts RTL."""
import argparse
from pathlib import Path
import shutil
import subprocess
import sys

sys.dont_write_bytecode = True
ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0,str(ROOT / "verification/coverage"))
import gap46_akv_oracle as oracle
from build_gap36_timeout_successors import Build as ExistingBuild
from coverage_evidence import Evidence

OWN = [ROOT / p for p in (
    "apps/akv_gap46_skew_context/main.c",
    "verification/coverage/gap46_akv_oracle.py",
    "verification/coverage/gap46_akv_admission.py",
    "verification/coverage/run_gap46_akv_checked_extension.py",
    "verification/coverage/gap46_akv_admission.md",
    "verification/tests/build_gap46_akv.py",
    "verification/tests/prepare_gap46_akv_admission.py",
    "verification/tests/test_gap46_akv_negative.py",
    "verification/tests/gap46_akv_host_negative.c")]


class Build(ExistingBuild):
    def run(self, argv, label, timeout=120, split=False):
        argv = list(map(str,argv))
        oracle.require(timeout <= 120, "software-only bounded command")
        result = subprocess.run(argv,cwd=ROOT,capture_output=True,timeout=timeout)
        log = self.out / (label+".log")
        log.write_bytes(result.stdout+result.stderr)
        self.commands.append(dict(command=argv,cwd=str(ROOT),timeout_s=timeout,
                                  returncode=result.returncode,log=str(log)))
        oracle.save(self.out / "commands.json",self.commands)
        oracle.require(result.returncode == 0,f"{label} failed: {log}")
        return result


def build(out):
    oracle.require(out.is_relative_to(ROOT / "verification/out") and not out.exists(), "fresh integration output required")
    out.mkdir(parents=True)
    proof = Evidence()
    targets = oracle.native_targets(proof)
    oracle.save(out / "native-targets.json",targets)
    old_helpers = [ROOT / p for p in (
        "verification/tests/build_gap36_timeout_successors.py", "verification/coverage/check_elf_fit.py",
        "verification/coverage/coverage_evidence.py", "verification/coverage/run_checked_extension.py",
        "verification/coverage/run_targeted_extension.py", "verification/coverage/run_full_recollection_20260928.py",
        "verification/coverage/run_vcs_dve_batch.py", "verification/coverage/coverage_bitmap_delta.py",
        "verification/coverage/reviewed_20261004/audit_readonly.py", "verification/ara_verify/runner.py",
        "hardware/Makefile", "apps/qbs_gap35_common/test.h")]
    protected = {str(p):oracle.sha(p) for p in old_helpers}
    protected.update(proof.files)
    b = Build(out)
    b.runtime()
    elf,sources = b.link_dut(OWN[0],oracle.NAME)
    b.metadata(elf,oracle.NAME)
    audit = oracle.elf_audit(elf.read_bytes())
    oracle.save(out / "elf-audit.json",audit)
    ref = ROOT / "software/akv/src/akv_v2_reference.c"
    objs = []
    for source,label in ((OWN[0],"host-main"),(ref,"host-reference")):
        obj,deps = b.compile(source,label,host=True)
        objs.append(obj)
        sources.update(deps)
    b.run(["cc",*objs,"-lm","-o",out / "host"],"host-link")
    b.run([out / "host"],"host",timeout=30)
    host = oracle.validate_log((out / "host.log").read_text(),True)
    obj,deps = b.compile(ROOT / "verification/tests/gap46_akv_host_negative.c","host-negative",host=True)
    sources.update(deps)
    b.run(["cc",obj,objs[1],"-lm","-o",out / "host-negative"],"host-negative-link")
    negative = b.run([out / "host-negative"],"host-negative",timeout=30)
    oracle.require(negative.stdout.decode().splitlines()[-1] == "GAP46_NEGATIVE_HOST rejected=20", "host injections not rejected")
    b.run([sys.executable,"-B",ROOT / "verification/tests/test_gap46_akv_negative.py",
           "--build",out],"negative-tests",timeout=120)
    tools = [b.cc,b.llvm / "bin/ld.lld",b.llvm / "bin/llvm-objdump",b.llvm / "bin/llvm-readobj",
             Path(shutil.which("cc")),Path(sys.executable),ROOT / "verification/tools/soc-venv/bin/python"]
    oracle.save(out / "tool-hashes.json",{str(p):oracle.sha(p) for p in tools})
    sources.update(OWN+old_helpers)
    sources.add(ROOT / "software/akv/include/akv/akv_abi.h")
    oracle.save(out / "source-hashes.json",{str(p):oracle.sha(p) for p in sorted(sources)})
    for p,h in protected.items():
        oracle.require(oracle.sha(p) == h,"protected input changed during preflight: "+p)
    oracle.save(out / "source-audit.json",dict(status="PASS",compiled_manifest=targets["compiled_manifest"],
        input_hashes=protected,old_helpers_modified=False,rtl_modified=False,vcs_launched=False,
        descriptor_version=1,v1_skew=[2,6,14],v1_stride=130,v2_stride=128,
        operations=12,traps=3,host_checks=oracle.HOST_CHECKS,dut_checks=oracle.DUT_CHECKS,
        checks_formula="common 12*(256+1 seed+1 frame guards+6 full sources+2 descriptors); host +12*2; DUT +12*3+3*3",
        perf_default=False,perf_evidence="runner.py _run_test has no AKV_PERF; hardware/Makefile enables it only in sim_verilator",
        perf_local="gap46-only directed hook adds +AKV_PERF, logs effective argv, preserves old helpers",
        bounds="two 3x256-byte sources share one 4096-aligned page, payload starts 66/70/78 or 64, 128 bytes each",
        limitations=["No custom instruction executed by host", "V1 bounded snapshot is ABI/data oracle, not hardware model",
                     "No cycle latency prediction, no FSM transition ID inference, no VCS/DVE execution",
                     "600s hard simulation limit; retain first timeout, no automatic retry or relaxed oracle"]))
    record = dict(format=oracle.FORMAT,status="HOST_PASS_ELF_STATIC_ONLY",vcs_launched=False,
                  returncode=0,host=host,elf=audit)
    oracle.save(out / "build-result.json",record)
    print(f"HOST/ELF PASS: {elf}; checks={oracle.HOST_CHECKS}; no VCS",flush=True)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output",required=True,type=Path)
    args = parser.parse_args()
    build(args.output.resolve())


if __name__ == "__main__":
    main()
