"""Offline full scalar/RVC/gold and actual DTLB slot qualification; never admission."""
import argparse
from collections import Counter
import csv
from pathlib import Path
import re
import subprocess
from types import FunctionType

import run_dtlb_ppn_swap1200 as runner
import scoped_rv64c_memory as rv64c
import audit_gap115_axi_v2 as vcd_reader
from ara_verify import spike_trace, contract, vector_commit

pre, life, require = runner.pre, runner.life, runner.require
SCOPE = pre.shared.SCOPE
LOAD = SCOPE.rsplit('.gen_mmu',1)[0]+'.i_load_unit'
MONITOR = 'ara_tb.dut.i_ara_soc.i_system.i_ara_commit_monitor.cycle_q'
CONVERTER = Path('/home/wangwy/software/synopsys/install/vcs/V-2023.12-SP1/linux64/bin/vpd2vcd.exe')
CONVERTER_SHA = '195fae31e4cbacabcbbd97bfd61c98a333f68ff2fd013002ab322e5108f97002'
FIELDS = ('cycle','event','order','port','trans_id','pc','insn','rd','rd_wdata',
          'mem_addr','mem_rmask','mem_wmask','mem_wdata','trap')


def source_layout():
    from check_operand_index_snapshot_offline_v2 import source_contract
    pins = {str(pre.shared.SOURCE):pre.shared.SOURCE_SHA}
    pins, reset = source_contract(pins)
    book = life.read_bound(pre.shared.SOURCE, pre.shared.SOURCE_SHA)
    rels = ('hardware/deps/cva6/core/cva6_mmu/cva6_mmu.sv',
            'hardware/deps/cva6/core/cva6_mmu/cva6_tlb.sv',
            'hardware/deps/cva6/core/cva6_mmu/cva6_ptw.sv',
            'hardware/deps/cva6/core/cva6_mmu/cva6_shared_tlb.sv',
            'hardware/deps/cva6/core/load_unit.sv', 'hardware/deps/cva6/core/cva6.sv',
            'hardware/deps/cva6/core/include/build_config_pkg.sv', 'hardware/tb/ara_commit_monitor.sv')
    texts = {}
    for rel in rels:
        p = life.ROOT/rel; pins = life.merge_pins(pins,{str(p):book[str(p)]})
        require(life.digest(p) == book[str(p)], 'Frozen layout source drift')
        texts[rel.split('/')[-1]] = re.sub(r'\s+','',re.sub(r'/\*.*?\*/|//[^\n]*','',p.read_text(),flags=re.S))
    anchors = {
        'cva6_mmu.sv': ('logic[9:0]reserved;logic[CVA6Cfg.PPNW-1:0]ppn;logic[1:0]rsw;'
            'logicd;logica;logicg;logicu;logicx;logicw;logicr;logicv;',
            'logicvalid;logic[CVA6Cfg.PtLevels-2:0][HYP_EXT:0]is_page;logic[CVA6Cfg.VpnLen-1:0]vpn;'
            'logic[CVA6Cfg.ASID_WIDTH-1:0]asid;logic[CVA6Cfg.VMID_WIDTH-1:0]vmid;'
            'logic[HYP_EXT*2:0]v_st_enbl;pte_cva6_tcontent;pte_cva6_tg_content;'),
        'cva6_tlb.sv': ('pte_cva6_tpte;pte_cva6_tgpte;}[TLB_ENTRIES-1:0]content_q,content_n;',
            'logic[CVA6Cfg.ASID_WIDTH-1:0]asid;logic[CVA6Cfg.VMID_WIDTH-1:0]vmid;'
            'logic[CVA6Cfg.PtLevels+HYP_EXT-1:0][(CVA6Cfg.VpnLen/CVA6Cfg.PtLevels)-1:0]vpn;'
            'logic[CVA6Cfg.PtLevels-2:0][HYP_EXT:0]is_page;logic[HYP_EXT*2:0]v_st_enbl;'
            'logicvalid;}[TLB_ENTRIES-1:0]tags_q,tags_n;',
            'elseif(update_i.valid&replace_en[i]&!lu_hit_o)'),
        'load_unit.sv': ('assignvaddr_o=lsu_ctrl_i.vaddr;', 'pop_ld_o=1\'b1;'),
        'build_config_pkg.sv': ('cfg.PPNW=(CVA6Cfg.XLEN==32)?22:44;',
            'cfg.ASID_WIDTH=(CVA6Cfg.XLEN==64)?16:1;', 'cfg.VMID_WIDTH=(CVA6Cfg.XLEN==64)?14:1;',
            'cfg.GPLEN=(CVA6Cfg.XLEN==32)?34:41;'),
        'cva6.sv': ('logic[CVA6Cfg.XLEN-1:0]cause;logic[CVA6Cfg.XLEN-1:0]tval;'
            'logic[CVA6Cfg.GPLEN-1:0]tval2;logic[31:0]tinst;logicgva;logicvalid;'),
        'ara_commit_monitor.sv': ('cycle_q<=cycle_q+1;', 'if(rvfi_instr_i[port].valid)'),
    }
    for name, tokens in anchors.items():
        require(all(x in texts[name] for x in tokens), 'Packed/owner source contract differs: '+name)
    return dict(update_width=189, content_per_slot_width=128, content_slots=16,
        tag_per_slot_width=61, exception_width=203, PPN_width=44, RVH=0,
        update_fields={'valid':[188,188],'vpn':[185,159],'asid':[158,143],
            'content':[127,64],'g_content':[63,0]}, reset_source=reset,
        basis='Verilog packed field order and [15:0] dimensions, not Toggle MDA flatten offsets'), pins


