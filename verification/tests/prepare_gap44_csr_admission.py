#!/usr/bin/env python3
"""Seal a new gap44 selection and replay precheck. No compiler or simulator."""
import argparse
import hashlib
import json
from pathlib import Path
import sys

sys.dont_write_bytecode = True
ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "verification/coverage"))
import coverage_evidence as evidence
import gap44_csr_admission as csr


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def save(path, value):
    with path.open("x") as stream:
        json.dump(value, stream, indent=2)
        stream.write("\n")


def create(directory):
    directory = Path(directory).resolve()
    csr.require(directory.is_relative_to(ROOT), "admission must stay in this worktree")
    directory.mkdir(exist_ok=False)
    proof = evidence.Evidence()
    sources, original, replay = csr.frozen_inputs(proof)
    sources = dict(sources)
    for path in csr.OWN_SOURCES:
        proof.pin(path)
        sources[str(path)] = proof.files[str(path)]
    record_path, manifest = directory / "admission.json", directory / "source-hashes.json"
    binding = dict(format=csr.FORMAT, name=csr.TEST, status="SPIKE_PASS_ONLY", returncode=0,
        vcs_launched=False, original_record=str(csr.RECORD), original_record_sha256=csr.RECORD_SHA256,
        binary=str(csr.ELF), elf_sha256=original["elf_sha256"], source_hashes=sources,
        validated=replay, hpm_dut_preservation_pending=True, files=dict(proof.files))
    save(manifest, sources)
    save(record_path, binding)
    item = dict(name=csr.TEST, binary=str(csr.ELF), binary_sha256=original["elf_sha256"], timeout_s=300,
        sources=sorted(sources), source_hashes=sources,
        evidence=sorted([*binding["files"], str(record_path), str(manifest)]),
        source_audit=str(csr.AUDIT), targets=["ara_tb.dut.i_ara_soc.i_system.i_ariane.csr_regfile_i"],
        runtime_contract=csr.oracle.RUNTIME_FORMAT,
        rationale="50 missing absent-H/RV64-high rejection vectors: M-only read/write with recovery and nonzero DUT HPM preservation.",
        predicted_missing_native_branches=[p["native"] for p in original["missing_branch_targets"]],
        precheck=dict(format=csr.FORMAT, record=str(record_path), record_sha256=digest(record_path),
            source_hashes=str(manifest), source_hashes_sha256=digest(manifest), log=str(csr.LOG)))
    audit = json.loads(csr.AUDIT.read_text())
    selection = dict(status="CHECKED_SELECTION_NOT_LAUNCHED", baseline=audit["baseline"],
        baseline_bits=str(Path(audit["baseline"]) / "combined-bits.json"), cases=[item],
        admission="Parent calls gap44_csr_admission.install_hooks() in every process; parent retains checked.SCRIPT ownership.",
        runtime_measured=False, vcs_launched=False)
    return selection


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    selection = create(args.output)
    directory = args.output.resolve()
    proof = evidence.Evidence()
    result = csr.precheck(selection["cases"][0], proof)
    path = directory / "selection.json"
    save(path, selection)
    save(directory / "precheck.json", dict(status="PASS", result=result, files=proof.files,
        selection_sha256=digest(path), vcs_launched=False, runtime_measured=False,
        json_roundtrip_equal=json.loads(json.dumps(result)) == result))
    save(directory / "seal.json", {str(p): digest(p) for p in sorted(directory.iterdir()) if p.is_file()})
    print(path)
    print(f"PASS: original sealed Spike proof replay; {len(proof.files)} pinned inputs; no VCS")


if __name__ == "__main__":
    main()
