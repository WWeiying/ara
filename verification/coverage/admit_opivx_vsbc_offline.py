"""Fresh historical718 from sealed717 plus strict VSBC; no EDA or RTL edits."""
import argparse
import hashlib
import json
from pathlib import Path

import collect_opivx_vsbc_strict as c
from inventory_operand_debug import Design, points
from audit_readonly import xml

life, bitmap, require = c.life, c.bitmap, c.require
ROOT, OUT = c.ROOT, c.OUT
CANDIDATE = OUT / "opivx-vsbc-vd0-strict-candidate-717-20261006-01"
CANDIDATE_SEAL = "b7a991e6d1f6fdb5f850d012b201322d8dfadbf4da6cb21b19f885898cea4c53"
BASE_SEALS = {
    "status.json": "896a1090914f54eb50013fb6a4c85cf39a456452a1b5e334ba8a6a665b51c203",
    "combined-bits.json": "facf291c2f34060d9dba42d295d63bcc6ff61373308697f0b523e36861bb4382",
    "combined-inputs.txt": "8de122437e16494d7ea490c98578783e89470b8b3956b875192592ec099d6ce2",
    "evidence-pins.json": "f676292e4aedbc89c2b6681ec350f0ef1fd1bb3033a3169a5172ed965808d42d",
    "admission-manifest.json": "82cd5f277d934c7b2435bfff3e2af1d4dd64cdea6435baba67b72749be183b62",
}
DELTA = dict(line=1, cond=1, branch=1, fsm=0)
SCOPE = c.runner.SCOPE
AUTHORIZATION = dict(source="PARENT_AGENT_AUTHORIZATION_WITHIN_USER_GOAL",
                     parent_verification_source="PARENT_AGENT_INDEPENDENT_EXECUTION",
                     completed_parent_checks=["31tests_PASS_no_skip", "strict_status_seal_PASS"],
                     parent_191_pin_completion_not_asserted=True)


def bound(path, expected):
    path = Path(path)
    require(path.is_absolute() and path.resolve() == path and not path.is_symlink(), "Aliased evidence")
    raw = path.read_bytes()
    require(hashlib.sha256(raw).hexdigest() == expected, "Sealed evidence changed: " + str(path))
    return raw


def population(before, single, proposed):
    new = str(c.RUN / "code.vdb")
    require(len(before["tests"]) == len(set(before["tests"])) == 717 and single["tests"] == [new],
            "Wrong exact717/single population")
    require(not any("gap101-illegal-segment-store-old-image" in p or
                    "/results/gap71_qbs_fault/" in p for p in before["tests"] + single["tests"]),
            "Historical FAIL mixed")
    union = bitmap.combine(before, single)
    require(union == proposed and union["tests"] == before["tests"] + [new] and
            len(union["tests"]) == len(set(union["tests"])) == 718, "Not exact717 prefix plus one")
    delta = bitmap.delta(before, union)
    require(delta["metrics"] == DELTA and sum(delta["metrics"].values()) > 0, "Unexpected/nonpositive raw delta")
    return union, delta


def elf_unique(elf, expected, base_pins):
    require(str(elf).endswith(".elf") and len(expected) == 64, "Invalid candidate ELF identity")
    require(not any(p.endswith(".elf") and h == expected for p, h in base_pins.items()), "Duplicate admitted ELF")
    return dict(elf=str(elf), sha256=expected, baseline_elf_pins=sum(p.endswith(".elf") for p in base_pins),
                duplicate_vdb=False, duplicate_elf=False)


def coverage_identity(single):
    design = Design(c.DESIGN)
    proofs = []
    expected = [("branch", 968, 1215, "1558979345", "25", "161", "3771491581"),
                ("line", 502, 1718, "1316526434", "494", "", "2568828943"),
                ("cond", 249, 1140, "1370170966", "103", "1", "3836970433")]
    for metric, index, width, checksum, ident, vector, check in expected:
        row = single["metrics"][metric][SCOPE]
        require((row["width"], row["checksum"]) == (width, checksum), "Compiled coverage shape differs")
        if metric == "cond":
            defs = [n for n in xml(design.db / "shape/cond.verilog.shape.xml").findall("conddef")
                    if n.get("id") == design.hierarchy[SCOPE].get("id") and n.get("chksum") == checksum]
            require(len(defs) == 1, "Ambiguous native condition definition")
            definition = defs[0]
        else:
            definition = design.definition(SCOPE, metric)
        p = next(p for p in points(metric, definition, width) if p["raw_index"] == index)
        require(p["native_id"] == ident and p["vector"] == vector and
                p["attributes"]["chksum"] == check and p["file_id"] == "547", "Compiled native identity differs")
        require(int(row["bits"], 16) & (1 << (width - 1 - index)), "Native target not hit")
        if metric != "branch": require(p["line"] == "2123", "Wrong source location")
        if metric == "branch":
            require(p["native_vector"]["id"] == "161", "Branch vector identity differs")
            expr = next(e for e in p["expressions"] if e["id"] == "2123")
            require(expr["exprstr"] == "(insn.varith_type.rd == 5'b0)" and
                    p["native_vector"]["vector"][-int(expr["index"])] == "1", "Wrong branch predicate")
        item = dict(metric=metric, scope=SCOPE, width=width, checksum=checksum,
                    raw_index=index, compiled_id=ident, vector=vector, file_id="547",
                    source_condition_line="2123", attributes=p["attributes"])
        if metric == "branch": item["compiled_vector"] = p["native_vector"]
        if metric == "cond": item.update(expression=p["expression"], truth_table=p["truth_table"])
        proofs.append(item)
    return dict(status="FROZEN_COMPILED_XML_IDENTITIES_VERIFIED", points=proofs,
                new_DVE_qualification=False, raw_indices_are_DVE_selectors=False)


