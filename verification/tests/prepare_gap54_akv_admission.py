#!/usr/bin/env python3
"""Seal one software-prechecked case for composition; no batch preparation/launch."""
import argparse
from pathlib import Path
import sys

sys.dont_write_bytecode = True
ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0,str(ROOT / "verification/coverage"))
import gap54_akv_admission as admission
import gap54_akv_oracle as oracle
from coverage_evidence import Evidence


def prepare(out):
    oracle.require(out.is_relative_to(ROOT / "verification/out"), "integration output required")
    for name in ("evidence.json","selection.json","sealed-precheck.json","draft.json"):
        oracle.require(not (out / name).exists(), "refuse to replace sealed admission")
    record = oracle.read(out / "build-result.json")
    sources = oracle.read(out / "source-hashes.json")
    audit = oracle.read(out / "source-audit.json")
    files = dict(audit["input_hashes"])
    files.update({str(p):oracle.sha(p) for p in out.iterdir() if p.is_file()})
    files.update(oracle.read(out / "tool-hashes.json"))
    targets = oracle.read(out / "native-targets.json")
    path = out / "evidence.json"
    elf = out / (oracle.NAME+".elf")
    item = dict(name=oracle.TEST,binary=str(elf),binary_sha256=oracle.sha(elf),
        sources=sorted(sources),source_hashes=sources,source_audit=str(out / "source-audit.json"),
        evidence=sorted([*files,str(path)]),targets=sorted({p["scope"] for p in targets["points"]}),
        rationale="Plan A: legal V1 skew split-bank writes, V2 mismatch invalidation, V1 empty-context faults, aligned V2 recovery",
        timeout_s=600,precheck=dict(format=oracle.FORMAT),runtime_contract=oracle.RUNTIME_FORMAT)
    record.update(case=item,files=files)
    oracle.save(path,record)
    item = dict(item,precheck=dict(item["precheck"],record=str(path),record_sha256=oracle.sha(path)))
    draft = dict(baseline=str(oracle.BASE),baseline_bits=str(oracle.BASE / "combined-bits.json"),cases=[item])
    oracle.save(out / "draft.json",draft)
    proof = Evidence()
    result = admission.precheck(item,proof)
    seal = dict(status="PASS",vcs_launched=False,draft=str(out / "draft.json"),
                draft_sha256=oracle.sha(out / "draft.json"),case_sha256=oracle.canonical(item),
                result=result,checked_files=proof.files)
    oracle.save(out / "sealed-precheck.json",seal)
    selection = dict(draft,sealed_precheck=dict(path=str(out / "sealed-precheck.json"),
        sha256=oracle.sha(out / "sealed-precheck.json"),result=result))
    oracle.save(out / "selection.json",selection)
    # Re-read without normalization: parent composition must preserve this exact object.
    second = Evidence()
    replay = admission.precheck(oracle.read(out / "selection.json")["cases"][0],second)
    oracle.require(replay == result and second.files == proof.files, "sealed precheck replay differs")
    print(f"SEALED: {out / 'selection.json'}; 1 exact case; no batch prepare or VCS",flush=True)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--build",type=Path,required=True)
    prepare(parser.parse_args().build.resolve())
