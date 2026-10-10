"""Full scalar/gold plus12 native faults and accepted allocation/flush ownership."""
import argparse
import ast
from collections import deque
import inspect
from pathlib import Path
from types import FunctionType, SimpleNamespace
import run_scalar_slot_rotation792 as runner
import collect_scalar_misalign789 as original
import scalar_misalign789_soc_width_adapter as widths

life, require, oracle=runner.life,runner.require,runner.oracle
SB=original.CORE+'.issue_stage_i.i_scoreboard'


def source_proof():
    proof=widths.source_proof()
    bookpath=original.shared.oracle.inventory.BUILD/'build-source-pins.json'
    book=life.read_bound(bookpath,original.packed.BOOK_SHA)
    root=life.ROOT/'hardware/deps/cva6/core'
    for name in ('scoreboard.sv','decoder.sv','controller.sv','issue_stage.sv','csr_regfile.sv'):
        p=root/name; require(life.digest(p)==book[str(p)],'Frozen slot producer/flush source')
        proof['pins'][str(p)]=book[str(p)]
    text=(root/'scoreboard.sv').read_text()
    for token in ('issue_instr_o[i].trans_id = issue_pointer[i];',
                  'decoded_instr_valid_i[i] && decoded_instr_ack_o[i] && !flush_unissued_instr_i',
                  "issue_pointer_n = '0;"):
        require(token in text,'Actual allocation/flush override clause')
    require(proof['layouts']['scoreboard_entry_t']['fields']['pc']==[437,374]
        and proof['layouts']['scoreboard_entry_t']['fields']['trans_id']==[373,371], 'Exact packed allocation type')
    proof.update(slot_contract='NrIssuePorts1: accepted valid && ack && !flush_unissued; fullflush overrides pointer_n0; capture issued trans_id, not retire-count inference',
        NOP_contract='0x13 OpcodeOpImm ALU/ADD; FU_NONE not required',
        fault_accounting='12 native ordered LSU/CSR owners and exact software frames',
        source_closure='Frozen SoC DCACHE_USER_WIDTH1 reused; no old HOLD/cache dependency')
    return proof


def owner_gate(edges,expected,handler_cycles):
    require(len(expected)==len(handler_cycles)==12,'Twelve exact fault owners')
    detected={}; pending=deque(); returned=[]; commits=[]; last=None; killed=0
    for e in edges:
        require(last is None or e['cycle']==last+1,'Native contiguous epoch'); last=e['cycle']
        if e['detector'] is not None:
            d=e['detector']; require(d['cause'] in (4,6) and d['tval'] in oracle.ADDRESSES and d['tval']&7 in (3,4) and 0<=d['tid']<8,'Owned full64 misalignment')
            detected[(d['tid'],d['cause'],d['tval'])]=e['cycle']
        for r in e['responses']:
            i=len(returned); require(i<12,'No extra fault response')
            key=(r['tid'],r['cause'],r['tval'])
            require(key in detected and detected[key]<=e['cycle'],'Response follows detector')
            require(r['tid']==oracle.SLOTS[i] and all(r[k]==expected[i][k] for k in ('cause','tval')),'Exact predicted allocation VID and ordered full64 address')
            pending.append(dict(r,returned_cycle=e['cycle'])); returned.append(r)
        if e['load_fault']:
            require(not e['tag_valid'] or e['kill_req'],'Fault load tag must kill'); killed+=int(e['tag_valid'] and e['kill_req'])
        if e['store_fault']: require(e['st_valid']==0,'Fault store cannot enqueue')
        if e['commit'] is not None:
            require(pending and len(commits)<12,'No unowned CSR exception')
            r=pending.popleft(); a=e['commit']; i=len(commits)
            require({k:a[k] for k in ('pc','cause','tval')}==expected[i]
                and a['tid']==r['tid']==oracle.SLOTS[i] and a['cause']==r['cause'] and a['tval']==r['tval']
                and e['ack']==0 and r['returned_cycle']<=e['cycle']<handler_cycles[i],'Exact fault PC/VID/noack/handler ordering')
            commits.append(dict(a,cycle=e['cycle'],returned_cycle=r['returned_cycle']))
    require(len(returned)==len(commits)==12 and not pending,'All twelve fault owners complete')
    return dict(status='TWELVE_NATIVE_FAULT_OWNERS_EXACT',owners=commits,killed_speculative_tags=killed,
        no_fault_store_enqueue=True,external_AXI_directly_observed=False)


