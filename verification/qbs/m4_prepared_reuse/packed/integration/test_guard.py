import copy
import unittest

from guard import merge
from run_graph import check
from stage import ROOT


class GuardTests(unittest.TestCase):
    def test_conflicting_pin_is_not_refreshed(self):
        original = {'source': 'accepted', 'unchanged': 'same'}
        pins = copy.deepcopy(original)
        with self.assertRaises(ValueError):
            merge(pins, {'source': 'changed', 'new': 'value'})
        self.assertEqual(pins, original)

    def test_identical_pin_and_new_artifact(self):
        pins = {'source': 'accepted'}
        merge(pins, {'source': 'accepted', 'object': 'compiled'})
        self.assertEqual(pins, {'source': 'accepted', 'object': 'compiled'})

    @classmethod
    def setUpClass(cls):
        cls.log = (ROOT / 'verification/out/m4-packed-integration-graph-20261027-01/qemu.log').read_text()

    def test_actual_combined_graph_replay(self):
        self.assertEqual(check(self.log)['graphs'], 24)

    def test_old_producer_cannot_masquerade_as_packed(self):
        with self.assertRaises(ValueError):
            check(self.log.replace('tag=2', 'tag=1'))

    def test_missing_selection_record(self):
        lines = self.log.splitlines()
        index = next(i for i, line in enumerate(lines) if line.startswith('GGML_RISCV_QBS_M4_SELECTED '))
        del lines[index]
        with self.assertRaises(ValueError):
            check('\n'.join(lines))

    def test_cache_hit_is_not_execution(self):
        with self.assertRaises(ValueError):
            check(self.log.replace('source=cache tag=2 event=hit', 'source=cache tag=2 event=compute_rvv'))

    def test_generic_fallback_is_not_packed_execution(self):
        with self.assertRaises(ValueError):
            check(self.log.replace('source=direct tag=2 path=generic', 'source=direct tag=2 path=rvv'))


if __name__ == '__main__':
    unittest.main()
