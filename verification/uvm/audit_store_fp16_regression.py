#!/usr/bin/env python3
"""Read-only artifact audit of the fixed 21-task FP16 batch (no simulator calls).

PASS proves consistency of available artifacts, not that post-run hashes were
captured before execution. The checker snapshot explicitly has post-start timing.
Missing evidence is NOT_PROVEN. completion.json is deliberately not required.
"""

import argparse
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import re
import shlex


ROOT = Path(__file__).resolve().parents[2]
DEFAULT_SNAPSHOT = ROOT / "verification/out/store-fp16-checker-snapshot-20260926-01.json"
REPLAYS = {
    "control401": ("ara_dsa_rvv1_short_control_cross_0", 401),
    "control301": ("ara_dsa_rvv1_short_control_cross_4", 305),
    "control201": ("ara_dsa_rvv1_short_control_cross_1", 202),
}
FOCUSED = (
    "numeric", "fault", "handoff", "masked", "vfncvt", "vfwcvt", "vfredmax",
    "vstore_axi_error", "vfwcvt_int8", "narrow_smoke",
    *(f"narrow_shard_{i}" for i in range(8)),
)
EXPECTED = set(FOCUSED) | set(REPLAYS)
DIGEST = re.compile(r"[0-9a-f]{64}")


class MissingEvidence(ValueError):
    pass


def field(obj, key, kind=None):
    if not isinstance(obj, dict) or key not in obj:
        raise MissingEvidence(f"missing field {key}")
    value = obj[key]
    if kind is not None and (not isinstance(value, kind) or
                             (kind is int and isinstance(value, bool))):
        raise MissingEvidence(f"unsupported type for {key}")
    return value


def sha256(path):
    h = hashlib.sha256()
    with Path(path).open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def digest(value):
    if not isinstance(value, str) or not DIGEST.fullmatch(value):
        raise MissingEvidence("missing or malformed SHA-256")
    return value


def hash_map(value):
    if not isinstance(value, dict) or not value:
        raise MissingEvidence("missing or empty runtime image hash map")
    result = {}
    for name, hashed in value.items():
        if not isinstance(name, str) or not Path(name).is_absolute():
            raise MissingEvidence("runtime hash paths must be absolute")
        canonical = str(Path(name).resolve())
        if canonical in result:
            raise MissingEvidence("duplicate runtime hash path")
        result[canonical] = digest(hashed)
    return result