def allocation_gate(edges,symbols):
    completed=[]; active=None; latest_flush=None; previous_fault=-1; vetoes=0
    for e in edges:
        raw=bool(e['valid'] and e['ack'] and not e['flush_unissued'])
        want=0 if e['flush'] else (e['q']+int(raw))%8
        require(e['n']==want,'Same-cycle pointer next / fullflush priority')
        require(e['post']==want or e.get('terminal_no_nba',False) and e['post']==e['q'],'Pointer NBA observation')
        if e['flush']:
            require(active is None,'Unexpected fullflush within landing/fault accepted sequence')
            latest_flush=(e['cycle'],e['eret']); vetoes+=int(raw)
        if not raw or e['flush']: continue
        require(e['tid']==e['q'],'Actual issued allocation trans_id matches pointer')
        i=len(completed)
        if i>=12: continue
        start=symbols['slot_landing'+str(i)]; fault=symbols['slot_fault'+str(i)]
        if active is None:
            if e['pc']!=start: continue
            require(latest_flush and latest_flush[1]==1 and latest_flush[0]>previous_fault and e['q']==0,'MRET fullflush is fresh landing origin')
            active=[]
        offset=len(active)
        require(e['pc']==start+4*offset and e['q']==offset and offset<=oracle.SLOTS[i],'Only expected accepted landing sequence')
        opcode=(0x00943023 if i%3==1 else 0x00043e83) if e['pc']==fault else 0x13
        require(e['op']==opcode,'Exact accepted opcode, not inferred FU_NONE')
        active.append(dict(pc=e['pc'],tid=e['tid'],cycle=e['cycle'],op=e['op']))
        if e['pc']==fault:
            require(offset==oracle.SLOTS[i],'Exact fault allocation VID')
            completed.append(dict(index=i,slot=offset,flush_cycle=latest_flush[0],accepted=active))
            previous_fault=e['cycle']; active=None
    require(len(completed)==12 and active is None,'All twelve allocation chains complete')
    return dict(status='TWELVE_ACCEPTED_ALLOCATION_FLUSH_CHAINS_EXACT',chains=completed,fullflush_same_cycle_vetoes=vetoes,
        retirement_used_to_infer_slots=False)


def allocation_wave(path,symbols,terminal_cycle):
    proof=source_proof(); layout=proof['layouts']['scoreboard_entry_t']
    parse=FunctionType(original.shared.wave.vcd.__code__,dict(original.shared.wave.vcd.__globals__,ROOT='ara_tb',WIDTHS={'clk':1,'rst_n':1}))
    stream=iter(parse(path)); _,decl=next(stream)
    fields={'issue_pointer_q':3,'issue_pointer_n':3,'flush_i':1,'flush_unissued_instr_i':1,
            'decoded_instr_valid_i':1,'decoded_instr_ack_o':1,'decoded_instr_i':438,'issue_instr_o':438,'orig_instr_i':32}
    need={SB+'.'+n:w for n,w in fields.items()}
    need.update({'ara_tb.clk':1,'ara_tb.rst_n':1,original.MONITOR:64,original.CSR+'.eret_o':1})
    require(all(decl.get(n,{}).get('width')==w for n,w in need.items()),'Exact source-derived allocation probe shapes')
    def number(state,name):
        bits=state.get(decl[name]['code'],'x'); require(set(bits)<={'0','1'},'Unknown active allocation signal '+name); return int(bits,2)
    def field(state,parent,name):
        bits=state.get(decl[parent]['code'],'x'); bits=bits.rjust(438,bits[0] if bits[0] in 'xz' else '0')
        left,right=layout['fields'][name]; value=bits[437-left:438-right]
        require(len(bits)==438 and set(value)<={'0','1'},'Unknown exact active allocation member '+name)
        return int(value,2)
    def edges():
        active=False
        for _,before,after in stream:
            if before.get(decl['ara_tb.clk']['code'])!='0' or after.get(decl['ara_tb.clk']['code'])!='1': continue
            if number(before,'ara_tb.rst_n')!=1:
                require(not active,'Unexpected reset'); continue
            active=True
            e={k:number(before,SB+'.'+n) for k,n in [('q','issue_pointer_q'),('n','issue_pointer_n'),('flush','flush_i'),('flush_unissued','flush_unissued_instr_i'),('valid','decoded_instr_valid_i'),('ack','decoded_instr_ack_o')]}
            e.update(cycle=number(before,original.MONITOR),post=number(after,SB+'.issue_pointer_q'),eret=number(before,original.CSR+'.eret_o'))
            e['terminal_no_nba']=e['cycle']==terminal_cycle and number(after,original.MONITOR)==terminal_cycle
            if e['valid'] and e['ack'] and not e['flush_unissued'] and not e['flush']:
                e.update(pc=field(before,SB+'.decoded_instr_i','pc'),tid=field(before,SB+'.issue_instr_o','trans_id'),op=number(before,SB+'.orig_instr_i'))
                require(field(before,SB+'.issue_instr_o','pc')==e['pc'],'Issued/decoded exact PC')
            yield e
    return allocation_gate(edges(),symbols)


