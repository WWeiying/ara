"""Host parser/oracle mutations. Synthetic logs are never native evidence."""
import copy
import importlib.util
from pathlib import Path
import re
import tempfile
import unittest

HERE=Path(__file__).resolve().parent
def load(name):
    spec=importlib.util.spec_from_file_location('gate_test_'+name,HERE/(name+'.py'))
    module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module);return module
c=load('cases');check=load('check')


def binding():
    return dict(pcs={name:dict(pc=0x80001000+8*i,insn=c.instruction(name)) for i,name in enumerate(c.OP_NAMES)},
                addresses=dict(descriptor=0x80010000,queries=0x80020000,keys=0x80030000,values=0x80040000))


def guest_log(manifest,b):
    lines=[]
    def row(tag,**data):
        lines.append('GATE_'+tag+' '+' '.join(k+'='+(format(v,'016x') if k in check.HEXES else str(v)) for k,v in data.items()))
    rows=manifest['cases'];row('START',mode=manifest['mode'],cases=len(rows))
    row('ADDRESS',descriptor=b['addresses']['descriptor'],q=b['addresses']['queries'],k=b['addresses']['keys'],v=b['addresses']['values'])
    traps=0
    for item in rows:
        a=item['a']
        if item['op'] in ('full','v1full','bad_full'):
            a=0x10000000 if item['fault']==6 else b['addresses']['descriptor']+int(item['fault']==7)
        pc=b['pcs'][item['op']]['pc']
        row('CASE',id=item['id'],pc=pc,a=a,b=item['b'],fcsr=item['frm']*32+(8|item['expected_flags']),
            vcsr=5,vstart=item['vstart'],vl=0,vtype=(1<<63) if item['vill'] else 0xc0,traps=int(bool(item['cause'])),errors=0)
        if item['cause']:
            traps+=1;row('TRAP',id=item['id'],pc=pc,cause=item['cause'],tval=item['tval'],mstatus=0)
        if item['op']=='info' and not item['cause']:
            row('INFO',id=item['id'],index=item['a'],value=c.info(item['a']),mstatus=0)
        for index,bits in enumerate(item['expected']):row('OUT',id=item['id'],index=index,bits=bits)
        row('MEMORY',id=item['id'],outside=item['outside_hash'],errors=0)
    row('RVV',errors=0);row('DONE',mode=manifest['mode'],cases=len(rows),traps=traps,errors=0)
    return '\n'.join(lines)+'\n'


def trace_line(tag,**fields):
    return '123@0.0:akv_arch_'+tag+' '+' '.join(k+'='+('0x%x'%v if k in check.TRACE_HEX else str(v)) for k,v in fields.items())+'\n'


def short_trace(manifest,b,calls,address,memory=False):
    text='';seq=0
    for case,call in zip(manifest['cases'],calls):
        if case['layer']=='decode':continue
        seq+=1;pc=b['pcs'][case['op']]['pc']
        text+=trace_line('begin',seq=seq,pc=pc,insn=case['insn'],rs1=call['a'],rs2=call['b'],frm=case['frm'],fflags=8)
        if case['layer']=='memory':continue
        if case['op']=='full':
            reads=[(address['descriptor'],64)]+[(address['q']+i*256,case['d']*2) for i in range(case['rows'])]
            reads += [(address[k]+i*256,case['d']*2) for k in ('k','v') for i in range(case['active_tokens'])]
            for at,size in reads:text+=trace_line('read',seq=seq,pc=pc,address=at,bytes=size)
        text+=trace_line('end',seq=seq,pc=pc,status=int(bool(case['cause'])),fflags=case['expected_flags'],
            valid=int(case['context']),tile=case['tile'],tokens=case['active_tokens'],tval=case['tval'] if case['cause'] else 0)
    return text