def no_duplicate_keys(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            raise MissingEvidence(f"duplicate JSON key: {key}")
        result[key] = value
    return result


class Audit:
    def __init__(self):
        self.sections = []
        self.current = None
        self.evidence = {}

    def issue(self, status, message):
        self.current["issues"].append({"status": status, "message": message})

    def equal(self, actual, expected, label):
        self.current["checks"] += 1
        if actual != expected:
            self.issue("FAIL", f"{label}: expected {expected!r}, got {actual!r}")

    def section(self, name, action):
        self.current = {"name": name, "checks": 0, "issues": []}
        self.sections.append(self.current)
        try:
            action()
        except (OSError, ValueError, KeyError, TypeError) as error:
            self.issue("NOT_PROVEN", str(error))
        self.current["status"] = self.status(self.current["issues"])

    @staticmethod
    def status(issues):
        statuses = {issue["status"] for issue in issues}
        return "FAIL" if "FAIL" in statuses else "NOT_PROVEN" if statuses else "PASS"

    def read(self, path):
        path = Path(path)
        raw = path.read_bytes()
        self.evidence[str(path.resolve())] = hashlib.sha256(raw).hexdigest()
        return raw.decode("utf-8")

    def document(self, path):
        return json.loads(self.read(path), object_pairs_hook=no_duplicate_keys)

    def file_hash(self, path, expected, label):
        actual = sha256(path)
        self.evidence[str(Path(path).resolve())] = actual
        self.equal(actual, digest(expected), label)

    def report(self):
        return {
            "schema_version": 1,
            "status": self.status([i for s in self.sections for i in s["issues"]]),
            "audited_at": datetime.now(timezone.utc).isoformat(),
            "scope": "Recorded artifact identity and DUT coverage; not proof of pre-run checker freezing",
            "completion_required": False,
            "expected_batch_tests": 21,
            "sections": self.sections,
            "evidence_sha256": self.evidence,
        }


def named_rows(rows, label):
    if not isinstance(rows, list):
        raise MissingEvidence(f"{label} must be a list")
    result = {}
    for row in rows:
        name = field(row, "name", str)
        if name in result:
            raise MissingEvidence(f"duplicate {label} name: {name}")
        result[name] = row
    return result


def unique_match(audit, pattern, text, label):
    matches = re.findall(pattern, text, re.MULTILINE)
    if not matches:
        raise MissingEvidence(f"missing {label}")
    audit.equal(len(matches), 1, f"unique {label}")
    return matches[0]


def check_command(audit, command, simv, elf):
    if not isinstance(command, list) or not command:
        raise MissingEvidence("missing simulator command")
    audit.equal(str(Path(command[0]).resolve()), str(simv), "executed simulator path")
    preloads = [s[len("+PRELOAD="):] for s in command if s.startswith("+PRELOAD=")]
    audit.equal(preloads, [str(elf)], "executed PRELOAD")


def check_log(audit, path, simv, elf):
    text = audit.read(path)
    command = unique_match(audit, r"^Command: (.+)$", text, "VCS command")
    check_command(audit, shlex.split(command), simv, elf)
    audit.equal(bool(re.search(r"Core Test \*\*\* SUCCESS", text)), True, "Core SUCCESS")
    audit.equal(bool(re.search(r"\b(?:FAIL(?:ED)?|ERROR|FATAL)\b|Error:|Fatal:", text)),
                False, "failure diagnostic absent")
    # UVM_ERROR/FATAL zero summaries are legal; nonzero summaries are not.
    for severity in ("ERROR", "FATAL"):
        count = unique_match(audit, rf"^UVM_{severity}\s*:\s*(\d+)\s*$", text,
                             f"UVM_{severity} summary")
        audit.equal(int(count), 0, f"UVM_{severity}")
    return text


def check_narrow(audit, text, row, bundle):
    count, vlen = unique_match(audit, r"^vfncvt_int8: (\d+) cases, VLEN=(\d+)\s*$",
                               text, "narrow case count")
    observed = unique_match(audit,
        r"^vfncvt_int8_checks: ordinals=(\d+) bytes=(\d+) active=(\d+) csr=(\d+)\s*$",
        text, "narrow counters")
    bitmap = unique_match(audit, r"^vfncvt_int8_ids:([ \t0-9a-f]+)\r?$",
                          text, "narrow ordinal bitmap")
    catalog = field(bundle, "catalog", list)
    audit.equal(int(count), field(row, "case_count", int), "DUT case count")
    audit.equal(int(vlen), field(bundle, "vlen", int), "DUT VLEN")
    expected = [len(catalog), *(field(row, k, int) for k in
                               ("byte_checks", "active_checks", "csr_checks"))]
    audit.equal(list(map(int, observed)), expected, "DUT ordinal/byte/active/CSR counts")
    words = [int(word, 16) for word in bitmap.split()]
    audit.equal(len(words), (len(catalog) + 63) // 64, "bitmap word count")
    audit.equal(all(word < 1 << 64 for word in words), True, "bitmap 64-bit words")
    ids = [i * 64 + bit for i, word in enumerate(words)
           for bit in range(64) if word & (1 << bit)]
    audit.equal(ids, field(row, "ordinals", list), "DUT executed ordinals")
    audit.equal(ids, field(row, "observed_ordinals", list), "DUT versus golden ordinals")


def check_bundle(audit, bundle):
    audit.equal(field(bundle, "status"), "PASS", "shard manifest status")
    audit.equal(field(bundle, "shard_count", int), 8, "shard count")
    partition = field(bundle, "partition", dict)
    audit.equal(field(partition, "status"), "PASS", "partition status")
    rows = named_rows(field(bundle, "shards", list), "shard")
    audit.equal(set(rows), {f"shard_{i}" for i in range(8)}, "shard names")
    catalog = field(bundle, "catalog", list)
    audit.equal([field(c, "ordinal", int) for c in catalog], list(range(len(catalog))),
                "catalog ordinal space")
    audit.equal(len(catalog) > 0, True, "nonempty catalog")
    all_ids = []
    for row in [*rows.values(), field(bundle, "smoke", dict)]:
        ids = field(row, "ordinals", list)
        if any(type(i) is not int or not 0 <= i < len(catalog) for i in ids):
            raise MissingEvidence("invalid manifest ordinal list")
        audit.equal(ids, sorted(set(ids)), "unique ordered manifest ordinals")
        audit.equal(field(row, "observed_ordinals", list), ids, "golden ordinal list")
        audit.equal(field(row, "case_count", int), len(ids), "manifest case count")
        audit.equal(field(row, "spike_status"), "PASS", "golden status")
        for key in ("byte_checks", "active_checks", "csr_checks"):
            audit.equal(field(row, key, int), sum(field(catalog[i], key, int) for i in ids),
                        f"manifest {key}")
    for row in rows.values():
        all_ids.extend(row["ordinals"])
    audit.equal(sorted(all_ids), list(range(len(catalog))), "disjoint complete shard union")
    audit.equal(field(partition, "case_count", int), len(catalog), "partition cases")
    for key in ("byte_checks", "active_checks", "csr_checks"):
        audit.equal(field(partition, key, int), sum(field(row, key, int) for row in rows.values()),
                    f"partition {key}")
    return {**{f"narrow_{name}": row for name, row in rows.items()},
            "narrow_smoke": bundle["smoke"]}


def check_focused(audit, directory, record, simv, gate_hashes, narrow=None, bundle=None,
                  expected_cases=None):
    directory = directory.resolve()
    work = directory / "work"
    elf = work / "input.elf"
    expected_hash = digest(field(record, "sha256"))
    # The optional standalone CSR test can supply an independently recorded digest.
    if "elf" in record:
        audit.file_hash(Path(record["elf"]), expected_hash, "frozen staging ELF")
    audit.file_hash(elf, expected_hash, "executed ELF copy")
    report = audit.document(directory / "uvm_result.json")
    if directory.name == "vstore_axi_error" and report.get("status") == "FAIL":
        audit.equal(report.get("issues"),
                    ["real DUT UVM observed no complete Ara AXI read traffic"],
                    "only the incorrect read-traffic requirement failed")
        rechecked = audit.document(directory / "rechecked_uvm_result.json")
        for key in ("elf_sha256", "sim_image_sha256", "simv_sha256", "log_sha256",
                    "vector_trace_sha256", "contract_counts", "axi_write_counts",
                    "axi_read_counts"):
            audit.equal(field(rechecked, key), field(report, key),
                        "unchanged evidence for write-only recheck: " + key)
        audit.equal(field(report["contract_counts"], "exceptions"), 3,
                    "three directed store exceptions")
        audit.equal(field(report["axi_read_counts"], "ar"), 0,
                    "store-only program has no vector reads")
        report = rechecked
    audit.equal(field(report, "status"), "PASS", "focused report")
    audit.equal(field(report, "issues", list), [], "focused checker issues")
    audit.equal(digest(field(report, "elf_sha256")), expected_hash, "reported ELF")
    audit.equal(hash_map(field(report, "sim_image_sha256", dict)), gate_hashes, "runtime image")
    audit.equal(digest(field(report, "simv_sha256")), gate_hashes[str(simv)], "launcher hash")
    audit.file_hash(work / "run.vcs.log", field(report, "log_sha256"), "reported log hash")
    audit.file_hash(work / "vector_trace.csv", field(report, "vector_trace_sha256"), "vector trace hash")
    text = check_log(audit, work / "run.vcs.log", simv, elf)
    if narrow is not None:
        audit.equal(expected_hash, digest(field(narrow, "sha256")), "golden-bound shard ELF")
        check_narrow(audit, text, narrow, bundle)
    if expected_cases is not None:
        label = "vec_fp_csr_order" if expected_cases[0] == "csr" else "vfwcvt_int8"
        pattern = (rf"^{label}: (\d+) cases, (\d+) checks, traps=(\d+)\s*$"
                   if label == "vec_fp_csr_order" else rf"^{label}: (\d+) cases\s*$")
        value = unique_match(audit, pattern, text, label + " completion")
        audit.equal(int(value[0] if isinstance(value, tuple) else value), expected_cases[1],
                    label + " case count")
        if isinstance(value, tuple):
            audit.equal(int(value[1]) > 0, True, "CSR-order checks nonzero")
    if directory.name == "numeric":
        audit.equal("[VSET_PREVIEW_FORWARD]" in text, True, "numeric preview exercised")


def check_replay(audit, directory, expected_name, seed, simv, gate_hashes):
    rows = named_rows(audit.document(directory / "summary.json"), "replay summary")
    audit.equal(set(rows), {expected_name}, "replay case set")
    result = audit.document(directory / "tests" / expected_name / "result.json")
    audit.equal(rows.get(expected_name), result, "replay summary versus result")
    audit.equal(field(result, "status"), "PASS", "replay status")
    audit.equal(field(result, "name"), expected_name, "replay name")
    audit.equal(field(result, "seed", int), seed, "replay seed")
    audit.equal(field(result, "input_errors", list), [], "replay input checks")
    for engine in ("rtl", "spike"):
        audit.equal(field(result, engine + "_returncode", int), 0, engine + " returncode")
        audit.equal(field(result, engine + "_timed_out", bool), False, engine + " timeout")
    audit.equal(field(field(result, "comparison", dict), "status") in
                {"MATCH", "TERMINAL_MATCH", "TERMINAL_TOHOST_MATCH"}, True, "scalar terminal match")
    audit.equal(field(field(result, "vector_commit", dict), "status"), "PASS", "vector match")
    audit.equal(field(field(result, "trace", dict), "status"), "VALID", "trace validity")
    run = audit.document(directory / "run.json")
    audit.equal(field(run, "status"), "COMPLETE", "replay completed")
    audit.equal(field(run, "verdict"), "PASS", "replay verdict")
    audit.equal(hash_map(field(run, "simv_image_sha256", dict)), gate_hashes, "replay runtime image")
    case = (directory / "tests" / expected_name).resolve()
    inputs = audit.document(case / "inputs.json")
    image = field(inputs, "simv", dict)
    audit.equal(hash_map(field(image, "image_sha256", dict)), gate_hashes, "replay case image")
    audit.equal(str(Path(field(image, "path", str)).resolve()), str(simv), "replay simulator path")
    binary = field(inputs, "binary", dict)
    elf = case / "input.elf"
    audit.equal(str(Path(field(binary, "path", str)).resolve()), str(elf), "replay frozen path")
    audit.equal(str(Path(field(result, "elf", str)).resolve()), str(elf), "replay result ELF path")
    audit.file_hash(elf, field(binary, "sha256"), "replay executed ELF")
    manifest = named_rows(audit.document(directory / "replay_manifest.json"), "replay manifest")
    audit.equal(set(manifest), {expected_name}, "replay frozen selection")
    selected = manifest[expected_name]
    source = Path(field(selected, "elf", str)).resolve()
    audit.equal(str(Path(field(binary, "source", str)).resolve()), str(source), "replay source")
    audit.equal(field(selected, "seed", int), seed, "manifest seed")
    audit.file_hash(source, field(binary, "sha256"), "archived replay source ELF")
    spike = field(inputs, "spike", dict)
    audit.equal(digest(field(spike, "sha256")), digest(field(run, "spike_sha256")), "Spike snapshot")
    audit.file_hash(Path(field(spike, "path", str)), field(spike, "sha256"), "current Spike executable")
    command = audit.document(case / "rtl.command.json")
    check_command(audit, field(command, "command", list), simv, elf)


def check_snapshot(audit, path):
    snapshot = audit.document(path)
    audit.equal(field(snapshot, "schema_version", int), 1, "snapshot schema")
    audit.equal(field(snapshot, "kind"), "checker_snapshot", "snapshot kind")
    audit.equal(field(snapshot, "proves_pre_run_freeze", bool), False, "snapshot provenance disclaimer")
    field(snapshot, "captured_at", str)
    field(snapshot, "timing", str)
    rows = field(snapshot, "files", list)
    if not rows:
        raise MissingEvidence("empty checker snapshot")
    paths = set()
    for row in rows:
        source = Path(field(row, "path", str)).resolve()
        if source in paths:
            raise MissingEvidence("duplicate checker snapshot path")
        paths.add(source)
        expected = field(row, "sha256")
        amendment = snapshot.get("reviewed_changes", {}).get(str(source))
        if amendment is not None:
            audit.equal(field(amendment, "before"), expected, "amendment original hash")
            field(amendment, "reason", str)
            expected = field(amendment, "after")
        audit.file_hash(source, expected, "checker hash including explicit reviewed changes")


def audit_batch(image, batch, snapshot, csr_order=None, csr_hash=None, csr_cases=20):
    audit = Audit()
    image, batch = image.resolve(), batch.resolve()
    simv = (image / "sim/simv").resolve()
    context = {}

    def gates():
        audit.equal(field(audit.document(image / "source_check.json"), "status"), "PASS", "source gate")
        gate = audit.document(image / "uvm_result.json")
        audit.equal(field(gate, "status"), "PASS", "image UVM gate")
        hashes = hash_map(field(gate, "sim_image_sha256", dict))
        if str(simv) not in hashes or not any(p.endswith(".so") for p in hashes):
            raise MissingEvidence("gate lacks launcher or runtime libraries")
        context["hashes"] = hashes
        audit.equal(digest(field(gate, "simv_sha256")), hashes[str(simv)], "gate launcher")
        files = {str(simv)} | {str(p.resolve()) for p in Path(str(simv) + ".daidir").rglob("*.so")}
        audit.equal(files, set(hashes), "current image file inventory")
        for name, hashed in hashes.items():
            audit.file_hash(Path(name), hashed, "current gated image")

    def inputs():
        manifest = audit.document(batch / "inputs.json")
        if not isinstance(manifest, dict):
            raise MissingEvidence("unsupported frozen inputs manifest")
        context["inputs"] = manifest
        audit.equal(set(manifest), set(FOCUSED), "fixed 18 focused inputs")
        for name, row in manifest.items():
            frozen = (batch / "inputs" / (name + ".elf")).resolve()
            audit.equal(str(Path(field(row, "elf", str)).resolve()), str(frozen), "frozen ELF path")
            audit.file_hash(frozen, field(row, "sha256"), "frozen manifest ELF")

    def coverage():
        bundle = audit.document(batch / "shard_manifest.json")
        context["bundle"] = bundle
        context["narrow"] = check_bundle(audit, bundle)

    def summary():
        rows = named_rows(audit.document(batch / "summary.json"), "batch summary")
        unexpected = set(rows) - EXPECTED
        audit.equal(sorted(unexpected), [], "unexpected batch tasks")
        missing = EXPECTED - set(rows)
        if missing:
            audit.issue("NOT_PROVEN", "unfinished/missing tasks: " + ", ".join(sorted(missing)))
        for name, row in rows.items():
            if name == "vstore_axi_error" and row.get("status") == "FAIL":
                audit.equal(field(row, "returncode", int), 1, name + " original checker rejection")
                # check_focused proves this was only an inappropriate read-traffic
                # requirement, using the unchanged log and a separate new report.
            else:
                audit.equal(field(row, "status"), "PASS", name + " aggregate status")
                audit.equal(field(row, "returncode", int), 0, name + " driver returncode")
            expected = batch / name / ("summary.json" if name in REPLAYS else "uvm_result.json")
            audit.equal(str(Path(field(row, "report", str)).resolve()), str(expected), name + " report path")

    audit.section("image_gate", gates)
    audit.section("checker_snapshot", lambda: check_snapshot(audit, snapshot))
    audit.section("frozen_inputs", inputs)
    audit.section("shard_manifest", coverage)
    audit.section("batch_summary", summary)
    for name in FOCUSED:
        def focused(name=name):
            record = field(context.get("inputs"), name, dict)
            narrow = None
            if name.startswith("narrow_"):
                narrow = field(context.get("narrow"), name, dict)
            check_focused(audit, batch / name, record, simv, field(context, "hashes", dict),
                          narrow, context.get("bundle"),
                          ("wide", 24) if name == "vfwcvt_int8" else None)
        audit.section(name, focused)
    for name, (case, seed) in REPLAYS.items():
        audit.section(name, lambda name=name, case=case, seed=seed: check_replay(
            audit, batch / name, case, seed, simv, field(context, "hashes", dict)))
    if csr_order is not None:
        audit.section("standalone_vec_fp_csr_order", lambda: check_focused(
            audit, csr_order, {"sha256": digest(csr_hash)}, simv,
            field(context, "hashes", dict), expected_cases=("csr", csr_cases)))
    result = audit.report()
    result.update(image=str(image), batch=str(batch), checker_snapshot=str(snapshot.resolve()),
                  audit_script_sha256=sha256(Path(__file__)),
                  standalone_csr_order=str(csr_order.resolve()) if csr_order else None)
    return result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("image", type=Path)
    parser.add_argument("batch", type=Path)
    parser.add_argument("--output", type=Path, help="New audit JSON; stdout when omitted")
    parser.add_argument("--checker-snapshot", type=Path, default=DEFAULT_SNAPSHOT)
    parser.add_argument("--csr-order", type=Path, help="Optional separate focused-run directory")
    parser.add_argument("--csr-order-sha256", help="Independently recorded expected CSR-order ELF hash")
    parser.add_argument("--csr-order-cases", type=int, default=20)
    args = parser.parse_args()
    if args.csr_order_cases <= 0:
        parser.error("--csr-order-cases must be positive")
    if args.csr_order is None and args.csr_order_sha256 is not None:
        parser.error("--csr-order-sha256 requires --csr-order")
    if args.output and args.output.exists():
        parser.error("refusing to overwrite an existing audit artifact")
    result = audit_batch(args.image, args.batch, args.checker_snapshot,
                         args.csr_order, args.csr_order_sha256, args.csr_order_cases)
    output = json.dumps(result, indent=2, sort_keys=True) + "\n"
    if args.output:
        with args.output.open("x", encoding="utf-8") as stream:
            stream.write(output)
        print(f"{result['status']}: {args.output}")
        for section in result["sections"]:
            if section["status"] != "PASS":
                print(f"  {section['name']}: {section['status']}")
    else:
        print(output, end="")
    return {"PASS": 0, "FAIL": 1, "NOT_PROVEN": 2}[result["status"]]


if __name__ == "__main__":
    raise SystemExit(main())
