"""Offline Branch720 integration contract, not a report runner or approval.

Targets have one source: the frozen raw772 subset audit. Existing policies are
opaque, immutable native directives; no six707 target list is imported here.
The next report consumer must supply real count evidence before asserting the
720 official Branch denominator delta. Percentages are never inverted.
"""
import argparse
from collections import Counter
import csv
import hashlib
import io
import json
from pathlib import Path
import re

import prepare_operand_parameter720_772 as subset

OUT, require = subset.OUT, subset.require
AUDIT = OUT / "operand-parameter720-native-reuse-772-agent-20261007-01/audit.json"
AUDIT_SHA = "bf5cb5f4ff4e1b9e1dd912047222693675fe5a0e5522c5de46740409edeb32c6"
STAGES = ("raw", "applied", "after_root", "reset", "reloaded", "final")
ACTIVE = {"applied", "after_root", "reloaded"}


def native_inventory(blob):
    """Preserve opaque existing directives, machine context and whole observers.

    This is an integration difference checker, not a replacement for the existing
    per-policy parsers. Unknown directives fail; annotation changes cannot hide
    a coordinate change. Repeated blocks may legitimately share an owner.
    """
    text = blob.decode("ascii")
    require(not text or text.endswith("\n"), "Truncated native EL")
    require(all(c in "\n\r\t" or 32 <= ord(c) <= 126 for c in text), "Nonprintable native EL")
    inventory = Counter()
    branches = []
    for block in re.split(r"(?m)(?=^CHECKSUM:)", text):
        if not block.strip():
            continue
        checksums = re.findall(r'^CHECKSUM: *"([0-9]+(?: [0-9]+)*)"$', block, re.M)
        scopes = re.findall(r"^INSTANCE: *(\S+)$", block, re.M)
        require(len(checksums) == len(scopes) == 1, "Missing/ambiguous native header")
        checksum, scope = checksums[0], scopes[0]
        machine = None
        directives = 0
        for line in block.splitlines():
            if not line or line.startswith(("CHECKSUM:", "INSTANCE:", "ANNOTATION:", "//")):
                continue
            require(line.startswith(("Toggle ", "Fsm ", "Transition ", "State ", "Branch ")),
                    "Unknown/mixed native directive")
            directives += 1
            if line.startswith("Branch "):
                branches.append((scope, checksum, line))
            else:
                if line.startswith("Fsm "):
                    machine = line
                require(not line.startswith(("State ", "Transition ")) or machine is not None,
                        "FSM leaf without machine")
                inventory[(scope, checksum, machine if line.startswith(("State ", "Transition ")) else "", line)] += 1
        if not directives:
            # Whole-module observers exclude more than one metric; retain exact
            # identity and forbid observer ancestors of any Branch720 scope.
            inventory[(scope, checksum, "", "WHOLE_SCOPE")] += 1
    return inventory, branches


def assert_no_overlap(existing, audit):
    inventory, branches = native_inventory(existing)
    require(not branches, "Existing canonical Branch requires a separate overlap review")
    scopes = set(audit["scopes"])
    for scope, _, _, directive in inventory:
        if directive == "WHOLE_SCOPE":
            require(not any(s == scope or s.startswith(scope + ".") for s in scopes),
                    "Whole-scope observer overlaps Branch720")
    return inventory


def validate_subset(audit, candidate):
    require(audit["schema"] == "OPERAND_PARAMETER720_RAW772_NATIVE_REUSE_PREPARATION_V1" and
            audit["status"] == "EXACT720_HISTORICAL_NATIVE_REUSE_ELIGIBLE_NOT_APPLIED" and
            audit["formal_tests"] == 772 and audit["application_approval"] is False and
            audit["other_707_targets_included"] is False and audit["excluded_metrics"] == ["Branch"],
            "Not the reviewed sole target source")
    require(len(audit["scopes"]) == 12 and len(audit["targets"]) == 720 and len(audit["protected"]) == 492,
            "Wrong subset population")
    expected = {}
    for scope, stats in audit["scopes"].items():
        require(stats["targets"] == 60 and stats["protected"] == 41, "Wrong scope partition")
        require(re.fullmatch(r"ara_tb\.dut\.i_ara_soc\.i_system\.i_ara\.gen_lanes\[[0-3]\]"
                            r"\.i_lane\.i_operand_queues\.i_operand_queue_(st_mask_a|slide_addrgen_a|mask_m)", scope),
                "Unexpected scope")
        owned = [p for p in audit["targets"] + audit["protected"] if p["scope"] == scope]
        require(len(owned) == 101 and {p["raw_index"] for p in owned} == set(range(101)) and
                len({p["selector"] for p in owned}) == 101, "Incomplete/duplicate complement")
    for t in audit["targets"]:
        require(t["scope"] in audit["scopes"] and t["hit772"] is False and t["source_proof"],
                "Hit/unproved target")
        require(all(p["constant_value"] == 0 and p["demanded_value"] == "1" for p in t["source_proof"]),
                "Not a false parameter TRUE-body proof")
        n = t["native"]
        key = t["scope"] + "|" + n["point"]
        require(key not in expected and n["scope"] == t["scope"], "Duplicate/native owner mismatch")
        expected[key] = n
    require(all(p["scope"] in audit["scopes"] for p in audit["protected"]), "Extra protection scope")
    require(subset.native.parse_native(candidate) == expected, "Candidate differs from frozen native subset")
    return expected


