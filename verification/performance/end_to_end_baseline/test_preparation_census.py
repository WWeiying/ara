import unittest

from preparation_census import records, summarize
from run_preparation_census import traced_source


def fixture():
    lines = ['OUTPUT_MODEL_BEGIN enabled=0']
    for seq in (1, 2):
        for i in range(10):
            if i < 8:
                event = 'compute_rvv' if seq == 1 else 'hit'
                lines.append(f'GGML_RISCV_QBS_M4_CACHE epoch=1 group={i} event={event} fill={2-seq}')
                lines.append(f'GGML_RISCV_QBS_M4_SELECTED source=cache tag=2 event={event} k=2048')
            else:
                lines.append('GGML_RISCV_QBS_M4_SELECTED source=direct tag=2 path=rvv k=2048')
        lines.append(f'GGML_RISCV_QBS_LIFETIME seq={seq} graph_epoch=1 op=Qcur-0 source=attn_norm-0 '
                     f'source_id=0x1 digest=abc activation_type=q8_K m=40 n=2048 k=2048 '
                     f'bytes=93440 match_seq={seq-1} reusable={seq-1}')
    for step in range(6):
        lines.append(f'OUTPUT_MODEL_STEP enabled=0 kind={step//3} step={step%3}')
    lines.append('OUTPUT_MODEL_END enabled=0')
    return lines


class PreparationCensusTests(unittest.TestCase):
    def test_exact_routes_and_candidate_scope(self):
        rows = records(fixture())
        totals = summarize(rows)['totals']
        self.assertEqual(totals['m4_groups'], 20)
        self.assertEqual(totals['hit'], 8)
        self.assertEqual(totals['compute_rvv'], 8)
        self.assertEqual(totals['direct_rvv'], 4)
        self.assertEqual(totals['direct_groups_in_duplicate_buffers'], 2)
        self.assertEqual(totals['direct_groups_ge8'], 4)

    def test_truncation_and_missing_groups_rejected(self):
        with self.assertRaises(ValueError): records(fixture()[:-1])
        lines = fixture(); del lines[3:5]
        with self.assertRaises(ValueError): records(lines)

    def test_cache_event_cannot_be_relabelled(self):
        lines = fixture(); lines[2] = lines[2].replace('compute_rvv', 'hit')
        with self.assertRaises(ValueError): records(lines)
        lines = fixture(); lines[1] = lines[1].replace('group=0', 'group=8')
        with self.assertRaises(ValueError): records(lines)

    def test_duplicate_requires_actual_identity(self):
        lines = fixture(); last = next(i for i, s in enumerate(lines) if s.startswith('GGML_RISCV_QBS_LIFETIME seq=2'))
        lines[last] = lines[last].replace('source_id=0x1', 'source_id=0x2')
        with self.assertRaises(ValueError): records(lines)

    def test_fixture_change_only_enables_two_traces(self):
        before = '\n'.join(f'env("{name}", "0");' for name in
                           ('GGML_RISCV_QBS_TRACE_M4_PREPARE', 'GGML_RISCV_QBS_TRACE_LIFETIME'))
        after = traced_source(before)
        self.assertEqual(after, before.replace('"0"', '"1"'))
        with self.assertRaises(ValueError): traced_source(after)


if __name__ == '__main__': unittest.main()
