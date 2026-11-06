import unittest
from pathlib import Path
import tempfile

from audit import digest
from projection_work_ledger import check, command_work, verify_runtime_artifact


def row(m=1, profile=1):
    return dict(m=str(m), n='32', k_blocks='8', weight_profile=str(profile), access='2',
                activation_profile='1', emulated='0', segmented='0')


def fixture():
    lines = []
    for mode in (0, 1):
        lines.append(f'REGISTER_MODEL_BEGIN enabled={mode}')
        for i in range(6):
            m = 4 if i % 3 == 0 else 1
            lines.append(f'GGML_RISCV_QBS_CALL type=q4_K mode={"gemm" if m == 4 else "gemv"} '
                         f'k=2048 input_rows={m} output_rows=32 split_k=0')
            fields = dict(row(m), seq=str(i+1), graph_epoch=str(i+1))
            lines.append('GGML_RISCV_QBS_COMMAND '+' '.join(k+'='+v for k, v in fields.items()))
            lines.append(f'REGISTER_MODEL_STEP enabled={mode} kind={i//3} step={i%3}')
        lines.append(f'REGISTER_MODEL_END enabled={mode}')
    return '\n'.join(lines)


class ProjectionWorkLedgerTests(unittest.TestCase):
    def test_profile_specific_roof(self):
        q4 = command_work(row())
        self.assertEqual(q4['useful_pairs'], 65536)
        self.assertEqual(q4['baseline_dot_issue_budget'], 2048)
        self.assertEqual(q4['weight_r_beat_floor'], 2304)
        q6 = command_work(row(profile=2))
        self.assertEqual(q6['weight_r_beat_floor'], 3360)
        self.assertEqual(q6['candidate_dot_issue_budget'], 2048)

    def test_m4_candidate_and_weight_reuse(self):
        value = command_work(row(m=4))
        self.assertEqual(value['useful_pairs'], 262144)
        self.assertEqual(value['nominal_weight_payload_bytes'], 36864)
        self.assertEqual(value['baseline_dot_issue_budget'], 8192)
        self.assertEqual(value['candidate_dot_issue_budget'], 4096)
        self.assertEqual(value['candidate_dot_or_weight_floor'], 4096)

    def test_work_conservation_and_stage(self):
        measured = check(fixture())
        self.assertEqual(measured['stages_per_mode']['prefill']['matrix_candidate_mac_fraction'], 1)
        self.assertEqual(measured['stages_per_mode']['decode']['matrix_candidate_mac_fraction'], 0)
        self.assertFalse(measured['hardware_cycles_measured'])

    def test_no_missing_or_extra_work(self):
        with self.assertRaises(ValueError): check(fixture().replace('input_rows=4', 'input_rows=8', 1))
        with self.assertRaises(ValueError): check(fixture().replace('seq=2', 'seq=3', 1))
        with self.assertRaises(ValueError): check(fixture().rsplit('\n', 1)[0])

    def test_unknown_profiles_and_non_native_rejected(self):
        for changes in (dict(weight_profile='9'), dict(emulated='1'), dict(segmented='1'), dict(n='31')):
            with self.assertRaises(ValueError): command_work(dict(row(), **changes))

    def test_historical_symlink_key_preserves_hash_check(self):
        with tempfile.TemporaryDirectory() as directory:
            target = Path(directory)/'real'; target.write_bytes(b'kernel')
            alias = Path(directory)/'Image'; alias.symlink_to(target)
            sha = digest(target)
            verify_runtime_artifact({str(alias): sha}, alias)
            verify_runtime_artifact({str(target): sha}, alias)
            with self.assertRaises(ValueError): verify_runtime_artifact({}, alias)
            with self.assertRaises(ValueError): verify_runtime_artifact({str(alias): 'wrong'}, alias)
            with self.assertRaises(ValueError):
                verify_runtime_artifact({str(alias): sha, str(target): 'wrong'}, alias)


if __name__ == '__main__': unittest.main()
