"""Exact monitor request ordinal versus independent whole-hart retirement order."""
import argparse
from pathlib import Path
from types import FunctionType, SimpleNamespace
import collect_btb_target_ring_v2 as prior

original,life,require=prior.original,prior.life,prior.require


def source_contract():
    pins=prior.source_contract();book=life.read_bound(original.pre.BOOK,original.pre.BOOK_SHA)
    monitor=life.ROOT/'hardware/tb/ara_commit_monitor.sv'
    pins=life.merge_pins(pins,{str(monitor):book[str(monitor)]});life.check(pins)
    text=original.axi.clean(monitor.read_text())
    require('start_arch=acc_req_i.req_valid&&!front_active_q;' in text and
            "if(finish_front)beginfront_active_q<=1'b0;arch_seq_q<=active_seq+1;end" in text and
            'next_order++;' in text,'Frozen request/retirement counters differ')
    for p in (Path(__file__).resolve(),Path(__file__).with_name('test_collect_btb_target_ring_v3.py').resolve()):
        pins=life.merge_pins(pins,{str(p):life.digest(p)})
    return pins


def lifecycle(rows,vectors,summary):
    starts=[r for r in rows if r['event']=='arch_start']
    require([int(r['order']) for r in starts]==list(range(len(starts))),'Incomplete request ordinal prefix')
    opcodes={r['insn'] for r in starts}
    retired=[r for r in rows if r['event']=='retire' and r['insn'] in opcodes]
    require(len(retired)==len(starts) and [r['insn'] for r in retired]==[r['insn'] for r in starts] and
            all(not int(r['trap']) for r in retired),'Exact accepted opcode/retire stream differs')
    mapping=[];proxy=[r for r in rows if r['event']!='retire']
    for start,retire in zip(starts,retired):
        require(int(start['cycle'])<=int(retire['cycle']),'Retirement precedes corresponding request')
        mapping.append(dict(arch_seq=int(start['order']),retire_order=int(retire['order']),
            retire_PC=retire['pc'],opcode=retire['insn'],start_cycle=int(start['cycle']),retire_cycle=int(retire['cycle'])))
        proxy.append(dict(retire,order=start['order']))
    result=original.lifecycle(proxy,vectors,summary)
    return dict(result,request_ordinal_is_not_retirement_order=True,exact_retire_bindings=mapping,
                full_hart_retirement_independently_checked_by_scalar_and_native_gold=True)


def collect(prepared,seal,out,vcd=None):
    arch=SimpleNamespace(**dict(original.pre.arch.__dict__,scalar_exact=prior.scalar_exact))
    pre=SimpleNamespace(**dict(original.pre.__dict__,arch=arch))
    FunctionType(original.collect.__code__,dict(original.collect.__globals__,pre=pre,
        source_contract=source_contract,lifecycle=lifecycle))(prepared,seal,out,vcd)


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--prepared',type=Path,required=True)
    p.add_argument('--seal',required=True);p.add_argument('--output',type=Path,required=True);p.add_argument('--vcd',type=Path)
    a=p.parse_args();collect(a.prepared.resolve(),a.seal,a.output.resolve(),a.vcd.resolve() if a.vcd else None)
