"""Host-only classification tests; no builder imports or artifact access."""
import copy
import itertools
import json
import unittest

from common_variant import (
    BOTH_RVV_DECODE,
    CANDIDATE_RVV_DECODE,
    ORIGINAL_DECODERS,
    classify,
)


def candidate():
    return {
        "rvv_value_decode": True,
        "ordinary_value_decode": "unchanged production scalar decoder",
        "scope": "Same public-entry ABBA Attention; only candidate V decode uses RVV",
    }


def both():
    return {
        "rvv_value_decode": True,
        "rvv_baseline_decode": True,
        "ordinary_value_decode": "same RVV decoder as candidate",
        "scope": "Public-entry ABBA; both schedules use identical RVV V decoder",
    }


class CommonVariantTest(unittest.TestCase):
    def test_original_absent_or_false_flags(self):
        for present_value, present_baseline in itertools.product((False, True), repeat=2):
            report = {"scope": "Original six-head KV-head-0 group; public GGML mapping/runtime candidate, not model execution"}
            if present_value:
                report["rvv_value_decode"] = False
            if present_baseline:
                report["rvv_baseline_decode"] = False
            with self.subTest(report=report):
                result = classify(report)
                self.assertEqual(result["variant"], ORIGINAL_DECODERS)
                self.assertEqual(result["ordinary_value_decode"], "production scalar decoder")
                self.assertEqual(result["candidate_value_decode"], "production scalar decoder")
                self.assertIs(result["decoder_implementation_matched"], True)
        self.assertEqual(classify({})["variant"], ORIGINAL_DECODERS)

    def test_candidate_only_absent_or_false_baseline(self):
        for baseline in ({}, {"rvv_baseline_decode": False}):
            result = classify(dict(candidate(), **baseline))
            self.assertEqual(result["variant"], CANDIDATE_RVV_DECODE)
            self.assertEqual(result["ordinary_value_decode"], "production scalar decoder")
            self.assertEqual(result["candidate_value_decode"], "RVV decoder")
            self.assertIs(result["decoder_implementation_matched"], False)
            self.assertIn("Combined decoder vectorization", result["attribution"])
            self.assertIn("cannot isolate", result["fairness"])

    def test_both_rvv_equal_implementation_not_hardware_only(self):
        result = classify(both())
        self.assertEqual(result["variant"], BOTH_RVV_DECODE)
        self.assertEqual(result["ordinary_value_decode"], result["candidate_value_decode"])
        self.assertIs(result["decoder_implementation_matched"], True)
        self.assertIn("equal RVV software decode", result["attribution"])
        self.assertIn("counts and schedules may differ", result["fairness"])

    def test_exact_bool_required(self):
        for key, bad in itertools.product(
            ("rvv_value_decode", "rvv_baseline_decode"),
            (0, 1, 0.0, 1.0, "0", "1", "true", "False", None, [], {}),
        ):
            for base in ({}, candidate(), both()):
                with self.subTest(key=key, bad=bad, base=base), self.assertRaises(ValueError):
                    classify(dict(base, **{key: bad}))

    def test_baseline_only_rejected(self):
        for base in ({}, {"rvv_value_decode": False}):
            for label in (None, "same RVV decoder as candidate", "unchanged production scalar decoder"):
                report = dict(base, rvv_baseline_decode=True)
                if label is not None:
                    report["ordinary_value_decode"] = label
                with self.subTest(report=report), self.assertRaises(ValueError):
                    classify(report)

    def test_original_rejects_any_decoder_label(self):
        for label in (None, False, "", "unchanged production scalar decoder", "same RVV decoder as candidate"):
            with self.subTest(label=label), self.assertRaises(ValueError):
                classify({"ordinary_value_decode": label})

    def test_rvv_requires_exact_decoder_label(self):
        for base in (candidate(), both()):
            expected = base["ordinary_value_decode"]
            missing = dict(base)
            del missing["ordinary_value_decode"]
            with self.assertRaises(ValueError):
                classify(missing)
            for label in (None, True, 1, "", expected + " ", expected.upper(),
                          "unchanged production scalar decoder" if base.get("rvv_baseline_decode") else "same RVV decoder as candidate"):
                with self.subTest(base=base, label=label), self.assertRaises(ValueError):
                    classify(dict(base, ordinary_value_decode=label))

    def test_scope_and_variant_cannot_mislabel_configuration(self):
        examples = ({}, candidate(), both())
        variants = (ORIGINAL_DECODERS, CANDIDATE_RVV_DECODE, BOTH_RVV_DECODE)
        for base, variant in zip(examples, variants):
            self.assertEqual(classify(dict(base, variant=variant))["variant"], variant)
            for wrong in variants:
                if wrong != variant:
                    with self.subTest(base=base, wrong=wrong), self.assertRaises(ValueError):
                        classify(dict(base, variant=wrong))
            for key in ("scope", "variant"):
                for label in (None, True, "", "model speedup", "hardware-only speedup"):
                    with self.subTest(base=base, key=key, label=label), self.assertRaises(ValueError):
                        classify(dict(base, **{key: label}))
        with self.assertRaises(ValueError):
            classify(dict(candidate(), scope=both()["scope"]))
        with self.assertRaises(ValueError):
            classify(dict(both(), scope=candidate()["scope"]))

    def test_non_object_rejected(self):
        for value in (None, False, 1, "ORIGINAL_DECODERS", [], ()):
            with self.subTest(value=value), self.assertRaises(ValueError):
                classify(value)

    def test_pure_json_annotations_and_no_acceptance_inference(self):
        for base in ({}, candidate(), both()):
            report = dict(base, state="COMMON_ENTRY_BUILT_NOT_EXECUTED",
                          artifact_sha256={"file": "hash"}, elapsed_cycles=-1)
            before = copy.deepcopy(report)
            result = classify(report)
            self.assertEqual(report, before)
            self.assertEqual(json.loads(json.dumps(result, allow_nan=False)), result)
            self.assertIs(result["hardware_only_claim_supported"], False)
            self.assertIs(result["model_speedup_claim_supported"], False)
            self.assertIn("not model execution", result["scope"])
            self.assertNotIn("state", result)
            self.assertNotIn("elapsed_cycles", result)
            result["variant"] = "mutated"
            self.assertNotEqual(classify(report)["variant"], "mutated")


if __name__ == "__main__":
    unittest.main()
