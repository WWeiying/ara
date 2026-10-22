"""Exact native/branch checks shared by admission and the immutable runtime copy."""
import csv
import gzip
import hashlib
import io
import json
from pathlib import Path
import re
import xml.etree.ElementTree as ET


def require(ok, message):
    if not ok:
        raise ValueError(message)


def sha(path):
    h = hashlib.sha256()
    with Path(path).open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def json_bytes(data):
    def unique(pairs):
        obj = {}
        for key, value in pairs:
            require(key not in obj, "Duplicate JSON key: " + key)
            obj[key] = value
        return obj
    return json.loads(data, object_pairs_hook=unique)


def jread(path):
    return json_bytes(Path(path).read_bytes())


def verify_hashes(pins):
    for path, digest in pins.items():
        require(sha(path) == digest, "Input hash drift: " + str(path))


def verify_snapshot(bundle, reviewed_sha256):
    """The independent receipt, never the mutable manifest, supplies the root."""
    require(isinstance(reviewed_sha256, str) and re.fullmatch(r"[0-9a-f]{64}", reviewed_sha256),
            "Explicit reviewed snapshot SHA256 required")
    bundle = Path(bundle)
    require(bundle.is_dir() and not bundle.is_symlink(), "Snapshot must be a real directory")
    manifest = bundle / "snapshot.json"
    require(manifest.is_file() and not manifest.is_symlink(), "Snapshot manifest must be a regular file")
    data = manifest.read_bytes()
    require(hashlib.sha256(data).hexdigest() == reviewed_sha256, "Reviewed snapshot root changed")
    hashes = json_bytes(data)
    require(isinstance(hashes, dict) and "context.json" in hashes, "Incomplete snapshot manifest")
    directories = set()
    for name, digest in hashes.items():
        path = Path(name)
        require(name != "snapshot.json" and not path.is_absolute() and path.as_posix() == name and
                name and ".." not in path.parts and "\\" not in name and
                isinstance(digest, str) and re.fullmatch(r"[0-9a-f]{64}", digest), "Unsafe snapshot member")
        directories.update(str(p) for p in path.parents if p != Path("."))
    def membership():
        entries = {str(p.relative_to(bundle)): p for p in bundle.rglob("*")}
        require(set(entries) == set(hashes) | directories | {"snapshot.json"}, "Unexpected snapshot member")
        require(all(not p.is_symlink() and (p.is_dir() if name in directories else p.is_file())
                    for name, p in entries.items()), "Snapshot member type/symlink differs")
    membership()
    context = None
    for name, digest in hashes.items():
        contents = (bundle / name).read_bytes()
        require(hashlib.sha256(contents).hexdigest() == digest, "Snapshot hash drift: " + name)
        if name == "context.json":
            context = json_bytes(contents)
    membership()
    require(manifest.read_bytes() == data, "Reviewed snapshot root changed during verification")
    return context


def point_id(name):
    match = re.fullmatch(r"Branch (0|[1-9][0-9]*) \((0|[1-9][0-9]*)\)", name)
    require(match is not None, "Not an exact Branch vector: " + name)
    return tuple(map(int, match.groups()))


def exact_inventory(definition):
    """XML order determines bitmap offset; vector ID is NEVER an offset or zero."""
    result, base, specs = {}, 0, set()
    for spec in definition.iter("branch_spec"):
        sid = int(spec.get("id"))
        require(sid not in specs, "Duplicate branch spec ID")
        specs.add(sid)
        vectors = spec.findall("branch_vector")
        require(vectors, "Empty branch spec")
        for position, vector in enumerate(vectors):
            vid = int(vector.get("id"))
            key = (sid, vid)
            require(key not in result, "Duplicate branch vector ID")
            result[key] = dict(spec=sid, vector_id=vid, raw_index=base + len(vectors) - 1 - position,
                spec_base=base, spec_width=len(vectors), vector=dict(vector.attrib),
                xml_point_checksum=spec.get("chksum"), expressions=[dict(e.attrib) for e in spec.findall("branch_expr")])
        base += len(vectors)
    require({p["raw_index"] for p in result.values()} == set(range(base)), "Nonbijective bitmap mapping")
    return result, base