def evaluate():
    state = json.loads(bound(CANDIDATE / "status.json", CANDIDATE_SEAL))
    require(state["status"] == "OPIVX_VSBC_STRICT_CANDIDATE_VERIFIED_NOT_ADMITTED" and
            state["coverage_admitted"] is False and state["new_admitted"] == 0 and
            state["baseline_tests"] == 717 and state["candidate_tests"] == 1 and state["raw_delta"] == DELTA,
            "Candidate not exact strict PASS")
    base_raw = {n: bound(c.BASE / n, h) for n, h in BASE_SEALS.items()}
    base_status = json.loads(base_raw["status.json"])
    require(base_status["status"] == "PASS_RAW_UNION_HISTORICAL_ONLY" and
            base_status["aggregate_passed"] == 717, "Wrong717 baseline status")
    seals = {str(c.BASE / n): h for n, h in BASE_SEALS.items()}
    seals[str(CANDIDATE / "status.json")] = CANDIDATE_SEAL
    base_pins = json.loads(base_raw["evidence-pins.json"])
    pins = life.merge_pins(seals, base_pins)
    pins = life.merge_pins(pins, state["pins"])
    helper_paths = [Path(__file__).resolve(), Path(__file__).with_name("test_admit_opivx_vsbc_offline.py"),
                    ROOT / "verification/coverage/inventory_operand_debug.py",
                    ROOT / "verification/coverage/reviewed_20261004/audit_readonly.py",
                    ROOT / "verification/coverage/closure_point_inventory.py"]
    pins = life.merge_pins(pins, {str(p): life.digest(p) for p in helper_paths})
    life.check(pins)
    def candidate(name):
        path = CANDIDATE / name
        require(str(path) in state["pins"], "Unsealed candidate product: " + name)
        return json.loads(bound(path, state["pins"][str(path)]))
    pre = life.read_bound(c.runner.PRE / "preflight-manifest.json", c.PRE_SEAL); c.runner.validate(pre)
    identity = elf_unique(pre["input_elf"], pre["pins"][pre["input_elf"]], base_pins)
    reference = c.software.parse_spike_commits(c.runner.PRE / "spike.trace")
    counts = c.reference_counts(reference, pre["symbols"])
    c.scalar_exact(candidate("scalar-comparison.json"), counts)
    control = candidate("lifecycle.json")
    c.vector_exact(candidate("vector-comparison.json"), control["exception_arch_seq"], reference)
    rows = c.read_csv((c.RUN / "commit_trace.csv").read_bytes(), c.COMMIT_FIELDS)
    vectors = c.read_csv((c.RUN / "vector_trace.csv").read_bytes(), c.VECTOR_FIELDS)
    require(c.lifecycle(rows, vectors, pre["symbols"]) == control, "Actual lifecycle differs")
    require(c.observed(rows, pre["symbols"]) == candidate("observed-signatures.json"), "Actual signatures differ")
    trap = c.tracer_exact((c.RUN / "trace_hart_0.log").read_text(), rows, pre["symbols"])
    trap["tracer_tail"] = [list(r) for r in trap["tracer_tail"]]
    require(trap == candidate("trap-proof.json"), "Actual exception trace differs")
    before = json.loads(base_raw["combined-bits.json"]); single = candidate("single-raw-bits.json")
    require(base_raw["combined-inputs.txt"].decode().splitlines() == [str(c.DESIGN), *before["tests"]],
            "717 input order differs")
    require(bound(CANDIDATE / "diagnostic-inputs.txt", state["pins"][str(CANDIDATE / "diagnostic-inputs.txt")]).decode().splitlines() ==
            [str(c.DESIGN), str(c.RUN / "code.vdb")], "Candidate VDB identity differs")
    union, delta = population(before, single, candidate("raw-union.proposed.json"))
    require(delta == candidate("raw-bitmap-delta.json") and
            c.target_hits(before, single, pre["targets"]) == candidate("target-hits.json"), "Sealed raw evidence differs")
    native = coverage_identity(single)
    pins = life.merge_pins(pins, union["input_hashes"])
    pins = life.merge_pins(pins, {str(c.DESIGN / "snps/coverage/db" / p): h for p, h in union["design"].items()})
    life.check(pins)
    outputs = {"combined-bits.json": union, "raw-bitmap-delta.json": delta, "evidence-pins.json": pins,
               "coverage-identity.json": native, "candidate-identity.json": identity}
    for name in ("scalar-comparison.json", "vector-comparison.json", "lifecycle.json",
                 "observed-signatures.json", "trap-proof.json", "target-hits.json"):
        outputs[name] = candidate(name)
    outputs["status.json"] = dict(status="PASS_RAW_UNION_HISTORICAL_ONLY", baseline=717,
        aggregate_passed=718, new_passed=1, raw_delta=DELTA, official_DVE_report=False,
        rtl_changed=False, new_RTL_signoff=False, simulations_started=False,
        inherited_717_full_oracle_readmission=False, sealed_strict_oracle_reused=True,
        actual_trace_and_signature_rechecked=True, frozen_compiled_coverage_identity_checked=True,
        native_DVE_qualification_not_claimed=True, original_717_order_preserved=True,
        historical_failures_not_added=True, no_duplicate_vdb_or_elf=True, full_scalar_matched=11444,
        full_scalar_gpr_writes=7219, full_scalar_memory_accesses=912, scalar_skips=0,
        vector_instructions=4, vector_bytes=388, checks=138, exceptions=1,
        illegal_backend_allocations=0, trap_vstart=1, post_mret_vstart=1,
        verified_input_pins=len(pins), authorization=AUTHORIZATION)
    return outputs, "\n".join([str(c.DESIGN), *union["tests"]]) + "\n"


