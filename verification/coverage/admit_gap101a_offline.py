"""Admit only sealed GAP101A to historical715; no simulation or DVE report."""
import argparse
import csv
import hashlib
import io
import json
from pathlib import Path

import collect_gap101a_strict_v2 as collector

ROOT, OUT, require = collector.ROOT, collector.OUT, collector.require
life, bitmap = collector.runner.life, collector.bitmap
CANDIDATE = OUT / "gap101a-strict-candidate-715-20261006-02"
CANDIDATE_SEALS = dict(zip((
    "diagnostic-inputs.txt", "evidence-pins.json", "lifecycle.json", "observed-data.json",
    "raw-bitmap-delta.json", "raw-union.proposed.json", "scalar-comparison.json",
    "single-raw-bits.json", "status.json", "target-hits.json", "trap-ledger.json",
    "vector-comparison.json"), (
    "f8fef912f0de48f6287067288c9aa9916c5e4f0190ad19085eb6bee18d3d4e37",
    "a744376fc4d3e25505d04c4ca23ab47a14b2832a186626a56d29b23bfeea7467",
    "9f84eef2f81fe8b46910d817765587adeca99f52655294934ff0e76dcdafc22d",
    "0fa74337e3e81ab9bcc727b693bc8a7af5e1b13fdd9a821423b836150e3c0cb7",
    "225d30c2977064d22e80b293c4394819a810fc2182eb33c62f31ef64f6eaf3ff",
    "8701fda16631c38588941de54deddfd81440e779d7160c13741a053fa81a8189",
    "ecc26a476c08bff23ae686aac01608bbf8240f36454c2aabebb5b827741536fc",
    "4399d78558c09e520bba56248185aca01031c3665b7cc98182dd30b2241bacd3",
    "469a884543ce4001a9940dd9c036d65d933601c3b06a78205178d30af73b27d7",
    "9e6789902ae7498d5bf0a65135a13ba3ae0371a558635afc60cceee1c5dc49b0",
    "64171655de1ae52c8325ec5e0100028528b0187bac0772a76bbdfab9d45e2c36",
    "530cc5a9fb573f23e46d4da4aa156b51a4b28af5fcd87ad0abf3edd99a54d5e4")))
BASE_SEALS = dict(zip(("combined-bits.json", "status.json", "combined-inputs.txt", "evidence-pins.json"), (
    "6ee84ddb63d2a14004bf4288ad1c26f64ff6cc9227d77e3c05966c870880f286",
    "fbbc2479a3ce18985c1740d62105c6570fadf1cc78f9730f757d541397a60cbf",
    "e8a3d1a5b95b362c5c965a45692155f45a7441756859829a77e3abe15b734f33",
    "9b4a1e4ec05c1fac98343dd48cf0d66efe872986500537e3b058cabeeb355197")))
DELTA = dict(line=1, cond=1, branch=1, fsm=0)


def bound(path, expected):
    path = Path(path)
    require(path.is_absolute() and path.resolve() == path and not path.is_symlink(), "Aliased evidence")
    raw = path.read_bytes()
    require(hashlib.sha256(raw).hexdigest() == expected, "Sealed evidence changed: " + str(path))
    return raw


def population(before, single, proposed):
    new = str(collector.RUN / "code.vdb")
    require(len(before["tests"]) == len(set(before["tests"])) == 715 and single["tests"] == [new],
            "Wrong baseline/single population")
    require(not any("gap101-illegal-segment-store-old-image" in t for t in before["tests"] + single["tests"]),
            "Original GAP101 FAIL mixed")
    union = bitmap.combine(before, single)
    require(union == proposed and union["tests"] == before["tests"] + [new] and
            len(union["tests"]) == len(set(union["tests"])) == 716, "Not exact715 prefix plus single")
    change = bitmap.delta(before, union)
    require(change["metrics"] == DELTA, "Unexpected raw gain")
    return union, change


def tracer_json(text, rows, symbols):
    result = collector.tracer_exact(text, rows, symbols)
    result["tracer_tail"] = [list(row) for row in result["tracer_tail"]]
    return result


