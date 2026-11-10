#!/usr/bin/env python3
"""Host contract/mutation tests; fixtures are not guest acceptance evidence."""
from pathlib import Path
import struct
import subprocess
import tempfile
import unittest

import check_ggml_functional as c
import run_ggml_functional as r


class GateTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        self.golden = struct.pack('<512f', *[i/32 for i in range(512)])
        (self.root/'output.bin').write_bytes(self.golden)
        for arm in ('m8', 'm4', 'shape'):
            rows, _, _ = c.geometry(arm)
            (self.root/f'workspace_{arm}.bin').write_bytes(bytes(range(256))*(rows*8*292//256)+
                bytes(range((rows*8*292)%256)))
            count = len(c.command_shapes(arm))
            (self.root/f'flags_{arm}.bin').write_bytes(struct.pack('<'+'I'*count, *([1]*count)))
            (self.root/f'headers_{arm}.bin').write_bytes(struct.pack('<'+'Q'*count, *([0x1234]*count)))

    def tearDown(self):
        self.temp.cleanup()

    def fixture(self, arm):
        rows, _, _ = c.geometry(arm)
        shapes = c.command_shapes(arm)
        packed = (self.root/f'workspace_{"m4" if arm == "rvv" else arm}.bin').read_bytes()
        output = self.golden[:rows*64*4]
        records = []
        def dump(kind, cmd, data):
            records.extend(f'G4_BYTES kind={kind} command={cmd} offset={i} hex={data[i:i+32].hex()}'
                           for i in range(0, len(data), 32))
        records.append(f'GGML_RISCV_REPACK={"Q4_K_32x1_Q8_K" if arm == "rvv" else "QBS type=q4_K"} shape=2048x64')
        if shapes:
            records.append(f'GGML_RISCV_QBS_CALL type=q4_K mode=gemm k=2048 input_rows={rows} output_rows=64 split_k=0')
        for _, _, m, n in shapes:
            records.append(f'GGML_RISCV_QBS_COMMAND seq=1 weight_type=q4_K m={m} n={n} k_blocks=8 access=0 segmented=0 emulated=0')
        records.append(f'G4_META arm={arm} m={rows} n=64 k=2048 wide={int(arm == "m8")} qbs={int(arm != "rvv")} graph_calls=1 commands={len(shapes)} info_calls={0 if arm == "rvv" else 5} workspace_bytes={len(packed)} flags_probe=1')
        dump('workspace', 0, packed); dump('output', 0, output)
        for i, (row, col, m, n) in enumerate(shapes):
            seed = 8 if i % 2 else 0
            records.append(f'G4_COMMAND id={i} m={m} n={n} kb=8 woff={col*8*144} aoff={row*8*292} stride=64 seed={seed} flags={seed|1} status=0 header=0000000000001234')
            dump('activation', i, packed[row*8*292:(row+m)*8*292])
            dump('command_output', i, b''.join(output[((row+j)*64+col)*4:((row+j)*64+col+n)*4]
                                              for j in range(m)))
        records += [f'G4_PASS arm={arm} outputs={rows*64} integrity=1 cycles_measured=0',
                    f'G4_EXIT arm={arm} code=0']
        return '\n'.join(records)+'\n'

    def reject(self, text, arm='m8'):
        with self.assertRaises(ValueError): c.check_arm(arm, text, self.root)

    def test_all_four_contracts(self):
        for arm in c.ARMS:
            with self.subTest(arm=arm):
                self.assertEqual(c.check_arm(arm, self.fixture(arm), self.root)['state'], 'PASS')

    def test_quantization_mutation(self):
        s = self.fixture('m8')
        self.reject(s.replace('kind=workspace command=0 offset=0 hex=00',
                              'kind=workspace command=0 offset=0 hex=ff', 1))

    def test_missing_byte_chunk(self):
        self.reject('\n'.join(x for x in self.fixture('m8').splitlines()
                              if 'kind=workspace command=0 offset=32 ' not in x))

    def test_duplicate_chunk(self):
        s = self.fixture('m8'); line = next(x for x in s.splitlines() if x.startswith('G4_BYTES'))
        self.reject(s.replace(line, line+'\n'+line, 1))

    def test_flags_no_nx(self):
        self.reject(self.fixture('m8').replace('seed=0 flags=1', 'seed=0 flags=0', 1))

    def test_flags_lost_sticky_dz(self):
        self.reject(self.fixture('m8').replace('seed=8 flags=9', 'seed=8 flags=1', 1))

    def test_wrong_descriptor(self):
        self.reject(self.fixture('m8').replace('woff=18432 ', 'woff=0 ', 1))

    def test_native_matrix_bits(self):
        self.reject(self.fixture('m8').replace('kind=output command=0 offset=0 hex=00',
                                              'kind=output command=0 offset=0 hex=01', 1))

    def test_command_raw_bits(self):
        self.reject(self.fixture('m8').replace('kind=command_output command=0 offset=0 hex=00',
                                              'kind=command_output command=0 offset=0 hex=01', 1))

    def test_rvv_cannot_issue_or_probe_qbs(self):
        self.reject(self.fixture('rvv').replace('info_calls=0', 'info_calls=1'), 'rvv')
        self.reject('GGML_RISCV_QBS_CALL unexpected\n'+self.fixture('rvv'), 'rvv')

    def test_missing_or_duplicate_terminal(self):
        self.reject(self.fixture('m8').replace('G4_EXIT arm=m8 code=0', 'G4_EXIT arm=m8 code=1'))
        self.reject(self.fixture('m8')+'G4_EXIT arm=m8 code=0\n')

    def test_no_emulated_acceptance(self):
        self.reject(self.fixture('m8').replace('emulated=0', 'emulated=1', 1))

    def test_frozen_abi_exact_compatibility(self):
        model = r.QEMU.parent.parent/'qemu-10.2.0/target/riscv/qbs_abi.h'
        new = subprocess.check_output(['git','-C',r.ROOT,'show',r.SDK_COMMIT+':apps/common/qbs_abi.h'], text=True)
        self.assertTrue(r.compatible_abi(model.read_text(), new)['ordinary_qbexec_unchanged'])
        with self.assertRaises(ValueError):
            r.compatible_abi(model.read_text(), new.replace('#define QBS_QBEXEC_FUNCT3 0u',
                                                          '#define QBS_QBEXEC_FUNCT3 2u'))

    def test_fixed_bounds_and_no_qbacc_client(self):
        code = (r.HERE/'run_ggml_functional.py').read_text()
        self.assertIn('p.wait(timeout=600)', code)
        self.assertIn("'--target', 'ggml'", code)
        self.assertNotIn('qbs_encode_qbacc', (r.HERE/'ggml_functional.cpp').read_text())
        self.assertEqual(c.command_shapes('m8'), [(0, i, 8, 16) for i in (0,16,32,48)])
        self.assertEqual(len(c.command_shapes('m4')), 4)
        self.assertEqual(len(c.command_shapes('shape')), 2)
        self.assertFalse(c.command_shapes('rvv'))


if __name__ == '__main__': unittest.main()
