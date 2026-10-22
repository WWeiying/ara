#!/usr/bin/env python3
"""Offline migration audit. No simulator, coverage tool, or frozen helper imports."""
import argparse
import csv
import gzip
import hashlib
import io
import json
from pathlib import Path
import re
import xml.etree.ElementTree as ET

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[2]
OUT = ROOT / "verification/out"
BUILD = OUT / "repaired-aligned-build-20260930-01"
PLAN = OUT / "repaired-aligned-600-20260930-01/plan.json"
REPORT = OUT / "gap35-control-current-20261004-01/combined-dve"
OLD_REPORT = OUT / "dve-waiver-reviewed-598-20260929-01"
OLD_BUILD = OUT / "fp16-repaired-coverage-20260928-02"
SYSTEM = "ara_tb.dut.i_ara_soc.i_system"
CORE = SYSTEM + ".i_ariane"
QUEUES = ("alu_a", "alu_b", "mfpu_a", "mfpu_b", "mfpu_c", "mask_b")
TIE_LINES = dict(zip(QUEUES, (82, 112, 144, 172, 200, 292)))
OBSERVER_REASONS = {
    "llm_perf_monitor": "Input-only performance counters; assertion remains active.",
    "vrf_perf_monitor": "Input-only bank request/conflict accounting; no DUT drive.",
    "ara_commit_monitor": "Input-only trace/scoreboard/watchdog; finish/fatal behavior remains active.",
    "ara_acc_contract_monitor": "Input-only bound protocol checker; assertions/errors remain active.",
    "ara_fault_vstart_probe": "Input-only bound pre/NBA trace; local bookkeeping and display only.",
    "cva6_rvfi_probes": "Output is verification RVFI packaging, routed to i_cva6_rvfi and trace monitor, not execution feedback.",
    "uvm_custom_install_verdi_recording": "Vendor UVM recording infrastructure; no product RTL descendant; recording remains active.",
}


def require(ok, message):
    if not ok:
        raise ValueError(message)


def sha(path):
    h = hashlib.sha256()
    with Path(path).open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def jread(path):
    return json.loads(Path(path).read_text())


def xml(path):
    data = Path(path).read_bytes()
    return ET.fromstring(gzip.decompress(data) if data[:2] == b"\x1f\x8b" else data)


def tree_digest(node):
    # Ignore serialization whitespace, but keep all semantic XML attributes/order.
    def obj(n):
        return [n.tag, dict(n.attrib), (n.text or "").strip(), [obj(c) for c in n]]
    return hashlib.sha256(json.dumps(obj(node), sort_keys=True).encode()).hexdigest()


def expected_points():
    result = set()
    for lane in range(4):
        for queue in QUEUES:
            scope = f"{SYSTEM}.i_ara.gen_lanes[{lane}].i_lane.i_operand_queues.i_operand_queue_{queue}"
            result.update((scope, p) for p in ("Block 7", "Block 172", "Toggle flush_i"))
            if queue in ("alu_a", "alu_b"):
                result.update((scope, p) for p in ("Branch 2 (0)", "Branch 7 (0)"))
    result.update((s, "Toggle " + n) for s in (CORE, CORE + ".csr_regfile_i")
                  for n in ("ipi_i", "time_irq_i", "debug_req_i"))
    return result


