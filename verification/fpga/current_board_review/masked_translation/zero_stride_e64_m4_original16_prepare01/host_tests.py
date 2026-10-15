#!/usr/bin/env python3
"""Counterexamples against actual final ELF symbols and full original model."""
import sys
sys.dont_write_bytecode=True
import observer as o
import prepare as p

def sample(s,c,phase):
    m=o.expected(s,c,phase)
    for row in range(c+1):
        count=(2 if row%4<3 else 1) if row<c or phase>=3 else int(row%4<3 and phase>=1)
        for n in range(count):
            for i,b in enumerate((0x800).to_bytes(8,'little')):m[s['mx_records']+row*192+n*96+24+i]=b
    o.compare(m,s,c,phase);return m

def main():
    s=p.read(p.OUT/'spike.symbols.json');positive=0
    for c in range(16):
        for phase in ([0,1,2,3,4] if c%4<3 else [0,3,4]):sample(s,c,phase);positive+=1
    tests=[(0,4,'active_load',s['mx_out']+8),(1,4,'inactive_load',s['mx_out']+8),
      (0,4,'tail',s['mx_out']+8*64),(0,4,'typed_seed_not_repeated_byte',s['mx_out']+8*20+1),
      (4,4,'active_store',s['mx_pages']+4096),(7,3,'alloff_precleanup_store',s['mx_pages']+4096),
      (15,3,'unmapped_alloff_pre_refill',s['mx_pages']+4096),(12,2,'full_refill',s['mx_pages']+8191),
      (2,1,'prestart_saved_group',s['mx_fault']+64),(2,1,'fault_vstart',s['mx_records']+2*192+56),
      (4,1,'store_cause',s['mx_records']+4*192),(0,1,'fault_tval',s['mx_records']+16),
      (0,4,'returned_vstart',s['mx_post']+16),(15,4,'crosscase_history',s['mx_records']+8),
      (0,4,'guard_low',s['mx_out']),(0,4,'guard_high65',s['mx_out']+65*8),
      (0,4,'allocation_end513',s['mx_out']+513*8),(0,0,'full_input_tail',s['mx_input']+511*8),
      (0,0,'original_mask64',s['mx_mask']+63),(0,0,'ordinary_offset512',s['mx_offsets']+511*8),
      (0,0,'zero_stride',s['mx_stride']),(15,4,'page_table_neighbor',s['mx_pages']+5*4096-8),
      (0,0,'bootstrap',s['mx_action_copy']),(3,3,'unexpected_alloff_fault',s['mx_count'])]
    negative=[]
    for c,phase,name,a in tests:
        memory=sample(s,c,phase);memory[a]^=1
        try:o.compare(memory,s,c,phase)
        except ValueError:negative.append(name);continue
        raise ValueError('Accepted negative '+name)
    memory=sample(s,15,4);del memory[s['mx_pages']+8191]
    try:o.compare(memory,s,15,4)
    except ValueError:negative.append('missing_full_memory_last_byte')
    else:raise ValueError('Missing data accepted')
    # Do not accidentally constrain the original fault suffix beyond prestart.
    memory=sample(s,2,1);memory[s['mx_fault']+64+63*8]=0xa5;o.compare(memory,s,2,1)
    result=dict(status='HOST_PASS_NOT_REFERENCE',positive_checkpoints=positive,
                allowed_fault_suffix_positive=True,negative_count=len(negative),negative=negative)
    p.save(p.OUT/'host_tests.json',result);print(result)
if __name__=='__main__':main()