def rewrite(fn,ns,numbers=None,strings=None):
    tree=ast.parse(inspect.getsource(fn)); numbers=numbers or {}; strings=strings or {}
    class Replace(ast.NodeTransformer):
        def visit_Constant(self,node):
            if type(node.value) is int and node.value in numbers: return ast.copy_location(ast.Constant(numbers[node.value]),node)
            if type(node.value) is str and node.value in strings: return ast.copy_location(ast.Constant(strings[node.value]),node)
            return node
    tree=Replace().visit(tree); ast.fix_missing_locations(tree)
    exec(compile(tree,str(Path(__file__).resolve()),'exec'),ns); return ns[fn.__name__]


def architecture(rows,reference,symbols,elf,ledger):
    stats=life.read_bound(runner.PRE/'preflight-manifest.json',runner.PRE_SEAL)['validation']
    ns=dict(original.architecture.__globals__,oracle=SimpleNamespace(GUARDS=original.oracle.GUARDS,validate=oracle.validate))
    return rewrite(original.architecture,ns,{866:stats['retired_instructions'],226:stats['scalar_memory_accesses'],6:12},
        {'mis_guards':'slot_guards','mis_handler':'slot_handler','FULL_SCALAR_AND_SIX_TRAP_GOLD_EXACT':'FULL_SCALAR_AND_TWELVE_TRAP_GOLD_EXACT'})(rows,reference,symbols,elf,ledger)


def wave_audit(path,expected,handlers,terminal_cycle):
    # The validated width adapter itself constructs the original strict wave
    # body; supply a private original namespace with the new12-owner gate.
    private=SimpleNamespace(**dict(vars(original),wave_audit=FunctionType(original.wave_audit.__code__,dict(original.wave_audit.__globals__,owner_gate=owner_gate))))
    native=FunctionType(widths.wave_audit.__code__,dict(widths.wave_audit.__globals__,original=private,source_proof=source_proof))(path,expected,handlers,terminal_cycle)
    pre=life.read_bound(runner.PRE/'preflight-manifest.json',runner.PRE_SEAL)
    allocations=allocation_wave(path,pre['symbols'],terminal_cycle)
    for chain,owner in zip(allocations['chains'],native['owners']):
        event=chain['accepted'][-1]
        require(event['pc']==owner['pc'] and event['tid']==owner['tid'] and event['cycle']<=owner['returned_cycle']<=owner['cycle'],'Allocation -> native LSU/CSR exact fault owner')
    return dict(faults=native,allocations=allocations,source_closure=source_proof())


def collect(run,seal,out):
    record=life.read_bound(Path(run).with_name(Path(run).name+'.prepared.json'),seal)
    runner.configure(record['preflight'],record['preflight_seal'])
    stats=life.read_bound(runner.PRE/'preflight-manifest.json',runner.PRE_SEAL)['validation']
    terminal=FunctionType(original.terminal_gate.__code__,dict(original.terminal_gate.__globals__,runner=runner))
    ns=dict(original.collect.__globals__,runner=runner,oracle=oracle,terminal_gate=terminal,architecture=architecture,wave_audit=wave_audit)
    fn=rewrite(original.collect,ns,{866:stats['retired_instructions'],226:stats['scalar_memory_accesses'],56:89,6:12},
        {'SCALAR_MISALIGN789_FULL_SCALAR_SIX_NATIVE_FAULTS_QUALIFIED_NOT_ADMITTED':'SLOT_ROTATION792_FULL_SCALAR_TWELVE_NATIVE_OWNERS_QUALIFIED_NOT_ADMITTED'})
    fn(run,seal,out)


if __name__=='__main__':
    p=argparse.ArgumentParser(); p.add_argument('--run',required=True,type=Path); p.add_argument('--run-seal',required=True); p.add_argument('--output',required=True,type=Path)
    a=p.parse_args(); collect(a.run,a.run_seal,a.output)
