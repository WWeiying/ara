from pathlib import Path
import struct
import subprocess
import tempfile
import unittest

from rtl_build import gather, HOST_FLAGS, HERE
from rtl_check import (SHAPES, COUNTERS, PERF_FIELDS, SUMMARY_FIELDS, fnv,
                       check_output, check_perf)


def fixture():
    golden = bytes(range(256))*6
    cases = [dict(c, fcsr=9) for c in SHAPES]
    lines = ['PAIR_CAP native=1 panel4=1 vlenb=128 pairs=3']
    records = []
    for c in cases:
        i, d, t = c['id'], c['d'], c['tokens']
        for mode in (0, 1):
            lines.append(f"PAIR_BEGIN case={i} mode={mode} head={c['head']} d={d} tokens={t} stride={c['stride']}")

            def emit(command):
                r = dict.fromkeys(PERF_FIELDS, 0)
                r.update(seq=len(records)+1, id=3, command=command, success=1,
                         context_ready=int(command != 3), busy_cycles=17)
                if command == 4:
                    r.update(v2_full=1, q_external_bytes=4*d, kv_external_bytes=256*d,
                             read_ranges=131, read_payload_bytes=64+260*d,
                             ar=131, r_beats=600, read_outstanding_max=2)
                elif command == 6:
                    r.update(v2_column_load=1, v2_column_panel=mode,
                             v2_logical_column=4 if mode else 1,
                             v2_k_view_bank_cycles=8, replay_bytes=512 if mode else 128)
                elif command == 2:
                    r.update(load=1, v2_row_load=1, replay_bytes=2*d)
                else:
                    r.update(release=1)
                records.append(r)
                lines.append('[AKV_PERF] '+' '.join(f'{k}={r[k]}' for k in PERF_FIELDS))

            emit(4)
            for _ in range(d//4 if mode else 2*d):
                emit(6)
            lines.append(f"PAIR_QK case={i} mode={mode} outputs={2*t} tailbytes={512-8*t} compared=512 hash={fnv(golden[i*512:(i+1)*512]):08x} fcsr=9 vcsr=5 guardbytes=1152 inputbytes=34112 errors=0")
            for _ in range(t if mode else 2*t):
                emit(2)
            emit(3)
            lines.append(f"PAIR_PV case={i} mode={mode} outputs={2*d} gapbytes={1024-4*d} baseline_bytes={mode*1024} hash=12345678 fcsr=11 vcsr=5 guardbytes=1152 inputbytes=34112 errors=0")
            lines.append(f'PAIR_END case={i} mode={mode} errors=0')
    lines += ['PAIR_SUITE_PASS pairs=3 runs=6 qk_outputs=512 pv_outputs=1152 commands=1044', 'Core Test *** SUCCESS']
    total = {k: max(r[k] for r in records) if k == 'read_outstanding_max' else sum(r[k] for r in records) for k in COUNTERS}
    total.update(records=1044, success_records=1044, fault_records=0, validation_fault_records=0)
    lines.append('[AKV_PERF_SUMMARY] '+' '.join(f'{k}={total[k]}' for k in SUMMARY_FIELDS))
    return '\n'.join(lines), cases, golden


class GateTest(unittest.TestCase):
    def test_valid_complete_fixture(self):
        text, cases, golden = fixture()
        self.assertEqual(check_output(text, cases, golden)['runs'], 6)
        counters = check_perf(text)
        self.assertEqual((counters['v2_column_load'], counters['v2_column_panel'], counters['v2_row_load']), (648,72,384))
        self.assertEqual(counters['replay_bytes'], 196416)

    def test_numeric_missing_fake_and_mutations(self):
        text, cases, golden = fixture()
        mutations = [text.replace('compared=512', 'compared=508', 1),
                     text.replace('vcsr=5', 'vcsr=1', 1),
                     text.replace('fcsr=9', 'fcsr=8', 1),
                     text.replace('errors=0', 'errors=1', 1),
                     text.replace('inputbytes=34112', 'inputbytes=0', 1),
                     text.replace('hash=12345678', 'hash=ffffffff', 1),
                     text.replace('PAIR_END case=0 mode=0 errors=0\n', ''),
                     text+'\nPAIR_SUITE_PASS pairs=3 runs=6 qk_outputs=512 pv_outputs=1152 commands=1044',
                     'PAIR_SUITE_PASS pairs=3 runs=6 qk_outputs=512 pv_outputs=1152 commands=1044\nCore Test *** SUCCESS',
                     text.replace('Core Test *** SUCCESS', ''), text+'\nFATAL']
        for mutation in mutations:
            with self.subTest(mutation=mutation[-80:]), self.assertRaises(ValueError):
                check_output(mutation, cases, golden)
        wrong = bytearray(golden)
        wrong[4] ^= 1
        with self.assertRaises(ValueError):
            check_output(text, cases, wrong)

    def test_trace_missing_unknown_wrong_work(self):
        text, _, _ = fixture()
        lines = text.splitlines()
        index = next(i for i,s in enumerate(lines) if s.startswith('[AKV_PERF]'))
        mutations = ['\n'.join(lines[:index]+lines[index+1:]),
                     text.replace('success=1', 'success=x', 1),
                     text.replace('read_payload_bytes=16704', 'read_payload_bytes=16703', 1),
                     text.replace('context_ready=1', 'context_ready=0', 1),
                     text.replace('replay_bytes=512', 'replay_bytes=128', 1),
                     text.replace('v2_column_panel=1', 'v2_column_panel=0', 1),
                     text.replace('fault=0', 'fault=1', 1),
                     text.replace('load=1', 'load=0', 1),
                     '\n'.join(s for s in lines if not s.startswith('[AKV_PERF_SUMMARY]')),
                     text+'\n[QBS_PERF] seq=1']
        for mutation in mutations:
            with self.subTest(mutation=mutation[-80:]), self.assertRaises(ValueError):
                check_perf(mutation)

    def test_stage_boundary(self):
        text, _, _ = fixture()
        lines = text.splitlines()
        index = next(i for i,s in enumerate(lines) if s.startswith('PAIR_QK '))
        lines[index], lines[index+1] = lines[index+1], lines[index]
        with self.assertRaises(ValueError):
            check_perf('\n'.join(lines))

    def test_gather_coordinates_and_padding(self):
        q = b''.join(struct.pack('<H', i) for i in range(1536))
        k = b''.join(struct.pack('<H', i) for i in range(65536))
        v = b''.join(struct.pack('<H', 65535-i) for i in range(65536))
        for c in SHAPES:
            data = gather(q,k,v,c)
            d, t, h, stride = (c[x] for x in ('d','tokens','head','stride'))
            for row in range(2):
                for dim in range(d):
                    self.assertEqual(struct.unpack_from('<H',data,row*stride+2*dim)[0], (h*6+row)*128+dim)
                    self.assertEqual(struct.unpack_from('<H',data,33984+row*512+2*dim)[0], 65535-((h*256+row)*128+dim))
                self.assertEqual(data[33984+row*512+2*d:33984+(row+1)*512], b'\xa5'*(512-2*d))
                self.assertEqual(data[33408+row*256+4*t:33408+(row+1)*256], b'\xa5'*(256-4*t))
            for token in range(64):
                for dim in range(d):
                    coordinate = (h*256+token)*128+dim
                    self.assertEqual(struct.unpack_from('<H',data,640+2*(token*d+dim))[0], coordinate)
                    self.assertEqual(struct.unpack_from('<H',data,17024+2*(token*d+dim))[0], 65535-coordinate)
            live = {row*stride+j for row in range(2) for j in range(2*d)}
            self.assertTrue(all(data[i] == 0xa5 for i in range(640) if i not in live))

    def test_host_oracle_exact_integer_coordinates(self):
        with tempfile.TemporaryDirectory(prefix='akv-pair-host-') as tmp:
            out = Path(tmp)
            oracle = out/'oracle'
            subprocess.run(['/usr/bin/gcc',*HOST_FLAGS,str(HERE/'rtl_oracle.c'),'-lm','-o',str(oracle)], check=True, timeout=60, capture_output=True)
            q = [(head*2+dim)%7-3 for head in range(12) for dim in range(128)]
            k = [(head*3+token+dim*2)%9-4 for head in range(2) for token in range(256) for dim in range(128)]
            (out/'q').write_bytes(b''.join(struct.pack('<e',v) for v in q))
            (out/'k').write_bytes(b''.join(struct.pack('<e',v) for v in k))
            result = subprocess.run([str(oracle),str(out/'q'),str(out/'k'),str(out/'golden')], check=True, capture_output=True, text=True, timeout=60)
            expected = bytearray(b'\xa5'*1536)
            for c in SHAPES:
                for row in range(2):
                    for token in range(c['tokens']):
                        value = sum(q[(c['head']*6+row)*128+dim] * k[(c['head']*256+token)*128+dim] for dim in range(c['d']))
                        struct.pack_into('<f',expected,c['id']*512+row*256+token*4,value)
            self.assertEqual((out/'golden').read_bytes(),expected)
            self.assertEqual(len(result.stdout.splitlines()),3)
            self.assertTrue(all(line.endswith('fcsr=0') for line in result.stdout.splitlines()))


if __name__ == '__main__':
    unittest.main()
