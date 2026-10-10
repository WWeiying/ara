#!/usr/bin/env python3
"""Create new checked-selection evidence and dry precheck; never run a simulator."""
import copy
import json
from pathlib import Path
import sys

sys.dont_write_bytecode = True
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "coverage"))
import coverage_evidence as evidence
import gap37_csr_admission as admission


def save(filename, value):
    with filename.open("x") as stream:
        json.dump(value, stream, indent=2)
        stream.write("\n")


def create(directory):
    """Generate into a NEW directory; return a selection without touching draft."""
    directory = Path(directory).resolve()
    directory.mkdir(exist_ok=False)
    proof = evidence.Evidence()
    original_sources, record, stub = admission.frozen_inputs(proof)
    validator = admission.load_validator(proof, original_sources)
    validated = validator.validate_log(admission.NAME, admission.LOG.read_text(), stub)
    admission.require(all(record.get(k) == v for k, v in validated.items()), "strict source replay differs")
    sources = dict(original_sources)
    for filename in admission.OWN_SOURCES:
        pinned = proof.pin(filename)
        sources[str(pinned)] = proof.files[str(pinned)]
    for filename in (admission.OUT / "finalization.json", admission.OUT / "analysis.md",
                     admission.BUILD / "gap37_csr_counters.spike.log", admission.BUILD / "failure.json"):
        proof.pin(filename)
    final = proof.read(admission.OUT / "finalization.json")
    proof.pin(admission.BUILD / "gap37_csr_counters.spike.log", final["counter_log_sha256"])
    source_manifest = directory / "source-hashes.json"
    record_path = directory / "admission.json"
    save(source_manifest, sources)
    binding = dict(format=admission.FORMAT, name=admission.TEST, status="SPIKE_PASS_ONLY",
        returncode=0, vcs_launched=False, binary=str(admission.ELF), elf_sha256=record["elf_sha256"],
        log_sha256=record["log_sha256"], original_record=str(admission.RECORD),
        source_hashes=sources, files=dict(proof.files), validated=validated,
        scope="New admission metadata only; original compiler, stimuli, ELFs and rejected counter evidence unchanged")
    save(record_path, binding)
    selection = copy.deepcopy(proof.read(admission.ORIGINAL_SELECTION))
    admission.require(len(selection["cases"]) == 1 and selection["cases"][0]["name"] == admission.TEST,
                      "original selection differs")
    item = selection["cases"][0]
    item.update(sources=sorted(sources), source_hashes=sources,
        evidence=sorted([*binding["files"], str(source_manifest), str(record_path)]),
        precheck=dict(format=admission.FORMAT, record=str(record_path),
            record_sha256=admission.hashlib.sha256(record_path.read_bytes()).hexdigest(),
            source_hashes=str(source_manifest),
            source_hashes_sha256=admission.hashlib.sha256(source_manifest.read_bytes()).hexdigest(),
            log=str(admission.LOG)),
        runtime_contract="gap37-csr-uart-generic-trace-v1")
    selection.update(status="CHECKED_SELECTION_NOT_LAUNCHED",
        admission="Use gap37_csr_admission.handles/precheck/runtime_proof. Parent may replace ONLY top-level baseline/baseline_bits and compose other independently admitted cases.")
    return selection


def main():
    directory = admission.OUT / "admission-01"
    selection_path = admission.OUT / "selection-checked.json"
    admission.require(not selection_path.exists(), "checked selection already exists")
    selection = create(directory)
    item = selection["cases"][0]
    proof = evidence.Evidence()
    checked = admission.precheck(item, proof)
    try:
        evidence.precheck(item, evidence.Evidence())
    except ValueError as exc:
        legacy_rejection = str(exc)
    else:
        raise ValueError("Legacy precheck unexpectedly admitted the new format")
    save(selection_path, selection)
    save(directory / "precheck-dry.json", dict(status="PASS", result=checked,
        legacy_format_rejection=legacy_rejection, checked_files=proof.files,
        selection=str(selection_path), selection_sha256=admission.hashlib.sha256(selection_path.read_bytes()).hexdigest(),
        simulations_started=False, scope="Precheck only; no baseline prepare, runner launch, Spike or VCS execution"))
    print("Checked selection:", selection_path)
    print("PASS: strict Spike evidence replay;", len(proof.files), "pinned inputs; no simulation")


if __name__ == "__main__":
    main()