def evaluate():
    seals = {str(CANDIDATE / n): h for n, h in CANDIDATE_SEALS.items()}
    seals.update({str(collector.BASE / n): h for n, h in BASE_SEALS.items()})
    raw = {p: bound(p, h) for p, h in seals.items()}
    def candidate(name):
        return json.loads(raw[str(CANDIDATE / name)])
    state = candidate("status.json")
    require(state["status"] == "GAP101A_STRICT_V2_EXACT_SCALAR_CANDIDATE_NOT_ADMITTED" and
            state["new_admitted"] == 0 and state["coverage_admitted"] is False and
            state["scalar_exact_counts"] == collector.SCALAR_EXPECTED, "Candidate not strict v2")
    base_state = json.loads(raw[str(collector.BASE / "status.json")])
    require(base_state["status"] == "PASS_RAW_UNION_HISTORICAL_ONLY" and
            base_state["aggregate_passed"] == 715, "Wrong715 status")
    pins = life.merge_pins(seals, candidate("evidence-pins.json"))
    pins = life.merge_pins(pins, json.loads(raw[str(collector.BASE / "evidence-pins.json")]))
    for path in (Path(__file__).resolve(), Path(__file__).with_name("test_admit_gap101a_offline.py")):
        pins = life.merge_pins(pins, {str(path): life.digest(path)})
    life.check(pins)
    collector.scalar_exact(candidate("scalar-comparison.json"))
    rows = list(csv.DictReader(io.StringIO((collector.RUN / "commit_trace.csv").read_text())))
    vectors = list(csv.DictReader(io.StringIO((collector.RUN / "vector_trace.csv").read_text())))
    runtime = json.loads((collector.RUN / "manifest.json").read_text())
    symbols = runtime["preflight"]["symbols"]
    control = collector.lifecycle(rows, vectors)
    require(control == candidate("lifecycle.json"), "Actual lifecycle differs")
    require(collector.observed(rows, symbols) == candidate("observed-data.json"), "Actual observed data differs")
    require(tracer_json((collector.RUN / "trace_hart_0.log").read_text(), rows, symbols) ==
            candidate("trap-ledger.json"), "Actual trap trace differs")
    collector.vector_exact(candidate("vector-comparison.json"), control["exception_arch_seq"])
    before = json.loads(raw[str(collector.BASE / "combined-bits.json")])
    require(raw[str(collector.BASE / "combined-inputs.txt")].decode().splitlines() ==
            [str(collector.DESIGN), *before["tests"]], "715 input order differs")
    require(raw[str(CANDIDATE / "diagnostic-inputs.txt")].decode().splitlines() ==
            [str(collector.DESIGN), str(collector.RUN / "code.vdb")], "Single input identity differs")
    single = bitmap.collect(CANDIDATE / "diagnostic-inputs.txt")
    require(single == candidate("single-raw-bits.json"), "Actual single VDB differs")
    union, delta = population(before, single, candidate("raw-union.proposed.json"))
    require(delta == candidate("raw-bitmap-delta.json"), "Sealed delta differs")
    # Keep full inherited metric/design pins; do not replace expectations with observed hashes.
    pins = life.merge_pins(pins, union["input_hashes"])
    pins = life.merge_pins(pins, {str(collector.DESIGN / "snps/coverage/db" / p): h
                                  for p, h in union["design"].items()})
    life.check(pins)
    outputs = {"combined-bits.json": union, "raw-bitmap-delta.json": delta,
               "evidence-pins.json": pins, "scalar-comparison.json": candidate("scalar-comparison.json"),
               "vector-comparison.json": candidate("vector-comparison.json"),
               "observed-data.json": candidate("observed-data.json"), "lifecycle.json": control,
               "trap-ledger.json": candidate("trap-ledger.json"), "target-hits.json": candidate("target-hits.json")}
    outputs["status.json"] = dict(status="PASS_RAW_UNION_HISTORICAL_ONLY", baseline=715,
        aggregate_passed=716, new_passed=1, official_DVE_report=False, rtl_changed=False,
        new_RTL_signoff=False, simulations_started=False, inherited_715_full_oracle_readmission=False,
        sealed_strict_v2_oracle_reused=True, actual_trace_and_single_vdb_rechecked=True,
        original_gap101_fail_excluded=True, original_715_order_preserved=True, raw_delta=delta["metrics"],
        full_scalar_matched=13025, full_scalar_gpr_writes=6436, full_scalar_memory_accesses=1731,
        scalar_skips=0, scalar_unknown=False, vector_instructions=32, vector_bytes=4096,
        checks=539, exceptions=1, verified_input_pins=len(pins))
    return outputs, "\n".join([str(collector.DESIGN), *union["tests"]]) + "\n"


def main(argv=None):
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--output", type=Path, required=True)
    p.add_argument("--verify", action="store_true")
    p.add_argument("--seal")
    args = p.parse_args(argv)
    out = args.output.absolute()
    require(out.parent == OUT and out.resolve() == out, "Direct independent output required")
    if args.verify:
        require(args.seal is not None, "Verification requires external manifest seal")
        manifest = json.loads(bound(out / "admission-manifest.json", args.seal))
        require(manifest["schema"] == "GAP101A_HISTORICAL716_ADMISSION_V1" and
                manifest["output"] == str(out), "Wrong admission manifest")
        for path, expected in manifest["output_pins"].items():
            require(Path(path).parent == out, "Foreign output artifact")
            bound(path, expected)
        outputs, text = evaluate()
        require(set(manifest["output_pins"]) == {str(out / n) for n in [*outputs, "combined-inputs.txt"]},
                "Incomplete output seal")
        for name, value in outputs.items():
            require(json.loads((out / name).read_bytes()) == value, "Reconstructed output differs: " + name)
        require((out / "combined-inputs.txt").read_text() == text, "716 input list differs")
        print("GAP101A_HISTORICAL716_OFFLINE_REVERIFIED " + args.seal)
        return
    require(args.seal is None and not out.exists(), "Fresh output required; never overwrite candidate")
    outputs, text = evaluate()
    require(not out.exists(), "Output appeared during audit")
    out.mkdir()
    for name, value in outputs.items():
        life.save(out / name, value)
    with (out / "combined-inputs.txt").open("x") as stream:
        stream.write(text)
    life.check(outputs["evidence-pins.json"])
    life.save(out / "admission-manifest.json", dict(schema="GAP101A_HISTORICAL716_ADMISSION_V1",
        output=str(out), candidate=str(CANDIDATE), baseline=str(collector.BASE),
        output_pins={str(out / n): life.digest(out / n) for n in [*outputs, "combined-inputs.txt"]}))
    print(json.dumps(dict(output=str(out), status=outputs["status.json"]["status"],
                          seal=life.digest(out / "admission-manifest.json"))))


if __name__ == "__main__":
    main()
