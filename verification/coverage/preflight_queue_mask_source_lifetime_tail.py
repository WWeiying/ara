"""One checker correction: mask tail ISA set-valued, unchanged eight-cell stimulus."""
import argparse
import inspect
from pathlib import Path
import preflight_queue_mask_source_lifetime as predecessor

prior=predecessor.prior
life,require=prior.life,prior.require
APP=prior.ROOT/'apps/riscv-tests/isa/rv64uv/vqueue_mask_source_lifetime_tail.c'
PREDECESSOR_SHA='49fa8b3507e3ba3f9b48b52d9077b30bbd837545085b9661531f990d717a144b'
SPEC='https://docs.riscv.org/reference/isa/v20260120/unpriv/v-st-ext.html'

def tail_policy():
    return dict(source=SPEC,section='30.1.3.4.3',VL_equals_VLMAX=True,
        mask_destination_register=8,active_mask_bits=720,agnostic_tail_bits=7472,
        strictly_defined_snapshot_bytes=6912,active_mask_store_bytes=90,non_destination_v9_bytes=512,
        tail_allowed='Each tail bit independently retains old or becomes 1; old1 cannot clear',
        computed_VLMAX_tail_alternative_has_no_extra_positions=True,
        agnostic_tail_not_exported_or_read_by_C=True,VRF_diff_requires_tail_policy=True,
        non_destination_v9_strict=True,source_div_guards_strict=True,
        reference_tail_choice_is_not_a_DUT_requirement=True)

def expected(cell,kind):
    if kind!='vid':return prior.expected(cell,kind)
    sew,lmul=prior.CELLS[cell];maximum=(1<<sew)-1;vl=128*lmul//(sew//8)
    result=bytearray([0xa5]*288)
    for i in range(vl):
        byte=16+i//8;bit=i%8
        if bit==0:result[byte]=0
        result[byte]|=int(((maximum-13*i)%(1<<sew))<maximum//2)<<bit
    if lmul==2:result[144:272]=prior.expected(cell,'source')[144:272]
    return bytes(result)

def compare_buffer(cell,kind,actual):
    require(len(actual)==288,'Full snapshot including guards required')
    require(actual==expected(cell,kind),'Strict active mask/v9/source/div/guard mismatch')

def tail_bit_allowed(old,actual):
    require(old in (0,1) and actual in (0,1),'Known bit values required')
    return actual==old or actual==1

def namespace():
    require(life.digest(Path(predecessor.__file__))==PREDECESSOR_SHA,'Frozen predecessor changed')
    ns=predecessor.namespace()
    ns.update(APP=APP,__file__=str(Path(__file__).resolve()),expected=expected,compare_buffer=compare_buffer,tail_policy=tail_policy)
    source=inspect.getsource(prior.validate)
    pair_old="pair[1].instruction>>26 == 20 and\n                (pair[1].instruction>>15)&31 == 17"
    pair_new="pair[1].instruction>>26 == 26 and\n                (pair[1].instruction>>12)&7 == 4 and (pair[1].instruction>>20)&31 == 24"
    buffer_old="require(read('qv_'+k,n*288,288) == expected(n,k), 'Independent buffer/guard mismatch')"
    buffer_new="compare_buffer(n,k,read('qv_'+k,n*288,288))"
    require(source.count(pair_old)==source.count(buffer_old)==1,'Exact predecessor oracle structure')
    source=source.replace(pair_old,pair_new).replace(buffer_old,buffer_new)
    source=source.replace("buffer_bytes=6912,","strictly_defined_snapshot_bytes=6912, active_mask_bits=720, unobserved_agnostic_VRF_tail_bits=7472,")
    exec(compile(source,__file__+':oracle','exec'),ns)
    original_binding=ns['binding']
    def binding():
        targets,pins=original_binding()
        deps=[Path(predecessor.__file__).resolve(),Path(predecessor.__file__).with_name('test_preflight_queue_mask_source_lifetime.py'),
              prior.ROOT/'verification/tests/queue_mask_source_lifetime_tail_review.txt']
        pins=life.merge_pins(pins,{str(f):life.digest(f) for f in deps})
        life.check(pins);return targets,pins
    ns['binding']=binding
    source=inspect.getsource(prior.build)
    require(source.count('len(rvv)==48')==1 and source.count('test_preflight_queue_vid_source_lifetime.py')==1,
            'Exact build adapter structure')
    source=source.replace('len(rvv)==48','len(rvv)==60')
    source=source.replace('test_preflight_queue_vid_source_lifetime.py','test_preflight_queue_mask_source_lifetime_tail.py')
    source=source.replace("schema='QUEUE_VID_LIFETIME_SOFTWARE_PREFLIGHT_V1'",
                          "schema='QUEUE_MASK_LIFETIME_TAIL_SOFTWARE_PREFLIGHT_V2',tail_policy=tail_policy()")
    exec(compile(source,__file__+':build','exec'),ns)
    return ns

if __name__=='__main__':
    ap=argparse.ArgumentParser();ap.add_argument('--output',type=Path,required=True)
    namespace()['build'](ap.parse_args().output.resolve())
