"""Focused host contracts; generated trace fixtures are NOT simulator evidence."""
import copy
import csv
import importlib.util
import io
from pathlib import Path
import struct
import tempfile
import unittest

HERE=Path(__file__).resolve().parent
def module(name):
    spec=importlib.util.spec_from_file_location('features_test_'+name,HERE/(name+'.py'))
    result=importlib.util.module_from_spec(spec);spec.loader.exec_module(result);return result
f=module('fixture');b=module('build');c=module('check')


def numeric_log(fixture,data):
    records=[]
    def emit(tag,**row):
        hexes=('q','k','v','out','query_hash','guard_hash','hash','bits')
        records.append('FEATURE_'+tag+' '+' '.join(k+'='+format(v,'x' if k in hexes else 'd') for k,v in row.items()))
    for i,tr in enumerate(fixture['trials']):
        item=fixture['oracle']['cases'][tr['case']];case=item['case'];heads=case.get('rows',case['heads'])
        n=case['heads']*case['dimension'];groups=case['heads']//heads
        emit('CALL',trial=i,case=tr['case'],requested=tr['requested'],frm=tr['frm'],
            initial=tr['frm']*32+tr['initial_flags'],begin=100+i*100,returned=150+i*100,end=160+i*100,
            fcsr=tr['frm']*32|item['expected']['fflags']|tr['initial_flags'],vcsr=5,vstart=0,groups=groups,errors=0)
        for g in range(groups):
            emit('GROUP',trial=i,group=g,first=g*heads,rows=heads,
                q=0x81000000+g*heads*256,k=0x82000000+g*65536,v=0x83000000+g*65536,out=0x84000000+g*heads*512)
        query=bytearray(b'\xa5'*1536)
        for h,row in enumerate(case.get('query_rows',[0,1])):
            query[h*256:h*256+case['dimension']*2]=data[row*256:row*256+case['dimension']*2]
        guard=384+(768-n)*6+(2048-heads*case['dimension'])*2+(8-heads)*268+32
        emit('MEMORY',trial=i,query_hash=f.fnv(query),guard_hash=f.fnv(b'\xa5'*guard),guard_bytes=guard)
        for j,bits in enumerate(item['expected']['bits']):emit('OUT',trial=i,index=j,bits=bits)
    emit('DATA',bytes=fixture['data_bytes'],hash=fixture['data_hash'])
    emit('DONE',calls=len(fixture['trials']),errors=0)
    return '\n'.join(records)+'\n'


def retire_log(fixture):
    names=('feature_full_call','feature_terminal_marker',*c.ENTRY_NAMES,'rotation_body')
    binding={name:dict(pc=0x80000000+i*4,end=0x80000004+i*4,insn=0x13) for i,name in enumerate(names)}
    lines=['cycle,event,pc,insn,trap'];cycle=0
    for tr in fixture['trials']:
        events=['feature_full_call']
        for name,count in c.expected_entries(fixture,tr).items():events.extend([name]*count)
        events.append('feature_terminal_marker')
        for name in events:
            cycle+=1;lines.append(f'{cycle},retire,{binding[name]["pc"]:x},13,0')
    return '\n'.join(lines)+'\n',binding


class FullCallTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.oracle,cls.contract,cls.pins=f.target()
        cls.temp=tempfile.TemporaryDirectory();cls.root=Path(cls.temp.name)
        cls.fixtures={};cls.data={}
        for kind in ('perf','functional'):
            p=cls.root/kind;p.mkdir();cls.fixtures[kind]=f.generate(p,kind,cls.oracle);cls.data[kind]=(p/'data.bin').read_bytes()

    @classmethod
    def tearDownClass(cls):cls.temp.cleanup()

    def test_target02_exact_samples_and_source_closure(self):
        self.assertEqual(self.contract['sdk_revision'],f.SDK)
        self.assertEqual(len(self.oracle['cases']),9)
        self.assertFalse(self.oracle['host_libm_used'])
        self.assertTrue(self.oracle['query_conversion_outside_roi'])
        self.assertIn(f.LIBM_SHA,self.pins.values())

    def test_perf_equal_work_and_balanced_initial_flags(self):
        fixture=self.fixtures['perf'];ts=fixture['trials'];work=fixture['work']
        self.assertEqual([t['requested'] for t in ts],[0,1,1,0])
        for arm in (0,1):self.assertEqual(sorted(t['initial_flags'] for t in ts if t['requested']==arm),[0,8])
        self.assertEqual(work['per_call'],[237,4,4,237]);self.assertEqual(len(work['legacy']),482)
        self.assertEqual(len(work['resident']),12)
        totals={name:sum(c.expected_entries(fixture,t)[name] for t in ts) for name in (*c.ENTRY_NAMES,'rotation_body')}
        for name in ('rotation_body','akv_experimental_qk_f16_pair_panel4','akv_experimental_resident_qk',
                     'akv_experimental_resident_pv','akv_experimental_resident_pv_prepare'):self.assertEqual(totals[name],6)

    def test_functional_pairs_tail_no_skip_and_nonrne(self):
        fixture=self.fixtures['functional'];work=fixture['work'];ts=fixture['trials']
        self.assertEqual(len(ts),18);self.assertEqual(len(work['legacy']),713);self.assertEqual(len(work['resident']),30)
        for i in range(0,18,2):
            self.assertEqual(ts[i]['requested'],0);self.assertEqual(ts[i+1]['requested'],1)
            self.assertEqual({k:v for k,v in ts[i].items() if k!='requested'},
                             {k:v for k,v in ts[i+1].items() if k!='requested'})
        self.assertEqual(ts[-1]['frm'],1)
        self.assertFalse(any(row['trial']>=16 for row in work['resident']))
        for case in range(4,8):
            trial=next(i for i,t in enumerate(ts) if t['case']==case and t['requested'])
            self.assertEqual([(r['mode'],r['tokens']) for r in work['resident'] if r['trial']==trial],
                             [('QK',64),('PV',64),('QK',1),('PV',1)])

    def test_physical_stride256_and_group_reset_not_repacked_d64(self):
        data=self.data['functional'];source=(f.DATA/'decode_key.bin').read_bytes()
        off=data.find(source)
        self.assertGreaterEqual(off,0);self.assertEqual(data[off+65536:off+131072],source)
        rows=[r for r in self.fixtures['functional']['work']['resident'] if r['trial']==15]
        self.assertEqual([(r['group'],r['mode'],r['base'],r['heads']) for r in rows],
            [(g,m,base,h) for g in range(2) for m in ('QK','PV') for base,h in ((0,2),(2,1))])

    def test_pv_flags_exclude_prep_and_incoming_sticky(self):
        fixture=copy.deepcopy(self.fixtures['perf']);cmd=next(x for x in fixture['work']['resident'] if x['mode']=='PV')
        before=f.local_flags(fixture['oracle'],fixture['trials'],cmd)
        for phase in fixture['oracle']['cases'][0]['expected']['phases']:
            if phase['phase'][0]=='PV_PREP':phase['fflags']|=16
        self.assertEqual(f.local_flags(fixture['oracle'],fixture['trials'],cmd),before)
        self.assertEqual(before&8,0)

    def test_complete_raw_numerical_and_csr_records(self):
        for kind in ('perf','functional'):
            fixture=self.fixtures[kind];proof=c.numerical(numeric_log(fixture,self.data[kind]),fixture,self.data[kind])
            self.assertTrue(proof['bitexact']);self.assertTrue(proof['fflags_checked'])
            self.assertEqual(proof['calls'],len(fixture['trials']))

    def test_output_sticky_guard_and_duplicate_mutations(self):
        fixture=self.fixtures['perf'];text=numeric_log(fixture,self.data['perf'])
        bitline=next(x for x in text.splitlines() if x.startswith('FEATURE_OUT'))
        mutations=(text.replace(bitline,bitline[:-1]+('0' if bitline[-1]!='0' else '1'),1),
            text.replace('fcsr=11','fcsr=3',1),text.replace('vstart=0','vstart=1',1),
            text.replace('vcsr=5','vcsr=0',1),
            text.replace('guard_bytes=','guard_bytes=1',1),text+text.splitlines()[-1]+'\n')
        for changed in mutations:
            with self.assertRaises(ValueError):c.numerical(changed,fixture,self.data['perf'])

    def test_nonrne_compares_samefrm_not_rne_golden(self):
        fixture=self.fixtures['functional'];text=numeric_log(fixture,self.data['functional'])
        lines=text.splitlines()
        for trial in (16,17):
            prefix=f'FEATURE_OUT trial={trial} index=0 '
            index=next(i for i,line in enumerate(lines) if line.startswith(prefix));lines[index]=prefix+'bits=00000000'
        c.numerical('\n'.join(lines),fixture,self.data['functional'])
        lines[index]=prefix+'bits=00000001'
        with self.assertRaises(ValueError):c.numerical('\n'.join(lines),fixture,self.data['functional'])

    def test_retirement_body_and_candidate_bypass(self):
        fixture=self.fixtures['perf'];text,binding=retire_log(fixture)
        p=self.root/'commit.csv';p.write_text(text)
        self.assertEqual(c.actual_entries(p,fixture,binding)['calls'],4)
        body=f'{binding["rotation_body"]["pc"]:x}'
        for changed in (text.replace(body,'80010000',1),text.replace(',13,0',',93,0',1),
                        text.replace(',13,0',',13,1',1),'\n'.join(text.splitlines()[:-1])):
            p.write_text(changed)
            with self.assertRaises(ValueError):c.actual_entries(p,fixture,binding)

    def test_resident_tail_mask_and_bytecounts(self):
        for t in (1,5,64):
            for h in (1,2):
                q=c.shape(dict(mode='QK',tokens=t,heads=h,dimension=64,base=2))
                self.assertEqual(q['counts']['query_base'],2)
                self.assertEqual(sum(bin(mask).count('1') for lane in q['writes'] for mask in lane.values()),t*h*4)
                pv=c.shape(dict(mode='PV',tokens=t,heads=h,dimension=64,base=2))
                self.assertEqual(pv['counts']['source_words'],96)
                self.assertEqual(pv['counts']['result_words'],16*h)

    def test_strong_baseline_source_abi_and_no_duplicate_pvprep(self):
        main=(HERE/'main.c').read_text();builder=(HERE/'build.py').read_text()
        self.assertIn('resident_pv_rotation_selected=1',main)
        self.assertIn('"AKV_PAIR_HEADS"',main)
        self.assertIn('ctx->device,plan,&workspace.value,&c->features[group],&options,0',main)
        self.assertNotIn('fcvt.h.s',main)
        self.assertIn("*contract['link_flags']",builder)
        self.assertNotIn("sdk/'experimental/resident_attention/pv_prepare.S'",builder)

    def test_selection_branch_decode(self):
        # bne x31,x0,+8: target must be inside the selected body, not its wrapper entry.
        word=(31<<15)|(1<<12)|(4<<8)|0x63
        self.assertEqual(b.branch_target(0x80000000,word),0x80000008)
        with self.assertRaises(ValueError):b.branch_target(0x80000000,0x13)

    def test_exact_legacy_and_command_local_resident_probes(self):
        fixture=self.fixtures['perf'];old=c.support('legacy/check.py');lines=[];totals={}
        for i,want in enumerate(fixture['work']['legacy']):
            row=dict.fromkeys(old.PERF_FIELDS,0);row.update(want)
            row.update(seq=i+1,success=1,busy_cycles=1,context_ready=int(row['command']!=3),
                read_payload_bytes=row['q_external_bytes']+row['kv_external_bytes']+64*row['v2_full'])
            for key in old.SUMMARY_FIELDS-{'records','success_records','fault_records','validation_fault_records'}:
                totals[key]=max(totals.get(key,0),row[key]) if key=='read_outstanding_max' else totals.get(key,0)+row[key]
            lines.append('[AKV_PERF] '+' '.join(k+'='+str(v) for k,v in row.items()))
        totals.update(records=482,success_records=482,fault_records=0,validation_fault_records=0)
        lines.append('[AKV_PERF_SUMMARY] '+' '.join(k+'='+str(v) for k,v in totals.items()))
        text='\n'.join(lines);self.assertEqual(c.legacy_work(text,fixture)['commands'],482)
        with self.assertRaises(ValueError):c.legacy_work(text.replace('success=1','success=0',1),fixture)
        lines=[]
        for i,command in enumerate(fixture['work']['resident']):
            shape=c.shape(command);flags=f.local_flags(fixture['oracle'],fixture['trials'],command)
            first=True
            for lane,writes in enumerate(shape['writes']):
                if not writes:continue
                row=dict(lane=lane,vid=i%8,tokens=command['tokens'],elements=shape['elements'][lane],
                    heads=command['heads'],issued=shape['fma'][lane],returned=shape['fma'][lane],
                    writes=len(writes),flags=flags if first else 0,error=0);first=False
                if command['mode']=='QK':row['dimensions']=command['dimension']
                lines.append('[RESIDENT_'+command['mode']+'_LANE] '+' '.join(k+'='+str(v) for k,v in row.items()))
            row=dict(shape['counts'],seq=i+1,vid=i%8,cycles=1,error=0,flags=flags)
            lines.append('[RESIDENT_'+command['mode']+'_PERF] '+' '.join(k+'='+
                (format(v,'b') if k=='active' else str(v)) for k,v in row.items()))
        text='\n'.join(lines);self.assertEqual(len(c.resident_work(text,fixture)),12)
        with self.assertRaises(ValueError):c.resident_work(text.replace('source_words=96','source_words=95',1),fixture)

    def test_actual_vector_signatures_and_result_mask_mutations(self):
        fixture=self.fixtures['perf'];stream=io.StringIO()
        fields='cycle event arch_seq vid lane source insn use_vd vd eew vl vstart addr be wdata nr_lanes vlen_bits'.split()
        writer=csv.DictWriter(stream,fieldnames=fields);writer.writeheader();clock=0;resident=0
        def emit(event,**kwargs):
            nonlocal clock
            row=dict.fromkeys(fields,0);row.update(cycle=clock,event=event,nr_lanes=4,vlen_bits=1024,**kwargs)
            writer.writerow(row);clock+=1
        emit('config')
        for index,word in enumerate(fixture['work']['signatures']):
            base=dict(arch_seq=index+1,vid=index%8,insn=format(word,'08x'))
            if word not in (0x0605705b,0x0485705b):emit('alloc',**base);continue
            shape=c.shape(fixture['work']['resident'][resident]);resident+=1
            base.update(use_vd=1,vd=0,eew=shape['eew'],vl=shape['vl'],vstart=0)
            emit('alloc',**base)
            for lane,writes in enumerate(shape['writes']):
                for addr,mask in writes.items():emit('write',**base,lane=lane,addr=addr,be=format(mask,'x'),source=4,wdata='0123456789abcdef')
            emit('done',**base)
        path=self.root/'vector.csv';text=stream.getvalue();path.write_text(text)
        self.assertEqual(c.vector_work(path,fixture)['resident_commands'],12)
        for changed in (text.replace(',ff,0123456789abcdef',',0f,0123456789abcdef',1),
                        text.replace('0605705b','0485705b',1),'\n'.join(text.splitlines()[:-1])):
            path.write_text(changed)
            with self.assertRaises(ValueError):c.vector_work(path,fixture)


if __name__=='__main__':unittest.main()