def validate_population(audit, manifest_path, manifest_seal, reader):
    """Explicit baseline only: no permissive successor schema guessing."""
    require(manifest_path == subset.BASE / "admission-manifest.json" and manifest_seal == subset.BASE_SHA,
            "Unreviewed successor: create an explicit fresh population contract")
    manifest = reader.json(manifest_path, manifest_seal)
    require(manifest["coverage_admitted"] is True and
            manifest["schema"] == "SCALAR_FPU_BACKPRESSURE_HISTORICAL772_ADMISSION_V1", "Nonformal population")
    before_path = manifest_path.parent / "combined-bits.json"
    before = reader.json(before_path, manifest["output_pins"][str(before_path)])
    inputs = manifest_path.parent / "combined-inputs.txt"
    membership = reader.read(inputs, manifest["output_pins"][str(inputs)]).decode().splitlines()
    require(len(before["tests"]) == len(set(before["tests"])) == 772 and
            membership == [str(subset.BUILD / "sim/simv.vdb"), *before["tests"]], "Nonexact full membership")
    for target in audit["targets"]:
        b = before["metrics"]["branch"][target["scope"]]
        require(b["width"] == 101 and b["checksum"] in (None, "1417162425") and
                not (int(b["bits"], 16) & (1 << (100-target["raw_index"]))), "Fresh target hit/shape drift")
    return dict(population=772, manifest=str(manifest_path), manifest_sha256=manifest_seal,
                membership_sha256=reader.pins[str(inputs)], design=before["design"],
                requires_explicit_rebind_for_successor=True)


def check_stage_el(blob, stage, existing, expected):
    require(stage in STAGES, "Unknown stage")
    if stage not in ACTIVE:
        require(blob == b"", "Global raw/reset/final exclusions remain")
        return
    baseline, old_branch = native_inventory(existing)
    require(not old_branch, "Baseline Branch overlap")
    got, branches = native_inventory(blob)
    require(got == baseline, "Existing policies changed/missing/extra")
    actual = Counter(branches)
    wanted = Counter((n["scope"], " ".join(n["checksum"]), n["directive"]) for n in expected.values())
    require(actual == wanted and sum(actual.values()) == 720, "Applied native Branch not exact720")


def check_stage_rows(blob, stage, contract):
    require(stage in STAGES, "Unknown stage")
    reader = csv.DictReader(io.StringIO(blob.decode("ascii")), delimiter="\t")
    require(reader.fieldnames == ["scope", "coordinate", "meta", "path", "excluded"], "Wrong audit columns")
    expected = {(p["scope"], p["selector"]): p for p in contract["branch_inventory"]}
    got = set()
    for row in reader:
        key = row["scope"], row["coordinate"]
        require(key in expected and key not in got and set(row) == set(reader.fieldnames), "Extra/duplicate/malformed row")
        p = expected[key]
        require(row["meta"] == p["meta"] and row["path"] == p["path"], "Native metadata/alias drift")
        require(row["excluded"] == ("1" if stage in ACTIVE and p["target"] else "0"),
                "Protected or target exclusion differs")
        got.add(key)
    require(got == set(expected), "Missing protected/target row")


