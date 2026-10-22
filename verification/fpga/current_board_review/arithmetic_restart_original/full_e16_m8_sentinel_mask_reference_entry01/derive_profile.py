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
            for name,length,events in [('out',2052,init),('mask',128,mask),('a',2048,seed),('b',2048,seed)]:
                if symbols[name]<=event['address']<symbols[name]+length:
                    x=dict(event,bank=name,offset=event['address']-symbols[name],insn=code[event['pc']]);events.append(x)
            return
        name=names[event['dest']]
        if name=='capacity':return 512
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
        if desc and desc['kind']=='write' and desc['base']==2 and desc['size']==8 and desc['reg'] in range(8,28) and x['pc']<seeds[0]['events'][0]['pc']:
            abi.append(x['pc'])
    failure=[value for name,value in symbols.items() if name.startswith('failure') or name in ('trap_entry','replay_trap')]
    park=symbols['replay_exit']+0x16
    require(code[park]==0xa001,'Actual exact pure park')
    save(HERE/'PROFILE.json',dict(elf_sha256=ELF_SHA,initializer=initializers,mask_profiles=masks,seed_profiles=seeds,
        bss_pc=0x80000046,bss_code=0x0002b023,abi_unknown_save_pcs=abi,failure_pcs=failure,park_pc=park,park_insn=code[park],
        cfg_is_static_not_reference=True,full4095_profile_walk=True,private_same_epoch_reorder_actual_PC_bound=True))
    print('PROFILE_FULL4095_ACTUAL_PC_BOUND',sum(len(x['events']) for x in seeds))
if __name__=='__main__':main()