def reference_check(q):
    commits = spike_trace.parse_spike_commits(runner.PRE.parent/'spike.trace')
    require(pre.validate(commits,q['symbols']) == q['counts'], 'Frozen full reference/gold differs')
    return commits


def memory_gate(rows, commits):
    prefix = []
    for c in commits:
        if not prefix and c.pc != 0x80000000: continue
        prefix.append(c)
        if (0x80001000,1) in c.memory_accesses: break
    require(prefix and prefix[-1].memory_accesses == ((0x80001000,1),) and len(rows)==len(prefix),
            'Complete scalar/reference terminal alignment')
    regs = [0]*32; counts = Counter()
    for order,(row,c) in enumerate(zip(rows,prefix)):
        require(row['event']=='retire' and int(row['order'])==order and int(row['trap'])==0 and
            int(row['pc'],16)==c.pc and int(row['insn'],16)==c.instruction, 'PC/opcode/order/trap mismatch')
        expected_gpr = {r:v for r,v in c.gpr_writes.items() if r}
        rd = int(row['rd']); require(0<=rd<32, 'Invalid native GPR')
        actual_gpr = {} if rd==0 else {rd:int(row['rd_wdata'],16)}
        require(actual_gpr==expected_gpr, 'Complete GPR/load return mismatch')
        rm,wm = int(row['mem_rmask'],16),int(row['mem_wmask'],16)
        word = c.instruction; compressed = word&3 != 3
        if compressed: access = rv64c.decode(word)
        else:
            decoded = spike_trace._scalar_memory_access(word)
            access = None
            if decoded is not None:
                kind,size = decoded
                require(kind in ('read','write') and word&127 in (3,35), 'Unexpected FP/AMO memory')
                immediate = (word>>20) if kind=='read' else ((word>>25)<<5)|((word>>7)&31)
                immediate = immediate-4096 if immediate&2048 else immediate
                access = dict(kind=kind,size=size,base=(word>>15)&31,offset=immediate,
                    register=(word>>7)&31 if kind=='read' else (word>>20)&31)
        if access is None:
            require(not c.memory_accesses and rm==wm==0, 'Unknown/extra scalar memory effect')
        else:
            size,reg,kind = access['size'],access['register'],access['kind']
            a = (regs[access['base']]+access['offset']) & pre.MASK
            require(a%size==0 and (a&7)+size<=8 and int(row['mem_addr'],16)==a,
                    'Scalar effective address/alignment differs')
            mask=((1<<size)-1)<<(a&7)
            if kind=='write':
                value=regs[reg]&((1<<(8*size))-1)
                require(c.memory_accesses==((a,value),) and rm==0 and wm==mask and
                    int(row['mem_wdata'],16)&((1<<(8*size))-1)==value, 'Store address/mask/data differs')
            else:
                require(c.memory_accesses==((a,None),) and rm==mask and wm==0,
                        'Load address/mask differs')
                require(reg==rd and reg in expected_gpr, 'Load destination/return missing')
            counts['compressed' if compressed else 'uncompressed']+=1
            counts[kind]+=1
        for r,v in expected_gpr.items(): regs[r]=v
        regs[0]=0
    return dict(status='ALL_INTEGER_RVC_AND_UNCOMPRESSED_MEMORY_EXACT',
        retired=len(prefix), compressed=counts['compressed'],uncompressed=counts['uncompressed'],
        loads=counts['read'],stores=counts['write'],total=counts['compressed']+counts['uncompressed'],
        skipped=0, expected_addresses_and_stores_from='Reference prior GPRs, never DUT feedback')


