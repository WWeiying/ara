"""Local CSR partial-bit qualification: exact native EL authority, not per-bit GUI flags."""
import argparse
import csv
import json
import math
from pathlib import Path
from types import FunctionType

import capture_csr_reserved1193 as original

life,require,tools=original.life,original.require,original.tools
HERE=Path(__file__).resolve().parent
HOOK=HERE/'capture_csr_reserved1193_v2.tcl'
ROOTED=HERE/'apply_points740_v4.tcl'
ORIGIN=life.OUT/'csr-reserved1193-native-agent-20261007-01'
ORIGIN_SHA='bb4624d77946b3edee17fed9dfaf2b2411c69c8169a72843f31ef84345c05f36'
STAGES=original.STAGES
EL_FILES=dict(before='initial-empty.el',selected='first.el',reset='reset-empty.el',
              reloaded='second.el',final='final-empty.el')
AUTHORITY='Exact native EL identities for both directions; GUI object flags aggregate only; no per-bit GUI flag claim.'


def contract(c):
    original.contract(c)
    require(c['membership_authority']==AUTHORITY and c['origin_config_sha']==ORIGIN_SHA and
            c['protected_objects']==2031 and c['protected_target_bits']==111 and
            c['per_bit_GUI_flags_read'] is False,'Exact reviewed02 authority/boundary')
    require(len(c['nodes'])-len(c['targets'])==2031 and
            sum(len(t['retained_source_bits']) for t in c['targets'])==111,'Complete typed complements')


def inventory(out,c,stage):
    require(stage in STAGES,'Exact five stages')
    byalias={alias:n for n in c['nodes'] for alias in original.base.aliases(n)}
    targets={t['signal'] for t in c['targets']}
    with (out/('objects-'+stage+'.tsv')).open(newline='') as stream:
        rows=list(csv.reader(stream,delimiter='\t'))
    require(rows and rows[0]==['path','meta','name','excluded'] and len(rows)==2078,'Complete2077 object inventory')
    found={}
    for row in rows[1:]:
        require(len(row)==4,'Strict native attributes')
        path,meta,name,flag=row
        require(name in byalias and path==meta==name and flag in ('0','1'),'Exact typed native identity/aggregate flag')
        node=byalias[name];key=node['name']
        require(key not in found,'Duplicate/alias compiled object')
        if stage in ('before','reset','final') or key not in targets:
            require(flag=='0','Protected object/array/port or reset excluded')
        found[key]=(path,meta,name)
    require(set(found)=={n['name'] for n in c['nodes']},'Missing typed object complement')
    return sorted(found.items())


def el(out,c,stage):
    text=(out/EL_FILES[stage]).read_text()
    if stage in ('before','reset','final'):
        require(text=='','All-scope reset EL must be empty');return []
    actual=records(text,c)
    complement={(t['signal'],b,d) for t in c['targets'] for b in t['retained_source_bits'] for d in ('0to1','1to0')}
    require(len(complement)==222 and not set(actual)&complement,'All111 retained bits have zero membership intersection')
    return actual


def records(text,c):
    lines=[line.strip() for line in text.splitlines()]
    require(sum(line.startswith('CHECKSUM:') for line in lines)==1 and
            sum(line.startswith('INSTANCE:') for line in lines)==1,'Exactly one complete native scope/checksum block')
    return original.records(text,c)


def metrics(out,c,stage):
    with (out/('rooted_'+stage+'.csv')).open(newline='') as stream:
        rows=list(csv.DictReader(stream))
    require(len(rows)==1 and set(rows[0])=={'Stage','Scope','Token','Handle','GUIPath','Name',
                'Score','Line','Toggle','FSM','Condition','Branch'},'Exactly one rooted native scope row')
    row=rows[0]
    require(row['Stage']==stage and row['Scope']==row['Token']==c['scope'] and
            row['GUIPath']==row['Name']=='csr_regfile_i' and row['Handle'].isdigit(),'Exact selected/rooted CSR identity')
    result={m:row[m] for m in ('Score','Line','Toggle','FSM','Condition','Branch')}
    for metric,value in result.items():
        if value=='NA':require(metric not in ('Toggle','Score'),'Available native Toggle/Score required');continue
        try:number=float(value)
        except ValueError:raise ValueError('Native metric encoding') from None
        require(math.isfinite(number) and 0<=number<=100,'Native metric range')
    return result


def compare_metrics(values):
    require(set(values)==set(STAGES),'Five actual native metric stages')
    raw=values['before'];applied=values['selected']
    require(raw==values['reset']==values['final'],'Exact native raw/reset/final restoration')
    require(applied==values['reloaded'],'Exact native applied/reloaded effect')
    require(all(raw[m]==applied[m] for m in ('Line','FSM','Condition','Branch')),'Only Toggle denominator may change')
    require(float(applied['Toggle'])>float(raw['Toggle']),'No measured native application effect')


