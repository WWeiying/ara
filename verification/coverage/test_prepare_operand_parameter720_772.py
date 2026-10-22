"""Exact compiled/native reuse and protected-complement regressions; no EDA."""
import copy
import json
from pathlib import Path
import tempfile
import unittest

import prepare_operand_parameter720_772 as p


class Parameter720(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.six = json.loads(p.old.SIX.read_bytes())
        cls.design = p.old.shared.shared.Design(p.BUILD / "sim/simv.vdb")
        cls.scope = next(s for s in cls.six["groups"]["operand"]["plan"]["scopes"] if s.endswith("st_mask_a"))
        cls.definition = cls.design.definition(cls.scope, "branch")
        cls.signature = cls.design.definition(cls.scope, "tgl").get("name")
        cls.records = p.native.parse_native((p.CAPTURE / "first.el").read_bytes())
        cls.qualified = {q["scope"] + "|" + q["point"]: q for q in cls.six["groups"]["operand"]["qualified"]}
        cls.queue, cls.stage, cls.package = [(p.ROOT / n).read_text() for n in (
            "hardware/src/lane/operand_queue.sv", "hardware/src/lane/operand_queues_stage.sv", "hardware/include/ara_pkg.sv")]
        cls.inventory = cls.six["groups"]["operand"]["plan"]["scopes"][cls.scope]

    def bind(self, **changes):
        args = dict(scope=self.scope, definition=copy.deepcopy(self.definition),
                    bitmap=dict(width=101, checksum="1417162425", bits="0"),
                    inventory=copy.deepcopy(self.inventory), qualified=copy.deepcopy(self.qualified),
                    records=copy.deepcopy(self.records), signature=self.signature, queue=self.queue)
        args.update(changes)
        return p.bind_scope(**args)

    def test_actual_shape_native_60_and_41(self):
        targets, protected = self.bind()
        self.assertEqual((len(targets), len(protected)), (60, 41))
        self.assertEqual({x["raw_index"] for x in targets + protected}, set(range(101)))
        self.assertEqual(len(p.native.parse_native("".join(x["native_raw"] for x in targets).encode())), 60)

    def test_actual_source_contract(self):
        p.source_contract(self.queue, self.stage, self.package)

    def test_default_enabled_rejected(self):
        with self.assertRaises(ValueError):
            p.source_contract(self.queue.replace("SupportIntExt2      = 1'b0", "SupportIntExt2      = 1'b1"), self.stage, self.package)

    def test_none_enum_mutation_rejected(self):
        with self.assertRaises(ValueError):
            p.source_contract(self.queue, self.stage, self.package.replace("FPUSupportNone             = 6'b000000", "FPUSupportNone             = 6'b000001"))

    def test_predicate_bit_mutation_rejected(self):
        with self.assertRaises(ValueError):
            p.source_contract(self.queue, self.stage, self.package.replace("return e[1];", "return e[2];"))

    def test_override_rejected(self):
        stage = self.stage.replace(") i_operand_queue_st_mask_a (", ", .SupportIntExt2(1'b1)) i_operand_queue_st_mask_a (")
        with self.assertRaises(ValueError):
            p.source_contract(self.queue, stage, self.package)

    def test_compiled_parameter_enabled_rejected(self):
        with self.assertRaises(ValueError):
            self.bind(signature=self.signature.replace("SupportIntExt2=0", "SupportIntExt2=1"))

    def test_unknown_scope_rejected(self):
        with self.assertRaises(ValueError):
            self.bind(scope=self.scope.replace("st_mask_a", "mask_b"))

    def test_hit_candidate_rejected(self):
        index = self.inventory["targets"][0]["raw_index"]
        with self.assertRaises(ValueError):
            self.bind(bitmap=dict(width=101, checksum="1417162425", bits=hex(1 << (100-index))))

    def test_protected_hits_retained(self):
        index = self.inventory["protected"][0]["raw_index"]
        _, protected = self.bind(bitmap=dict(width=101, checksum="1417162425", bits=hex(1 << (100-index))))
        self.assertEqual(sum(x["hit772"] for x in protected), 1)

    def test_missing_protection_rejected(self):
        inv = copy.deepcopy(self.inventory)
        inv["protected"].pop()
        with self.assertRaises(ValueError):
            self.bind(inventory=inv)

    def test_duplicate_protection_rejected(self):
        inv = copy.deepcopy(self.inventory)
        inv["protected"][0] = inv["protected"][1]
        with self.assertRaises(ValueError):
            self.bind(inventory=inv)

    def test_wrong_selector_rejected(self):
        inv = copy.deepcopy(self.inventory)
        inv["targets"][0]["selector"] += "0"
        with self.assertRaises(ValueError):
            self.bind(inventory=inv)

    def test_native_signature_checksum_expression_rejected(self):
        key = self.scope + "|" + next(q["point"] for q in self.qualified.values() if q["scope"] == self.scope)
        for field, value in (("signature", "wrong"), ("checksum", ["0", "1417162425"]),
                             ("expression", "cmd.conv"), ("annotation", "unreviewed")):
            with self.subTest(field=field):
                records = copy.deepcopy(self.records)
                records[key][field] = value
                with self.assertRaises(ValueError):
                    self.bind(records=records)

    def test_source_span_mutation_rejected(self):
        with self.assertRaises(ValueError):
            self.bind(queue=self.queue.replace("if (SupportNtrVal || SupportReduct)", "if (SupportNtrVal && SupportReduct)"))

    def test_false_arm_and_default_not_proven(self):
        for text, vector in (("SupportIntExt2", "0"), ("cmd.conv", "1"), ("default", "1")):
            self.assertEqual(p.old.guards(dict(native_vector=dict(vector=vector),
                expressions=[dict(exprstr=text, index="1", id="336")])), [])

    def test_reader_conflicting_pin_rejected(self):
        reader = p.Reader()
        reader.read(p.old.SIX, p.old.SIX_SHA)
        with self.assertRaises(ValueError):
            reader.read(p.old.SIX, "0" * 64)

    def test_streamed_unchanged_and_changed_rejected(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "input"
            path.write_bytes(b"original")
            reader = p.Reader()
            reader.read(path)
            reader.unchanged()
            path.write_bytes(b"changed")
            with self.assertRaises(ValueError):
                reader.unchanged()


if __name__ == "__main__":
    unittest.main()
