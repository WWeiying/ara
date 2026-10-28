"""Check that promotion only combines the separately accepted deltas."""
from pathlib import Path
import unittest
from unittest.mock import patch

import prepare_promotion as promotion
from stage import files


class PromotionTests(unittest.TestCase):
    def test_only_two_reviewed_guards_change(self):
        staged = files()
        combined = promotion.candidate_files()
        self.assertEqual(set(staged), set(combined))
        old = 'if constexpr (is_qbs_block_type<BLOC_TYPE>::value && INTER_SIZE == 1) {'
        new = ('if constexpr (INTER_SIZE == 1 &&\n'
               '                              (PARAM_TYPE == GGML_TYPE_Q8_K || PARAM_TYPE == GGML_TYPE_Q8_0)) {')
        for name in staged:
            if name == Path('repack.cpp'):
                self.assertEqual(staged[name].count(old), 2)
                self.assertEqual(combined[name], staged[name].replace(old, new))
                start = combined[name].index('    void forward_mul_mat(')
                end = combined[name].index('    void forward_mul_mat_id', start)
                self.assertEqual(combined[name][start:end].count(new), 2)
            else:
                self.assertEqual(staged[name], combined[name])

    def test_changed_guard_count_rejected(self):
        staged = files()
        name = Path('repack.cpp')
        old = 'if constexpr (is_qbs_block_type<BLOC_TYPE>::value && INTER_SIZE == 1) {'
        staged[name] = staged[name].replace(old, 'if constexpr (false) {', 1)
        with patch.object(promotion, 'files', return_value=staged):
            with self.assertRaises(ValueError):
                promotion.candidate_files()


if __name__ == '__main__':
    unittest.main()