class GatesTests(unittest.TestCase):
    def test_exact_instruction_words_in_guest(self):
        source=(HERE/'issue.S').read_text()
        for name in c.OP_NAMES:
            match=re.search(r'ISSUE '+name+r', (0x[0-9a-f]+)',source)
            self.assertIsNotNone(match);self.assertEqual(int(match[1],16),c.instruction(name))

    def test_finite_geometry_and_exact_rounding(self):
        rows=c.cases();self.assertEqual([r['id'] for r in rows],list(range(len(rows))))
        self.assertEqual({r['t'] for r in rows if r['label'].startswith('shape_') and r['op']=='qk'},{1,2,3,17,64})
        self.assertEqual({r['d'] for r in rows if r['label'].startswith('shape_')},{64,96,128})
        rounding=[r for r in rows if r['label'] in ['round_'+str(i) for i in range(5)]]
        self.assertEqual([r['expected'][0] for r in rounding],[0x3c00,0x3c00,0x3c00,0x3c01,0x3c01])
        self.assertTrue(all(r['expected_flags']==1 for r in rounding))
        self.assertEqual(c.info(4),0);self.assertEqual(c.info(2)&(1<<39),0)
        with tempfile.TemporaryDirectory() as temporary:
            p=Path(temporary);c.emit(p,0);header=(p/'fixture.h').read_text()
            self.assertNotIn('True',header);self.assertNotIn('False',header)

    def test_same_context_recovery_and_fault_layers(self):
        rows=c.cases()
        negatives=[r for r in rows if r['label'] in ('bad_dimension','overshoot','bad_base','bad_control','bad_rd',
                    'bad_source','alias','bad_frm','bad_start','fs_off','vs_off')]
        self.assertEqual(len(negatives),11)
        for r in negatives:
            next_good=rows[r['id']+1]
            self.assertEqual(next_good['label'],r['label']+'_next_good')
            self.assertEqual(next_good['op'],'qk');self.assertEqual(next_good['init'],0)
        self.assertTrue(all(r['tval']==r['insn'] for r in negatives if r['layer'] in ('front','decode')))
        self.assertTrue(all(r['tval']==0 for r in negatives if r['layer']=='backend'))

    def test_guest_all_modes_and_terminal_mutations(self):
        b=binding()
        for mode in range(3):
            m=dict(mode=mode,cases=c.cases(mode));raw=guest_log(m,b)
            result,_,_=check.guest(raw,m,b);self.assertEqual(result['cases'],len(m['cases']))
            for changed in [raw+raw.splitlines()[-1]+'\n',raw.replace('vcsr=5','vcsr=0',1),
                            '\n'.join(raw.splitlines()[:-1])+'\n',raw.replace('errors=0','errors=1',1)]:
                with self.assertRaises(ValueError):check.guest(changed,m,b)

    def test_output_guard_and_trap_mutations(self):
        m=dict(mode=0,cases=c.cases());b=binding();raw=guest_log(m,b)
        out=next(x for x in raw.splitlines() if x.startswith('GATE_OUT '))
        trap=next(x for x in raw.splitlines() if x.startswith('GATE_TRAP '))
        changes=[raw.replace(out,out[:-1]+('1' if out[-1]!='1' else '2'),1),
                 raw.replace(trap,trap.replace('cause=2','cause=5'),1),
                 raw.replace('outside='+format(m['cases'][0]['outside_hash'],'016x'),'outside=0000000000000000',1)]
        for changed in changes:
            with self.assertRaises(ValueError):check.guest(changed,m,b)

    def test_short_real_route_contract_and_ignored_resident_off_rejected(self):
        m=dict(mode=1,cases=c.cases(1));b=binding();_,calls,address=check.guest(guest_log(m,b),m,b)
        raw=short_trace(m,b,calls,address);result=check.architectural(raw,m,b,calls,address)
        self.assertEqual(result['helper_calls'],3)
        for changed in [raw+raw.splitlines()[-1]+'\n',raw.replace('fflags=8','fflags=0',1),
                        raw.replace('bytes=64','bytes=32',1),raw.replace('valid=0','valid=1')]:
            with self.assertRaises(ValueError):check.architectural(changed,m,b,calls,address)

    def test_memory_callback_no_end_is_narrowly_scoped(self):
        rows=c.cases();begin=next(i for i,r in enumerate(rows) if r['label']=='descriptor_mmio')
        m=dict(mode=0,cases=copy.deepcopy(rows[begin:begin+3]));b=binding()
        _,calls,address=check.guest(guest_log(m,b),m,b)
        raw=short_trace(m,b,calls,address);result=check.architectural(raw,m,b,calls,address)
        self.assertEqual(result['memory_callback_faults'],1)
        fake=trace_line('end',seq=1,pc=b['pcs']['full']['pc'],status=2,fflags=0,valid=0,tile=0,tokens=64,tval=0x10000000)
        first,rest=raw.split('\n',1)
        with self.assertRaises(ValueError):check.architectural(first+'\n'+fake+rest,m,b,calls,address)

    def test_trace_schema_duplicate_or_unknown_rejected(self):
        for raw in ['akv_arch_info index=0 result=0x0 index=0\n','akv_arch_unknown x=1\n',
                    'akv_arch_info index=0 result=nope\n']:
            with self.assertRaises(ValueError):check.trace_rows(raw)


if __name__=='__main__':unittest.main()
