"""Mechanical isolated successor of reviewed M1; no ELF/RTL/runtime mutation."""
from pathlib import Path
import json
HERE=Path(__file__).resolve().parent
OLD=HERE.parent/'full_e32_m1_packed_vcs_m9_plan01'
ROOT=HERE.parent/'full_e32_m2_block_prepare01'
REF=ROOT/'reference_entry01'

def emit(name,text):
    with (HERE/name).open('x') as f:f.write(text)

def changes(text,pairs):
    for old,new in pairs:
        assert old in text,old
        text=text.replace(old,new)
    return text

def common(text):
    for old,new in [("full_e32_m1_packed_prepare01","full_e32_m2_block_prepare01"),
        ("e32_m1","e32_m2"),("e32-m1","e32-m2"),("e32/m1","e32/m2"),
        ("191520","383040"),("101745","197505")]:text=text.replace(old,new)
    return text

text=(OLD/'checker.py').read_text()
text=common(text)
text=changes(text,[("SOFT=ROOT/'software02'","SOFT=ROOT/'software01'"),
    ('CAP=32','CAP=64'),('d1f70125ab071283390749323120204356e07da6a3a420f450e46c58e5859691','e48688057ac67a1452ef5d9e901f2e99dd8ba8a500fbdf3adf0d2e6777bba17e'),
    ('8b6c67293ad57aff6ddeaf478aa4c94bd07d44421f3c6eb901378fe4cf23db5c','b9a09a69f9ae8d93b38f5a3f8de1049967a79127ebb473da7f321e73143039f6'),
    ('e32m1','e32m2'),('vlmax=32','vlmax=64'),('==136','==264'),('range(17)','range(33)'),
    ('full17','full33'),('Full17','Full33'),('17 words','33 words'),
    ('Exact136','Exact264'),('exact136','exact264'),
    ('0x0102f557','0x0112f557'),('vtype16','vtype17'),('group1','group2'),('vlm4bytes','vlm8bytes'),
    ('0x010772d7','0x011772d7'),('0x0106f2d7','0x0116f2d7'),
    ("desc['base']==22 and desc['offset']==offset","desc['base']==8 and desc['offset']==offset"),
    ("lmul='m1',cap=32","lmul='m2',cap=64"),('vtype=16,physical_group_registers=1,observed_group_bytes=128','vtype=17,physical_group_registers=2,observed_group_bytes=256'),
    ('vlm_bytes=4','vlm_bytes=8'),("g['vl'],32,self.s", "g['vl'],64,self.s"),('[91]*34','[91]*66'),
    ('self.init_index==17','self.init_index==33'),('ordinal*32','ordinal*64'),('(10,32)','(10,64)'),('VLMAX32','VLMAX64'),
    ("g['vl'] if j==5 else 32","g['vl'] if j==5 else 64"),('self.init_index<17','self.init_index<33'),
    ("('a',128),('b',128),('mask',128),('out',136)","('a',256),('b',256),('mask',128),('out',264)"),
    ('self.life.read(pc,addr,size)','self.life.read(pc,addr,size,result)'),('offset+size<=136','offset+size<=264'),
    ('position>=132','position>=260'),('fresh_output_bytes_each_call=136','fresh_output_bytes_each_call=264'),
    ('mask_clear_stores=self.life.mask_clear_stores','seed_cache_reads=self.life.cache_reads,seed_cache_stores=self.life.cache_stores,FP_cache_reads=self.life.fp_reads,mask_clear_stores=self.life.mask_clear_stores')])
# No opaque guessed ABI frame: the exact compiled SoC prologue must establish it.
text=text.replace("self.body_entered=True\n", "self.body_entered=True\n            require(insn==0x714d and (rd,result)==(2,self.s['__stack_top']-336),'Actual336B main frame')\n")
text=text.replace("minimum_required_owners=len(gold)*5+targets)","minimum_required_owners=len(gold)*5+targets,\n        baseline_vstart_noops=sum(g['vstart']>=g['vl'] for g in gold),\n        additional_exact_VI2_noops=sum(g['vstart']<g['vl'] and not target_required(spec['backend']['helpers'][f'op_{g[\"op\"]}'][8]['insn'],g,spec) for g in gold))")
text=text.replace("minimum_required_owners=len(memories)+expected_targets,", "minimum_required_owners=len(memories)+expected_targets,\n            baseline_vstart_noops=sum(g['vstart']>=g['vl'] for g in gold['rows']),\n            additional_exact_VI2_noops=sum(g['vstart']<g['vl'] and not target_required(spec['backend']['helpers'][f'op_{g[\"op\"]}'][8]['insn'],g,spec) for g in gold['rows']),")
emit('checker.py',text)

