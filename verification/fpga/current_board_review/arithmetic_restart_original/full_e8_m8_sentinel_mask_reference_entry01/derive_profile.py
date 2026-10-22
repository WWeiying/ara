"""Derive exact scalar store profiles from the already linked main CFG."""
from context import *
def main():
    symbols,code,helpers,machine=artifacts()
    cfg=sys.modules['sentinel_linked_profile_cfg'];rows=read(OLD/'sequence.json')
    index=0;init=[];mask=[];seed=[];initializers=[];masks=[];seeds=[]
    names={machine.s[n]:n for n in machine.functions}
    def callback(kind,event,regs,loadmem):
        nonlocal index,init,mask,seed
        if kind=='store':
            for name,length,events in [('out',1026,init),('mask',128,mask),('a',1024,seed),('b',1024,seed)]:
                if symbols[name]<=event['address']<symbols[name]+length:
                    x=dict(event,bank=name,offset=event['address']-symbols[name],insn=code[event['pc']]);events.append(x)
            return
        name=names[event['dest']]
        if name=='capacity':return 1024
        if name.startswith('op_'):
            row=rows[index]
            require(name=='op_'+str(row['op']),'Actual original op')
            if index==0:initializers.extend(init)
            require([(x['pc'],x['offset'],x['size'],x['value']) for x in init]==[(x['pc'],x['offset'],x['size'],x['value']) for x in initializers],'Every call same actual init sequence')
            if row['si']==0:
                mode=row['mode']
                if index<9:masks.append(dict(mode=mode,events=mask))
                require(len(mask)==16 and sorted((x['offset'],x['size']) for x in mask)==[(i,8) for i in range(0,128,8)],'Mask complete actual sequence')
            else:require(not mask,'Only original group mask')
            if index in (0,1365,2730):seeds.append(dict(seed=row['seed'],events=seed))
            else:require(not seed,'No extra input writes between seeds')
            init=[];mask=[];seed=[];index+=1;return 0
        if name.startswith('packed_mismatch'):return 0
        if name=='replay_write':return regs['a3']
        if name=='number':return None
        raise ValueError('Unexpected positive CFG call '+name)
    cfg.walk(machine,'arithmetic_main',{},callback=callback)
    require(index==4095 and len(initializers)==129 and len(masks)==3 and len(seeds)==3,'Full profile derivation')
    abi=[]
    for x in machine.functions['arithmetic_main']:
        desc=memory_op(x['insn'])
        if desc and desc['kind']=='write' and desc['base']==2 and desc['size']==8 and desc['register'] in (8,9,18,19,20,21,22,23,24,25,26,27) and x['pc']<seeds[0]['events'][0]['pc']:
            abi.append(x['pc'])
    failure=[value for name,value in symbols.items() if name.startswith('failure') or name in ('trap_entry','replay_trap')]
    parks=[x for x in machine.functions['replay_exit'] if x['op']=='j' and int(x['args'].split()[0],16)==x['pc']]
    require(len(parks)==1,'Actual unique self-park')
    park=parks[0]['pc']
    bss=[x for x in machine.functions['_start'] if x['op']=='sd' and x['args']=='zero,0(t0)']
    require(len(bss)==1,'Actual exact startup zero-store')
    for events in [initializers]+[x['events'] for x in masks+seeds]:
        for e in events:
            e['source_register_value']=e['value'];e['value']&=(1<<(8*e['size']))-1
    require(code[park]==0xa001,'Actual exact pure park')
    save(HERE/'PROFILE.json',dict(elf_sha256=ELF_SHA,initializer=initializers,mask_profiles=masks,seed_profiles=seeds,
        bss_pc=bss[0]['pc'],bss_code=bss[0]['insn'],abi_unknown_save_pcs=abi,failure_pcs=failure,park_pc=park,park_insn=code[park],
        store_value_semantics='Decoded ISA-width, full source register retained',
        cfg_is_static_not_reference=True,full4095_profile_walk=True,private_same_epoch_reorder_actual_PC_bound=True))
    print('PROFILE_FULL4095_ACTUAL_PC_BOUND',sum(len(x['events']) for x in seeds))
if __name__=='__main__':main()
