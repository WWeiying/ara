"""Private cause-only reuse of frozen scalar, packed and RVFI owner gates."""
import argparse
from pathlib import Path
from types import CodeType, FunctionType, SimpleNamespace

import collect_csr_satp_sepc786 as original
import csr_satp_sepc_cycle_adapter as cycle
import run_csr_cause_wlrl788 as runner

life, require, oracle = runner.life, runner.require, runner.oracle
ADDRESSES = (0x342, 0x142)


def specialize(code):
    # Only named case identities/counts and CSR selectors change. The memory,
    # terminal, ready, ownership, privilege and unknown-value predicates stay.
    integers = {673: 664, 388: 380, 786: 788, 0x180: 0x342, 0x141: 0x142}
    strings = {
        'test_collect_csr_satp_sepc786.py': 'test_collect_csr_cause_wlrl788.py',
        'CSR_SATP_SEPC786_FULL_SCALAR_NATIVE_OWNER_QUALIFIED_NOT_ADMITTED': 'CAUSE_WLRL788_FULL_SCALAR_NATIVE_OWNER_QUALIFIED_NOT_ADMITTED'}
    def value(v):
        if isinstance(v, CodeType): return specialize(v)
        if type(v) is int: return integers.get(v,v)
        if type(v) is str: return strings.get(v,v)
        if type(v) is tuple: return tuple(value(x) for x in v)
        return v
    return code.replace(co_consts=tuple(value(v) for v in code.co_consts))


def csr_expected(reference, rows, ops):
    registers = {i:0 for i in range(32)}; state = {a:0 for a in ADDRESSES}; result=[]
    require(len(reference)==len(rows)==664,'Exact complete reference/retirement pairing')
    for row,c in zip(rows,reference):
        insn=c.instruction;address=insn>>20;fun=insn>>12&7
        if insn&127==0x73 and address in state:
            rs,rd=insn>>15&31,insn>>7&31
            require(fun==1 or (fun==2 and rs==0),'Cause owner opcode')
            operand,old=registers[rs],state[address]
            require(not rd or c.gpr_writes=={rd:old},'Independent old/readback value')
            if fun==1:state[address]=operand
            result.append(dict(order=row['order'],cycle=row['cycle'],pc=c.pc,insn=insn,csr=address,operand=operand,old=old,new=state[address],operation=ops['CSR_WRITE' if fun==1 else 'CSR_READ']))
        registers.update(c.gpr_writes);registers[0]=0
    require(len(result)==30 and state=={a:0 for a in ADDRESSES},'All30 cause owners restored')
    return result


def wave_audit(path, expected):
    cycle.source_contract()
    def vcd(p):
        # Packed layouts are source-derived unchanged types. Observation epoch
        # uses actual pre/post counters and the registered RVFI source proof.
        rows=original.primitive.parse_rows(CURRENT_RUN/'commit_trace.csv');terminal=rows[-1]
        require(len(rows)==664 and terminal['event']=='retire' and terminal['trap']==0
                and terminal['mem_addr']==0x80001000 and terminal['mem_wmask']!=0
                and terminal['mem_wdata']==1,'Exact cause tohost terminal')
        rebind=FunctionType(specialize(cycle.rebind.__code__),cycle.rebind.__globals__)
        yield from rebind(cycle.packed.vcd(p),terminal['cycle'])
    ns=dict(original.wave_audit.__globals__,wave=SimpleNamespace(vcd=vcd),owner_gate=owner_gate)
    return FunctionType(specialize(original.wave_audit.__code__),ns)(path,expected)


def owner_gate(edges,expected):
    result=FunctionType(specialize(original.owner_gate.__code__),original.owner_gate.__globals__)(edges,expected)
    require(not result['canceled_uncommitted_issues'],'No canceled cause transactions permitted')
    return result


def raw_gain(run,out,record,pins):
    bitmap=original.bitmap
    base=life.read_bound(runner.BASE/'admission-manifest.json',runner.BASE_SHA)
    life.check(base['input_pins']);life.check(base['output_pins'])
    before=life.read_bound(runner.BASE/'combined-bits.json',base['output_pins'][str(runner.BASE/'combined-bits.json')])
    ledger=(runner.BASE/'combined-inputs.txt').read_text().splitlines()
    require(ledger==[str(oracle.prior.inventory.BUILD/'sim/simv.vdb'),*before['tests']]
            and len(before['tests'])==len(set(before['tests']))==788 and str(run/'code.vdb') not in before['tests'],'Exact788 prefix/unique singleton')
    inputs=out/'single-inputs.txt'
    with inputs.open('x') as f:f.write(ledger[0]+'\n'+str(run/'code.vdb')+'\n')
    sample=bitmap.collect(inputs)
    require(sample['design']==before['design'] and all(pins.get(p)==s for p,s in sample['input_hashes'].items()),'Exact design/full metrics pins')
    combined=bitmap.combine(before,sample)
    require(combined['tests']==before['tests']+sample['tests'] and sum(len(x) for x in combined['metrics'].values())==6162,'Full6162 OR exact prefix')
    delta=bitmap.delta(before,combined)
    for n,v in (('single-bits.json',sample),('combined-bits.json',combined),('raw-delta.json',delta)):life.save(out/n,v)
    pins=life.merge_pins(life.merge_pins(pins,base['input_pins']),base['output_pins'])
    return dict(baseline=788,four_metrics=delta['metrics'],official_percentage_claimed=False,diagnostic_not_admission=True),pins


def namespace():
    # All imported frozen modules remain untouched; each original function
    # resolves its helper calls in this one private successor namespace.
    def observed_scalar(**fields):
        require(set(fields)=={'pc','instruction','vector_writes','gpr_writes','memory_accesses'},
                'Exact validated scalar observation fields')
        return SimpleNamespace(fpr_writes={},**fields)
    ns=dict(vars(original),runner=runner,oracle=SimpleNamespace(**dict(vars(oracle),inventory=oracle.prior.inventory)),
            __file__=__file__,csr_expected=csr_expected,wave_audit=wave_audit,raw_gain=raw_gain)
    for name in ('terminal_gate','scalar_gate','architecture','collect'):
        ns[name]=FunctionType(specialize(getattr(original,name).__code__),ns)
    # Original architecture explicitly rejects reference floating writes and
    # checks every GPR/memory effect before making this scalar-only view.
    ns['SimpleNamespace']=observed_scalar
    return ns


def collect(run,seal,out):
    global CURRENT_RUN
    CURRENT_RUN=Path(run).absolute()
    return namespace()['collect'](CURRENT_RUN,seal,Path(out).absolute())

if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--run',type=Path,required=True);p.add_argument('--run-seal',required=True);p.add_argument('--output',type=Path,required=True);a=p.parse_args()
    collect(a.run,a.run_seal,a.output)
