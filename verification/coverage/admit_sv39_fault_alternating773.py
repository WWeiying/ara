"""Offline exact772 prefix plus one independently-qualified vector fault run."""
import argparse
import json
from pathlib import Path
import gain_sv39_fault_alternating772 as g
from admit_stride_metadata768 import dedup

life,require=g.life,g.require
GAIN=life.OUT/'sv39-fault-alternating-raw772-agent-20261007-01/diagnostic.json'
GAIN_SHA='d6a12b73341bd28671b70098a357fde2605689801f1542096a5d6458a9b18380'

def architecture(q):
    require(q['status']=='FULL_SCALAR_VECTOR_EXACT_FAULT_MEMORY_CSR_GUARDS_PASS_NOT_ADMITTED'
      and q['coverage_admitted'] is False and q['run']==str(g.q.csr.prefix.RUN) and
      q['baseline_seal']==g.old.p.BASE_SHA,'Exact full architecture qualification')
    s=q['scalar'];require(s['status']=='TERMINAL_TOHOST_MATCH' and s['mismatch'] is None and
      s['skipped_unobservable_register_values']==0 and s['stopped_at_unobservable'] is None and
      s['matched_instructions']==19759 and len(s['aligned_vector_faults'])==8,'Complete scalar+fault proof')
    require(q['scalar_memory']['instructions']==19759 and q['scalar_memory']['unmodeled_memory_effects']==0
      and q['oracle']['full_VRF_bytes']==4096 and q['oracle']['checks']==1091
      and q['oracle']['full_page_no_fault_store_effect_bytes']==4096,'All scalar/RVC/VRF/page/guards checks')
    require(q['lifecycle']['requests']==q['lifecycle']['responses']==79 and
      len(q['lifecycle']['rejected'])==8,'Exact terminal native lifecycle')

def union(before,single):
    require(len(before['tests'])==len(set(before['tests']))==772 and
      single['tests']==[str(g.q.csr.prefix.RUN/'code.vdb')] and single['tests'][0] not in before['tests'],
      'Exact772 prefix/unique single candidate')
    after=g.old.bitmap.combine(before,single);count=0
    for metric,rows in before['metrics'].items():
        for scope,old in rows.items():
            require(int(after['metrics'][metric][scope]['bits'],16)==
              int(old['bits'],16)|int(single['metrics'][metric][scope]['bits'],16),'Every native raw OR')
            count+=1
    require(count==6162 and after['tests']==before['tests']+single['tests'],'Complete6162 same-design OR/prefix')
    return after

