"""Integration differences, exact native complement and denominator gates."""
import copy
import csv
import io
import json
import unittest

import branch720_next_report_contract as c


class Contract(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.audit = json.loads(c.AUDIT.read_bytes())
        cls.candidate = (c.AUDIT.parent / "candidate720.el").read_bytes()
        cls.expected = c.validate_subset(cls.audit, cls.candidate)
        cls.existing = b'CHECKSUM: "1 2"\nINSTANCE: ara_tb.safe\nANNOTATION: "kept"\nToggle x "logic x[7:0]"\n'
        cls.inventory = []
        for target, points in ((True, cls.audit["targets"]), (False, cls.audit["protected"])):
            for p in points:
                sid, vid = p["selector"].split(",")
                meta = "Branch%s.%s" % (sid, vid)
                cls.inventory.append(dict(scope=p["scope"], selector=p["selector"],
                                          target=target, meta=meta, path="Item%s.%s" % (sid, meta)))
        cls.contract = dict(branch_inventory=cls.inventory, scopes=list(cls.audit["scopes"]),
                            protected_hits={s: x["protected_hits"] for s, x in cls.audit["scopes"].items()})

    def count_fixture(self):
        result = {}
        for stage in ("raw", "canonical", "applied", "after_root", "reset", "reloaded", "final"):
            result[stage] = {s: dict(hit=n, total=41 if stage in c.ACTIVE else 101)
                             for s, n in self.contract["protected_hits"].items()}
            # Whole observers make raw->canonical differ independently of Branch720.
            result[stage]["SYSTEM"] = (dict(hit=900, total=1280) if stage in c.ACTIVE else
                                       dict(hit=900, total=2000) if stage == "canonical" else
                                       dict(hit=910, total=2050))
        return result

    def rows(self, stage, mutation=None):
        result = []
        for p in self.inventory:
            result.append(dict(scope=p["scope"], coordinate=p["selector"], meta=p["meta"], path=p["path"],
                               excluded="1" if stage in c.ACTIVE and p["target"] else "0"))
        if mutation:
            mutation(result)
        stream = io.StringIO()
        writer = csv.DictWriter(stream, fieldnames=["scope", "coordinate", "meta", "path", "excluded"], delimiter="\t")
        writer.writeheader()
        writer.writerows(result)
        return stream.getvalue().encode("ascii")

    def test_actual_frozen_subset_exact(self):
        self.assertEqual(len(self.expected), 720)
        self.assertEqual(c.subset.sha(c.AUDIT.read_bytes()), c.AUDIT_SHA)

    def test_extra_old707_target_rejected(self):
        audit = copy.deepcopy(self.audit)
        audit["targets"].append(audit["targets"][0])
        with self.assertRaises(ValueError):
            c.validate_subset(audit, self.candidate)

    def test_missing_complement_rejected(self):
        audit = copy.deepcopy(self.audit)
        audit["protected"].pop()
        with self.assertRaises(ValueError):
            c.validate_subset(audit, self.candidate)

    def test_target_hit_or_false_arm_rejected(self):
        for mutate in (lambda a: a["targets"][0].update(hit772=True),
                       lambda a: a["targets"][0]["source_proof"][0].update(demanded_value="0")):
            audit = copy.deepcopy(self.audit)
            mutate(audit)
            with self.assertRaises(ValueError):
                c.validate_subset(audit, self.candidate)

    def test_native_signature_changed_rejected(self):
        with self.assertRaises(ValueError):
            c.validate_subset(self.audit, self.candidate.replace(b'Branch 4 "', b'Branch 44 "', 1))

    def test_unknown_scope_rejected(self):
        audit = copy.deepcopy(self.audit)
        key = next(iter(audit["scopes"]))
        audit["scopes"][key + ".injected"] = audit["scopes"].pop(key)
        with self.assertRaises(ValueError):
            c.validate_subset(audit, self.candidate)

    def test_whole_scope_overlap_rejected(self):
        scope = next(iter(self.audit["scopes"]))
        for scope in (scope, scope.rsplit(".", 1)[0]):
            blob = ('CHECKSUM: "1"\nINSTANCE: ' + scope + '\nANNOTATION: "observer"\n').encode()
            with self.assertRaises(ValueError):
                c.assert_no_overlap(blob, self.audit)

    def test_existing_branch_rejected(self):
        with self.assertRaises(ValueError):
            c.assert_no_overlap(self.existing + self.candidate, self.audit)

    def test_nonbranch_retained_all_stages(self):
        for stage in c.STAGES:
            c.check_stage_el(self.existing + self.candidate if stage in c.ACTIVE else b"",
                             stage, self.existing, self.expected)

    def test_canonical_modified_rejected(self):
        blob = self.existing.replace(b'logic x[7:0]', b'logic x[6:0]') + self.candidate
        with self.assertRaises(ValueError):
            c.check_stage_el(blob, "applied", self.existing, self.expected)

    def test_missing_duplicate_extra_branch_rejected(self):
        for blob in (self.existing, self.existing + self.candidate + self.candidate,
                     self.existing + self.candidate.replace(b'Branch 4 "', b'Branch 999 "', 1)):
            with self.assertRaises(ValueError):
                c.check_stage_el(blob, "applied", self.existing, self.expected)

    def test_unknown_line_condition_default_rejected(self):
        for line in ('Line 1', 'Condition 1', 'MISSING_ELSE 1', 'DEFAULT 1'):
            with self.assertRaises(ValueError):
                c.native_inventory(self.existing + line.encode() + b"\n")

    def test_dirty_reset_rejected(self):
        for stage in ("raw", "reset", "final"):
            with self.assertRaises(ValueError):
                c.check_stage_el(self.existing, stage, self.existing, self.expected)

    def test_full_complement_six_stage_audit(self):
        for stage in c.STAGES:
            c.check_stage_rows(self.rows(stage), stage, self.contract)

    def test_protected_excluded_rejected(self):
        def mutate(rows):
            rows[-1]["excluded"] = "1"
        with self.assertRaises(ValueError):
            c.check_stage_rows(self.rows("applied", mutate), "applied", self.contract)

    def test_missing_duplicate_meta_alias_rejected(self):
        for mutate in (lambda rows: rows.pop(), lambda rows: rows.append(rows[0]),
                       lambda rows: rows[0].update(meta="MISSING_ELSE999.1"),
                       lambda rows: rows[0].update(path="ItemWrong")):
            with self.assertRaises(ValueError):
                c.check_stage_rows(self.rows("reloaded", mutate), "reloaded", self.contract)

    def test_count_delta720_but_raw_delta_other(self):
        c.check_official_counts(self.count_fixture(), self.contract)

    def test_denominator_719_or_721_rejected(self):
        for delta in (-1, 1):
            fixture = self.count_fixture()
            fixture["applied"]["SYSTEM"]["total"] += delta
            with self.assertRaises(ValueError):
                c.check_official_counts(fixture, self.contract)

    def test_numerator_changed_rejected(self):
        fixture = self.count_fixture()
        fixture["applied"]["SYSTEM"]["hit"] -= 1
        with self.assertRaises(ValueError):
            c.check_official_counts(fixture, self.contract)

    def test_bool_percent_missing_stage_rejected(self):
        for value in (True, "80.00%", 80.0):
            fixture = self.count_fixture()
            fixture["raw"]["SYSTEM"]["hit"] = value
            with self.assertRaises(ValueError):
                c.check_official_counts(fixture, self.contract)
        fixture = self.count_fixture()
        fixture.pop("canonical")
        with self.assertRaises(ValueError):
            c.check_official_counts(fixture, self.contract)

    def test_root_refresh_local_counts_changed_rejected(self):
        fixture = self.count_fixture()
        fixture["after_root"][next(iter(self.contract["scopes"]))]["total"] = 42
        with self.assertRaises(ValueError):
            c.check_official_counts(fixture, self.contract)

    def test_unreviewed_population_cannot_be_relabeled(self):
        with self.assertRaises(ValueError):
            c.validate_population(self.audit, c.subset.BASE / "admission-manifest.json", "0" * 64, c.subset.Reader())


if __name__ == "__main__":
    unittest.main()
