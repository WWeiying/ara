#!/usr/bin/env python3
"""Host-only oracle/protocol/collector guards; no simulator or generator execution."""
import copy
import importlib.util
from pathlib import Path
import sys
import unittest

sys.dont_write_bytecode=True
spec=importlib.util.spec_from_file_location('wide_compute_runner',Path(__file__).with_name('run_wide_compute.py'))
r=importlib.util.module_from_spec(spec);spec.loader.exec_module(r)
sys.path.insert(0,str(r.HERE))
from matrix_dot_pair import candidate_vectors


def fake_shapes():
    result=[]
    for p in range(1,10):
        s=dict(case=p-1,profile=p,m=1,n=5,kb=2,wl=2,al=1,flags=0,
               outputs={i:0x3f800000+i for i in range(5)})
        s['counters']=r.expected_counters(s);result.append(s)
    s=dict(case=9,profile=1,m=4,n=9,kb=2,wl=2,al=2,flags=1,
           outputs={c*32+n:0x40000000+c*32+n for c in range(4) for n in range(9)})
    s['counters']=r.expected_counters(s);result.append(s)
    return result


def fake_log(shapes,wide):
    def line(tag,**fields):
        return tag+' '+' '.join(k+'='+str(v) for k,v in fields.items())
    lines=[line('WC_CONFIG',version=1,wide=wide,weight_bits=256 if wide else 128,matrix=1)]
    order=[(1000+i,shapes[0]) for i in range(5)]+list(enumerate(shapes))
    for eid,s in order:
        seq=[0,1,2,3,4,5] if s['profile'] in (1,4,7) else [0,2,4]
        for acc in s['outputs']:
            for k in range(s['kb']):
                for st in seq:
                    lines.append(line('WC_FP',episode=eid,acc=acc,block=k,
                         kind=0 if st<2 else 2 if st==2 and s['profile'] in (3,6,8,9) else 1,
                         state=st,op=0,mod=0,rm=0,a='00000001',b='00000002',c='00000003'))
        for acc,bits in s['outputs'].items():
            lines.append(line('WC_OUTPUT',episode=eid,index=acc,bits=f'{bits:08x}'))
        c=s['counters'];probe=(s['profile'],s['m'],s['n'],s['kb'])==(1,4,9,2)
        fields=dict(episode=eid,case=s['case'],recovery=int(eid>=1000),
                    **{k:s[k] for k in ('profile','m','n','kb','wl','al','flags')},
                    **dict(zip(r.COUNTERS,c)),accepted=c[1],act_accepted=c[2],
                    beats=(c[1]+15)//16,stalls=1,overlap=1,result_wait=5,
                    probe_edges=2 if wide and probe else 0,probe_bytes=64 if wide and probe else 0)
        lines.append(line('WC_CASE',**fields))
    for kind in range(5):lines.append(line('WC_FAULT',kind=kind,pending=int(kind==0),drain=2))
    lines.append(line('WC_PASS',normal=len(shapes),recovery=5,faults=5,overlap=len(order),stalls=len(order)))
    return '\n'.join(lines)+'\n'


class WideComputeTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.raw=(r.PRIOR/'matrix.txt').read_text()
        cls.wide=candidate_vectors(cls.raw)
        cls.shapes=fake_shapes();cls.log=fake_log(cls.shapes,1)

    def test_native_all_nine_oracle(self):
        old=r.parse_vectors(self.raw,matrix=False);new=r.parse_vectors(self.wide)
        self.assertEqual(len(old),36)
        self.assertEqual({s['profile'] for s in old},set(range(1,10)))
        for a,b in zip(old,new):
            self.assertEqual(a['outputs'],b['outputs']);self.assertEqual(a['flags'],b['flags'])
            for i in (0,1,2,3,6,7):self.assertEqual(a['counters'][i],b['counters'][i])

    def test_generator_extension_is_exact_and_bounded(self):
        original=(r.ROOT/'verification/qbs/qbs_command_vectors.c').read_text()
        extended=r.extend_generator(original)
        self.assertIn('QBSCMD1 64',extended)
        self.assertIn('id = 36 + (p - 1) * 3',extended)
        self.assertIn('failed |= emit_case(output, 63,',extended)
        self.assertEqual(original.split('int main(')[0],extended.split('int main(')[0])
        with self.assertRaises(ValueError):r.extend_generator(original.replace('QBSCMD1 36','QBSCMD1 37'))

    def test_combined_inputs_renumber_only_commands(self):
        combined=r.combine_vectors([self.raw,(r.PRIOR/'real-m1.txt').read_text(),(r.PRIOR/'real-m4.txt').read_text()])
        cases=r.parse_vectors(combined,matrix=False)
        self.assertEqual(len(cases),38);self.assertEqual(cases[-1]['kb'],6)

    def test_payload_invalid_truncated_duplicate_and_shape(self):
        lines=self.raw.splitlines();weight=next(l for l in lines if l.startswith('W '))
        variants=[self.raw.rsplit('END',1)[0],self.raw+'O 0 00000000\n',
                  self.raw.replace('CMD 0 1 1 1 1 5 2','CMD 0 1 1 1 1 0 2',1),
                  self.raw.replace(weight,weight+'\n'+weight,1),
                  self.raw.replace(weight,weight.replace('ffff','fffe'),1),
                  self.raw.replace(weight,'',1),
                  self.raw.replace('O 0 ', 'O 129 ',1)]
        for text in variants:
            with self.subTest(text=text[:30]):
                with self.assertRaises(ValueError):r.parse_vectors(text,matrix=False)

    def test_counter_models_reject_arithmetic_mismatch(self):
        with self.assertRaises(ValueError):r.parse_vectors(self.raw,matrix=True)
        with self.assertRaises(ValueError):r.parse_vectors(self.wide,matrix=False)

    def test_log_accepts_all_substantive_guards(self):
        measured,events=r.check_log(self.log,self.shapes,1)
        self.assertEqual(measured['totals']['normal'],10)
        self.assertTrue(events)
        self.assertEqual(sum(len(e) for e in events.values()),sum(s['counters'][6] for s in self.shapes)+5*self.shapes[0]['counters'][6])

    def test_missing_duplicate_records_rejected(self):
        for tag in ('WC_CONFIG','WC_FP','WC_OUTPUT','WC_CASE','WC_FAULT','WC_PASS'):
            line=next(l for l in self.log.splitlines() if l.startswith(tag+' '))
            for replacement in ('',line+'\n'+line):
                with self.subTest(tag=tag,duplicate=bool(replacement)):
                    with self.assertRaises(ValueError):r.check_log(self.log.replace(line+'\n',replacement+'\n',1),self.shapes,1)

    def test_exact_output_flags_counters_and_metadata_gates(self):
        for tag,old,new in [('WC_OUTPUT','bits=3f800000','bits=3f800001'),
                            ('WC_CASE','result_wait=5','result_wait=4'),
                            ('WC_CASE','weight=1440','weight=1439'),
                            ('WC_CONFIG','matrix=1','matrix=0'),
                            ('WC_FAULT','pending=1','pending=0'),
                            ('WC_PASS','faults=5','faults=4')]:
            line=next(l for l in self.log.splitlines() if l.startswith(tag+' ') and old in l)
            with self.subTest(old=old):
                with self.assertRaises(ValueError):r.check_log(self.log.replace(line,line.replace(old,new),1),self.shapes,1)
        line=next(l for l in self.log.splitlines() if l.startswith('WC_CASE ') and 'probe_bytes=64' in l)
        with self.assertRaises(ValueError):r.check_log(self.log.replace(line,line.replace('probe_bytes=64','probe_bytes=0')),self.shapes,1)

    def test_fp_order_unknown_and_wrong_owner_rejected(self):
        lines=self.log.splitlines();first=next(i for i,l in enumerate(lines) if l.startswith('WC_FP '))
        changed=lines.copy();changed[first],changed[first+1]=changed[first+1],changed[first]
        with self.assertRaises(ValueError):r.check_log('\n'.join(changed),self.shapes,1)
        for old,new in [('a=00000001','a=xxxxxxxx'),('acc=0','acc=127'),('state=0','state=6')]:
            with self.assertRaises(ValueError):r.check_log(self.log.replace(old,new,1),self.shapes,1)

    def test_fp_operands_are_preserved_for_pair_comparison(self):
        _,a=r.check_log(self.log,self.shapes,1)
        _,b=r.check_log(self.log.replace('a=00000001','a=00000002',1),self.shapes,1)
        self.assertNotEqual(a,b)

    def test_fatal_zero_exit_and_unknown_record_rejected(self):
        for extra in ('Fatal: test','Error-[FAIL]','Assertion abc failed','WC_IGNORED value=1'):
            with self.assertRaises(ValueError):r.check_log(self.log+extra+'\n',self.shapes,1)

    def test_minimal_sources_exclude_parallel_reader_files(self):
        names={p.name for p in r.SOURCES}
        self.assertIn('qbs_weight_wide_bank.sv',names)
        for name in ('qbs_engine.sv','qbs_read_engine.sv','qbs_akv_shared_reader.sv','shared_reader_types.svh'):
            self.assertNotIn(name,names)
        self.assertEqual(len(names),len(r.SOURCES))

    def test_valid_before_ready_and_latched_tags_static_contract(self):
        text=(r.HERE/'qbs_wide_compute_tb.sv').read_text()
        task=text.split('task automatic send_weight(',1)[1].split('endtask',1)[0]
        self.assertLess(task.index('wvalid=1'),task.index('@(posedge clk)'))
        self.assertNotIn('while (!wready)',task)
        self.assertNotIn('expected_rows',task)
        self.assertIn('!== held',task)
        self.assertIn('WC_OWNED_FOUR_ROW_WINDOW',text)


if __name__=='__main__':unittest.main(verbosity=2)
