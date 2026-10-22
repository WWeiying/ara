"""Offline oracle tests, including deliberate corruption and missing evidence."""
import copy
import unittest

import audit_extra_acceptance_20261008 as a


def row(pc=0, word=0x13, addr=0, read=0, write=0, value=0, data=0, event='retire'):
    return dict(event=event, pc='%x' % pc, insn='%x' % word, mem_addr='%x' % addr,
                mem_rmask='%x' % read, mem_wmask='%x' % write, rd_wdata='%x' % value,
                mem_wdata='%x' % data, rd='12', trap='0', order='0', cycle='1')


def cache_fixture(complete=True):
    rows = []
    for r in range(3 if complete else 1):
        for i in range(4096):
            rows.append(row(pc=(0x8000013c, 0x800001c0, 0x80000248)[r],
                            addr=0x80001680+8*i, write=255, data=(r << 32)^i^0xfeed1234))
        for j, i in enumerate(range(0, 4096, 7)):
            rows.append(row(pc=(0x80000170, 0x800001f4, 0x8000027c)[r],
                            addr=0x80001680+8*i, read=255, value=(r << 32)^i^0xfeed1234))
            rows.append(row(pc=(0x8000017a, 0x800001fe, 0x80000286)[r],
                            addr=0x80009680, write=15, data=r*586+j+1))
    for n, item in enumerate(rows):
        item.update(order=str(n), cycle=str(n+1))
    return rows


def skew_fixture():
    sizes = dict(source=1536, got=640, initial=640, descriptor=128, descriptor_copy=128)
    symbols = {name: dict(value=0x90000000+i*4096, size=size)
               for i, (name, size) in enumerate(sizes.items())}
    rows = []
    desc = a.descriptor_bytes(symbols['source']['value'])
    for phase, command in enumerate(a.WORDS):
        rows.append(row(word=command, event='cvx_req'))
        for name, obj in symbols.items():
            width = 2 if name in ('got', 'initial') else 1
            for off in range(0, obj['size'], width):
                addr = obj['value']+off
                if name == 'source':
                    e, s, b = off//768, off%768//256, off%256
                    value = a.source_byte(e, s, b, phase > (7 if e else 0))
                    pc = 0x8000099e
                elif name in ('got', 'initial'):
                    value = int.from_bytes(a.frame_bytes(phase, name == 'got')[off:off+2], 'little')
                    pc = 0x800007e6 if name == 'got' else 0x8000084c
                else:
                    value = desc[off]
                    pc = 0x80000a3c if name == 'descriptor' else 0x80000a40
                rows.append(row(pc=pc, word=0x5003 if width == 2 else 0x4003,
                                addr=addr, read=((1 << width)-1) << (addr % 8), value=value))
        if phase in (0, 7):
            e = int(phase == 7)
            for s in range(3):
                for b in range(a.offset(e, s), a.offset(e, s)+128):
                    addr = symbols['source']['value']+e*768+s*256+b
                    rows.append(row(pc=0x80000afe, addr=addr, read=1 << (addr % 8),
                                    value=a.source_byte(e, s, b)))
                    rows.append(row(pc=0x80000b06, addr=addr, write=1 << (addr % 8),
                                    data=a.source_byte(e, s, b, True)))
    return rows, symbols


class Cache(unittest.TestCase):
    def test_prefix_never_promoted_to_pass(self):
        report = a.cache_prefix(cache_fixture(False))
        self.assertEqual(report['status'], 'INCOMPLETE_PREFIX_NO_OBSERVED_DATA_FAILURE')
        self.assertFalse(report['full_acceptance'])

    def test_all_data_still_requires_full_acceptance(self):
        report = a.cache_prefix(cache_fixture())
        self.assertEqual(report['loads'], [586]*3)
        self.assertFalse(report['full_acceptance'])

    def test_bad_store_load_order_trap_and_fail_rejected(self):
        source = cache_fixture(False)
        for index, field, value in ((4, 'mem_wdata', '0'), (4096, 'rd_wdata', '0'),
                                    (1, 'order', '3'), (2, 'trap', '1'), (3, 'pc', '80000188')):
            items = copy.deepcopy(source)
            items[index][field] = value
            with self.subTest(field=field), self.assertRaises(ValueError):
                a.cache_prefix(items)


class Skew(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.rows, cls.symbols = skew_fixture()

    def test_all_frames_and_poison(self):
        report = a.skew_readback(self.rows, self.symbols)
        self.assertEqual(report['independently_checked_bytes'], 36864)
        self.assertFalse(report['full_ISA_qualified'])

    def test_corrupt_each_object_rejected(self):
        for name, obj in self.symbols.items():
            items = copy.deepcopy(self.rows)
            hit = next(r for r in items if int(r['mem_addr'], 16) == obj['value'] and
                       int(r['mem_rmask'], 16))
            hit['rd_wdata'] = '%x' % (int(hit['rd_wdata'], 16)^1)
            with self.subTest(object=name), self.assertRaises(ValueError):
                a.skew_readback(items, self.symbols)

    def test_missing_frame_byte_rejected(self):
        items = copy.deepcopy(self.rows)
        del items[1]
        with self.assertRaisesRegex(ValueError, 'Incomplete independent frame'):
            a.skew_readback(items, self.symbols)

    def test_missing_phase_rejected(self):
        items = [r for r in self.rows if not (r['event'] == 'cvx_req' and r['insn'] == '505b')]
        with self.assertRaises(ValueError):
            a.skew_readback(items, self.symbols)

    def test_poison_changes_cannot_define_expected_output(self):
        items = copy.deepcopy(self.rows)
        hit = next(r for r in items if r['pc'] == '80000b06')
        hit['mem_wdata'] = '%x' % (int(hit['mem_wdata'], 16)^1)
        with self.assertRaisesRegex(ValueError, 'Poison write'):
            a.skew_readback(items, self.symbols)

    def test_tail_not_zero_and_descriptor_layout(self):
        frame = a.frame_bytes(8, True)
        self.assertEqual(int.from_bytes(frame[64+128:64+130], 'little'), 0x9000+8*256+64*13)
        self.assertEqual(len(a.descriptor_bytes(0x80003000)), 128)
        self.assertEqual(a.descriptor_bytes(0x80003000)[:8], bytes.fromhex('0101010040000100'))


if __name__ == '__main__':
    unittest.main()
