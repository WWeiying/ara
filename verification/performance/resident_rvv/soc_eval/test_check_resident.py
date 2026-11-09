#!/usr/bin/env python3
"""Adversarial host tests of the new PV work checker, not RTL acceptance."""
import copy
import csv
from pathlib import Path
import tempfile
import unittest

from check_resident import check_successful_pv, geometry, instruction, performance, vector_writes


SHAPE = dict(dimension=96, heads=2, tokens=9, vd=16, vs2=0)
FIELDS = ('cycle,event,arch_seq,vid,lane,source,insn,use_vd,vd,eew,vl,vstart,addr,be,'
          'wdata,nr_lanes,vlen_bits').split(',')


def trace(shape=SHAPE):
    s = geometry(shape)
    def row(event, cycle, **kwargs):
        r = dict(zip(FIELDS, map(str, (cycle, event, 1, 2, 0, 0, f'{s["instruction"]:08x}',
                 1, s['vd'], 1, 256, 0, 0, '00', '0000000000000000', 4, 1024))))
        r.update({k: str(v) for k, v in kwargs.items()})
        return r
    rows = [row('config', 0), row('alloc', 10)]
    for lane in range(4):
        for addr in sorted(s['slots']):
            rows.append(row('write', 11+(addr-s['vd']*4), lane=lane, source=4, addr=addr, be='ff'))
    rows[2:] = sorted(rows[2:], key=lambda r: int(r['cycle']))
    rows.append(row('done', 100))
    return rows


def log(shape=SHAPE):
    s = geometry(shape)
    rows = []
    for lane in range(4):
        rows.append(f'[RESIDENT_PV_LANE] lane={lane} vid=2 tokens={s["tokens"]} '
                    f'elements={s["dimension"]//4} heads={s["heads"]} issued={s["fma_per_lane"]} '
                    f'returned={s["fma_per_lane"]} writes={s["writes"]//4} flags=1 error=0')
    rows.append(f'[RESIDENT_PV_PERF] seq=1 vid=2 control={s["control"]} tokens={s["tokens"]} '
                f'words={s["words"]} heads={s["heads"]} cycles=200 error=0 flags=1 source_words=96 '
                f'seed_words={s["writes"]} coefficients={4*s["tokens"]} '
                f'value_words={4*s["tokens"]*s["words"]} result_words={s["writes"]} '
                f'final_acks={s["writes"]} row_reads={s["tokens"]*s["words"]}')
    return '\n'.join(rows)


class TestPV(unittest.TestCase):
    def check_trace(self, rows, shapes=None):
        with tempfile.TemporaryDirectory() as td:
            p = Path(td)/'trace.csv'
            with p.open('w', newline='') as stream:
                writer = csv.DictWriter(stream, fieldnames=FIELDS)
                writer.writeheader()
                writer.writerows(rows)
            return vector_writes(p, shapes or [SHAPE])

    def test_encoding(self):
        self.assertEqual(instruction(), 0x0485705b)
        for args in ((0, 0), (4, 0), (28, 24), (2, 8), (0, 4)):
            with self.assertRaises(ValueError): instruction(*args)

    def test_matrix(self):
        for d in (64, 96, 128):
            for h in (1, 2):
                for t in (1, 9, 32, 64):
                    s = dict(dimension=d, heads=h, tokens=t)
                    self.assertEqual(self.check_trace(trace(s), [s])[0]['writes'], 4*(d//16)*h)
                    self.assertEqual(len(performance(log(s), [s])), 1)

    def test_bad_write_fields(self):
        for key, value in (('addr', 1000), ('source', 1), ('be', '0f'),
                           ('wdata', 'xxxxxxxxxxxxxxxx'), ('arch_seq', 2), ('vid', 3),
                           ('eew', 2), ('vd', 0), ('vl', 128), ('vstart', 1)):
            rows = trace()
            rows[2][key] = str(value)
            with self.subTest(key=key), self.assertRaises(ValueError): self.check_trace(rows)

    def test_missing_duplicate_and_late_write(self):
        rows = trace()
        for bad in (rows[:2]+rows[3:], rows[:3]+[copy.copy(rows[2])]+rows[3:], rows[:-1],
                    rows[:3]+[dict(rows[3], event='done')]+rows[4:]):
            with self.assertRaises(ValueError): self.check_trace(bad)

    def test_wrong_encoding_and_epoch(self):
        for index, key, value in ((1, 'insn', '048570db'), (1, 'nr_lanes', '8'),
                                  (2, 'cycle', '1'), (2, 'event', 'reset')):
            rows = trace()
            rows[index][key] = value
            if key == 'insn':
                # Removing PV identity must produce missing command, not acceptance.
                rows = rows[:2]
            with self.subTest(key=key), self.assertRaises(ValueError): self.check_trace(rows)

    def test_probe_failures(self):
        original = log()
        s = geometry(SHAPE)
        for bad in (original.replace('source_words=96', 'source_words=95'),
                    original.replace('final_acks=48', 'final_acks=47'),
                    original.replace('seq=1', 'seq=2'),
                    original.replace('flags=1 source', 'flags=2 source'),
                    original.replace('error=0', 'error=1'),
                    original.replace(f'issued={s["fma_per_lane"]}', 'issued=0'),
                    original.replace('lane=3', 'lane=2'),
                    original+'\n[RESIDENT_PV_UNRECOGNIZED] bad=1'):
            with self.assertRaises(ValueError): performance(bad, [SHAPE])

    def test_cross_identity(self):
        with tempfile.TemporaryDirectory() as td:
            p = Path(td)/'trace.csv'
            with p.open('w', newline='') as stream:
                writer = csv.DictWriter(stream, fieldnames=FIELDS)
                writer.writeheader(); writer.writerows(trace())
            ok = check_successful_pv(p, log(), [SHAPE])
            self.assertFalse(ok['numerical_checked'])
            self.assertFalse(ok['protocol_checked'])
            bad = log().replace('vid=2', 'vid=3')
            with self.assertRaises(ValueError): check_successful_pv(p, bad, [SHAPE])


if __name__ == '__main__': unittest.main()
