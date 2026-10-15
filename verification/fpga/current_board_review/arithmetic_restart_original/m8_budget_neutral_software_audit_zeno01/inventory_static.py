"""Static linked-code and existing immutable ID-table accounting only."""
from collections import Counter
import hashlib,json,re,struct
from pathlib import Path
HERE=Path(__file__).resolve().parent;A=HERE.parent
P=A/'full_e16_m8_block_unrolled01'
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
def check(ok,msg):
    if not ok:raise ValueError(msg)
dis=P/'soc/program.dis';elf=P/'soc/program.elf'
raw=elf.read_bytes();lower=json.loads((P/'lowering.json').read_text())['soc']
check(sha(elf)==lower['elf_sha256']=='f70831da5a87b07ff0c14852d4d38968226a35653a7568b775577b0a07948923','Actual linked ELF')
rows=[(int(m[1],16),int(m[2],16),m[3].strip()) for m in re.finditer(r'^\s*([0-9a-f]+):\s+([0-9a-f]{4,8})\s+([^\n]+)',dis.read_text(),re.M)]
phoff=struct.unpack_from('<Q',raw,32)[0];ents,num=struct.unpack_from('<HH',raw,54)
segs=[struct.unpack_from('<IIQQQQQQ',raw,phoff+i*ents) for i in range(num)]
windows=[x for x in rows if 0x8000007a<=x[0]<=0x800006d4 or 0x80000b2a<=x[0]<=0x80000b44]
for pc,insn,_ in windows:
    n=4 if insn&3==3 else 2
    data=[raw[off+pc-va:off+pc-va+n] for kind,flags,off,va,pa,fs,ms,align in segs if kind==1 and va<=pc and pc+n<=va+fs]
    check(len(data)==1 and data[0]==insn.to_bytes(n,'little'),'Disassembly actual ELF bytes')
comp=[x for x in rows if 0x8000007a<=x[0]<=0x800006d4]
counts=Counter(x[2].split()[0] for x in comp)
check(counts['bne']==127 and counts['beq']==1 and counts['sub']==counts['snez']==1,'Actual comparator, not boolean OR')
check(not any(x[2].split()[0] in ('sd','sw','addi') and 'sp' in x[2] for x in comp),'Frameless comparator')
seq=json.loads((P/'sequence.json').read_text())
check(len(seq)==4095 and all(len(r['indices'])==17 for r in seq),'Existing full4095 immutable ID rows')
hits=sum(sum(r['indices'][j]==r['indices'][j-1] for j in range(1,16)) for r in seq)
sentinel=sum(r['indices'][:16].count(0) for r in seq)
dictionary=(P/'dictionary.h').read_text().split('expected_dictionary[]')[1].split('};')[0]
words=[int(v,16) for v in re.findall(r'UINT64_C\(0x([0-9a-fA-F]+)\)',dictionary)]
check(words[:8]==[0x005b005b005b005b]*8,'Actual dictionary block0 typed sentinel')
ready=json.loads((P/'READY.json').read_text())
check(ready['firmware']==2807400 and ready['calls']==4095 and ready['packed_output_reads']==528255,'Accepted reference metadata baseline, no raw read')
compile=json.loads((P/'soc/compile.log.command.json').read_text())
check(str(P/'case.c') in compile['command'] and str(P/'original/scenario.S') in compile['command'],'Actual linked C/helper')
sources=[P/'case.c',P/'packed.h',P/'dictionary.h',P/'sequence.json',P/'READY.json',P/'lowering.json',
    P/'soc/compile.log.command.json',P/'soc/main.c',P/'soc/program.dis',P/'soc/program.elf',P/'original/scenario.S',
    A/'full_e32_m4_block_prepare01/software02/packed_cache.h',
    A/'full_e32_m4_block_prepare01/software02/soc/program.dis',
    A/'full_e64_m4_block_prepare01/software02/packed_output.h',
    A/'full_e64_m4_block_prepare01/software02/soc/program.dis',Path(__file__)]
out=dict(status='STATIC_SOFTWARE_OVERHEAD_OPPORTUNITIES_NOT_IMPLEMENTED',
    source_pins={str(p):sha(p) for p in sources},original_compile_command=compile,
    reference_firmware_baseline=ready['firmware'],reference_projection_s_not_guarantee=ready['projected_seconds_20percent_margin'],
    mandatory=dict(calls=4095,results=2096640,guards=8190,returned_vstart=4095,helper=53235,
        output_bytes=1028,percall_SD=128,percall_SW_tail=1,percall_actual_LD=128,percall_actual_LW_tail=1,
        all_actual_output_reads=528255,mask_groups=1575,mask_SD_pergroup=16),
    comparator=dict(pc_start='8000007a',pc_end='800006d4',mnemonic_counts=dict(counts),
        pass_path_static_instruction_count=len(comp)-2,pass_path_excludes_failure_pcs=['800000ac','800000ae'],
        stack_frame_bytes=0,body='128 pairs expectedLD/actualLD plus BEQ/BNE; one LW tail SUB/SNEZ',
        SUB_SNEZ_OR_per_word_claim=False),
    mask=dict(loop_pcs=['80000b38','80000b3a','80000b3c','80000b3e','80000b42','80000b44'],
        pergroup_loop_body_instructions=95,detail='16SD +15LD +15sourceADDI +16endADDI +16destinationADDI +16BNE +1entryJ',
        no_business_mask_LBU_ORI_SB=True,upper64_mask_bytes_zero=True,
        original_mask_table_copy_bytes=128,unrolled_16LD_16SD_bound=32,
        loop_region_saving_if_32_instructions=63,allgroups_saving_directional=63*1575),
    IDs=dict(full_blocks=4095*16,adjacent_fullblock_cache_hits=hits,sentinel_ID0_fullblock_uses=sentinel,
        existing_full_expected_LD=4095*128,
        eight_register_cache_expected_LD_reduction_if_no_spills=8*hits,
        cache_tag_branches=15*4095,
        eight_register_saved_reg_save_restore_illustration=16*4095,
        preliminary_cache_net_before_tag_moves_branch_joins_and_spills=8*hits-15*4095-16*4095,
        sentinel_specialization_expected_LD_reduction_if_no_reload=8*sentinel,
        allblock_sentinel_dispatch_branches=16*4095,
        sentinel_net_before_constant_loads_branch_joins_and_other_overheads=8*sentinel-16*4095),
    Host_runs=0,compile_runs=0,reference_runs=0,DUT_runs=0,raw_reads=0,
    budgets_changed=False,scope_shortened=False)
with (HERE/'STATIC_EVIDENCE.json').open('x') as f:json.dump(out,f,indent=2);f.write('\n')
print(json.dumps({k:out[k] for k in ('status','comparator','mask','IDs')},indent=2))

