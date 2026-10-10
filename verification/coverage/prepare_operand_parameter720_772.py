"""Reuse exact historical native Branch evidence for parameter-false bodies only.

Offline preparation, never a DVE launcher or application receipt. No historical
ELF replay; the sealed formal population is consumed only for shape/raw binding.
"""
import argparse
import hashlib
import json
from pathlib import Path
import re
import sys

import audit_operand_parameter_dedup_716_v2 as old
import capture_operand_1144 as native
from closure_point_inventory import points

ROOT, OUT, BUILD, require = old.ROOT, old.OUT, old.shared.BUILD, old.require
BASE = OUT / "scalar-fpu-backpressure-offline-admitted-772-agent-20261007-01"
BASE_SHA = "28cc362f64c2c48e8a3b8a1dbf568903434464cc4dcea7e2dfad2aae282ca332"
CAPTURE = OUT / "operand-native-1144-capture-20261006-03-ready"
BOOK_SHA = "6d29e3ee19e7ac361d7a875b2acaacb6c9d17b4a976491538e9c6f5c918b761b"
CURRENT_ELS = tuple(OUT / name / "combined.el" for name in (
    "native-increment770-offline768-prepared-agent-20261007-02",
    "native-full771-padding-pack-prepared-agent-20261007-01"))


def sha(blob):
    return hashlib.sha256(blob).hexdigest()


class Reader:
    def __init__(self):
        self.pins = {}
        self.cache = {}

    def read(self, path, expected=None):
        path = Path(path).absolute()
        require(path.is_file() and not path.is_symlink(), "Missing/aliased input: " + str(path))
        if path not in self.cache:
            self.cache[path] = path.read_bytes()
            self.pins[str(path)] = sha(self.cache[path])
        require(expected is None or self.pins[str(path)] == expected, "Pin differs: " + str(path))
        return self.cache[path]

    def json(self, path, expected=None):
        return json.loads(self.read(path, expected))

    def unchanged(self):
        for path, expected in self.pins.items():
            digest = hashlib.sha256()
            with open(path, "rb") as stream:
                for chunk in iter(lambda: stream.read(1024 * 1024), b""):
                    digest.update(chunk)
            require(digest.hexdigest() == expected, "Input changed while preparing: " + path)


def source_contract(queue, stage, package):
    for name in old.PARAMS[:-1]:
        require(len(re.findall(r"parameter\s+logic\s+" + name + r"\s*=\s*1'b0\s*,", queue)) == 1,
                "False parameter default differs: " + name)
    require(re.search(r"FPUSupportNone\s*=\s*6'b000000", package) is not None,
            "FPUSupportNone differs")
    for function, bit in (("RVVB", 1), ("RVVBA", 0), ("RVVH", 3)):
        require(re.search(r"function automatic logic " + function +
                          r"\(fpu_support_e e\);\s*return e\[" + str(bit) + r"\];\s*endfunction", package),
                "FPU predicate differs: " + function)
    for name in old.NAMES:
        matches = re.findall(r"operand_queue\s*#\((.*?)\)\s*i_operand_queue_" + name + r"\s*\(", stage, re.S)
        require(len(matches) == 1, "Missing/ambiguous source instance: " + name)
        # The non-greedy match can start at an earlier instance; take the last opener.
        parameters = matches[0].rsplit("operand_queue #(", 1)[-1]
        require(re.search(r"\.FPUSupport\s*\(FPUSupportNone\s*\)", parameters), "FPU support override")
        require(not any(re.search(r"\." + p + r"\s*\(", parameters) for p in old.PARAMS[:-1]),
                "Support override in disabled queue")


