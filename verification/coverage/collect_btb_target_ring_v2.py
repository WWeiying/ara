"""BTB-specific retirement accounting: one S-ECALL plus all matched commits."""
import argparse
from pathlib import Path
from types import FunctionType, SimpleNamespace
import collect_btb_target_ring as original

life,require=original.life,original.require


def scalar_exact(result,expected):
    require(expected.get('ara_trap_events')==1,'Exactly one specified S-ECALL required')
    fixed=dict(expected,status='TERMINAL_TOHOST_MATCH',entry='0x0000000080000000',
        rvfi_store_data_layout='unshifted',skipped_unobservable_register_values=0,
        stopped_at_unobservable=None,aligned_vector_faults=[],mismatch=None,terminal_ecall=None,
        vector_state_compared=False,ara_retired_instructions=expected['matched_instructions']+1,
        ara_committed_instructions=expected['matched_instructions'])
    require(all(k in result and type(result[k]) is type(v) and result[k]==v for k,v in fixed.items()),
        'Exact committed/retired/trap scalar accounting differs')
    terminal=result.get('terminal_tohost')
    require(isinstance(terminal,dict) and terminal.get('address')=='0x0000000080001000' and
        terminal.get('write_value')=='0x1','Successful scalar terminal differs')


def source_contract():
    pins=original.source_contract()
    for p in (Path(__file__).resolve(),Path(__file__).with_name('test_collect_btb_target_ring_v2.py').resolve()):
        pins=life.merge_pins(pins,{str(p):life.digest(p)})
    return pins


def collect(prepared,seal,out,vcd=None):
    arch=SimpleNamespace(**dict(original.pre.arch.__dict__,scalar_exact=scalar_exact))
    pre=SimpleNamespace(**dict(original.pre.__dict__,arch=arch))
    implementation=FunctionType(original.collect.__code__,dict(original.collect.__globals__,
        pre=pre,source_contract=source_contract))
    implementation(prepared,seal,out,vcd)


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--prepared',type=Path,required=True)
    p.add_argument('--seal',required=True);p.add_argument('--output',type=Path,required=True);p.add_argument('--vcd',type=Path)
    a=p.parse_args();collect(a.prepared.resolve(),a.seal,a.output.resolve(),a.vcd.resolve() if a.vcd else None)
