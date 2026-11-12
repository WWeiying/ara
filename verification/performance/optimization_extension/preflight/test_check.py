import copy
import unittest
import check as c


def fixture():
    rows = []
    for index in range(8):
        k = 2048 if index < 4 else 4096
        b = k // 256 * 1168
        r = dict(k=k, trial=index % 4, candidate=int(index % 4 in (1, 2)), cycles=100+index,
                 instructions=50, bytes=b, fcsr=17, vcsr=5, queries=3, hits=2, producers=1,
                 misses=1, stores=1, rejected=0, conflicts=0, allocation_failures=0, evictions=0,
                 comparison_bytes_requested=2*k*16, copied_payload_bytes=k*16+3*b, vstart=0,
                 guard_bytes=128, payload_equal=1, payload_hash=k, errors=0)
        rows.append('EXT_PREFLIGHT_TRIAL'+''.join(' '+key+'='+str(r[key]) for key in c.FIELDS))
    return '\n'.join(rows+[c.DONE, 'Core Test *** SUCCESS ***', 'UVM_ERROR : 0', 'UVM_FATAL : 0'])+'\n'


class Tests(unittest.TestCase):
    def test_valid_and_spike_not_performance(self):
        ref = c.numerical(fixture())
        self.assertFalse(ref['performance_measured'])
        self.assertEqual(ref['cycle_metrics'], [])
        self.assertEqual(len(c.numerical(fixture(), vcs=True, reference=ref)['cycle_metrics']), 2)

    def test_negative_fields(self):
        for old, new in (('hits=2', 'hits=1'), ('vstart=0', 'vstart=1'), ('fcsr=17', 'fcsr=16'),
                         ('guard_bytes=128', 'guard_bytes=0'), ('payload_equal=1', 'payload_equal=0'),
                         ('payload_hash=2048', 'payload_hash=2049'), ('producers=1', 'producers=2'),
                         ('candidate=0', 'candidate=1'), ('bytes=9344', 'bytes=9343'),
                         ('cycles=100', 'cycles=0'), ('cycles=100', 'cycles=-1'),
                         ('queries=3', 'queries=3 queries=3'), ('errors=0', 'errors=1'),
                         ('allocation_failures=0', 'allocation_failures=1'),
                         ('comparison_bytes_requested=65536', 'comparison_bytes_requested=0'),
                         ('copied_payload_bytes=60800', 'copied_payload_bytes=0')):
            with self.subTest(old=old, new=new):
                text = fixture()
                self.assertIn(old, text)
                with self.assertRaises(ValueError):
                    c.numerical(text.replace(old, new, 1), vcs=True)

    def test_bad_structure(self):
        text = fixture()
        lines = text.splitlines()
        for bad in ('\n'.join(lines[1:]), text+lines[0]+'\n', text+c.DONE+'\n',
                    text.replace(c.DONE, c.DONE+' extra=1'), text.replace('EXT_PREFLIGHT_TRIAL', 'xEXT_PREFLIGHT_TRIAL', 1),
                    text+'EXT_PREFLIGHT_FAIL reason=bad\n', text+'TRAP cause=2\n',
                    text.replace('Core Test *** SUCCESS ***', ''), text+'UVM_ERROR x\n',
                    text.replace('UVM_FATAL : 0', 'UVM_FATAL : 1'), text+'Assertion failed\n'):
            with self.subTest(bad=bad[-100:]), self.assertRaises(ValueError):
                c.numerical(bad, vcs=True)

    def test_spike_reference_drift(self):
        ref = c.numerical(fixture())
        ref['functional'][0]['payload_hash'] += 1
        with self.assertRaises(ValueError):
            c.numerical(fixture(), vcs=True, reference=ref)

    def test_protocol_negative(self):
        proof = dict(status='PASS', issues=[], elf_sha256='abc', contract_counts=dict(
            exceptions=0, protocol_errors=0, outstanding=0, requests=12, responses=12))
        c.protocol(proof, dict(elf_sha256='abc'))
        for field, value in (('outstanding', 1), ('exceptions', 1), ('protocol_errors', 1),
                             ('requests', 0), ('responses', 11)):
            bad = copy.deepcopy(proof); bad['contract_counts'][field] = value
            with self.subTest(field=field), self.assertRaises(ValueError):
                c.protocol(bad, dict(elf_sha256='abc'))
        for change in (dict(elf_sha256='wrong'), dict(status='FAIL'), dict(issues=['error'])):
            with self.assertRaises(ValueError):
                c.protocol(dict(proof, **change), dict(elf_sha256='abc'))


if __name__ == '__main__':
    unittest.main()
