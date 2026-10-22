"""Normalize scalar store payloads by decoded ISA width, without rerunning CFG."""
from context import *
p=read(HERE/'PROFILE.json')
for events in [p['initializer']]+[x['events'] for x in p['mask_profiles']+p['seed_profiles']]:
    for e in events:
        d=memory_op(e['insn'])
        require(d and d['kind']=='write' and d['size']==e['size'],'Actual store width')
        e['source_register_value']=e['value']
        e['value'] &= (1<<(8*e['size']))-1
p['parent_profile_sha256']=sha(HERE/'PROFILE.json')
p['store_value_semantics']='ISA-width-truncated data; full CFG source_register_value retained'
save(HERE/'PROFILE02.json',p)