def bind_scope(scope, definition, bitmap, inventory, qualified, records, signature, queue):
    require(re.fullmatch(r"ara_tb\.dut\.i_ara_soc\.i_system\.i_ara\.gen_lanes\[[0-3]\]"
                        r"\.i_lane\.i_operand_queues\.i_operand_queue_(st_mask_a|slide_addrgen_a|mask_m)", scope),
            "Unknown scope")
    old.parameters(signature)
    require(bitmap["width"] == 101 and definition.get("chksum") == "1417162425" and
            bitmap["checksum"] in (None, "1417162425"), "Wrong compiled Branch shape")
    targets = {p["raw_index"]: p for p in inventory["targets"]}
    protected = {p["raw_index"]: p for p in inventory["protected"]}
    require(len(targets) == len(inventory["targets"]) == 60 and
            len(protected) == len(inventory["protected"]) == 41 and
            not targets.keys() & protected.keys() and targets.keys() | protected.keys() == set(range(101)),
            "Incomplete/duplicate target-protection partition")
    result, complement = [], []
    bits = int(bitmap["bits"], 16)
    require(bits.bit_length() <= 101, "Bitmap outside shape")
    for point in points("branch", definition, 101):
        index = point["raw_index"]
        prior = targets.get(index, protected.get(index))
        require(prior["selector"] == point["native_id"] + "," + point["vector"] and
                prior["spec_checksum"] == point["attributes"]["chksum"], "Selector/checksum drift")
        proof = old.guards(point)
        hit = bool(bits & (1 << (100 - index)))
        row = dict(scope=scope, raw_index=index, selector=prior["selector"], hit772=hit, compiled=point)
        if not proof:
            require(index in protected, "Old target lacks constant-false TRUE demand")
            complement.append(row)
            continue
        require(index in targets and not hit, "New target or hit contradicts false parameter")
        key = scope + "|Branch " + point["native_id"] + " (" + point["vector"] + ")"
        require(key in qualified and key in records, "Missing historical native owner")
        q, n = qualified[key], records[key]
        require(q["raw_index"] == index and q["spec_checksum"] == prior["spec_checksum"] and
                q["vector"] == point["native_vector"]["vector"] and
                n["directive"] == q["native"]["native_directive"] and
                n["signature"] == q["native"]["native_signature"] and
                n["checksum"] == q["checksum"] == q["native"]["checksum"] and
                n["spec_checksum"] == q["spec_checksum"] and n["expression"] == q["expression"] and
                n["annotation"] == native.ANNOTATION, "Historical native signature differs")
        source_proof = q["proof"]
        require({(p["expression"], p["expression_index"]) for p in proof} ==
                {(p["expression"], p["expression_index"]) for p in source_proof}, "Guard proof drift")
        for p in source_proof:
            g = p["source_guard"]
            start, end = g["start"], g["end"]
            require(start[0] == end[0] and p["constant_value"] == 0 and p["demanded_value"] == "1" and
                    queue.splitlines()[start[0]-1][start[1]-1:end[1]] == g["text"],
                    "Source guard span/value differs")
        # Copy a genuine saved directive, never synthesize a native vector ID/signature.
        saved = native.parse_native(q["native"]["raw"].encode("ascii"))
        require(saved == {key: n}, "Saved native block differs from real export")
        row.update(native=n, source_proof=source_proof, native_raw=q["native"]["raw"])
        result.append(row)
    require(len(result) == 60 and len(complement) == 41, "Wrong scope population")
    return result, complement


