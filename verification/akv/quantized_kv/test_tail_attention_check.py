import struct
import unittest

from batch_spec import Command
from check_batch_qk import schema, TERMINAL
from check_tail_attention import check_log, SUITE
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]


class TailAcceptance(unittest.TestCase):
    def fixture(self, kind=0):
        rtl = (ROOT / 'hardware/src/vlsu/vlsu.sv').read_text()
        fields = schema(rtl)
        row_bytes = 72 if kind else 136
        gold = {prefix: struct.pack('<1536f', *([1.0] * 1536)) for prefix in (5, 33)}
        lines = [f'QUANT_TAIL_CAP kind={kind} heads=6 dim=128 capacity=256 prefixes=5,33 '
                 f'native_repeats=2 k_token_stride={2 * row_bytes} v_token_stride=272 workspace=13120']
        seq = 0
        for visible in (5, 33):
            for trial in range(3):
                native = int(trial != 0)
                lines.append(f'QUANT_TAIL_BEGIN visible={visible} trial={trial} native={native}')
                if native:
                    for first in range(0, visible, 32):
                        for head, heads in ((0, 4), (4, 2)):
                            c = Command(kind, 0, head, heads, first, min(32, visible - first))
                            seq += 1
                            row = dict.fromkeys(fields, 0)
                            row.update(seq=seq, id=1, m=heads, n=c.n, vlen=1024, lanes=4, success=1,
                                       read_ranges=c.read_ranges, payload_bytes=c.payload_bytes,
                                       weight_bytes=c.weight_row_bytes * c.n, activation_bytes=136 * heads,
                                       useful_pairs=128 * c.outputs, busy_cycles=100, ar=c.read_ranges,
                                       r_beats=c.read_ranges + 4, read_outstanding_max=2, commit_groups=1)
                            lines.append('[QBS_PERF] ' + ' '.join(f'{key}={row[key]}' for key in fields))
                            lines.append(f'QUANT_TAIL_QK visible={visible} trial={trial} seq={seq} '
                                f'm={heads} n={c.n} stride=32 activation=' + '00' * (heads * 136) +
                                ' scores=' + '3f800000' * (heads * c.n))
                tiles = (visible + 31) // 32
                count = 2 * tiles if native else 0
                lines.append(f'QUANT_TAIL_RESULT visible={visible} trial={trial} native={native} '
                    f'map=0 status=0 selection=0 groups={native} commands={count} '
                    f'calls={count if native else 6 * visible} values={visible if native else 6 * visible} '
                    f'panels={tiles if native else 0} copied={visible * row_bytes if native else 0} '
                    'fcsr=1 vcsr=5 errors=0 hex=' + '3f800000' * 768)
        return '\n'.join(lines + [SUITE, TERMINAL, 'UVM_ERROR : 0', 'UVM_FATAL : 0']), gold, rtl

    def check(self, text, kind, gold, rtl):
        return check_log(text, kind, gold, rtl, bytes(512 * (72 if kind else 136)),
                         lambda _kind, _key, _query: (0x3f800000, 0))

    def test_profiles(self):
        for kind in (0, 1):
            text, gold, rtl = self.fixture(kind)
            result = self.check(text, kind, gold, rtl)
            self.assertEqual(result['commands'], 12)
            self.assertEqual([r['n'] for r in result['hardware_records']],
                             [5, 5, 5, 5, 32, 32, 1, 1, 32, 32, 1, 1])

    def test_reject_bad_work_or_evidence(self):
        text, gold, rtl = self.fixture()
        work = next(line for line in text.splitlines() if line.startswith('[QBS_PERF]'))
        for altered in (text.replace('prefixes=5,33', 'prefixes=5,32', 1),
                        text.replace('k_token_stride=272', 'k_token_stride=136', 1),
                        text.replace('panels=1', 'panels=2', 1),
                        text.replace('copied=680', 'copied=816', 1),
                        text.replace('groups=1', 'groups=0', 1),
                        text.replace('hex=3f800000', 'hex=7fc00000', 1),
                        text.replace('fcsr=1', 'fcsr=3', 1),
                        text.replace(work + '\n', '', 1),
                        text.replace('n=1 vlen=', 'n=32 vlen=', 1),
                        text.replace('errors=0', 'errors=1', 1),
                        text.replace('UVM_ERROR : 0', 'UVM_ERROR : 1'),
                        text.replace(TERMINAL, ''), text + '\n' + SUITE):
            with self.assertRaises(ValueError):
                self.check(altered, 0, gold, rtl)
        with self.assertRaises(ValueError):
            self.check(text, 0, {5: bytes(6144), 33: bytes(6144)}, rtl)

    def test_exact_scores_and_queries(self):
        text, gold, rtl = self.fixture()
        score = next(line for line in text.splitlines() if line.startswith('QUANT_TAIL_QK'))
        for altered in (text.replace(score + '\n', '', 1),
                        text.replace(score, score + '\n' + score, 1),
                        text.replace('scores=3f800000', 'scores=40000000', 1),
                        text.replace('stride=32', 'stride=64', 1),
                        text.replace('activation=00', 'activation=01', 1)):
            with self.assertRaises(ValueError):
                self.check(altered, 0, gold, rtl)


if __name__ == '__main__':
    unittest.main()
