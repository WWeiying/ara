"""Only linearize leaf validation; preserve the frozen48-call stimulus and every guard."""
import argparse
from pathlib import Path
from types import FunctionType
import build_itlb_asid_exec as old

life,require=old.life,old.require
ROOT,OUT=old.ROOT,old.OUT
APP=ROOT/'apps/riscv-tests/isa/rv64uv/vitlb_asid_exec_matrix_linear.c'
PRIOR=OUT/'itlb-asid-exec-preflight-771-agent-20261007-02/preflight.json'
PRIOR_SHA='37a67c8bc19563b8b267225a1c50169a5cc63c1ad3c8dbba477a5dce05618a2b'
OLD_BLOCK='''    for (unsigned i=0;i<512;i++) {
      unsigned long goldpte=0;
      for (unsigned entry=0;entry<16;entry++) if ((vpn(phase,entry)&511ul)==i)
        goldpte=pte((unsigned long)itm_code[entry],0x4b);
      check(itm_leaf[i],goldpte,&checks);
    }'''
NEW_BLOCK='    for (unsigned i=0;i<512;i++) check(itm_leaf[i],itm_leaf_gold[i],&checks);'


def transform(text):
    declaration='volatile unsigned long itm_root_gold[512], itm_mid_gold[512];'
    initialization='    for (unsigned i=0;i<512;i++) itm_leaf[i]=0;'
    require(all(text.count(x)==1 for x in (declaration,initialization,OLD_BLOCK)),
            'Exact frozen validation source required')
    return text.replace(declaration,declaration+'\nvolatile unsigned long itm_leaf_gold[512];').replace(
        initialization,initialization+'''
    for (unsigned i=0;i<512;i++) itm_leaf_gold[i]=0;
    for (unsigned entry=0;entry<16;entry++)
      itm_leaf_gold[vpn(phase,entry)&511ul]=pte((unsigned long)itm_code[entry],0x4b);''').replace(OLD_BLOCK,NEW_BLOCK)


def exact_change(original,replacement):
    require(replacement==transform(original),'Change outside leaf-oracle linearization')


def source_contract():
    q=life.read_bound(PRIOR,PRIOR_SHA)
    require(life.digest(old.APP)==q['input_pins'][str(old.APP)] and
        life.digest(Path(old.__file__).resolve())==q['input_pins'][str(Path(old.__file__).resolve())],
        'Frozen predecessor application/driver changed')
    exact_change(old.APP.read_text(),APP.read_text())
    proof,pins=old.source_contract()
    for p,h in ((PRIOR,PRIOR_SHA),(old.APP,q['input_pins'][str(old.APP)]),
                (Path(old.__file__).resolve(),q['input_pins'][str(Path(old.__file__).resolve())])):
        pins=life.merge_pins(pins,{str(p):h})
    test=Path(__file__).with_name('test_build_itlb_asid_exec_linear.py')
    pins=life.merge_pins(pins,{str(test):life.digest(test)})
    proof=dict(proof,validation_change='exact source diff: prebuild512 leaf oracle,16 fills,512 comparisons perphase',
        stimulus_unchanged=True,checks_unchanged=10966,code_guards_unchanged_bytes=65536,
        original_reference_instructions=q['counts']['matched_instructions'],old_vpn_checks=24576,
        new_oracle_entries=1536,new_oracle_fills=48,original_VCS_timeout_preserved=True)
    return proof,pins


def validate(commits,symbols):
    result=old.validate(commits,symbols)
    writes={};initialized=False;phases=0
    for c in commits:
        for a,v in c.memory_accesses:
            if v is None:continue
            writes[a]=v
            if a==symbols['itm_phase']:
                if not initialized:
                    require(v==0,'CRT phase init differs');initialized=True;continue
                require(v==phases,'Phase order differs');phases+=1
                expected=old.tables(symbols,v)[2]
                require([writes.get(symbols['itm_leaf_gold']+8*i) for i in range(512)]==expected,
                        'Independent full leaf-gold image differs')
    require(phases==3,'Missing full linear-oracle phase')
    return result


def prepare(output):
    namespace=dict(old.__dict__,APP=APP,SYMBOLS=old.SYMBOLS+('itm_leaf_gold',),
        __file__=str(Path(__file__).resolve()),source_contract=source_contract,validate=validate)
    # Private globals reuse the exact mature compiler/Spike/pin implementation;
    # the frozen module and its filesystem artifacts remain unchanged.
    impl=FunctionType(old.prepare.__code__,namespace,argdefs=old.prepare.__defaults__)
    impl(output)
    q=life.read_bound(output/'preflight.json',life.digest(output/'preflight.json'))
    prior=life.read_bound(PRIOR,PRIOR_SHA)
    reduction=prior['counts']['matched_instructions']-q['counts']['matched_instructions']
    require(reduction>200000,'Insufficient measured workload reduction; do not launch')
    life.save(output/'linear-workload.json',dict(status='SPIKE_MEASURED_LINEARIZATION_NOT_RTL',
        old_instructions=prior['counts']['matched_instructions'],new_instructions=q['counts']['matched_instructions'],
        removed_instructions=reduction,software_checks=q['software_checks'],trap_count=q['trap_count'],
        preflight_seal=life.digest(output/'preflight.json'),VCS_launched=False,coverage_admitted=False))
    print('LINEAR_PREFLIGHT_READY',life.digest(output/'preflight.json'),q['counts'],flush=True)


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--output',type=Path,required=True)
    prepare(p.parse_args().output.absolute())
