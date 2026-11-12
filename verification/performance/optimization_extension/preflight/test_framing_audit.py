import unittest
import framing_audit as a


def fixture():
    lines = []
    for index in range(8):
        k = 2048 if index < 4 else 4096; b = k//256*1168
        values = dict(k=k, trial=index % 4, candidate=int(index % 4 in (1, 2)), cycles=100+index,
            instructions=50, bytes=b, fcsr=17, vcsr=5, queries=3, hits=2, producers=1, misses=1,
            stores=1, rejected=0, conflicts=0, allocation_failures=0, evictions=0,
            comparison_bytes_requested=2*k*16, copied_payload_bytes=k*16+3*b, vstart=0,
            guard_bytes=128, payload_equal=1, payload_hash=k, errors=0)
        cut1, cut2 = a.FIELDS.index('vcsr'), a.FIELDS.index('vstart')
        parts = [''.join(' '+key+'='+str(values[key]) for key in keys) for keys in
                 (a.FIELDS[:cut1], a.FIELDS[cut1:cut2], a.FIELDS[cut2:])]
        parts[0] = 'EXT_PREFLIGHT_TRIAL'+parts[0]
        for n, insn in enumerate(('00f02473', '00802473')):
            cycle = 100+index*10+n*2
            lines.append(parts[n]+'[ARA_CONTRACT_TRACE] sample=pre_edge cycle='+str(cycle)+
                ' req=1/1 fire=1 id=2 insn='+insn+' resp=1/1 fire=1 id=2 exc=0 pending=00 stalled=10 errors=0000000')
            lines.append(a.UVM_PREFIX+str(cycle*10000)+': uvm_test_top.env.agent.monitor [CVXIF/EVENT] cycle='+
                str(cycle+1)+' req_fire=1 req_id=2 insn='+insn+' resp_fire=1 resp_id=2 exc=0')
        lines.append(parts[2])
    return '\n'.join(lines+['EXT_PREFLIGHT_DONE shapes=2 trials=8 calls=24 errors=0',
        'Core Test *** SUCCESS *** (tohost = 0)', 'UVM_ERROR : 0', 'UVM_FATAL : 0'])+'\n'


class Tests(unittest.TestCase):
    def test_exact_framing_original_parser(self):
        check = a.load(a.BENCH/'inputs/check.py')
        text = fixture()
        with self.assertRaises(ValueError): check.numerical(text, vcs=True)
        result, records = a.reconstruct(text)
        self.assertEqual(len(records), 8)
        self.assertEqual(len(check.numerical(result, vcs=True)['trials']), 8)
        self.assertTrue(all(len(r['fragment_sha256']) == 3 and len(r['probe_sha256']) == 4 for r in records))

    def test_unknown_probe_error_or_field_never_dropped(self):
        for old, new in (('errors=0000000', 'errors=1000000'), ('stalled=10', 'stalled=11'),
                         ('insn=00f02473', 'insn=00802473'), ('pending=00', 'pending=01'),
                         ('req_id=2', 'req_id=3'), ('cycle=101 req_fire', 'cycle=105 req_fire'),
                         ('exc=0 pending', 'exc=1 pending'), ('errors=0000000', 'errors=0000000 extra=1'),
                         ('UVM_INFO ', 'UVM_ERROR '), ('id=2 insn=00f02473', 'id=x insn=00f02473')):
            with self.subTest(old=old), self.assertRaises(ValueError):
                a.reconstruct(fixture().replace(old, new, 1))

    def test_extra_uart_fields_and_truncation(self):
        text = fixture(); lines = text.splitlines()
        for bad in (text.replace('fcsr=17[', 'fcsr=17 extra=1['),
                    text.replace('vcsr=5', 'vcsr=5 vcsr=5', 1), text.replace('errors=0\n', 'errors=0 extra=1\n', 1),
                    '\n'.join(lines[:4]), '\n'.join(lines[:10]+lines[11:]),
                    text+lines[4]+'\n', text+lines[0]+'\n', text+lines[-4]+'\n',
                    text.replace('EXT_PREFLIGHT_TRIAL', 'xEXT_PREFLIGHT_TRIAL', 1)):
            with self.subTest(bad=bad[-100:]), self.assertRaises(ValueError): a.reconstruct(bad)

    def test_numeric_and_severity_errors_still_rejected(self):
        check = a.load(a.BENCH/'inputs/check.py')
        for old, new in (('hits=2', 'hits=1'), ('guard_bytes=128', 'guard_bytes=0'),
                         ('fcsr=17', 'fcsr=16'), ('payload_equal=1', 'payload_equal=0'),
                         ('UVM_ERROR : 0', 'UVM_ERROR : 1'), ('errors=0\n', 'errors=1\n')):
            with self.subTest(old=old), self.assertRaises(ValueError):
                canonical, _ = a.reconstruct(fixture().replace(old, new, 1))
                check.numerical(canonical, vcs=True)


if __name__ == '__main__': unittest.main()
