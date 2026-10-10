"""Source-bound diagnostic CSR flush/retirement mapping; no checker gate changes."""
import csv
from pathlib import Path
from types import FunctionType
import collect_scalar_c910_pattern795 as c

life,require=c.life,c.require


def evidence():
    path=life.OUT/'scalar-c910-pattern795-schedule-diagnostic-agent-20261008-01.json'
    doc=life.read_bound(path,life.digest(path))
    wave=life.OUT/'scalar-c910-pattern795-qualified-v2-parent-20261008-01/probe.vcd'
    require(life.digest(wave)==doc['wave_sha256'],'Same unchanged wave')
    parser=c.frozen.original.oracle.prior.wave.vcd
    stream=iter(FunctionType(parser.__code__,dict(parser.__globals__,ROOT='ara_tb',WIDTHS={'clk':1,'rst_n':1}))(wave))
    _,decl=next(stream);starts=[]
    for time,before,after in stream:
        if before.get(decl['ara_tb.clk']['code'])=='0' and after.get(decl['ara_tb.clk']['code'])=='1' and before.get(decl['ara_tb.rst_n']['code'])=='1':
            starts.append(time)
            if len(starts)==2:break
    first,second=starts;period=second-first;require(first==155000 and period==10000,'Actual reset-release edge anchor')
    bookpath=c.oracle.reused.old.BUILD/'build-source-pins.json'
    book=life.read_bound(bookpath,c.oracle.reused.old.SOURCE_SHA)
    anchors={
        'hardware/tb/ara_commit_monitor.sv':("cycle_q <= '0;",'cycle_q <= cycle_q + 1;'),
        'hardware/deps/cva6/core/cva6_rvfi.sv':('always_ff @(posedge clk_i)','rvfi_instr_o[i].valid <= valid;'),
        'hardware/deps/cva6/core/csr_regfile.sv':('riscv::CSR_FCSR: begin',"flush_o = 1'b1;"),
        'hardware/deps/cva6/core/controller.sv':('if (flush_csr_i || flush_acc_i) begin',"flush_ex_o             = 1'b1;"),
        'hardware/deps/cva6/core/frontend/frontend.sv':('if (set_pc_commit_i) begin','npc_d = pc_commit_i +'),
        'hardware/deps/cva6/core/scoreboard.sv':("mem_n[i].issued       = 1'b0;",'if (flush_i) begin'),
        'hardware/deps/fpnew/src/fpnew_divsqrt_th_64_multi.sv':
            ('assign sqrt_valid  = in_valid_q & (op_q != fpnew_pkg::DIV) & in_ready & ~flush_i;',),
    }
    pins={str(path):life.digest(path),str(wave):life.digest(wave),str(bookpath):c.oracle.reused.old.SOURCE_SHA}
    for rel,needles in anchors.items():
        p=life.ROOT/rel;require(life.digest(p)==book[str(p)] and all(n in p.read_text() for n in needles),'Frozen sampling/flush/restart source')
        pins[str(p)]=book[str(p)]
    trace=life.OUT/'scalar-c910-pattern795-old-image-agent-20261008-01/commit_trace.csv'
    with trace.open() as f:rows=list(csv.DictReader(f))
    by={}
    for row in rows:by.setdefault(int(row['cycle']),[]).append(row)
    mappings=[]
    for row in doc['audit']['raw_events']:
        if row['root']['flush_i']!=1:continue
        time=row['time'];require((time-first)%period==0,'Exact clock edge')
        cycle=(time-first)//period
        candidates=[r for r in by.get(cycle+1,[]) if int(r['insn'],16)&127==115]
        require(len(candidates)==1 and int(candidates[0]['trap'])==0,'Unique next-edge CSR retirement for every flush')
        r=candidates[0];mappings.append(dict(time=time,native_cycle=cycle,retire_cycle=int(r['cycle']),
            order=int(r['order']),pc=r['pc'],instruction=r['insn'],CSR_address=int(r['insn'],16)>>20))
    require(len(mappings)==226 and sum(r['CSR_address']==3 for r in mappings)==225,'All225 FCSR plus startup CSR flushes')
    pins[str(trace)]=life.digest(trace);life.check(pins)
    return dict(status='CSR_FLUSH_EPOCH_DIAGNOSTIC_NOT_QUALIFICATION',input_pins=pins,
        first_postreset_edge=first,clock_period=period,monitor_preNBA=True,RVFI_register_delay_edges=1,
        mappings=mappings,architectural_FPU_owners=896,physical_outputs=1176,
        speculative_completed_FMV_outputs=280,flush_priority_input_cancellations=183,
        canceled_FMV=167,canceled_SQRT=16,accepted_arithmetic_cancellation_allowed=False,
        proposed_rule='Checkpoint exact cell prefix at source-bound FCSR flush; archive speculative attempts, require full exact final reissue/retirement and all physical owner gold.',
        coverage_admitted=False,new_simulation=False)


if __name__=='__main__':
    out=life.OUT/'scalar-c910-pattern795-flush-epoch-binding-agent-20261008-01.json'
    value=evidence();value['source_sha256']=life.digest(Path(__file__))
    life.save(out,value);print('DIAGNOSTIC_ONLY',life.digest(out),'mapped_flushes',len(value['mappings']))