ctx=(REF/'context.py').read_text().replace("SOFT=HERE.parent/'software01'","ROOT=HERE.parent/'full_e32_m2_block_prepare01'\nSOFT=ROOT/'software01'")
ctx=ctx.replace("SOFT/'spike/","SOFT/'soc/").replace("['backends']['spike']","['backends']['soc']")
emit('context.py',ctx)
text=(REF/'lifecycle.py').read_text().replace('from context import HERE,SOFT,read,require,width','from context import ROOT,SOFT,read,require,width')
text=changes(text,[("HERE.parent/'compiled_audit01/RESULT.json'","ROOT/'compiled_audit01/RESULT.json'"),("['compiled']['spike']","['compiled']['soc']"),
    ('b=0x80000418,a=0x8000041a,a0=0x800015ea,b0=0x800015ee','b=0x80000410,a=0x80000412,a0=0x800015f6,b0=0x800015fa'),
    ('a1=0x80000436,b1=0x80000438,a2=0x800015fc,b2=0x80001600,b3=0x800015cc','a1=0x8000042e,b1=0x80000430,a2=0x80001608,b2=0x8000160c,b3=0x800015d8'),
    ('CACHE_LOAD_PC=0x8000045a','CACHE_LOAD_PC=0x80000452'),('CACHE_STORE_PC=0x80000460','CACHE_STORE_PC=0x80000458')])
emit('lifecycle.py',text)

for name in ('replay.py','collect.py'):
    text=common((OLD/name).read_text())
    text=changes(text,[('2472244','2262610')] if name=='replay.py' else [('E32_M1','E32_M2')])
    text=text.replace('E32_M1','E32_M2').replace('120960','241920').replace('38955','77175').replace('full17','full33').replace('==136','==264')
    if name=='replay.py':
        text=changes(text,[("result['physical_registers_per_group']==1","result['physical_registers_per_group']==2"),
            ("result['observed_register_bytes']==128","result['observed_register_bytes']==256"),
            ("result['vlm_read_bytes']==4","result['vlm_read_bytes']==8"),("result['original_seed_scalar_writes']==276","result['original_seed_scalar_writes']==552"),
            ("e32_m2_packed_source_review01","e32_m2_scalar_source_review01"),
            ("'prepare_assets.py'","'prepare_assets.py','context.py','prepare_sources.py'")])
        text=text.replace("result['FP_calls']==1890", "result['seed_cache_reads']==result['seed_cache_stores']==24 and result['FP_cache_reads']==241920 and result['FP_calls']==1890")
    else:
        text=text.replace("c.require(report['strict_csv_parses']", "c.require(strict['seed_cache_reads']==strict['seed_cache_stores']==24 and strict['FP_cache_reads']==241920,'Full actual FP cache lifecycle')\n        c.require(report['strict_csv_parses']")
    emit(name,text)
for name in ('exit_hook.py','launch_once.py','run_host.py'):
    text=(OLD/name).read_text()
    if name=='run_host.py':text=text.replace("'lifecycle.py'","'lifecycle.py','context.py','prepare_sources.py'")
    emit(name,text)
text=(OLD/'prepare_assets.py').read_text().replace('0c11f7a2d6bcf0fa0ee27e5f4eb3f9d1fc567d29ad638c5e2c9675d0dc2785e4','978310da20bf437709dae962164491c1f1e8bea6acb9b62ba7a0dbe01c621c3c')
emit('prepare_assets.py',text)

text=(OLD/'host_records.py').read_text()
text=changes(text,[("code[body]==0x7169 and code[body+2]==0xea4a and code[body+4]==0xf606","code[body]==0x714d and code[body+2]==0xe686"),
    ("s['__stack_top']-304","s['__stack_top']-336"),('for pc in (body+2,body+4):','for pc in (body+2,):'),
    ('self.row(body+6,1,body+10)','self.row(body+4,1,body+8)'),('else 32 if j==1','else 64 if j==1'),
    ("g['vl'],32,s['mask']","g['vl'],64,s['mask']"),("g['vl'] if j==5 else 32","g['vl'] if j==5 else 64"),
    ("(g['ordinal']+1)*32","(g['ordinal']+1)*64")])
begin=text.index('            if group_first:');end=text.index('            for pc,_,size,offset',begin)
text=text[:begin]+'''                cache=s['__stack_top']-336+192
                for k in range(8):
                    value=c.lifecycle.FP_INPUTS[(g['seed']+k)%8]
                    yield from self.read(s['fp_inputs']+4*((g['seed']+k)%8),c.lifecycle.lw_value(value),4,c.lifecycle.CACHE_LOAD_PC)
                    yield from self.write(cache+4*k,value,4,c.lifecycle.CACHE_STORE_PC)
            if group_first:
                previous_mask={}
                for pc,offset,size,value,load in c.lifecycle.mask_schedule(g['mode']):
                    if load is not None:
                        yield from self.read(s['mask']+offset,previous_mask.get(offset,0),1,load)
                    yield from self.write(s['mask']+offset,value,size,pc)
                    if size==1:previous_mask[offset]=value
            if g['op']>=25:
                cache=s['__stack_top']-336+192
                for j,pc in enumerate(c.lifecycle.FP_PC):
                    i,bank=divmod(j,2);key=('a','b')[bank];slot=(3*i if bank else i)%8
                    yield from self.read(cache+4*slot,c.lifecycle.lw_value(g[key][i]),4,c.lifecycle.FP_LOAD_PC[j])
                    yield from self.write(s[key]+i*4,g[key][i],4,pc)
''' +text[end:]
emit('host_records.py',text)