def bind_targets(definition, targets):
    inventory, width = exact_inventory(definition)
    require(len(targets) == 107 and width == 626, "Wrong CSR branch population")
    seen = set()
    for point in targets:
        key = point_id(point["native"])
        require(key != (3, 187) and key not in seen and key in inventory, "Forbidden/duplicate/missing CSR vector")
        seen.add(key)
        require(point["metric"] == "branch" and point["eligibility"] == "ACCEPT_CONSTANT_GUARD", "Unreviewed CSR point")
        actual = inventory[key]
        for name in ("raw_index", "spec_base", "spec_width", "vector", "xml_point_checksum"):
            require(point[name] == actual[name], "Actual vector-ID mapping differs: " + name)
        require(point["proof_ids"], "Missing guard proof")
        for proof in point["proof_ids"]:
            guards = [e for e in actual["expressions"] if e["id"] == proof.rsplit(":", 1)[1]]
            require(len(guards) == 1 and actual["vector"]["vector"][-int(guards[0]["index"])] == "1", "Vector does not require guard")
    return inventory


def raw_csr_bits(data, scope, checksum, width):
    body = gzip.decompress(data) if data.startswith(b"\x1f\x8b") else data
    found = []
    for _, node in ET.iterparse(io.BytesIO(body), events=("end",)):
        if node.tag == "instance_data" and node.get("name") == scope:
            found.append(dict(node.attrib))
        node.clear()
    require(len(found) == 1, "Missing/duplicate raw CSR scope")
    row = found[0]
    require(row.get("chksum") in (None, checksum), "Raw branch checksum differs")
    bits = row.get("value", "")
    require(len(bits) == width and set(bits) <= {"0", "1"}, "Malformed/wrong-width CSR raw bits")
    return bits, row.get("chksum") is None


def zero_targets(bits, targets):
    require(len(bits) == 626 and set(bits) <= {"0", "1"}, "CSR bit width/content differs")
    for point in targets:
        index = point["raw_index"]
        require(type(index) is int and 0 <= index < len(bits), "Invalid target bit offset")
        require(bits[index] == "0", "CSR target has raw hit: " + point["native"])


def validate_union(data, context, audit, observers):
    """Legacy exact signatures plus byte-exact CSR annotation/directive blocks."""
    require(all(c == 10 or 32 <= c <= 126 for c in data), "Unsupported native encoding")
    text = data.decode("ascii")
    require(not any(line.startswith("//") for line in text.splitlines()), "Unexpected native comments")
    actual = audit.native_entries(text)
    expected = context["policy"]["allowed_points"]
    if observers:
        expected = expected + [{k: p[k] for k in ("scope", "point", "checksum", "native_directive",
            "nativepointchecksum", "native_signature")} for p in context["observers"]]
    key = lambda p: (p["scope"], p["point"])
    require(sorted(actual, key=key) == sorted(expected, key=key), "Native union differs from exact 94+107/10")
    expected_blocks = context["csr_blocks"]
    scope, checksum, previous, found = None, None, b"", {}
    header = b""
    annotation_pending, observer_record = False, False
    for line in data.splitlines(keepends=True):
        require(line.endswith(b"\n"), "Unterminated native line")
        if line == b"\n":
            require(not annotation_pending, "Detached annotation")
            previous = line
            continue
        if line.startswith(b"CHECKSUM:"):
            require(not annotation_pending and (checksum is None or scope is not None), "Unconsumed native header/annotation")
            checksum = re.fullmatch(rb'CHECKSUM: "([0-9 ]+)"\n', line)
            require(checksum is not None, "Malformed checksum header")
            checksum, scope = checksum[1].decode().split(), None
            header = line
            observer_record = False
        elif line.startswith(b"INSTANCE:"):
            require(checksum is not None and scope is None, "Detached/duplicate instance")
            scope = line[len(b"INSTANCE:"):].strip().decode()
            header += line
            observer_record = annotation_pending
            annotation_pending = False
        elif line.startswith(b"ANNOTATION:"):
            require(re.fullmatch(rb'ANNOTATION: "[^"\\\n]*"\n', line), "Malformed annotation")
            require(checksum is not None and not annotation_pending and not observer_record, "Detached duplicate annotation")
            require(scope is not None or len(checksum) == 1, "Annotation before point scope")
            annotation_pending = True
        else:
            require(line.startswith((b"Branch ", b"Block ", b"Toggle ")) and
                    scope is not None and annotation_pending and not observer_record, "Unconsumed native directive")
            annotation_pending = False
        if line.startswith(b"Branch ") and scope == context["csr_scope"]:
            match = re.fullmatch(rb'Branch ([0-9]+) "[0-9]+" "[^"\n]*" \(([0-9]+)\) "[^"\n]*"\n', line)
            require(match is not None, "Malformed CSR directive")
            name = f"Branch {int(match[1])} ({int(match[2])})"
            require(name not in found and name in expected_blocks, "Unexpected/duplicate CSR native point")
            require(checksum == context["csr_checksum"] and previous.startswith(b"ANNOTATION:"), "CSR header/annotation binding differs")
            require(header.decode() == context["csr_header"], "CSR header bytes changed")
            require((previous + line).decode() == expected_blocks[name], "Complete CSR native block changed")
            found[name] = True
        previous = line
    require(scope is not None and not annotation_pending, "Unconsumed final native header/annotation")
    require(set(found) == set(expected_blocks) and len(found) == 107, "Missing CSR native blocks")
    return len(actual)


