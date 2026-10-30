import importlib.util
from pathlib import Path
import unittest

HERE = Path(__file__).resolve().parent
spec = importlib.util.spec_from_file_location('grouped_pair_checker_test', HERE / 'check.py')
c = importlib.util.module_from_spec(spec)
spec.loader.exec_module(c)


def fixture():
    # Independent synthetic geometry, not captured execution evidence.
    names = ('seq m n vlen lanes success fault validation_fault validation_error read_fault translations '
             'read_ranges payload_bytes weight_bytes activation_bytes useful_pairs activation_access '
             'context_fill_count context_reuse_count context_reuse_block_count context_read_bytes '
             'activation_axi_bytes_saved context_replay_cycles context_replay_compute_overlap_cycles '
             'context_validation_fault_count id busy_cycles ar r_beats read_outstanding_max commit_groups').split()
    rtl = '$display("[QBS_PERF] ' + ' '.join(n+'=%0d' for n in names) + '");'
    lines = [c.CAP]
    for trial, enabled in enumerate(c.ORDER):
        lines.append(f'QUANT_GROUPED_BEGIN trial={trial} enabled={enabled} api={enabled}')
        for j in range(8):
            m = 4 if j % 2 == 0 else 2
            row = dict.fromkeys(names, 0)
            row.update(seq=trial*8+j+1, m=m, n=32, vlen=1024, lanes=4, success=1,
                       read_ranges=1+4*m+128, payload_bytes=16+136*m+72*32, weight_bytes=72*32,
                       activation_bytes=136*m, useful_pairs=128*m*32, busy_cycles=100,
                       ar=160, r_beats=240, read_outstanding_max=2, commit_groups=4)
            lines.append('[QBS_PERF] ' + ' '.join(f'{n}={row[n]}' for n in names))
        lines.append(f'QUANT_GROUPED_RESULT trial={trial} enabled={enabled} api={enabled} cycles=2000 '
                     'commands=8 values=128 panels=4 copied=9216 quantizations=6 map=0 status=0 selection=0 '
                     'groups=1 executor=0 fcsr=3 vcsr=5 max_abs=00000000 differences=0 errors=0 digest=0123456789abcdef')
    lines += [c.SUITE, c.TERMINAL, 'UVM_ERROR : 0', 'UVM_FATAL : 0']
    return '\n'.join(lines), bytes(6144), rtl


class CheckTests(unittest.TestCase):
    def test_valid(self):
        r = c.check_log(*fixture())
        self.assertEqual(len(r['hardware_records']), 32)
        self.assertEqual(r['sums'], {'0': 4000, '1': 4000})
        self.assertFalse(r['independent_host_output_recompute'])

    def test_protocol_mutations(self):
        text, gold, rtl = fixture()
        for old, new in [('trial=1 enabled=1 api=1', 'trial=1 enabled=1 api=0'),
                         ('commands=8', 'commands=7'), ('copied=9216', 'copied=9215'),
                         ('quantizations=6', 'quantizations=7'), ('errors=0', 'errors=1'),
                         ('differences=0', 'differences=1'), ('vcsr=5', 'vcsr=0'),
                         ('fcsr=3', 'fcsr=32'), ('cycles=2000', 'cycles=799'),
                         ('max_abs=00000000', 'max_abs=7fc00000'),
                         ('max_abs=00000000', 'max_abs=3f800000'),
                         ('digest=0123456789abcdef', 'digest=0123456789abcdee'),
                         (c.SUITE, c.SUITE+'BOGUS'), ('m=4 n=32', 'm=3 n=32'),
                         ('read_fault=0', 'read_fault=1')]:
            with self.subTest(new=new), self.assertRaises(ValueError):
                c.check_log(text.replace(old, new, 1), gold, rtl)

    def test_unknown_extra_missing(self):
        text, gold, rtl = fixture()
        lines = text.splitlines()
        for bad in (text+'\nQUANT_GROUPED_UNKNOWN x=0', text+'\n'+c.SUITE,
                    text+'\n[QBS_PERF] BOGUS', text+'\nUVM_ERROR : 0',
                    '\n'.join(lines[:3]+lines[4:]), text.replace(c.SUITE, ''),
                    text.replace('commit_groups=4', 'commit_groups=4 extra=0', 1)):
            with self.subTest(bad=bad[-80:]), self.assertRaises(ValueError):
                c.check_log(bad, gold, rtl)

    def test_command_header_strict(self):
        text, gold, rtl = fixture()
        argv = ['/simv', '+QBS_PERF']
        c.check_log('Command: /simv +QBS_PERF\n'+text, gold, rtl, argv)
        for header in ('Command: /wrong +QBS_PERF\n', 'Command: /simv +QBS_PERF\n'*2):
            with self.assertRaises(ValueError):
                c.check_log(header+text, gold, rtl, argv)


if __name__ == '__main__':
    unittest.main()