def evidence():
    r = Reader()
    manifest = r.json(BASE / "admission-manifest.json", BASE_SHA)
    require(manifest["schema"] == "SCALAR_FPU_BACKPRESSURE_HISTORICAL772_ADMISSION_V1" and
            manifest["coverage_admitted"] is True and manifest["output"] == str(BASE), "Wrong formal772")
    before = r.json(BASE / "combined-bits.json", manifest["output_pins"][str(BASE / "combined-bits.json")])
    membership = r.read(BASE / "combined-inputs.txt", manifest["output_pins"][str(BASE / "combined-inputs.txt")])
    require(len(before["tests"]) == len(set(before["tests"])) == 772 and
            membership.decode().splitlines() == [str(BUILD / "sim/simv.vdb"), *before["tests"]], "Population mismatch")
    six = r.json(old.SIX, old.SIX_SHA)
    book = r.json(BUILD / "build-source-pins.json", BOOK_SHA)
    sources = [r.read(ROOT / name, book[str(ROOT / name)]).decode() for name in (
        "hardware/src/lane/operand_queue.sv", "hardware/src/lane/operand_queues_stage.sv", "hardware/include/ara_pkg.sv")]
    source_contract(*sources)
    cap = r.json(CAPTURE / "config.json", six["pins"][str(CAPTURE / "config.json")])
    receipt = r.json(CAPTURE / "capture-result.json", six["pins"][str(CAPTURE / "capture-result.json")])
    require(receipt["status"] == "NATIVE_1144_CAPTURE_VERIFIED_NOT_APPLICATION_APPROVAL" and
            receipt["config_sha256"] == r.pins[str(CAPTURE / "config.json")] and
            receipt["captured_records"] == 1144 and receipt["final_reset"] is True, "Unqualified capture")
    for path, expected in receipt["files"].items():
        require(Path(path).is_relative_to(CAPTURE), "Unexpected capture file owner")
        r.read(path, expected)
    for path in (Path(native.__file__), Path(points.__code__.co_filename)):
        r.read(path, six["pins"][str(path)])
    r.read(Path(old.__file__))
    first, second = [native.parse_native(r.read(CAPTURE / name)) for name in ("first.el", "second.el")]
    native.bind_native(first, cap["expectations"], cap["pilot"])
    native.bind_native(second, cap["expectations"], cap["pilot"])
    require(first == second and len(first) == 1144, "Roundtrip differs")
    identity = None
    for stage in native.STAGES:
        identity = native.states(CAPTURE / ("states_%s.tsv" % stage), cap["plan"], stage, identity)
    for name in ("initial-empty.el", "reset-empty.el", "final-empty.el"):
        require(r.read(CAPTURE / name) == b"", "Reset exclusions remain")
    execution = r.json(CAPTURE / "execution.json")
    live = r.json(CAPTURE / "live-identity.json")
    require(execution["returncode"] == 0 and execution["launch_count"] == 1 and
            live["executable_verified"] is True and live["executable"] == cap["plan"]["tool_identity"]["executable"] and
            (live["launch_pid"], live["launch_starttime"]) ==
            (execution["launch_pid"], execution["launch_starttime"]), "Historical execution identity differs")
    log = r.read(CAPTURE / "DVEfiles/dve_gui.log").decode()
    require(log.splitlines().count("OP1144_CAPTURE_DONE_1144") == 1 and
            not re.search(r'OP1144_CAPTURE_FAILED|(?:^|\s)(Error|Fatal):|checksum.*mismatch', log, re.I),
            "Historical capture failed")
    for stage in native.STAGES:
        require(log.splitlines().count("OP1144_AUDIT %s 3636" % stage) == 1, "Missing stage marker")
    for name, field in (("integrity-before.json", "checked"), ("integrity-after.json", "unchanged")):
        require(r.json(CAPTURE / name) == {field: True, "pins": cap["pins"],
                "membership": cap["plan"]["input_membership"]}, "Historical integrity receipt differs")
    canonical = {}
    for path in CURRENT_ELS:
        data = r.read(path)
        require(re.search(rb"(?m)^Branch\s", data) is None, "Current canonical EL has Branch; re-audit overlap")
        canonical[str(path)] = dict(sha256=r.pins[str(path)], branch_directives=0)
    design = old.shared.shared.Design(BUILD / "sim/simv.vdb")
    for relative, expected in before["design"].items():
        r.read(design.db / relative, expected)
        r.read(design.db / relative, cap["pins"][str(design.db / relative)])
    for relative in ("shape/tgl.verilog.shape.xml", "shape/branch.verilog.info.xml",
                     "shape/tgl.verilog.info.xml", "auxiliary/verilog.sourceinfo.xml"):
        r.read(design.db / relative, cap["pins"][str(design.db / relative)])
    qualified = {q["scope"] + "|" + q["point"]: q for q in six["groups"]["operand"]["qualified"]}
    require(len(qualified) == 1144, "Duplicate qualified owner")
    targets, protected, scopes = [], [], {}
    for lane in range(4):
        for name in old.NAMES:
            scope = "ara_tb.dut.i_ara_soc.i_system.i_ara.gen_lanes[%d].i_lane.i_operand_queues.i_operand_queue_%s" % (lane, name)
            owner = design.source(scope)
            require(owner["resolved_path"] == str(ROOT / "hardware/src/lane/operand_queue.sv"), "Source owner drift")
            signature = design.definition(scope, "tgl").get("name")
            t, p = bind_scope(scope, design.definition(scope, "branch"), before["metrics"]["branch"][scope],
                              six["groups"]["operand"]["plan"]["scopes"][scope], qualified, first, signature, sources[0])
            require(all(x["native"]["checksum"][0] == owner["definition_checksum"] for x in t),
                    "Compiled module/native checksum differs")
            targets.extend(t)
            protected.extend(p)
            scopes[scope] = dict(source=owner, parameters=old.parameters(signature), compiled_signature=signature,
                                 targets=60, protected=41, protected_hits=sum(x["hit772"] for x in p))
    require(len(targets) == 720 and len(protected) == 492 and len(scopes) == 12, "Wrong scoped population")
    candidate = "".join(t["native_raw"] for t in targets).encode("ascii")
    require(len(native.parse_native(candidate)) == 720, "Candidate export population differs")
    for path in (Path(__file__), Path(__file__).with_name("test_prepare_operand_parameter720_772.py")):
        r.read(path)
    for module in tuple(sys.modules.values()):
        path = getattr(module, "__file__", None)
        if path and str(ROOT / "verification") in str(path) and path.endswith(".py"):
            r.read(Path(path).resolve())
    r.unchanged()
    return dict(schema="OPERAND_PARAMETER720_RAW772_NATIVE_REUSE_PREPARATION_V1",
                status="EXACT720_HISTORICAL_NATIVE_REUSE_ELIGIBLE_NOT_APPLIED", formal_tests=772,
                pins=r.pins, scopes=scopes, targets=targets, protected=protected,
                historical_native=dict(directory=str(CAPTURE), records=1144, protected=2492,
                                       five_stages_replayed=True, first_second_exact=True, three_empty=True),
                canonical_EL_observation=canonical, new_DVE_run=False, application_approval=False,
                other_707_targets_included=False, excluded_metrics=["Branch"],
                diagnostic_expected_branch_denominator_reduction=720,
                diagnostic_expected_branch_hit_numerator_change=0,
                official_denominator_verified=False, official_percentage=None,
                historical_PASS_only=True, new_RTL_signoff=False), candidate


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    out = args.output.absolute()
    require(out.parent == OUT and out.resolve() == out and not out.exists(), "Fresh direct output required")
    audit, candidate = evidence()
    out.mkdir()
    (out / "candidate720.el").write_bytes(candidate)
    audit["output_pins"] = {str(out / "candidate720.el"): sha(candidate)}
    blob = (json.dumps(audit, indent=2, sort_keys=True) + "\n").encode()
    (out / "audit.json").write_bytes(blob)
    print(json.dumps(dict(output=str(out), seal=sha(blob), candidate_sha256=sha(candidate),
                          targets=720, protected=492, status=audit["status"])))


if __name__ == "__main__":
    main()