def csv_rows(path):
    with Path(path).open() as stream:
        rows = list(csv.DictReader(stream))
    require(rows and {"Line", "Condition", "Branch", "FSM", "Toggle"} <= rows[0].keys(), "Incomplete coverage summary")
    return rows


def fresh_state(log, context):
    lines = log.splitlines()
    def one(marker):
        hits = [i for i, line in enumerate(lines) if line == marker]
        require(len(hits) == 1, "Missing/duplicate fresh state: " + marker)
        return hits[0]
    markers = ["CSR_RAW_EMPTY", "CSR_METADATA before total=626 selected=107 retained=519",
        "CSR_INCLUDED before count=626 excluded=0", "CSR_REVIEW_EMPTY 1",
        "CSR_METADATA loaded total=626 selected=107 retained=519", "CSR_INCLUDED loaded count=519 excluded=0"]
    positions = [one(m) for m in markers]
    saved = one("CSR_NATIVE_SAVED_EXACT")
    require(positions == sorted(set(positions)) and positions[-1] < saved, "Fresh CSR state order differs")
    actual = [(i, re.fullmatch(r"CSR_LOADED (\S+) excluded=1", line)) for i, line in enumerate(lines)]
    actual = [(i, match[1]) for i, match in actual if match]
    require(len([line for line in lines if line.startswith("CSR_LOADED ")]) == len(actual), "Malformed/false fresh loaded state")
    expected = {p["meta"] for p in context["csr_selection"]}
    require(len(actual) == 107 and {meta for _, meta in actual} == expected and
            all(positions[-1] < i < saved for i, _ in actual), "Fresh 107 loaded states differ")
    final = one("CSR_INCLUDED final count=626 excluded=0")
    done = one("CSR_SESSION_PROOF_DONE")
    require(saved < final < done, "Missing final reset proof")
    expected_markers = set(markers) | {"CSR_NATIVE_SAVED_EXACT", "CSR_INCLUDED final count=626 excluded=0", "CSR_SESSION_PROOF_DONE"}
    expected_markers.update("CSR_LOADED " + meta + " excluded=1" for meta in expected)
    callbacks = {}
    for stage in ("raw", "saved", "reset"):
        marker = "CSR_RUNTIME_CHECK_OK " + stage
        callbacks[stage] = one(marker)
        expected_markers.add(marker)
    require(callbacks["raw"] < positions[0] and max(i for i, _ in actual) < callbacks["saved"] < saved and
            final < callbacks["reset"] < done, "Runtime callback order differs")
    require({line for line in lines if line.startswith("CSR_")} == expected_markers, "Unexpected CSR state marker")
    one("All exclusions successfully imported and applied.")
    require(not re.search(r"Warning|Error|Fatal|DVE_COVERAGE_EXPORT_FAILED|unmappable|bypass", log), "DVE diagnostics reject")
    return dict(excluded=107, neighbors_included=519, imported_review=0, final_reset=True)


def approval(receipt, snapshot_sha, baseline_sha):
    require(receipt.get("status") == "APPROVED_SUPPLEMENTAL_CSR_REPORT_ONLY", "Independent application review required")
    require(receipt.get("authority") == "independent-parent-review" and isinstance(receipt.get("reviewer"), str)
            and receipt["reviewer"].strip(), "Missing independent reviewer")
    require(receipt.get("snapshot_sha256") == snapshot_sha and receipt.get("baseline_collection_sha256") == baseline_sha,
            "Review does not bind this snapshot/corpus")
    require(receipt.get("allow_one_dve_session") is True and receipt.get("allow_final_coverage_application") is False,
            "Wrong review authority")
    require(receipt.get("existing_points") == 94 and receipt.get("csr_points") == 107 and
            receipt.get("observers") == 10 and receipt.get("blocks_added") == 0, "Review population differs")