def check_official_counts(counts, contract):
    """Normalized exact-count gate, NOT a native API adapter or evidence receipt.

    The future report exporter must separately bind these values to actual native
    count artifacts/API, scopes and post-root handles. Calling this with fixtures
    or percentage-derived values never establishes official_count_verified.
    """
    require(set(counts) == {"raw", "canonical", "applied", "after_root", "reset", "reloaded", "final"},
            "Incomplete official count stages")
    for rows in counts.values():
        require(set(rows) == set(contract["scopes"]) | {"SYSTEM"}, "Count scopes differ")
        for row in rows.values():
            require(set(row) == {"hit", "total"} and all(type(v) is int and v >= 0 for v in row.values()) and
                    row["hit"] <= row["total"], "Not exact integer counts (no bool/percent)")
    for scope in contract["scopes"]:
        hits = contract["protected_hits"][scope]
        for stage in ("raw", "canonical", "reset", "final"):
            require(counts[stage][scope] == dict(hit=hits, total=101), "Local raw/canonical/reset counts differ")
        for stage in ACTIVE:
            require(counts[stage][scope] == dict(hit=hits, total=41), "Local Branch denominator not -60")
    base, applied = counts["canonical"]["SYSTEM"], counts["applied"]["SYSTEM"]
    require(base["total"] - applied["total"] == 720 and base["hit"] == applied["hit"],
            "System canonical-to-added Branch delta not exactly720/zero numerator")
    require(counts["after_root"]["SYSTEM"] == counts["reloaded"]["SYSTEM"] == applied and
            counts["raw"]["SYSTEM"] == counts["reset"]["SYSTEM"] == counts["final"]["SYSTEM"],
            "Root refresh/reload/reset global counts differ")


def prepare(output):
    require(output.parent == OUT and output.resolve() == output and not output.exists(), "Fresh direct output only")
    reader = subset.Reader()
    audit = reader.json(AUDIT, AUDIT_SHA)
    for path, seal in audit["pins"].items():
        reader.read(path, seal)
    candidate_path = AUDIT.parent / "candidate720.el"
    candidate = reader.read(candidate_path, audit["output_pins"][str(candidate_path)])
    expected = validate_subset(audit, candidate)
    canonical = subset.CURRENT_ELS[-1]
    old_el = reader.read(canonical, audit["canonical_EL_observation"][str(canonical)]["sha256"])
    assert_no_overlap(old_el, audit)
    population = validate_population(audit, subset.BASE / "admission-manifest.json", subset.BASE_SHA, reader)
    states_path = subset.CAPTURE / "states_before.tsv"
    states = csv.DictReader(io.StringIO(reader.read(states_path, audit["pins"][str(states_path)]).decode()), delimiter="\t")
    require(states.fieldnames == ["scope", "coordinate", "meta", "path", "excluded"], "Historical audit columns differ")
    identities = {}
    for row in states:
        key = row["scope"], row["coordinate"]
        require(key not in identities and row["excluded"] == "0", "Historical identity duplicate/excluded")
        identities[key] = row
    inventory = []
    for is_target, rows in ((True, audit["targets"]), (False, audit["protected"])):
        for point in rows:
            key = point["scope"], point["selector"]
            require(key in identities, "Missing observed native complement identity")
            n = identities[key]
            inventory.append(dict(scope=key[0], selector=key[1], raw_index=point["raw_index"],
                                  target=is_target, meta=n["meta"], path=n["path"]))
    combined = old_el + candidate
    check_stage_el(combined, "applied", old_el, expected)
    for path in (Path(__file__), Path(__file__).with_name("test_branch720_next_report_contract.py")):
        reader.read(path)
    contract = dict(schema="BRANCH720_NEXT_REPORT_INTEGRATION_CONTRACT_V1", status="PREPARED_NO_EDA_NOT_APPLICATION",
                    population=population, sole_target_source=dict(path=str(AUDIT), sha256=AUDIT_SHA),
                    canonical_EL=dict(path=str(canonical), sha256=reader.pins[str(canonical)], untouched=True),
                    targets=720, protected=492, scopes=sorted(audit["scopes"]), branch_inventory=inventory,
                    protected_hits={s: x["protected_hits"] for s, x in audit["scopes"].items()},
                    overlap=0, expected_branch_denominator_delta=720, expected_branch_hit_delta=0,
                    staged_checks=list(STAGES), native_signatures_reused=True, fresh_DVE_run=False,
                    official_count_verified=False, official_percentage=None, application_approval=False,
                    other_metrics_and_states_retained=True, other_707_targets_included=False,
                    counts_gate_requires_actual_native_API_artifacts=True,
                    full_protection_audits_require_existing_policy_verifier=True, pins=reader.pins)
    reader.unchanged()
    output.mkdir()
    merged = output / "proposed-combined.el"
    merged.write_bytes(combined)
    contract["output_pins"] = {str(merged): subset.sha(combined)}
    blob = (json.dumps(contract, sort_keys=True, indent=2) + "\n").encode()
    (output / "contract.json").write_bytes(blob)
    return dict(output=str(output), seal=subset.sha(blob), status=contract["status"], targets=720, protected=492)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, required=True)
    print(json.dumps(prepare(parser.parse_args().output.absolute())))