def terminal_gate(t):
    require(t['status']=='SIMULATION_EXITED_NOT_ADMITTED' and type(t['returncode']) is int and
        t['returncode']==0 and type(t['timeout']) is bool and t['timeout'] is False and
        t['case']==runner.CASE and t['coverage_admitted'] is False and t['automatic_retry'] is False,
        'Successful exact non-timeout terminal required')


def identity_gate(identity,record):
    require(type(identity['pid']) is int and identity['pid']>0 and
        identity['executable']==str(life.IMAGE.resolve()) and
        identity['executable_sha256']==record['pins'][str(life.IMAGE)] and
        identity['cwd']==record['output'] and identity['command']==record['command'] and
        identity['service']==record['service'] and
        any(record['service'] in line.split(':',2)[-1].split('/') for line in identity['cgroup'].splitlines()),
        'Sealed live executable/cwd/command/owning cgroup differs')
    require(not (Path('/proc')/str(identity['pid'])).exists(), 'Simulator PID still live or reused; terminal-only')


def vector_zero(result):
    for k,v in dict(status='UNOBSERVABLE', vector_destination_requests=0,
        prefix_vector_destination_requests=0, stopped_at_spike_index=None, compared_instructions=0,
        compared_bytes=0, skipped_unknown_bytes=0, non_bit_exact_instructions=[],
        unobservable_instructions=[], incomplete_requests=[], unretired_requests=[], trapped_requests=[],
        first_mismatch=None, instructions=[]).items():
        require(type(result.get(k)) is type(v) and result[k]==v, 'Exact zero vector-data scope differs: '+k)


def logs(console, vcs):
    for text in (console,vcs):
        lines=text.splitlines()
        require(lines.count('Core Test *** SUCCESS ***')==1, 'Exact terminal SUCCESS marker')
        for line in lines:
            if re.search(r'\bUVM_(ERROR|FATAL)\b',line):
                require(re.fullmatch(r'\s*UVM_(?:ERROR|FATAL)\s*:\s*0\s*',line) is not None, 'Actual UVM diagnostic')
            require(not re.match(r'^\s*(?:Error[-:]|Fatal[-:]|Exception @|\[ARA_CONTRACT_ERROR\]|DTLB_PPN1200_ERROR)',line),
                    'Actual simulator/probe/contract error')
            require('Core Test *** FAILED' not in line, 'Explicit core failure')
        summaries=[contract.parse_contract_summary(x) for x in lines if '[ARA_CONTRACT]' in x]
        require(len(summaries)==1 and summaries[0] is not None and all(v==0 for v in summaries[0].values()),
                'Complete exact zero-vector native contract')
    expected=['ara_tb.clk','ara_tb.rst_n',MONITOR]+[SCOPE+'.'+s for s in
        ('update_i','replace_en','lu_hit','lu_hit_o','lu_access_i','lu_vaddr_i','lu_asid_i','plru_tree_q',
         'flush_i','s_st_enbl_i','content_q','tags_q')]+[LOAD+'.'+s for s in
        ('pop_ld_o','valid_i','translation_req_o','dtlb_hit_i','vaddr_o','paddr_i','dtlb_ppn_i','flush_i','ex_i')]
    lines=console.splitlines()
    require([x for x in lines if x.startswith('DTLB_PPN1200_OBJECT ')]==['DTLB_PPN1200_OBJECT '+x for x in expected]
        and lines.count('DTLB_PPN1200_READY')==1, 'Actual probe object/READY membership')


