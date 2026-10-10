import csv
from pathlib import Path
import tempfile
import unittest
import collect_itlb_asid_exec_linear as c


def csr_rows():
    rows=[]
    for i,csr in enumerate([8,15]*3):
        word=(csr<<20)|0x2773;cycle=10*i+10
        def row(event,delta,**kw):
            return dict(event=event,cycle=str(cycle+delta),trans_id='0',order=str(i),
                trap='0',mem_rmask='0',mem_wmask='0',insn=hex(word),rd_wdata='0',
                pc=hex(0x80002000+4*i),**kw)
        rows.extend([row('arch_start',0),row('cvx_req',1),row('cvx_resp',2),row('retire',3)])
    return rows


class LinearCollector(unittest.TestCase):
    def test_packed_fields_exact(self):
        value=(1<<188)|(0x1234567<<159)|(0xaaaa<<143)
        bits=format(value,'0189b')
        self.assertEqual(c.packed_field(bits,'valid'),'1')
        self.assertEqual(int(c.packed_field(bits,'vpn'),2),0x1234567)
        self.assertEqual(int(c.packed_field(bits,'asid'),2),0xaaaa)

    def test_unknown_inactive_payload_not_fabricated(self):
        self.assertEqual(c.packed_field('0'+'x'*188,'valid'),'0')
        self.assertEqual(c.packed_field('0'+'x'*188,'asid'),'x'*16)

    def test_bad_packed_width_or_field(self):
        for bits,name in [('0'*188,'valid'),('0'*189,'foreign'),('?'*189,'valid')]:
            with self.assertRaises(ValueError):c.packed_field(bits,name)

    def test_actual_saved_vcd_header_and_source_binding(self):
        path=c.life.OUT/'itlb-asid-exec-timeout-wave-771-agent-20261007-01/itlb-exec.vcd'
        # The retained converter artifact is a real packed189 fixture, not
        # a declaration invented to agree with this decoder.
        if not path.exists():
            path=next((path.parent).glob('*.vcd'))
        reader=iter(c.projected_vcd(path));_,decl=next(reader)
        self.assertEqual(decl[c.pre.SCOPE+'.update_i']['width'],189)
        self.assertEqual(decl[c.pre.SCOPE+'.update_i.asid']['width'],16)
        self.assertEqual(c.source_layout()['RVH'],0)

    def test_duplicate_native_child_rejected(self):
        name=c.pre.SCOPE
        scopes=name.split('.')
        header='$timescale 100fs $end\n'+''.join('$scope module '+s+' $end\n' for s in scopes)
        header+='$var wire 189 u update_i $end\n$scope module update_i $end\n$var wire 1 v valid $end\n$upscope $end\n'
        header+=''.join('$upscope $end\n' for s in scopes)
        # clk/rst must be separate exact top declarations.
        header+='$scope module ara_tb $end\n$var wire 1 c clk $end\n$var wire 1 r rst_n $end\n$upscope $end\n$enddefinitions $end\n#0\n0c\n0r\n'
        with tempfile.TemporaryDirectory() as tmp:
            p=Path(tmp)/'wave.vcd';p.write_text(header)
            with self.assertRaisesRegex(ValueError,'Ambiguous'):next(iter(c.projected_vcd(p)))

    def test_finite_id_reuse_six_reads(self):
        self.assertEqual(c.csr_lifecycle(csr_rows())['requests'],6)

    def test_missing_duplicate_and_foreign_activity(self):
        cases=[]
        r=csr_rows();del r[1];cases.append(r)
        r=csr_rows();r.insert(3,dict(r[2]));cases.append(r)
        r=csr_rows();r[0]['insn']='0x30002773';cases.append(r)
        r=csr_rows();r[3]['rd_wdata']='1';cases.append(r)
        r=csr_rows();r[2]['cycle']='1';cases.append(r)
        for rows in cases:
            with self.assertRaises(ValueError):c.csr_lifecycle(rows)

    def test_actual_timeout_csr_prefix_cannot_qualify(self):
        path=c.life.OUT/'itlb-asid-exec-old-image-771-agent-20261007-01/commit_trace.csv'
        with path.open() as f:rows=list(csv.DictReader(f))
        with self.assertRaisesRegex(ValueError,'six architectural'):c.csr_lifecycle(rows)

    def test_baseline772_real_design_ledger(self):
        bits,ledger,pins=c.baseline()
        self.assertEqual(len(bits['tests']),772)
        self.assertEqual(ledger[1:],bits['tests'])
        self.assertTrue(all(str(Path(ledger[0])/'snps/coverage/db'/p) in pins for p in bits['design']))

    def test_union_rejects_old_prefix_and_duplicate(self):
        for before,single in [(dict(tests=['x']*772),dict(tests=['z'])),
            (dict(tests=list(map(str,range(771)))),dict(tests=['z'])),
            (dict(tests=list(map(str,range(772)))),dict(tests=['0']))]:
            with self.assertRaises(ValueError):c.full_union(before,single)

    def test_collector_namespace_not_shadowed_by_toggle_state(self):
        self.assertNotIn('old',c.collect.__code__.co_varnames)
        self.assertIs(c.collect.__globals__['old'],c.old)


if __name__=='__main__':unittest.main()