def native_entries(text):
    """Strictly retain saved DVE signatures, not just the old helper's point IDs."""
    result, checksum, scope, directives = [], None, None, []
    def finish():
        if scope is not None:
            for point, directive, point_checksum, signature in directives or [("INSTANCE", None, None, None)]:
                result.append(dict(scope=scope, point=point, checksum=checksum,
                                   native_directive=directive, nativepointchecksum=point_checksum,
                                   native_signature=signature))
    for raw in text.splitlines():
        line = raw.strip()
        if not line or line.startswith(("//", "ANNOTATION:")):
            continue
        if line.startswith("CHECKSUM:"):
            finish()
            scope, directives = None, []
            match = re.fullmatch(r'CHECKSUM:\s*"([0-9 ]+)"', line)
            require(match is not None, "Malformed checksum")
            checksum = match[1].split()
        elif line.startswith("INSTANCE:"):
            require(scope is None and checksum is not None, "Ambiguous native header")
            scope = line.split(":", 1)[1].strip()
            require(not any(c in scope for c in "{}\\\n\r*?"), "Unsafe native path")
        else:
            require(scope is not None, "Directive outside instance")
            b = re.fullmatch(r'Block (\d+) "(\d+)" "([^"]*)"', line)
            v = re.fullmatch(r'Branch (\d+) "(\d+)" "([^"]*)" \((\d+)\) "([^"]*)"', line)
            t = re.fullmatch(r'Toggle (\w+) "((?:logic|net) \w+)"', line)
            require(b or v or t, "Unreviewed native syntax: " + line)
            if b:
                directives.append(("Block " + b[1], line, b[2], b[3]))
            elif v:
                directives.append((f"Branch {v[1]} ({v[4]})", line, v[2], v[5]))
            else:
                directives.append(("Toggle " + t[1], line, None, t[2]))
    finish()
    keys = [(p["scope"], p["point"]) for p in result]
    require(len(keys) == len(set(keys)), "Duplicate native objects")
    return result


def branch_index(definition, spec_id, vector_id):
    base = 0
    for spec in definition.iter("branch_spec"):
        vectors = spec.findall("branch_vector")
        if spec.get("id") == spec_id:
            positions = [i for i, v in enumerate(vectors) if v.get("id") == vector_id]
            require(len(positions) == 1, "Ambiguous branch vector")
            return base + len(vectors) - 1 - positions[0], base, len(vectors), spec
        base += len(vectors)
    raise ValueError("Missing branch spec")


def scalar_toggle_offset(definition, signal):
    offset = 0
    for node in definition.find("tglshape"):
        if node.get("name") == signal:
            require(node.tag == "node" and node.get("portnode") == "2"
                    and node.get("excluded") == "0", "Not a retained scalar input")
            return offset, node
        if node.tag == "node":
            width = 1
        elif node.tag == "vectornode":
            width = abs(int(node.get("left")) - int(node.get("right"))) + 1
        else:
            # All 30 reviewed scalar ports precede any array. Do not guess packing.
            raise ValueError("Unreviewed toggle packing before scalar port")
        offset += 2 * width
    raise ValueError("Missing scalar toggle")


