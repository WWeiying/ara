"""Independent host contracts using sealed775 and real native family receipts.

No report helper edits, native launch, source approvals, or population apply.
"""
import copy
import hashlib
import json
from pathlib import Path
import unittest
import latest_full_aggregation_contract as c

OUT = Path(__file__).resolve().parents[1] / 'out'
FORMAL = OUT / 'vmacc-offline-admitted775-parent-20261007-01'
FORMAL_SHA = '59d67f7d5088baefaa498eda1d8e0f607e0eaf87945cc79a5f83607f8d679a13'


def bound(path, sha):
    raw = path.read_bytes()
    if hashlib.sha256(raw).hexdigest() != sha:
        raise ValueError('Sealed identity differs: ' + str(path))
    return json.loads(raw)


class Real775Tests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.m = bound(FORMAL / 'admission-manifest.json', FORMAL_SHA)
        path = FORMAL / 'combined-bits.json'
        cls.bits = bound(path, cls.m['output_pins'][str(path)])
        cls.previous = json.loads((OUT / 'sv39-fault-alternating-offline-admitted-773-agent-20261007-01/combined-bits.json').read_bytes())
        cls.final = dict(coverage_admitted=True, design=cls.bits['design'], tests=cls.bits['tests'],
                         metric_instances=sum(map(len, cls.bits['metrics'].values())))
        cls.mfpu = bound(OUT / 'mfpu272-five-phase-prepared-agent-20261007-01/capture-result.json',
                        '5b6ec22297d34ce9e7a944c0c9c677bca25d0856c1e39f4c82854e6cfa3e8dc8')
        cls.rvh = bound(OUT / 'rvh0-exception60-v5-offline-completion-receipt-agent-20261007-01.json',
                       '347dc22e6a8740b966bb324282b940ba94c299006903e83e57f15b51d5506372')

    def population(self, value):
        result = c.population_gate(value, self.previous['tests'], self.previous['design'], FORMAL_SHA)
        if result['population'] != 775 or value['tests'] != self.bits['tests']:
            raise ValueError('Exact selected formal775 ledger required')
        return result

    def test_real775_population_not_percentage_or_launch(self):
        result = self.population(self.final)
        self.assertEqual(result['population'], 775)
        self.assertFalse(result['percentage_verified'])
        self.assertFalse(result['official_denominator_verified'])
        self.assertFalse(result['launch_authorized'])

    def test_missing_ITLB_cannot_keep775_claim(self):
        changed = copy.deepcopy(self.final)
        changed['tests'].pop(-2)
        # The generic gate admits explicitly chosen774 too; the exact775
        # consumer additionally enforces its sealed complete ledger.
        with self.assertRaises(ValueError): self.population(changed)

    def test_wrong_prefix(self):
        changed = copy.deepcopy(self.final); changed['tests'][0] = '/wrong/code.vdb'
        with self.assertRaises(ValueError): self.population(changed)

    def test_wrong_design(self):
        changed = copy.deepcopy(self.final); changed['design'] = {}
        with self.assertRaises(ValueError): self.population(changed)

    def test_incomplete_native_shape(self):
        changed = dict(self.final, metric_instances=6161)
        with self.assertRaises(ValueError): self.population(changed)

    def test_complete_native_receipts(self):
        c.receipt_gate(self.mfpu, self.rvh)

    def test_readonly_MFPU_binding_not_five_stage_qualification(self):
        changed = dict(self.mfpu, status='MFPU272_COMPLETE_FRESH_BEFORE_OFFLINE_TYPED_BOUND_NOT_EXCLUSION_QUALIFICATION')
        with self.assertRaises(ValueError): c.receipt_gate(changed, self.rvh)

    def test_RVH_old_stdout_pin_cannot_replace_closure(self):
        changed = dict(self.rvh, original_inspect_all_checks_replayed=False)
        with self.assertRaises(ValueError): c.receipt_gate(self.mfpu, changed)

    def test_missing_final_stage(self):
        changed = copy.deepcopy(self.mfpu); changed['stages'].pop()
        with self.assertRaises(ValueError): c.receipt_gate(changed, self.rvh)

    def test_child_protection_missing(self):
        changed = dict(self.mfpu, protected_child_scopes=743)
        with self.assertRaises(ValueError): c.receipt_gate(changed, self.rvh)

    def test_source_no_X_waiver(self):
        changed = dict(self.mfpu, initial_X_waiver=True)
        with self.assertRaises(ValueError): c.receipt_gate(changed, self.rvh)


class IntersectionTests(unittest.TestCase):
    def row(self, family, role, **extra):
        return dict(metric='Toggle', scope='ara_tb.dut.fp', checksum='123 456',
            object='fmt_outputs[3].result', direction='0to1', array=False,
            low=0, high=63, role=role, family=family, **extra)

    def test_closed771_protection_requires_explicit_exact_owner(self):
        rows = [self.row('mfpu272', 'target'), self.row('closed771', 'protected')]
        with self.assertRaises(ValueError): c.intersection_review(rows, [])
        approval = c.identity(rows[0]) + (0, 63, 'closed771', 'mfpu272')
        self.assertEqual(len(c.intersection_review(rows, [approval])), 1)

    def test_direction_cannot_grant_other_direction(self):
        rows = [self.row('mfpu272', 'target'), self.row('closed771', 'protected')]
        approval = c.identity(rows[0]) + (0, 63, 'closed771', 'mfpu272')
        rows.extend([dict(r, direction='1to0') for r in rows])
        with self.assertRaises(ValueError): c.intersection_review(rows, [approval])

    def test_indexed_name_not_flattened(self):
        target = self.row('mfpu272', 'target')
        protected = dict(self.row('closed771', 'protected'), object='fmt_outputs[4].result')
        self.assertEqual(c.intersection_review([target, protected], []), [])

    def test_opaque_array_never_ownership_promoted(self):
        target = dict(self.row('mfpu272', 'target'), array=True)
        with self.assertRaises(ValueError): c.intersection_review([target], [])

    def test_boolean_true_not_excluded_flag_one(self):
        row = self.row('mfpu272', 'target')
        key = c.identity(row) + (0, 63)
        with self.assertRaises(ValueError): c.stage_gate('applied', [row], {key:True})

    def test_reset_requires_target_unexcluded(self):
        row = self.row('mfpu272', 'target')
        key = c.identity(row) + (0, 63)
        with self.assertRaises(ValueError): c.stage_gate('reset', [row], {key:1})


if __name__ == '__main__': unittest.main()
