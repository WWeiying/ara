"""Derive new SoC source epochs and success-path read sites, not execution."""
import hashlib,importlib.util,json,sys
from pathlib import Path
sys.dont_write_bytecode=True
HERE=Path(__file__).resolve().parent;A=HERE.parent
SOURCE=A/'full_e8_m8_sentinel_mask_software01';OLD=A/'full_e8_m8_block_unrolled01'
ELF_SHA='57a9513e3c4c9cd292f0bcea2596a898edd563dbb4380b63be4d33942f66596c'
def load(name,path):
    s=importlib.util.spec_from_file_location(name,path);m=importlib.util.module_from_spec(s);sys.modules[name]=m;s.loader.exec_module(m);return m
def sha(path):return hashlib.sha256(path.read_bytes()).hexdigest()
def save(path,value):
    with path.open('x') as f:json.dump(value,f,indent=2);f.write('\n')
def main():
    require=lambda ok,msg:None if ok else (_ for _ in ()).throw(ValueError(msg))
    require(sha(SOURCE/'soc/program.elf')==ELF_SHA,'Exact new SoC ELF')
    cfg=load('sentinel_soc_immutable_cfg',SOURCE/'linked_cfg_cost.py')
    m=cfg.Machine(SOURCE/'soc')
    rows=json.loads((OLD/'sequence.json').read_text())
    dictionary=[m.initial(m.s['expected_dictionary']+64*i,64) for i in range(3768)]
    code={x['pc']:x['insn'] for f in m.functions.values() for x in f}
    names={m.s[n]:n for n in m.functions};index=0;init=[];mask=[];seed=[];initial=[];ms=[];ss=[]
    def callback(kind,event,regs,loadmem):
        nonlocal index,init,mask,seed
        if kind=='store':
            for name,length,events in [('out',1026,init),('mask',128,mask),('a',1024,seed),('b',1024,seed)]:
                if m.s[name]<=event['address']<m.s[name]+length:
                    item=dict(event,bank=name,offset=event['address']-m.s[name],insn=code[event['pc']])
                    item['source_register_value']=item['value'];item['value']&=(1<<(8*item['size']))-1
                    events.append(item)
            return
        name=names[event['dest']]
        if name=='capacity':return 1024
        if name.startswith('op_'):
            r=rows[index];require(name=='op_'+str(r['op']),'Original chronological helper')
            if index==0:initial.extend(init)
            require(init==initial,'Same actual every-call fresh store sequence')
            if r['si']==0:
                require(len(mask)==16,'Actual sixteen mask stores')
                if index<9:ms.append(dict(mode=r['mode'],events=mask))
            else:require(not mask,'No mask outside group epoch')
            if index in (0,1365,2730):ss.append(dict(seed=r['seed'],events=seed))
            else:require(not seed,'Only original three input refresh epochs')
            init=[];mask=[];seed=[];index+=1;return 0
        if name.startswith('packed_mismatch'):return 0
        if name=='replay_write':return regs['a3']
        if name=='number':return None
        raise ValueError('Unexpected source call '+name)
    cfg.walk(m,'arithmetic_main',{},callback=callback)
    require(index==4095 and len(initial)==129 and [len(s['events']) for s in ss]==[2944]*3
        and len(ms)==3,'Full actual source geometry')
    comparator=next(n for n in m.functions if n.startswith('packed_mismatch'))
    paths=[];goldreads=0
    for r in rows:
        raw=b''.join(dictionary[i].to_bytes(64,'little') for i in r['indices'])[:1026]
        result=cfg.walk(m,comparator,{'a0':r['ordinal']-1},output=raw,maxsteps=1500)
        reads=[e for e in result['events'] if m.s['out']<=e['address']<m.s['out']+1026]
        require(len(reads)==129 and sorted((e['address']-m.s['out'],e['size']) for e in reads)==
            [(i,8) for i in range(0,1024,8)]+[(1024,2)],'Actual full128LD+LHUtail')
        ids=[e for e in result['events'] if m.s['expected_indices']<=e['address']<m.s['expected_indices']+4095*34]
        require(len(ids)==17 and [e['address'] for e in ids]==[m.s['expected_indices']+(r['ordinal']-1)*34+2*i for i in range(17)],'Actual seventeen dictionary IDs')
        gold=[e for e in result['events'] if m.s['expected_dictionary']<=e['address']<m.s['expected_dictionary']+len(dictionary)*64]
        require(len(gold)==sum(8 for i in r['indices'][:16] if i!=0)+1,'ID0 no gold load, nonzero eight, tail separate')
        paths.append(dict(output={str(e['address']-m.s['out']):e['pc'] for e in reads},
            IDs=[dict(pc=e['pc'],address=e['address'],size=e['size'],value=e['value']) for e in ids],
            gold=[dict(pc=e['pc'],address=e['address'],size=e['size'],value=e['value']) for e in gold]))
        goldreads+=len(gold)
    require(goldreads==109575,'Actual SoC static derived gold load scope')
    helpers={n:[dict(pc=x['pc'],insn=x['insn']) for x in m.functions[n]] for n in ['capacity']+['op_'+str(i) for i in range(25)]}
    abi=m.functions['arithmetic_main'][:3]
    require(abi[0]['op']=='addi' and abi[0]['args']=='sp,sp,-304','Actual ABI304')
    profile=dict(elf_sha256=ELF_SHA,symbols=m.s,helpers=helpers,initializer=initial,mask_profiles=ms,
        seed_profiles=ss,comparator_paths=paths,ABI_frame_bytes=304,ABI_entry=abi,
        expected_dictionary_blocks=len(dictionary),static_gold_reads=goldreads,static_ID_reads=4095*17,
        source_scope_calls=4095,source_profile_is_static_not_RVFI=True,
        source_inputs={str(p):sha(p) for p in [SOURCE/'soc/program.elf',SOURCE/'soc/program.dis',SOURCE/'soc/symbols.json',
            SOURCE/'linked_cfg_cost.py',OLD/'model.py',OLD/'sequence.json',OLD/'dictionary.h']})
    save(HERE/'soc_profile.json',profile)
    print('SOC_PROFILE_FULL4095',sha(HERE/'soc_profile.json'))
if __name__=='__main__':main()