def verify(out,seal):
    c=life.read_bound(out/'config.json',seal);contract(c);life.check(c['pins']);tools.revalidate(c['identity'])
    terminal=json.loads((out/'terminal.json').read_bytes())
    require(terminal['returncode']==0 and not terminal['timeout'] and len(terminal['actual_dve'])==1,'Actual tool/terminal')
    gui=(out/'DVEfiles/dve_gui.log').read_text()
    require(gui.splitlines().count('CSR1193_V2_NATIVE_DONE')==1 and not (out/'error.txt').exists(),
            'Complete local five-stage session')
    baseline=inventory(out,c,'before');values={}
    for stage in STAGES:
        require(inventory(out,c,stage)==baseline,'Typed target/complement identity drift')
        el(out,c,stage);values[stage]=metrics(out,c,stage)
    require(el(out,c,'selected')==el(out,c,'reloaded'),'Exact native1193 both-direction semantic reload')
    compare_metrics(values)
    output_pins={str(p):life.digest(p) for p in out.rglob('*') if p.is_file() and p.name!='capture-result.json'}
    result=dict(status='EXACT_CSR46_PARTIAL1193_LOCAL_NATIVE_EL_AUTHORITY_QUALIFIED',config_seal=seal,
        target_objects=46,target_source_bits=1193,directions=2386,protected_target_bits=111,
        protected_objects=2031,all_arrays_and_ports_included=True,metrics=values,
        membership_authority=AUTHORITY,per_bit_GUI_flags_read=False,global_empty_resets=True,
        valid_reset_settled_only=True,startup_X_excluded=False,boundary=original.BOUNDARY,
        population_application=False,official_percentage=None,pins=life.merge_pins(c['pins'],output_pins))
    path=out/'capture-result.json'
    if path.exists():require(json.loads(path.read_bytes())==result,'Existing local qualification differs')
    else:life.save(path,result)
    print(json.dumps(dict(status=result['status'],seal=life.digest(path),local_toggle_raw=values['before']['Toggle'],
                          local_toggle_applied=values['selected']['Toggle'])),flush=True)


def prepare(out):
    require(out.parent==life.OUT and not out.exists(),'Independent fresh02 output')
    c=life.read_bound(ORIGIN/'config.json',ORIGIN_SHA);original.contract(c);life.check(c['pins'])
    require((ORIGIN/'cleanup-empty.el').read_bytes()==b'' and (ORIGIN/'error.txt').is_file() and
            not (ORIGIN/'first.el').exists(),'Preserved01 before failure and empty cleanup')
    tools.revalidate(c['identity'])
    pins=life.merge_pins(c['pins'],{str(ORIGIN/'config.json'):ORIGIN_SHA})
    for p in (Path(__file__).resolve(),HOOK,ROOTED,HERE/'test_capture_csr_reserved1193_v2.py',
              ORIGIN/'error.txt',ORIGIN/'cleanup-empty.el'):
        pins=life.merge_pins(pins,{str(p):life.digest(p)})
    c=dict(c,pins=pins,output=str(out),origin_config_sha=ORIGIN_SHA,membership_authority=AUTHORITY,
           protected_objects=2031,protected_target_bits=111,per_bit_GUI_flags_read=False)
    contract(c)
    candidate=original.candidate(c);records(candidate,c)
    selection=(ORIGIN/'selection.tcl').read_text()
    selection+='set ::csr2_helper {%s}\n'%str(Path(__file__).resolve())
    selection+='set ::p740_scopes [list $::csr_scope]\nset ::p740_root_names($::csr_scope) {csr_regfile_i}\n'
    out.mkdir()
    for name,text in [('selection.tcl',selection),('candidate.el',candidate)]:
        with (out/name).open('x') as stream:stream.write(text)
        pins[str(out/name)]=life.digest(out/name)
    # Original source induction and all writer/config evidence retained verbatim.
    with (out/'writer-proof.json').open('xb') as stream:stream.write((ORIGIN/'writer-proof.json').read_bytes())
    pins[str(out/'writer-proof.json')]=life.digest(out/'writer-proof.json')
    life.check(pins);life.save(out/'config.json',c)
    print(json.dumps(dict(output=str(out),seal=life.digest(out/'config.json'),pins=len(pins))),flush=True)


class Route:
    def __truediv__(self,name):
        require(name=='capture_cast168_native.tcl','Fixed02 capture entry');return HOOK


def run(out,seal):
    FunctionType(original.base.runner.run.__code__,dict(vars(original.base.runner),
        contract=contract,inspect=verify,HERE=Route()))(out,seal)


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('mode',choices=('prepare','run','verify','inventory','el'))
    p.add_argument('--output',type=Path,required=True);p.add_argument('--seal');p.add_argument('--stage',choices=STAGES)
    a=p.parse_args();out=a.output.absolute()
    if a.mode=='prepare':prepare(out)
    elif a.mode in ('inventory','el'):
        c=json.loads((out/'config.json').read_bytes());life.check(c['pins']);require(a.stage,'Exact stage')
        print(len((inventory if a.mode=='inventory' else el)(out,c,a.stage)))
    else:require(a.seal,'Config seal');(run if a.mode=='run' else verify)(out,a.seal)
