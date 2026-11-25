import copy
import csv
import io
from pathlib import Path
import unittest
from unittest.mock import patch

import check as old
import check_vcsr_v2 as new
from test_qbs import fixture
from test_matrix_successor import matrix_fixture


def corrected_fixture(backend='native'):
    f = fixture(backend)
    return (f[0].replace(' vcsr=0 ',' vcsr=2 '), *f[1:])


def commit_fixture():
    f = corrected_fixture()
    result = new.parse_log(*f)
    build = f[1]
    instructions = {0x100:0xc0002073,0x180:0xc0002073,0x200:0x00a0d073,
                    0x150:0x003026f3,0x160:0x00f02773,0x170:0x008027f3}
    stamps = {0x104+i*4 for i in range(6)}
    instructions.update({pc:0xc00027f3 for pc in stamps})
    proof = ({},instructions,{0x200},set(instructions)-{0x200},stamps,[0x100,0x180])
    rows = []
    def put(pc,insn,data=0,trap=0):
        rows.append(dict(cycle=len(rows)*3,event='retire',order=len(rows),pc=f'{pc:016x}',
                         insn=f'{insn:08x}',rd=(insn>>7)&31,rd_wdata=f'{data:016x}',trap=trap))
    for trial in result['metrics']['trials']:
        csr = trial['csr']
        put(0x80,0x00f05073)
        put(0x100,0xc0002073)
        put(0x104,0xc00027f3,csr['t0'])
        for _ in range(8):
            put(0x200,0x00a0d073)
        put(0x108,0xc00027f3,csr['t1'])
        put(0x150,0x003026f3,csr['quant_fcsr'])
        for i in range(2,6):
            put(0x104+i*4,0xc00027f3,csr[f't{i}'])
        put(0x150,0x003026f3,csr['fcsr'])
        put(0x160,0x00f02773,2)
        put(0x170,0x008027f3,0)
        put(0x180,0xc0002073)
    return rows,build,result,proof


def check_commit(rows,build,result,proof):
    stream = io.StringIO()
    writer = csv.DictWriter(stream,fieldnames=('cycle','event','order','pc','insn','rd','rd_wdata','trap'))
    writer.writeheader()
    writer.writerows(rows)
    with patch.object(Path,'open',return_value=io.StringIO(stream.getvalue())):
        return new.parse_commit(Path('synthetic.csv'),build,result,proof)


class ScopedVcsrTests(unittest.TestCase):
    def test_only_parser_delta(self):
        new.verify_parser_delta()

    def test_old_fails_new_requires_exact_vcsr_two(self):
        for backend in ('native','rvv','rvv_x32'):
            f = corrected_fixture(backend)
            self.assertEqual(new.parse_log(*f)['state'],'PASS')
            with self.assertRaisesRegex(ValueError,'Vector CSR/quantization exception contract'):
                old.parse_log(*f)
            for value in (0,1,3,4,6):
                with self.subTest(backend=backend,value=value),self.assertRaises(ValueError):
                    new.parse_log(f[0].replace(' vcsr=2 ',f' vcsr={value} '),*f[1:])

    def test_numeric_flags_guards_phases_not_weakened(self):
        f = corrected_fixture()
        for old_value,bad in (('bits=3f800000','bits=3f800001'),(' fcsr=1 ',' fcsr=0 '),
                (' fcsr=9 ',' fcsr=1 '),(' vstart=0',' vstart=1'),
                ('a5'*64,'a4'+'a5'*63),('phase_compute_cycles=2048','phase_compute_cycles=2047'),
                ('activation_axi_bytes_saved=0','activation_axi_bytes_saved=2336'),
                ('OPQ_Q8 trial=0 block=0 hex=00','OPQ_Q8 trial=0 block=0 hex=01')):
            with self.subTest(old_value=old_value),self.assertRaises(ValueError):
                new.parse_log(f[0].replace(old_value,bad,1),*f[1:])

    def test_m8_gate_unchanged(self):
        f = matrix_fixture()
        text = f[0].replace(' vcsr=0 ',' vcsr=2 ')
        self.assertEqual(new.parse_log(text,*f[1:])['state'],'PASS')
        with self.assertRaises(ValueError):
            new.parse_log(text.replace('coop=1','coop=0'),*f[1:])

    def test_commit_requires_real_write_and_snapshot_alignment(self):
        rows,build,result,proof = commit_fixture()
        self.assertEqual(check_commit(rows,build,result,proof)['state'],'ELF_COMMIT_VCSR_PRESERVATION_CHECKED')
        mutations = []
        for pc,field,value in ((0x200,'insn','00a05073'),(0x160,'rd_wdata','0000000000000000'),
                              (0x150,'rd_wdata','0000000000000011'),(0x108,'rd_wdata','0000000000000001'),
                              (0x180,'trap',1)):
            modified = copy.deepcopy(rows)
            target = next(row for row in modified if int(row['pc'],16)==pc)
            target[field] = value
            mutations.append(modified)
        for modified in mutations:
            with self.assertRaises(ValueError):
                check_commit(modified,build,result,proof)

    def test_extra_vcsr_write_and_post_quant_saturation_fail(self):
        rows,build,result,proof = commit_fixture()
        for word in (0x00f05073,(0x2f<<26)|0x57):
            modified = copy.deepcopy(rows)
            replacement = modified[12]
            replacement['pc'],replacement['insn'] = '0000000000000300',f'{word:08x}'
            changed = copy.deepcopy(proof)
            changed[1][0x300] = word
            with self.assertRaises(ValueError):
                check_commit(modified,build,result,changed)

    def test_commit_truncation_fails(self):
        rows,build,result,proof = commit_fixture()
        with self.assertRaises(ValueError):
            check_commit(rows[:-1],build,result,proof)


if __name__ == '__main__':
    unittest.main()
