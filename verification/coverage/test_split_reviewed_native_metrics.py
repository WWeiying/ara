import hashlib
from pathlib import Path
import unittest

import split_reviewed_native_metrics as split

BRANCH = (b'CHECKSUM: "10 20"\nINSTANCE: dut.gen_lanes[0].i_lane.i_operand_requester\n'
          b'ANNOTATION: "UNIT TEST ONLY"\nBranch 1 "30" "state" (7) "state 1"\n')
COND = (b'CHECKSUM: "10 40"\nINSTANCE: dut.gen_lanes[0].i_lane.i_operand_requester\n'
        b'ANNOTATION: "UNIT TEST ONLY"\nCondition 2 "50" "replay 1 -1" (2 "1")\n')


class MetricSplitTests(unittest.TestCase):
    def setUp(self):
        self.sources = dict(branch=BRANCH, cond=COND)

    def reject(self, raw):
        with self.assertRaises(ValueError):
            split.split_exact(raw, self.sources)

    def test_same_scope_branch_and_condition_separate(self):
        self.assertEqual(split.split_exact(COND+BRANCH,self.sources),self.sources)

    def test_unknown_scope(self):
        self.reject(BRANCH+COND.replace(b'dut.gen_lanes',b'other.gen_lanes'))

    def test_scope_injection(self):
        self.reject(BRANCH+COND.replace(b'dut.gen_lanes',b'dut;evil.gen_lanes'))

    def test_unknown_metric_checksum(self):
        self.reject(BRANCH+COND.replace(b'10 40',b'10 41'))

    def test_wrong_module_checksum(self):
        self.reject(BRANCH+COND.replace(b'10 40',b'11 40'))

    def test_unknown_type(self):
        self.reject(BRANCH+COND.replace(b'Condition 2',b'Toggle 2'))

    def test_known_type_wrong_checksum_namespace(self):
        self.reject(BRANCH+COND.replace(b'10 40',b'10 20'))

    def test_mixed_types_same_block(self):
        self.reject(BRANCH+COND+b'Branch 1 "30" "state" (7) "state 1"\n')

    def test_changed_point_or_vector(self):
        self.reject(BRANCH+COND.replace(b'(2 "1")',b'(9 "1")'))

    def test_missing_block(self):
        self.reject(BRANCH)

    def test_duplicate_block(self):
        self.reject(BRANCH+COND+COND)

    def test_whole_instance(self):
        self.reject(BRANCH+b'CHECKSUM: "10 40"\nINSTANCE: dut.gen_lanes[0].i_lane.i_operand_requester\n')

    def test_ambiguous_reviewed_metric_owner(self):
        with self.assertRaises(ValueError):
            split.split_exact(BRANCH,dict(a=BRANCH,b=BRANCH))

    def test_actual_reviewed24_same_scopes_as_six_branch(self):
        root=Path(__file__).resolve().parents[2]
        cond=(root/'verification/coverage/waivers/mask_store_snapshot.el').read_bytes()
        branch=(root/'verification/out/branch-combo-six-policy-population-724-parent-20261006-01/combined.el').read_bytes()
        self.assertEqual(hashlib.sha256(cond).hexdigest(),
            'c11b89f8ae115a50c83bd409d57d003c768991ae589656c021c5209cdb9f44a8')
        self.assertEqual(hashlib.sha256(branch).hexdigest(),
            '3e2345b2bc906413c1baf65dd912a15faa70d55276e7c0cd772585a591bbca7f')
        self.assertEqual(sum(line.startswith(b'Condition ') for line in cond.splitlines()),24)
        cond_scopes={k[0] for k,_ in split.blocks(cond)}
        branch_scopes={k[0] for k,_ in split.blocks(branch)}
        self.assertEqual(len(cond_scopes),4)
        self.assertTrue(cond_scopes <= branch_scopes)
        self.assertEqual(split.split_exact(branch+cond,dict(six=branch,snapshot=cond)),
                         dict(six=branch,snapshot=cond))


if __name__=='__main__':
    unittest.main()
