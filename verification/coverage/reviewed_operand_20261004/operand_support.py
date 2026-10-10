"""Exact coordinate/native/session guards. No authority inferred from a pilot."""
import importlib.util
import io
import gzip
import json
from pathlib import Path
import re
import xml.etree.ElementTree as ET

HERE = Path(__file__).resolve().parent


def module(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    result = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(result)
    return result


csr = module("operand_borrowed_csr_support", HERE / "csr_support.py" if (HERE / "csr_support.py").exists()
             else HERE.parent / "reviewed_csr_20261004/support.py")
require, sha, jread = csr.require, csr.sha, csr.jread
verify_hashes, verify_snapshot = csr.verify_hashes, csr.verify_snapshot
ANNOTATION = "Operand parameter native discovery; exact vectors only; not application approval"
NUMBER = r"(0|[1-9][0-9]*)"
HEADER = re.compile(r'CHECKSUM: "([0-9]+(?: [0-9]+)?)"\n')
INSTANCE = re.compile(r'INSTANCE: ?([A-Za-z_][A-Za-z0-9_.\[\]]*)\n')
NOTE = re.compile(r'ANNOTATION: "([^"\\\n]*)"\n')
BRANCH = re.compile(r'Branch ' + NUMBER + ' "' + NUMBER + r'" "([^"\\\n]+)" \(' + NUMBER + r'\) "([^"\\\n]+)"\n')
BLOCK = re.compile(r'Block ' + NUMBER + ' "' + NUMBER + r'" "([^"\\\n]*)"\n')
TOGGLE = re.compile(r'Toggle ([A-Za-z_]\w*) "((?:logic|net) [A-Za-z_]\w*)"\n')


def point_key(p):
    return p["scope"], p["point"]


def blocks(data):
    """Consume all native bytes; key complete header+annotation+directive records.

    A single-checksum observer uses CHECKSUM/ANNOTATION/INSTANCE only. No other
    instance/module wildcard is admitted. Repeated point headers are allowed;
    duplicate point identities and empty/dangling headers are not.
    """
    require(data and data.endswith(b"\n") and not re.search(rb"[^\x0a\x20-\x7e]", data), "Native encoding/LF")
    lines = data.decode("ascii").splitlines(keepends=True)
    result, i = {}, 0
    while i < len(lines):
        if lines[i] == "\n":
            i += 1
            continue
        start = i
        h = HEADER.fullmatch(lines[i])
        require(h is not None, "Native checksum header expected")
        sums = h[1].split()
        i += 1
        if len(sums) == 1:
            require(i + 1 < len(lines) and NOTE.fullmatch(lines[i]) is not None, "Observer annotation expected")
            m = INSTANCE.fullmatch(lines[i + 1])
            require(m is not None, "Observer instance expected")
            k = (m[1], "INSTANCE")
            require(k not in result, "Duplicate observer")
            result[k] = dict(raw="".join(lines[start:i + 2]), header=lines[start] + lines[i + 1], checksum=sums,
                             native_directive=None, nativepointchecksum=None, native_signature=None)
            i += 2
            continue
        require(i < len(lines), "Dangling checksum")
        m = INSTANCE.fullmatch(lines[i])
        require(m is not None, "Native point instance expected")
        scope, header = m[1], lines[start] + lines[i]
        i += 1
        count = 0
        while i < len(lines) and not lines[i].startswith("CHECKSUM:"):
            if lines[i] == "\n":
                i += 1
                continue
            require(i + 1 < len(lines) and NOTE.fullmatch(lines[i]) is not None, "Point annotation expected")
            note, directive = lines[i:i + 2]
            b, v, t = BLOCK.fullmatch(directive), BRANCH.fullmatch(directive), TOGGLE.fullmatch(directive)
            require(b or v or t, "Unsupported native directive")
            if v:
                name, checksum, signature = f"Branch {v[1]} ({v[4]})", v[2], v[5]
            elif b:
                name, checksum, signature = "Block " + b[1], b[2], b[3]
            else:
                name, checksum, signature = "Toggle " + t[1], None, t[2]
            k = (scope, name)
            require(k not in result, "Duplicate native point")
            result[k] = dict(raw=header + note + directive, header=header, block=note + directive,
                checksum=sums, native_directive=directive.rstrip("\n"), nativepointchecksum=checksum,
                native_signature=signature, expression=v[3] if v else None)
            count += 1
            i += 2
        require(count > 0, "Empty point header")
    require(result, "No native records")
    return result


def validate_operand(data, context):
    actual = blocks(data)
    expected = {point_key(p): p for p in context["operand_targets"]}
    pilot_points = {point_key(p): p for p in context["pilot18"]}
    require(len(expected) == 1144 and set(actual) == set(expected), "Not exactly1144 operand vectors")
    for k, p in expected.items():
        a = actual[k]
        require(a["checksum"] == [p["module_checksum"], p["metric_checksum"]] and
                a["nativepointchecksum"] == p["spec_checksum"], "Operand checksum mismatch")
        sid, _ = csr.point_id(p["point"])
        require(a["expression"] == context["operand_specs"][str(sid)]["expression"], "Operand root expression mismatch")
        require(a["block"].startswith('ANNOTATION: "' + ANNOTATION + '"\n'), "Operand annotation mismatch")
        if k in pilot_points:
            pilot = pilot_points[k]
            require(a["native_directive"] == pilot["full_annotation_directive_block"].splitlines()[1], "Observed pilot18 directive differs")
    return actual


def pair(first, second, context, audit=None):
    validator = (lambda data: validate_operand(data, context)) if context["stage"] == "capture" else (lambda data: validate_composed(data, context, audit, True))
    left, right = validator(first), validator(second)
    equal_records(left, right)
    return left


def equal_records(left, right):
    require(set(left) == set(right), "Roundtrip identity set differs")
    require(all(left[k]["raw"] == right[k]["raw"] for k in left), "Roundtrip complete record differs")


def compose_policy(context, operand_data):
    records = validate_operand(operand_data, context)
    old = context["policy"]["allowed_points"]
    require(len(old) == 201 and len({point_key(p) for p in old}) == 201, "Baseline must be old94 plus CSR107")
    require(not (set(records) & {point_key(p) for p in old}), "Old201/operand1144 overlap")
    additions = [dict(scope=k[0], point=k[1], **{f: row[f] for f in
                 ("checksum", "native_directive", "nativepointchecksum", "native_signature")}) for k, row in records.items()]
    return dict(context["policy"], allowed_points=old + additions)


def validate_composed(data, context, audit, observers):
    # Reuse the unchanged CSR guard on the one derived union, not a second policy.
    csr.validate_union(data, context, audit, observers)
    actual = blocks(data)
    expected = context["operand_native_blocks"]
    for p in context["operand_targets"]:
        k = point_key(p)
        require(actual[k]["raw"] == expected[p["scope"]][p["point"]], "Pinned operand full native block differs")
    return actual


def scan_raw(data, scopes, masks):
    raw = gzip.decompress(data) if data.startswith(b"\x1f\x8b") else data
    result = {}
    for _, n in ET.iterparse(io.BytesIO(raw), events=("end",)):
        if n.tag == "instance_data" and n.get("name") in scopes:
            scope, bits = n.get("name"), n.get("value", "")
            require(scope not in result and n.get("chksum") in (None, "1417162425"), "Raw scope/checksum differs")
            require(len(bits) == 101 and set(bits) <= {"0", "1"}, "Raw operand width/value differs")
            require(not (int(bits, 2) & masks[scope]), "Operand target has raw hit")
            result[scope] = int(bits, 2)
        n.clear()
    require(set(result) == set(scopes), "Incomplete raw36 queue set")
    return result


def verify_inputs(context):
    verify_hashes(context["pins"])
    for root, members in context["input_tree"].items():
        require(tree(root) == members, "VDB member/type change")


def tree(root):
    paths = sorted(Path(root).rglob("*"))
    require(not Path(root).is_symlink() and all(not p.is_symlink() for p in paths), "VDB symlink")
    require(all(p.is_file() or p.is_dir() for p in paths), "VDB special member")
    return {str(p.relative_to(root)): "file" if p.is_file() else "directory" for p in paths}


def approval(record, root, context):
    require(record.get("status") == "APPROVED_OPERAND_" + context["stage"].upper() + "_SESSION_ONLY", "Independent stage approval required")
    require(record.get("authority") == "independent-parent-review" and record.get("reviewer", "").strip(), "Independent reviewer required")
    require(record.get("snapshot_sha256") == root and record.get("baseline_collection_sha256") == context["baseline_collection_sha256"], "Approval root/corpus differs")
    require(record.get("allow_one_dve_session") is True and record.get("allow_final_coverage_application") is False,
            "Wrong session authority")
    require(record.get("operand_points") == 1144 and record.get("existing_points") == 94 and record.get("csr_points") == 107
            and record.get("observers") == 10 and record.get("dve_max_seconds") == context["dve_max_seconds"], "Approval population/bound differs")
    require(record.get("native_capture_sha256") == context.get("native_capture_sha256"), "Native capture approval differs")


def state_proof(output, context, reviewed_root=None):
    """Every zero is either singleton-observed or a complete exact-group ANY=0 proof."""
    import csv
    phases = ("before", "selected", "reset", "reloaded", "final")
    expected = {(s, key) for s, keys in context["session_keys"].items() for key in keys}
    selected = {(s, key) for s, keys in context["session_targets"].items() for key in keys}
    records = {}
    for phase in phases:
        with (Path(output) / ("states_" + phase + ".tsv")).open() as f:
            rows = list(csv.DictReader(f, delimiter="\t"))
        require(len(rows) == len(expected), "State count differs")
        found = set()
        for row in rows:
            k = row["scope"], row["coordinate"]
            require(k in expected and k not in found, "Duplicate/foreign state")
            found.add(k)
            sid, vid = k[1].split(",")
            require(row["meta"] in (f"Branch{sid}.{vid}", f"MISSING_ELSE{sid}.{vid}") and
                    row["path"] == f"Item{sid}.{row['meta']}", "Native metadata mismatch")
            wanted = phase in ("selected", "reloaded") and k in selected
            require(row["excluded"] == str(int(wanted)), "Selected/neighbor state differs")
            require(row["proof"] == ("singleton" if wanted else "exact_group_any_zero"), "State proof kind differs")
            if phase != "before":
                require([row[x] for x in ("meta", "path")] == records[k]["metadata"], "Metadata changed across phases")
            else:
                records[k] = dict(scope=k[0], coordinate=k[1], selected=k in selected, metadata=[row["meta"], row["path"]], phases={})
            records[k]["phases"][phase] = dict(excluded=int(row["excluded"]), proof=row["proof"])
    log = (Path(output) / "DVEfiles/dve_gui.log").read_text()
    require(not re.search(r"Warning|Error|Fatal|FAILED|unmappable|bypass", log), "DVE diagnostic")
    lines = log.splitlines()
    session_roots = [t.split()[1] for t in lines if re.fullmatch(r"OQ_SESSION_ROOT [0-9a-f]{64}", t)]
    require(len(session_roots) == 1 and (reviewed_root is None or session_roots[0] == reviewed_root), "Observed session snapshot root differs")
    markers = ["OQ_CALLBACK raw", "OQ_STATES before", "OQ_STATES selected", "OQ_CALLBACK first",
               "OQ_STATES reset", "OQ_CALLBACK empty", "OQ_REVIEW_EMPTY", "OQ_STATES reloaded",
               "OQ_CALLBACK second", "OQ_STATES final", "OQ_CALLBACK final", "OQ_SESSION_DONE", "DVE_COVERAGE_EXPORT_DONE"]
    positions = []
    for marker in markers:
        hits = [i for i, line in enumerate(lines) if line == marker]
        require(len(hits) == 1, "Missing/duplicate session marker: " + marker)
        positions.append(hits[0])
    require(positions == sorted(set(positions)), "Session marker order differs")
    hashes = [line.split()[1] for line in lines if re.fullmatch(r"OQ_FIRST_SHA [0-9a-f]{64}", line)]
    require(len(hashes) == 1 and hashes[0] == sha(Path(output) / "first.el"), "Fresh first-export signature pin differs")
    # Exact selected lists were read back from DVE before each ANY query.
    groups = [line for line in lines if line.startswith("OQ_GROUP ")]
    expected_groups = []
    for phase in phases:
        for scope, keys in context["session_keys"].items():
            n = len(keys) - (len(context["session_targets"][scope]) if phase in ("selected", "reloaded") else 0)
            expected_groups.append(f"OQ_GROUP {phase} {scope} {n} excluded=0")
    require(groups == expected_groups, "Missing/extra exact neighbor/reset group witness")
    inventories = [line for line in lines if line.startswith("OQ_INVENTORY ")]
    expected_inventories = [f"OQ_INVENTORY {scope} full count={len(keys)}" for scope, keys in context["session_keys"].items()]
    require(inventories == expected_inventories * 2, "Need fresh complete inventory before and after import")
    return list(records.values())