def packed_slots(decl,state,name,width):
    """Accept one whole packed bus or sixteen exact native slot declarations, never guessed MDA offsets."""
    parent=decl.get(name)
    children=[decl.get(name+'['+str(i)+']') for i in range(16)]
    require(not(parent and any(children)), 'Ambiguous parent/child native slot encoding')
    def bits(d,w):
        require(d is not None and d['width']==w, 'Missing/wrong native packed slot width')
        value=state.get(d['code'],'x'*w);require(len(value)==w, 'Packed value width')
        return value
    if parent:
        value=bits(parent,16*width)
        return [value[(15-i)*width:(16-i)*width] for i in range(16)]
    return [bits(d,width) for d in children]


def wave_gate(iterator, target_loads):
    _,decl=next(iterator)
    widths={'ara_tb.clk':1,'ara_tb.rst_n':1,MONITOR:64}
    widths.update({SCOPE+'.'+k:w for k,w in dict(update_i=189,replace_en=16,lu_hit=16,
        lu_hit_o=1,lu_access_i=1,lu_vaddr_i=64,lu_asid_i=16,plru_tree_q=30,flush_i=1,s_st_enbl_i=1).items()})
    widths.update({LOAD+'.'+k:w for k,w in dict(pop_ld_o=1,valid_i=1,dtlb_hit_i=1,
        vaddr_o=64,dtlb_ppn_i=44,flush_i=1,ex_i=203).items()})
    for name,w in widths.items():require(decl.get(name,{}).get('width')==w, 'Missing exact wave field '+name)
    def bits(state,name):
        d=decl[name]; b=state.get(d['code'],'x'*d['width']);require(len(b)==d['width'], 'Wave width');return b
    def val(state,name):
        b=bits(state,name); require(set(b)<=set('01'), 'Unknown active field '+name);return int(b,2)
    def part(b,hi,lo):
        x=b[len(b)-1-hi:len(b)-lo];require(set(x)<=set('01'), 'Unknown active packed field');return int(x,2)
    updates,accepted=[],[]; fenced=False; seen_active=False; last_cycle=-1; final_tags=None
    for time,before,after in iterator:
        require(not(seen_active and before.get(decl['ara_tb.rst_n']['code'])=='1' and
                    after.get(decl['ara_tb.rst_n']['code'])=='0'), 'Unexpected post-startup reset')
        if before.get(decl['ara_tb.clk']['code'])!='0' or after.get(decl['ara_tb.clk']['code'])!='1' or \
           before.get(decl['ara_tb.rst_n']['code'])!='1':continue
        seen_active=True; cycle=val(before,MONITOR)
        final_tags=packed_slots(decl,after,SCOPE+'.tags_q',61)
        require(cycle>last_cycle, 'Nonmonotonic monitor cycle');last_cycle=cycle
        if val(before,SCOPE+'.flush_i'): fenced=True
        update=bits(before,SCOPE+'.update_i')
        if part(update,188,188) and not val(before,SCOPE+'.flush_i') and not val(before,SCOPE+'.lu_hit_o'):
            k=len(updates);require(k<48,'Extra DTLB update');phase,i=divmod(k,16)
            if i==0:require(fenced,'Missing phase SFENCE');fenced=False
            mask=val(before,SCOPE+'.replace_en'); owner=pre.shared.plru_order()[phase][i]
            require(mask==1<<owner and part(update,185,159)==pre.shared.vpn(0,i) and
                part(update,158,143)==0 and part(update,127,64)==pre.pte(pre.pa(pre.page(phase,i)),0xc7)
                and part(update,63,0)==0, 'Update slot/VPN/ASID/PPN/flags identity differs')
            contents=packed_slots(decl,after,SCOPE+'.content_q',128)
            tags=packed_slots(decl,after,SCOPE+'.tags_q',61)
            require(part(contents[owner],127,64)==part(update,127,64) and part(contents[owner],63,0)==0 and
                part(tags[owner],60,45)==0 and part(tags[owner],44,31)==0 and
                part(tags[owner],30,4)==pre.shared.vpn(0,i) and part(tags[owner],3,0)==3,
                'Actual post-update slot contents/tags differ')
            updates.append(dict(phase=phase,entry=i,slot=owner,cycle=cycle,time_100fs=time,
                                ppn=pre.pa(pre.page(phase,i))>>12))
        if val(before,LOAD+'.pop_ld_o') and val(before,SCOPE+'.s_st_enbl_i'):
            k=len(accepted);require(k<96,'Extra translated load dequeue');phase,i=divmod(k//2,16)
            owner=pre.shared.plru_order()[phase][i]
            require(len(updates)>=phase*16+i+1 and val(before,LOAD+'.valid_i')==1 and
                val(before,LOAD+'.flush_i')==0 and part(bits(before,LOAD+'.ex_i'),0,0)==0 and
                val(before,LOAD+'.vaddr_o')==pre.address(i) and val(before,SCOPE+'.lu_vaddr_i')==pre.address(i) and
                val(before,LOAD+'.dtlb_hit_i')==val(before,SCOPE+'.lu_hit_o')==1 and
                val(before,SCOPE+'.lu_hit')==1<<owner and val(before,SCOPE+'.lu_asid_i')==0 and
                val(before,LOAD+'.dtlb_ppn_i')==pre.pa(pre.page(phase,i))>>12,
                'Accepted load exact slot/VA/PPN/hit/exception differs')
            require(cycle<=int(target_loads[k]['cycle']), 'Load dequeue after owner retirement')
            if k>=2:require(cycle>=int(target_loads[k-2]['cycle']), 'Load owner crosses prior CSR-restored pair')
            accepted.append(dict(phase=phase,entry=i,slot=owner,load_in_pair=k%2,cycle=cycle,
                retire_order=int(target_loads[k]['order']),retire_pc=target_loads[k]['pc']))
    require(len(updates)==48 and len(accepted)==96 and fenced, 'Incomplete48 update/96 load/final SFENCE')
    require(final_tags is not None and all(part(b,0,0)==0 for b in final_tags), 'Final SFENCE left valid TLB entries')
    require(all(sorted(x['slot'] for x in updates if x['phase']==p)==list(range(16)) for p in range(3)),
            'Actual sixteen-slot visits incomplete')
    return dict(status='ACTUAL48_UPDATES_16_SLOTS_PER_PHASE_96_ACCEPTED_HITS_EXACT',updates=updates,
                accepted_loads=accepted, inference_from_VA_count=False)


def collect(path,seal,out):
    require(out.parent==life.OUT and out.resolve()==out and not out.exists(), 'Fresh qualification output')
    r=runner.check(path,seal); run=runner.validate_record(r)
    expected=dict(r,pins=life.merge_pins(r['pins'],{str(path):seal}))
    require(life.read_bound(run/'manifest.json',life.digest(run/'manifest.json'))==expected, 'Executed manifest differs')
    terminal_gate(life.read_bound(run/'simulation-status.json',life.digest(run/'simulation-status.json')))
    identity_gate(life.read_bound(run/'live-simv-identity.json',life.digest(run/'live-simv-identity.json')),r)
    pins=expected['pins']; members=sorted(p for p in run.rglob('*') if p.is_file())
    require(members and not any(p.is_symlink() for p in run.rglob('*')), 'Missing/aliased artifacts')
    pins=life.merge_pins(pins,{str(p):life.digest(p) for p in members});life.check(pins)
    q=life.read_bound(runner.PRE,runner.PRE_SHA); commits=reference_check(q)
    with (run/'commit_trace.csv').open() as f:
        reader=csv.DictReader(f);require(tuple(reader.fieldnames or ())==FIELDS,'Exact commit schema');rows=list(reader)
    require(rows and all(set(x)==set(FIELDS) and all(v is not None and v!='' for v in x.values()) for x in rows),
            'Incomplete commit row')
    memory=memory_gate(rows,commits)
    require((memory['retired'],memory['compressed'],memory['uncompressed'],memory['loads'],memory['stores'],memory['total'])
        ==(191475,16823,2248,8553,10518,19071),'Exact frozen full memory population differs')
    scalar=spike_trace.compare_commit_prefix(runner.PRE.parent/'spike.trace',run/'commit_trace.csv',0x80000000,
        terminal_tohost_address=0x80001000,rvfi_store_data_layout='unshifted')
    counts={k:q['counts'][k] for k in ('matched_instructions','matched_scalar_writes',
        'matched_floating_writes','matched_scalar_memory_accesses')}
    pre.shared.architecture.scalar_exact(scalar,counts)
    logs((run/'console.log').read_text(),(run/'run.vcs.log').read_text())
    with (run/'vector_trace.csv').open() as f: vectors=list(csv.DictReader(f))
    require(all(v['event']=='config' for v in vectors),'Unexpected vector data/backend activity')
    vector=vector_commit.compare_vector_commits(runner.PRE.parent/'spike.trace',run/'commit_trace.csv',
        run/'vector_trace.csv',0x80000000)
    vector_zero(vector)
    vpd=run/'dtlb-ppn-swap.vpd';require(0<vpd.stat().st_size<=256*1024*1024,'Focused VPD missing/oversize')
    require(life.digest(CONVERTER)==CONVERTER_SHA,'Converter drift')
    out.mkdir()
    try:
        vcd=out/'dtlb-ppn-swap.vcd'
        with (out/'convert.log').open('x') as f:
            subprocess.run([str(CONVERTER),'-splitpacked',str(vpd),str(vcd)],stdout=f,stderr=subprocess.STDOUT,
                           timeout=180,check=True)
        parser=FunctionType(vcd_reader.vcd.__code__,dict(vcd_reader.vcd.__globals__,ROOT='ara_tb',WIDTHS={'clk':1,'rst_n':1}))
        target=[x for x in rows if int(x['pc'],16) in (q['symbols']['ppm_first_load'],q['symbols']['ppm_second_load'])]
        require(len(target)==96,'Target retirement owner count')
        wave=wave_gate(iter(parser(vcd)),target)
        for name,value in (('full-memory-audit.json',memory),('scalar-comparison.json',scalar),
            ('vector-comparison.json',vector),('tlb-slot-audit.json',wave),('gold-audit.json',q['counts'])):
            life.save(out/name,value)
        require(members==sorted(p for p in run.rglob('*') if p.is_file()),'Postrun artifact membership drift')
        life.check(pins)
        life.save(out/'qualification.json',dict(status='DTLB_PPN_SWAP779_FULL_ARCHITECTURE_AND_ACTUAL_SLOTS_QUALIFIED_NOT_ADMITTED',
            baseline=779,run=str(run),prepared_seal=seal,input_pins=pins,
            output_pins={str(p):life.digest(p) for p in out.iterdir() if p.is_file()},
            scalar_memory_instructions=19071,slot_updates=48,slots_per_phase=16,translated_loads=96,
            all_gold_checks=8297,vector_data_scope='UNOBSERVABLE_ZERO_REQUESTS',
            coverage_gain_not_checked=True,coverage_admitted=False))
        print('QUALIFIED_NOT_ADMITTED',life.digest(out/'qualification.json'),flush=True)
    except Exception as e:
        life.save(out/'failure.json',dict(reason=str(e),coverage_admitted=False,retry=False));raise


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--prepared',type=Path,required=True)
    p.add_argument('--seal',required=True);p.add_argument('--output',type=Path,required=True);a=p.parse_args()
    collect(a.prepared.absolute(),a.seal,a.output.absolute())