text=(OLD/'test_host.py').read_text()
text=text.replace('191520','383040').replace('101745','197505').replace('word128','word256').replace('(0,128)','(0,256)')
text=text.replace('.remove(16)','.remove(32)').replace('self.assertIn(16,','self.assertIn(32,')
text=text.replace("self.abi[:-2]","self.abi[:-2]")
text=changes(text,[("(32,16,1,128,128,4)","(64,17,2,256,128,8)"),("(32,32,136,128)","(64,64,264,128)"),
    ("g['mask'][4:],[0]*124","g['mask'][8:],[0]*120"),('120960','241920'),('38955','77175'),
    ("0,32,state.s['mask']","0,64,state.s['mask']"),('[91]*34','[91]*66'),('range(64)','range(128)'),
    ("'64 fresh SW'","'128 paired cache LW/SW'"),
    ("assertRaisesRegex(ValueError,'Deleted fresh'):state.consume(row)","assertRaisesRegex(ValueError,'All33 output|Deleted fresh'):state.consume(row)")])
text=text.replace("'Complete output fresh|Deleted fresh'","'All33 output|Deleted fresh'").replace("'Complete output fresh|initialized values out|Deleted fresh|initializer'","'All33 output|initialized values out|Deleted fresh|initializer'")
begin=text.index('        life=copy(state.life);g=state.gold[life.calls]');end=text.index('    def test_typed32guards',begin)
text=text[:begin]+'''        life=copy(state.life);g=state.gold[life.calls]
        # Starting immediately before first SW, retain its preceding LW.
        for skip in range(128):
            candidate=copy(life)
            with self.subTest(skip=skip),self.assertRaises(ValueError):
                for j,pc in enumerate(c.lifecycle.FP_PC):
                    i,bank=divmod(j,2);key=('a','b')[bank];slot=(3*i if bank else i)%8
                    if j:
                        candidate.read(c.lifecycle.FP_LOAD_PC[j],candidate.cache_base+4*slot,4,c.lifecycle.lw_value(g[key][i]))
                    if j!=skip:candidate.store(pc,state.code[pc],state.s[key]+i*4,4,g[key][i])
                candidate.store(c.lifecycle.INIT_PC[0],state.code[c.lifecycle.INIT_PC[0]],state.s['out'],8,c.lifecycle.SENTINEL)

    def test_every_ordered_mask_clear_and_bitset_write_required(self):
        state,row=self.snapshots['first_mask_store'];life=state.life
        schedule=c.lifecycle.mask_schedule(0)
        self.assertEqual(len(schedule),80)
        for skip in range(len(schedule)):
            candidate=copy(life);previous={}
            with self.subTest(skip=skip),self.assertRaises(ValueError):
                for i,(pc,offset,width,value,load) in enumerate(schedule):
                    if load is not None:candidate.read(load,state.s['mask']+offset,1,previous.get(offset,0))
                    if i!=skip:candidate.store(pc,state.code[pc],state.s['mask']+offset,width,value)
                    if width==1:previous[offset]=value
                candidate.store(c.lifecycle.INIT_PC[0],state.code[c.lifecycle.INIT_PC[0]],state.s['out'],8,c.lifecycle.SENTINEL)
        pc,offset,size,value,load=schedule[16]
        with self.assertRaises(ValueError):copy(life).store(pc,state.code[pc],state.s['mask']+offset,size,value)

''' +text[end:]
text=text.replace("state.s['a']+3","state.s['a']+3")
text=text.replace("(1890,241920,35280,77175))", "(1890,241920,35280,77175))\n        self.assertEqual((self.strict['seed_cache_reads'],self.strict['seed_cache_stores'],self.strict['FP_cache_reads']),(24,24,241920))")
text=text.replace("self.assertEqual(len(noops),18)","self.assertEqual(len(noops),18)\n        self.assertEqual(c.owner_counts()['baseline_vstart_noops'],2205)\n        self.assertEqual(c.owner_counts()['additional_exact_VI2_noops'],18)")
emit('test_host.py',text)
print('OWN_SOURCE_PREPARED_NO_HOST_COMPILE_REFERENCE_DUT')
