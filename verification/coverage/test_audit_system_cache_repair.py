import copy
import unittest

import audit_system_cache_repair as a
from test_audit_extra_acceptance_20261008 import row


LOG = '''PASSED: system_gap30 case=6 checks=1758
Core Test *** SUCCESS *** (tohost = 0)
UVM_ERROR : 0
UVM_FATAL : 0
[ARA_CONTRACT] requests=0 responses=0 exceptions=0 mmu_request_cycles=0 protocol_errors=0 outstanding=0 req_stalled=0 resp_stalled=0
'''


def fixture(blob):
    items = [row(pc=0x80000000)]
    for r in range(3):
        for i in range(4096):
            items.append(row(pc=(0x8000013c, 0x800001c0, 0x80000248)[r],
                             addr=0x80001680+i*8, write=255, data=(r << 32)^i^0xfeed1234))
        items.append(row(pc=(0x80000146, 0x800001ca, 0x80000252)[r]))
        for j, i in enumerate(range(0, 4096, 7)):
            items.append(row(pc=(0x80000170, 0x800001f4, 0x8000027c)[r],
                             addr=0x80001680+i*8, read=255, value=(r << 32)^i^0xfeed1234))
            items.append(row(pc=(0x8000017a, 0x800001fe, 0x80000286)[r],
                             addr=0x80009680, write=15, data=r*586+j+1))
        items.append(row(pc=(0x800001a2, 0x80000226, 0x800002a8)[r]))
        items.append(row(pc=(0x800001a6, 0x8000022a, 0x800002ac)[r]))
    items += [row(pc=0x800002be, addr=0x80009688, write=255, data=0x7379733330),
              row(pc=0x800002e0, addr=0x80009688, read=255, value=0x7379733330),
              row(pc=0x800002e2, addr=0x80009680, read=15, value=1758),
              row(pc=0x800002e4, addr=0x80009684, read=240, value=0),
              row(pc=0x800000ec, addr=0xd0000000, write=255, data=0)]
    items[-4]['rd'], items[-2]['rd'] = '11', '13'
    for i, item in enumerate(items):
        pc = int(item['pc'], 16)
        word = int.from_bytes(a.extra.code_at(blob, pc, 2), 'little')
        if word & 3 == 3:
            word = int.from_bytes(a.extra.code_at(blob, pc, 4), 'little')
        item.update(insn='%x' % word, cycle=str(i+1), order=str(i))
    return items


class Acceptance(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.blob = (a.source()/'input.elf').read_bytes()
        cls.good = fixture(cls.blob)

    def test_original_hash_and_complete_contract(self):
        self.assertEqual(a.extra.sha(a.source()/'input.elf'), a.ELF_SHA)
        result = a.check_rows(self.good, self.blob)
        self.assertEqual((result['status'], result['rounds'], result['checks']), ('PASS', 3, 1758))
        self.assertEqual(result['independent_readback_bytes'], 14064)

    def test_scalar_zero_requests_are_required_not_an_error(self):
        self.assertEqual(a.check_log(LOG)['requests'], 0)
        with self.assertRaises(ValueError):
            a.check_log(LOG.replace('requests=0 responses=0', 'requests=1 responses=1'))

    def test_truncated_uart_and_fail_diagnostics_rejected(self):
        for text in (LOG.replace('1758', '1172'), LOG.replace('Core Test *** SUCCESS ***', ''),
                     LOG+'UVM_ERROR @ 12: broken\n', LOG+'FAIL: compare\n', LOG+'Fatal: stop\n',
                     LOG.replace('outstanding=0', 'outstanding=1')):
            with self.subTest(text=text[-60:]), self.assertRaises(ValueError):
                a.check_log(text)

    def test_corrupt_each_mandatory_data_gate(self):
        for pc, key, value in ((0x8000013c, 'mem_wdata', '0'),
                               (0x8000027c, 'rd_wdata', '0'),
                               (0x800002be, 'mem_wdata', '0'),
                               (0x800002e2, 'rd_wdata', '494'),
                               (0x800002e4, 'rd_wdata', '1'),
                               (0x800000ec, 'mem_wdata', '1'),
                               (0x80000146, 'insn', '13')):
            items = copy.deepcopy(self.good)
            next(r for r in items if int(r['pc'], 16) == pc)[key] = value
            with self.subTest(pc=hex(pc), key=key), self.assertRaises(ValueError):
                a.check_rows(items, self.blob)

    def test_real_timeout_is_not_a_pass(self):
        actual = list(a.extra.rows(a.source()/'commit_trace.csv'))
        with self.assertRaisesRegex(ValueError, 'All3 rounds'):
            a.check_rows(actual, self.blob)

    def test_missing_fence_rejected_even_when_data_counts_complete(self):
        items = [copy.deepcopy(r) for r in self.good if int(r['pc'], 16) != 0x800002ac]
        for i, item in enumerate(items):
            item['order'] = str(i)
        with self.assertRaisesRegex(ValueError, 'All9 original fences'):
            a.check_rows(items, self.blob)

    def test_out_of_order_fence_rejected(self):
        items = copy.deepcopy(self.good)
        first = next(i for i, r in enumerate(items) if int(r['pc'], 16) == 0x80000146)
        fence = items.pop(first)
        items.insert(1, fence)
        for i, item in enumerate(items):
            item.update(order=str(i), cycle=str(i+1))
        with self.assertRaisesRegex(ValueError, 'Round/fence/completion ordering'):
            a.check_rows(items, self.blob)


if __name__ == '__main__':
    unittest.main()