class Design:
    def __init__(self, vdb):
        self.db = Path(vdb) / "snps/coverage/db"
        self.design = xml(self.db / "design/verilog.design.xml")
        self.sources = {n.get("id"): dict(n.attrib) for n in
                        xml(self.db / "auxiliary/verilog.sourceinfo.xml").iter("fileinfo")}
        nodes = {n.get("id"): (n, d) for d in self.design.findall("srcdef") for n in d.findall("srcinst")}
        def path(key):
            n, _ = nodes[key]
            return (path(n.get("pid")) + "." if n.get("pid") in nodes else "") + n.get("name")
        self.hierarchy = {path(k): d for k, (_, d) in nodes.items()}
        self.shapes, self.info = {}, {}
        for metric in ("line", "branch", "tgl"):
            self.shapes[metric] = xml(self.db / f"shape/{metric}.verilog.shape.xml")
            self.info[metric] = {n.get("name"): n.get("chksum") for n in
                                 xml(self.db / f"shape/{metric}.verilog.info.xml").iter("instance_data")}

    def definition(self, scope, metric):
        module = self.hierarchy[scope]
        tag = dict(line="linedef", branch="branch_def", tgl="tgldef")[metric]
        checksum = self.info[metric].get(scope)
        candidates = [n for n in self.shapes[metric].findall(tag)
                      if (n.get("chksum") == checksum if checksum else n.get("id") == module.get("id"))
                      and (n.get("id") == module.get("id") if n.get("id") is not None
                           else n.get("name", "").split(" (")[0] == module.get("name"))]
        require(len(candidates) == 1, f"Ambiguous {metric} definition: {scope}")
        return candidates[0]

    def source(self, scope):
        module = self.hierarchy[scope]
        loc = module.find("srclocmult")
        source = self.sources[loc.get("file_id")]
        return dict(module=module.get("name"), definition_checksum=module.get("chksum"),
                    file_id=loc.get("file_id"), source_path=source["name"],
                    resolved_path=str(Path(source["name"]).resolve()),
                    definition_lines=[loc.get("start"), loc.get("end")])

    def point(self, item):
        scope, name = item["scope"], item["point"]
        metric = {"Block": "line", "Branch": "branch", "Toggle": "tgl"}[name.split()[0]]
        definition = self.definition(scope, metric)
        result = self.source(scope)
        result.update(metric=metric, metric_checksum=definition.get("chksum"),
                      complete_definition_sha256=tree_digest(definition))
        require(item["checksum"] == [result["definition_checksum"], result["metric_checksum"]],
                "Native header checksum mismatch: " + scope + " " + name)
        if metric == "line":
            matches = [n for n in definition.iter("linebb") if n.get("id") == name.split()[1]]
            require(len(matches) == 1, "Ambiguous line block")
            node = matches[0]
            result.update(xml_attributes=dict(node.attrib), statements=[dict(n.attrib) for n in node],
                          raw_indices=[int(node.get("index"))])
        elif metric == "branch":
            index, base, width, spec = branch_index(definition, name.split()[1], "0")
            result.update(xml_attributes=dict(spec.attrib),
                          expressions=[dict(n.attrib) for n in spec.findall("branch_expr")],
                          vectors=[dict(n.attrib) for n in spec.findall("branch_vector")],
                          raw_indices=[index], spec_base=base, spec_width=width,
                          mapping="reverse_within_each_branch_spec")
            require(spec.get("chksum") == item["nativepointchecksum"], "Branch checksum mismatch")
        else:
            offset, node = scalar_toggle_offset(definition, name.split()[1])
            result.update(xml_attributes=dict(node.attrib), raw_indices=[offset, offset + 1],
                          elaborated_parameter_shape=dict(definition.attrib),
                          mapping="two adjacent transition flags per scalar; no direction inference needed for 00")
        return result


def verify_hashes(pins):
    rows = []
    for path, expected in sorted(pins.items()):
        actual = sha(path)
        require(actual == expected, "Hash drift: " + path)
        rows.append(dict(path=path, sha256=actual))
    return rows