def evaluate():
    base=life.read_bound(g.BASE/'admission-manifest.json',g.BASE_SHA)
    diagnostic=life.read_bound(GAIN,GAIN_SHA);qualification=life.read_bound(g.QUAL,g.QUAL_SHA)
    architecture(qualification);life.check(diagnostic['input_pins']);life.check(diagnostic['output_pins'])
    require(diagnostic['status']=='QUALIFIED_SINGLE_FAULT_RAW772_DIAGNOSTIC_NOT_ADMITTED'
      and diagnostic['baseline_seal']==g.BASE_SHA and diagnostic['qualification_seal']==g.QUAL_SHA
      and diagnostic['coverage_admitted'] is False and diagnostic['scoped_binary_toggle_gain']>0,
      'Positive actual same772 measured Toggle gate')
    before=life.read_bound(g.BASE/'combined-bits.json',base['output_pins'][str(g.BASE/'combined-bits.json')])
    ledger=(g.BASE/'combined-inputs.txt').read_text().splitlines()
    require(life.digest(g.BASE/'combined-inputs.txt')==base['output_pins'][str(g.BASE/'combined-inputs.txt')]
      and ledger==[diagnostic['compiled_design'],*before['tests']],'Exact sealed772 ledger')
    directory=GAIN.parent;single=life.read_bound(directory/'single-bits.json',diagnostic['output_pins'][str(directory/'single-bits.json')])
    proposed=union(before,single)
    require(proposed==life.read_bound(directory/'proposed-combined-bits.json',diagnostic['output_pins'][str(directory/'proposed-combined-bits.json')]),
      'Actual diagnostic proposed OR equality')
    delta=g.old.bitmap.delta(before,proposed)
    require(delta['metrics']==diagnostic['metrics'],'Exact measured four-metric delta')
    pre=life.read_bound(g.old.PRE/'preflight.json',g.old.PRE_SHA)
    prior=life.read_bound(g.old.PRE/'elf-dedup.json',pre['input_pins'][str(g.old.PRE/'elf-dedup.json')])
    require([row['vdb'] for row in prior['members']]==ledger[1:-1] and prior['duplicate'] is False,
      'Already-verified771 full ELF ledger corresponds exact772 prefix')
    new_hash=diagnostic['input_pins'][str(g.old.PRE/'input.elf')]
    require(all(new_hash not in row['ELF_candidates'].values() for row in prior['members']),'No duplicate prior ELF')
    extra=dedup([ledger[0],ledger[-1]],new_hash,base['input_pins'])
    require(extra['ledger_members']==1 and extra['duplicate'] is False,'No duplicate newly-added772 ELF')
    pins=life.merge_pins(base['input_pins'],base['output_pins'])
    pins=life.merge_pins(pins,diagnostic['input_pins']);pins=life.merge_pins(pins,diagnostic['output_pins'])
    pins=life.merge_pins(pins,extra['pins'])
    for path,h in ((g.BASE/'admission-manifest.json',g.BASE_SHA),(GAIN,GAIN_SHA),(g.QUAL,g.QUAL_SHA)):
        pins=life.merge_pins(pins,{str(path):h})
    for path in (Path(__file__).resolve(),Path(__file__).with_name('test_admit_sv39_fault773.py'),Path(g.__file__).resolve()):
        pins=life.merge_pins(pins,{str(path):life.digest(path)})
    status=dict(status='PASS_RAW_UNION_HISTORICAL_ONLY',coverage_admitted=True,aggregate_passed=773,
      baseline=772,new_passed=1,exact772_prefix=True,unique_new_vdb=True,duplicate_ELF=False,
      full_OR_instances=6162,full_scalar_vector_fault_CSR_guards_verified=True,expected_vector_page_faults=8,
      expected_supervisor_ecalls=4,raw_delta=delta['metrics'],scoped_binary_toggle_new_positions=diagnostic['scoped_binary_toggle_gain'],
      official_percentage_claimed=False,RTL_changed=False,new_simulation=False)
    return dict(products={'combined-bits.json':proposed,'single-bits.json':single,'raw-delta.json':delta,
      'elf-dedup-extension.json':extra,'status.json':status,'evidence-pins.json':pins},
      ledger='\n'.join([ledger[0],*proposed['tests']])+'\n',input_pins=pins)

def admit(output):
    require(not output.exists() and output.parent==life.OUT,'Fresh formal output')
    result=evaluate();output.mkdir()
    for name,value in result['products'].items():life.save(output/name,value)
    with (output/'combined-inputs.txt').open('x') as f:f.write(result['ledger'])
    with (output/'generic-coverage-inputs.txt').open('x') as f:f.write(result['ledger'])
    products={str(p):life.digest(p) for p in output.iterdir() if p.is_file()}
    manifest=dict(output=str(output),baseline=str(g.BASE),baseline_seal=g.BASE_SHA,qualification=str(g.QUAL),
      qualification_seal=g.QUAL_SHA,gain=str(GAIN),gain_seal=GAIN_SHA,input_pins=result['input_pins'],output_pins=products,
      coverage_admitted=True,authorization_source='PARENT_AGENT_AUTHORIZATION_WITHIN_USER_GOAL')
    life.save(output/'admission-manifest.json',manifest)
    print('FORMAL773_PASS '+life.digest(output/'admission-manifest.json'),flush=True)

if __name__=='__main__':
    a=argparse.ArgumentParser();a.add_argument('--output',type=Path,required=True)
    admit(a.parse_args().output.resolve())