def fingerprints(out, outputs, text):
    result = {str(out / n): hashlib.sha256((json.dumps(v, indent=2) + "\n").encode()).hexdigest()
              for n, v in outputs.items()}
    result[str(out / "combined-inputs.txt")] = hashlib.sha256(text.encode()).hexdigest()
    return result


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("mode", choices=("prepare", "admit", "verify"))
    p.add_argument("--output", required=True, type=Path)
    p.add_argument("--seal")
    a = p.parse_args(); out = a.output.absolute()
    require(out.parent == OUT and out.resolve() == out, "Direct independent output required")
    require((a.mode != "prepare") == bool(a.seal), "Admit/verify require fixed seal")
    record = out.with_name(out.name + ".prepared.json")
    if a.mode == "verify":
        manifest = json.loads(bound(out / "admission-manifest.json", a.seal))
        require(manifest["schema"] == "OPIVX_VSBC_HISTORICAL718_ADMISSION_V1" and
                manifest["output"] == str(out) and manifest["authorization"] == AUTHORIZATION, "Admission identity differs")
        for name, h in manifest["output_pins"].items():
            require(Path(name).parent == out, "Foreign formal product"); bound(name, h)
        outputs, text = evaluate()
        require(manifest["output_pins"] == fingerprints(out, outputs, text), "Formal products differ from exact reconstruction")
        print("VERIFY_PASS exact717prefix/new1/718/positive_delta/native_XML/full_oracle_NOT_DVE")
        return
    require(not out.exists(), "Fresh718 output required")
    outputs, text = evaluate()
    proposal = dict(schema="OPIVX_VSBC_HISTORICAL718_PREPARED_V1", output=str(out),
                    candidate=str(CANDIDATE), baseline=str(c.BASE), output_pins=fingerprints(out, outputs, text),
                    input_pins=outputs["evidence-pins.json"], authorization=AUTHORIZATION,
                    raw_delta=DELTA, aggregate_passed=718)
    if a.mode == "prepare":
        life.save(record, proposal)
        print(json.dumps(dict(prepared=str(record), seal=life.digest(record), pins=len(proposal["input_pins"]))))
        return
    require(json.loads(bound(record, a.seal)) == proposal, "Prepared718 contract differs")
    require(not out.exists(), "Output appeared during audit")
    out.mkdir()
    for name, value in outputs.items(): life.save(out / name, value)
    with (out / "combined-inputs.txt").open("x") as stream: stream.write(text)
    life.check(outputs["evidence-pins.json"])
    for name, h in proposal["output_pins"].items(): bound(name, h)
    life.save(out / "admission-manifest.json", dict(schema="OPIVX_VSBC_HISTORICAL718_ADMISSION_V1",
        output=str(out), candidate=str(CANDIDATE), baseline=str(c.BASE), authorization=AUTHORIZATION,
        prepared=str(record), prepared_seal=a.seal, output_pins=proposal["output_pins"]))
    print(json.dumps(dict(output=str(out), status=outputs["status.json"]["status"],
                          aggregate_passed=718, raw_delta=DELTA, seal=life.digest(out / "admission-manifest.json"))))


if __name__ == "__main__":
    main()