def merge_selected(inputs, points, ledger_hashes):
    wanted = {m: {} for m in ("line", "branch", "tgl")}
    for p in points:
        c = p["current"]
        wanted[c["metric"]][p["scope"]] = c["metric_checksum"]
    merged, evidence = {}, []
    for i, vdb in enumerate(inputs):
        for metric, scopes in wanted.items():
            paths = list(vdb.glob(f"snps/coverage/db/testdata/*/{metric}.verilog.data.xml"))
            require(len(paths) == 1, f"Expected one {metric} testdata: {vdb}")
            data = paths[0].read_bytes()
            digest = hashlib.sha256(data).hexdigest()
            require(ledger_hashes.get(str(paths[0])) == digest, "Raw data differs from PASS ledger")
            stream = io.BytesIO(gzip.decompress(data) if data[:2] == b"\x1f\x8b" else data)
            seen = set()
            for _, node in ET.iterparse(stream, events=("end",)):
                if node.tag == "instance_data" and node.get("name") in scopes:
                    scope = node.get("name")
                    require(scope not in seen, "Duplicate raw instance")
                    seen.add(scope)
                    checksum, bits = node.get("chksum"), node.get("value")
                    require(checksum in (None, scopes[scope]), "Raw checksum mismatch")
                    require(bits and set(bits) <= {"0", "1"}, "Malformed raw bits")
                    key = (metric, scope)
                    row = merged.setdefault(key, dict(width=len(bits), bits=0, samples=0, inherited_checksum_samples=0))
                    require(row["width"] == len(bits), "Raw width drift")
                    row["bits"] |= int(bits, 2)
                    row["samples"] += 1
                    row["inherited_checksum_samples"] += checksum is None
                node.clear()
            require(seen == set(scopes), f"Missing reviewed raw instances in {paths[0]}")
            evidence.append(dict(path=str(paths[0]), sha256=digest))
        if (i + 1) % 100 == 0:
            print(f"Read-only testdata audit: {i + 1}/{len(inputs)}", flush=True)
    for p in points:
        current = p["current"]
        raw = merged[current["metric"], p["scope"]]
        bits = format(raw["bits"], f"0{raw['width']}b")
        indices = current["raw_indices"]
        require(max(indices) < len(bits), "Point exceeds raw vector")
        value = "".join(bits[i] for i in indices)
        p["raw_625_state"] = dict(width=raw["width"], indices=indices, value=value,
                                  samples=raw["samples"], inherited_checksum_samples=raw["inherited_checksum_samples"])
        if current["metric"] == "branch":
            start, width = current["spec_base"], current["spec_width"]
            p["raw_625_state"]["spec_slice"] = bits[start:start + width]
            require(bits[start:start + width] == "10", "Tied-zero branch control witness differs")
            p["raw_625_state"]["forward_order_would_falsely_mark_true_hit"] = True
        require(set(value) == {"0"}, "Reviewed constant/unreachable point has a raw hit")
        p["decision"] = "REUSABLE_OFFLINE_NOT_APPLIED"
    return evidence


def make_policy(audit):
    return dict(schema_version=1, status="REVIEWED_OFFLINE_NOT_APPLIED",
                audit_sha256=hashlib.sha256((json.dumps(audit, indent=2) + "\n").encode()).hexdigest(),
                design_sha256=audit["identity"]["design_sha256"],
                guard="Revalidate audit.json input hashes and exact objects; never fingerprint-only approval",
                allowed_points=[{k: p[k] for k in ("scope", "point", "checksum", "native_directive",
                                "nativepointchecksum", "native_signature")} for p in audit["points"]],
                allowed_observers=[dict(scope=o["scope"], checksum=o["checksum"], recursive=1)
                                   for o in audit["observers"]],
                application=dict(applied=False, native_current_validation="NOT_RUN_USER_PROHIBITED",
                                 require_zero_checksum_mismatch=True, require_zero_need_review=True,
                                 require_zero_unmappable=True, require_exact_saved_exclusions=True,
                                 bypass_checks_allowed=False, adjusted_percentages=None))


def validate_policy(policy, audit):
    require(policy == make_policy(audit), "Policy differs from independently audited exact set/state")
    require({(p["scope"], p["point"]) for p in policy["allowed_points"]} == expected_points(),
            "Wrong policy point set")
    require(len(policy["allowed_points"]) == 94 and len(policy["allowed_observers"]) == 10,
            "Wrong policy cardinality")


def audit():
    plan, old_status = jread(PLAN), jread(OLD_REPORT / "waiver_status.json")
    inputs = [Path(p) for p in (REPORT / "inputs.txt").read_text().splitlines() if p.strip()]
    require(len(inputs) == 626 and len(set(inputs)) == 626, "Not the exact 625-test report")
    require(str(inputs[0]) == plan["design_vdb"], "Report/image mismatch")
    require(old_status["status"] == "APPLIED", "Old exclusions never accepted")
    frozen = verify_hashes({**plan["image"], **plan["wrapper_image"], **plan["design_files"]})
    verify_hashes({str(OLD_REPORT / name): h for name, h in old_status["files"].items()})
    old_vdb = Path((OLD_REPORT / "inputs.txt").read_text().splitlines()[0])
    old, current = Design(old_vdb), Design(inputs[0])
    require(sha(old.db / "design/verilog.design.xml") == old_status["design_sha256"], "Old design drift")
    verify_hashes({str(old.db / "shape" / n): h for n, h in old_status["shape_files"].items()})
    entries = native_entries((OLD_REPORT / "exclusions.el").read_text())
    points = [p for p in entries if p["point"] != "INSTANCE"]
    observers = [p for p in entries if p["point"] == "INSTANCE"]
    require({(p["scope"], p["point"]) for p in points} == expected_points(), "Old scope broadened")
    require(len(points) == 94 and len(observers) == 10, "Wrong old object count")
    require({p["scope"] for p in observers} == {s[0] for s in old_status["scopes"]}, "Old observer mismatch")
    manifest = jread(BUILD / "sim/vcs_source_manifest.json")
    old_manifest = jread(OLD_BUILD / "sim/vcs_source_manifest.json")
    pins = {f["path"]: f["sha256"] for f in manifest["files"]}
    old_pins = {f["path"]: f["sha256"] for f in old_manifest["files"]}
    sources = verify_hashes(pins)
    defines = sorted({line.strip() for line in Path(manifest["filelist"]).read_text().splitlines()
                      if line.startswith("+define+")})
    for definition in ("+define+NR_LANES=4", "+define+VLEN=1024", "+define+ARA_QBS_ENABLE=1",
                       "+define+ARA_AKV_ENABLE=1", "+define+ARA_AKV_V2_ENABLE=1", "+define+FOR_VERIFY"):
        require(definition in defines, "Compiled configuration differs")
    delta = [dict(path=p, old_sha256=old_pins.get(p), current_sha256=pins.get(p))
             for p in sorted(pins.keys() | old_pins.keys()) if pins.get(p) != old_pins.get(p)]
    proof_paths = [ROOT / p for p in ("hardware/src/lane/operand_queue.sv",
        "hardware/src/lane/operand_queues_stage.sv", "hardware/src/ara_system.sv",
        "hardware/deps/cva6/core/cva6.sv", "hardware/deps/cva6/core/csr_regfile.sv",
        "hardware/tb/ara_tb.sv", "hardware/src/lane/lane.sv", "hardware/src/ara.sv",
        "hardware/src/ara_soc.sv", "hardware/include/ara_pkg.sv", "config/default.mk")]
    for path in proof_paths:
        require(pins[str(path)] == old_pins[str(path)], "Reviewed connectivity/config source changed")
    stage = (ROOT / "hardware/src/lane/operand_queues_stage.sv").read_text().splitlines()
    for queue, line in TIE_LINES.items():
        require(re.search(r"\.flush_i\s*\(1'b0\s*\)", stage[line - 1]), "Tie proof changed")
        require(f") i_operand_queue_{queue} (" in "\n".join(stage[line - 5:line]), "Tie scope changed")
    system = (ROOT / "hardware/src/ara_system.sv").read_text().splitlines()
    for signal, line in (("ipi_i", 183), ("time_irq_i", 184), ("debug_req_i", 185)):
        require(re.search(r"\." + signal + r"\s*\('0\s*\)", system[line - 1]), "Scalar tie changed")
    for p in points:
        p["old"], p["current"] = old.point(p), current.point(p)
        require(p["old"] == p["current"], "Point/source/parameter shape changed: " + p["scope"] + p["point"])
        path = p["current"]["source_path"]
        require(pins[path] == old_pins[path], "Point source differs from old compiled input")
        p["source_sha256"] = pins[path]
        p["category"] = "operand_flush" if "i_operand_queue_" in p["scope"] else "scalar_constant_toggle"
        if p["category"] == "operand_flush":
            q = p["scope"].split("i_operand_queue_")[-1]
            p["proof"] = dict(source="hardware/src/lane/operand_queues_stage.sv", line=TIE_LINES[q],
                              connection="flush_i=1'b0", no_false_vector_or_fifo_child_excluded=True)
        else:
            p["proof"] = dict(source="hardware/src/ara_system.sv", lines=[183, 184, 185],
                              forwarding_source="hardware/deps/cva6/core/cva6.sv",
                              forwarding_lines=[1193, 1250, 1251], only_external_scalar_port=True)
    for o in observers:
        scope = o["scope"]
        before, after = old.source(scope), current.source(scope)
        require(before == after, "Observer source/definition changed")
        require(o["checksum"] == [after["definition_checksum"]], "Observer native checksum changed")
        require(after["module"] in OBSERVER_REASONS, "Unreviewed observer")
        descendants = sorted(s for s in current.hierarchy if s.startswith(scope + "."))
        require(not descendants, "Recursive observer has descendants requiring separate review")
        o.update(current=after, old=before, descendants=descendants,
                 reason=OBSERVER_REASONS[after["module"]], decision="REUSABLE_OFFLINE_NOT_APPLIED")
        path = after["source_path"]
        o["current_source_sha256"] = sha(path)
        if path in pins:
            require(pins[path] == old_pins[path], "Observer compiled source changed")
            o["source_binding"] = "old/current compile manifests and current SHA256 agree"
        else:
            require(after["module"] == "uvm_custom_install_verdi_recording", "Unmanifested RTL observer")
            fid = after["file_id"]
            require(old.sources[fid] == current.sources[fid], "Vendor source path/timestamp drift")
            o["source_binding"] = "vendor source absent from project manifest; same native definition, sourceinfo path/timestamp and metric shapes; current SHA256 is NOT a compile-time pin"
        o["metric_shapes"] = {}
        for m in ("line", "branch", "tgl"):
            # NA observers need not have a definition for every metric.
            present = scope in current.info[m]
            require(present == (scope in old.info[m]), "Observer metric presence changed")
            if present:
                a, b = old.definition(scope, m), current.definition(scope, m)
                require(tree_digest(a) == tree_digest(b), "Observer shape/parameters changed")
                o["metric_shapes"][m] = dict(checksum=b.get("chksum"), sha256=tree_digest(b),
                                               parameters=dict(b.attrib))
    outcomes = jread(REPORT.parent / "all-passed-outcomes.json")
    require(len(outcomes) == 625 and all(o["status"] == "PASS" and o["passed_only"]
            and o["vdb_valid"] and o["vdb_rejection"] is None for o in outcomes), "PASS ledger mismatch")
    ledger_vdbs = {o["vdb"] for o in outcomes}
    require(ledger_vdbs == set(map(str, inputs[1:])), "PASS ledger does not cover exact report inputs")
    ledger_hashes = {p: h for o in outcomes for p, h in o["vdb_files"].items()}
    raw_evidence = merge_selected(inputs[1:], points, ledger_hashes)
    report_rows = list(csv.DictReader((REPORT / "summary.csv").open()))
    raw_status = jread(REPORT / "waiver_status.json")
    require(raw_status["status"] == "NOT_APPLICABLE_UNREVIEWED_DESIGN"
            and raw_status["waived_report"] is None, "Report is not raw")
    evidence_paths = [PLAN, REPORT / "summary.csv", REPORT / "inputs.txt", REPORT / "waiver_status.json",
        REPORT.parent / "all-passed-outcomes.json", OLD_REPORT / "waiver_status.json",
        OLD_REPORT / "exclusions.el", OLD_REPORT / "points.el", OLD_REPORT / "inputs.txt",
        BUILD / "sim/vcs_source_manifest.json", OLD_BUILD / "sim/vcs_source_manifest.json",
        BUILD / "compile.command.json", BUILD / "build-source-pins.json",
        ROOT / "verification/coverage/reviewed_20260929/prepare_dve_waivers.py",
        ROOT / "verification/coverage/reviewed_20260929/constant_inputs.el",
        ROOT / "verification/coverage/waivers/operand_flush.el",
        ROOT / "verification/coverage/prepare_dve_waivers.py",
        ROOT / "verification/coverage/vcs_point_audit.py",
        ROOT / "verification/tests/audit_gap35_rvv.py"]
    result = dict(schema_version=1, status="REVIEWED_OFFLINE_NOT_APPLIED", scope="existing 88+6 points and 10 observer instances only",
        identity=dict(plan=str(PLAN), build=str(BUILD), design_vdb=str(inputs[0]),
                      design_sha256=sha(current.db / "design/verilog.design.xml"),
                      old_design_sha256=old_status["design_sha256"], image_files_checked=len(plan["image"]),
                      wrapper_files_checked=len(plan["wrapper_image"]), design_files_checked=len(plan["design_files"])),
        compile_command=jread(BUILD / "compile.command.json"), compile_manifest=dict(files_checked=len(pins), drift=[], defines=defines,
                      old_to_current_delta=delta, proof_paths=list(map(str, proof_paths))),
        raw_report=dict(path=str(REPORT / "summary.csv"), sha256=sha(REPORT / "summary.csv"),
                        tests=625, top=report_rows[0], waiver_status=raw_status, adjusted_percentages=None),
        mapping=dict(branch="reverse WITHIN each branch_spec; never reverse whole instance; native vector ID is unchanged",
                     line="explicit linebb.index, not traversal position or native Block ID",
                     toggle="exact scalar port from tglshape; 00 is direction independent",
                     nativepointchecksum="DVE saved native point checksum, distinct from linebb.chksum; null for Toggle/INSTANCE (no per-point integer in saved native syntax)",
                     baseline_checked="620-test diagnostic only; not used as the 625-test state or as an exclusion authority"),
        points=sorted(points, key=lambda p: (p["scope"], p["point"])), observers=sorted(observers, key=lambda p:p["scope"]),
        counts=dict(reusable_operand_points=88, reusable_scalar_toggles=6, reusable_observer_scopes=10,
                    rejected_existing_points=0, rejected_existing_observers=0, applied_current=0),
        rejected_actions=["fingerprint-only migration", "frozen helper forward branch missing labels",
            "arithmetic adjusted coverage", "claiming current DVE APPLIED without running it",
            "new operand_requester inline FOR_VERIFY exclusions", "whole operand queue/FIFO/module exclusion",
            "dynamic LSU flush, false branch vectors, Linux/RVV/QBS/AKV reachable functionality exclusions"],
        limitations=["No current native DVE load/save/review-status check was run; PREPARED/APPLIED must not be inferred.",
            "PASS status is linked to the existing exact 625-entry ledger; architectural traces are not revalidated by this waiver-only audit.",
            "Vendor UVM tool source is not in the project compile SHA manifest; its fixed-image scope binding uses unchanged native checksums, sourceinfo and shape, not a claim of reproducible tool-source rebuild.",
            "No new waiver reason or instance is authorized; observer checker/termination behavior remains enabled."],
        evidence=dict(files=[dict(path=str(p),sha256=sha(p)) for p in evidence_paths],
                      image_and_design=frozen, compile_sources=sources, raw_testdata=raw_evidence))
    return result


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--write", action="store_true", help="Create new audit.json and policy.json in this directory only")
    args = parser.parse_args()
    if args.write:
        require(not (HERE / "audit.json").exists() and not (HERE / "policy.json").exists(), "Refuse to replace existing review")
    record = audit()
    policy = make_policy(record)
    validate_policy(policy, record)
    if args.write:
        for name, data in (("audit.json", record), ("policy.json", policy)):
            with (HERE / name).open("x") as stream:
                json.dump(data, stream, indent=2)
                stream.write("\n")
    print(json.dumps(record["counts"], sort_keys=True))
