"""One fail-closed continuation: exact124 qualification then combined full742."""
import argparse
import csv
import json
from pathlib import Path
import re
import subprocess
import time
import types

import capture_fsm124 as cap
import fma_datapath_native as fma

base, life, require = cap.base, cap.life, cap.require
CAPTURE = life.OUT/'fsm124-native-742-20261007-01'
CAPTURE_SEAL = '6dfa15da392b6eb053b285f574d6db7cd2d15c060c18ce33942a6bf8b0092970'
FMA = life.OUT/'fma-datapath-108-native-agent-20261007-02'
FMA_SEAL = '8d3c1c3e285b03de9b94244506b3a22436a8c59803680c981f4206b85b7dd9ee'
UNIT = 'ara-fsm124-native-742-20261007-01'
ANNOTATION = 'Approved unchanged local FMA datapath integration scope; all other signals retained'


def merge_inventories(*inventories):
    pins={}
    for inventory in inventories:
        pins=life.merge_pins(pins,inventory)
    return pins


def records(text, fma_config):
    fsm_blocks, toggle_blocks, observer_blocks = [], [], []
    for block in re.split(r'(?m)(?=^CHECKSUM:)', text):
        if not block: continue
        families = [name for name in ('Fsm ', 'Toggle ') if any(l.startswith(name) for l in block.splitlines())]
        require(len(families)<=1, 'Mixed native families')
        if families == ['Fsm ']: fsm_blocks.append(block)
        elif families == ['Toggle ']:
            require(re.findall(r'(?m)^ANNOTATION: "([^"\r\n]*)"$',block)==[ANNOTATION], 'FMA annotation differs')
            toggle_blocks.append(block)
        else: observer_blocks.append(block)
    fsm, empty = base.combined_records(''.join(fsm_blocks))
    require(not empty, 'Foreign FSM scope directive')
    no_fsm, observers = base.combined_records(''.join(observer_blocks))
    require(not no_fsm, 'Foreign observer directive')
    return fsm, observers, fma.parse_el(''.join(toggle_blocks),fma_config)


def prepare(out):
    require(not out.exists() and out.parent==life.OUT, 'Fresh output required')
    c=life.read_bound(CAPTURE/'config.json',CAPTURE_SEAL)
    q=json.loads((CAPTURE/'qualification.json').read_bytes())
    require(q['status']=='EXACT124_NATIVE_SAVE_RELOAD_RESET_QUALIFIED' and
            q['config_seal']==CAPTURE_SEAL and q['targets']==124 and q['population']==742, '124 not qualified')
    life.check(q['input_pins']); life.check(q['output_pins'])
    fq=life.read_bound(FMA/'capture-result.json',FMA_SEAL)
    require(fq['status']=='EXACT_108_FMA_TOGGLE_OBJECTS_NATIVE_ROUNDTRIP_PASS' and fq['objects']==108 and
            fq['semantic_reload'] and fq['reset_global_empty'] and fq['non_target_exclusions']==0, 'FMA not qualified')
    life.check(fq['pins'])
    fc=life.read_bound(FMA/'config.json',fq['config_seal'])
    require(fma.parse_el((FMA/'first.el').read_text(),fc)==fma.parse_el((FMA/'second.el').read_text(),fc), 'FMA reload differs')
    oq=life.read_bound(base.OBS/'qualification.json',base.OBS_QUAL_SHA)
    oc=life.read_bound(base.OBS/'config.json',base.OBS_SHA)
    require(oq['status']=='QUALIFIED_EFFECTIVE_FOUR_OBSERVER_741_INTEGRATION_SCOPE', 'Observers not qualified')
    life.check(oc['pins'])
    pins=merge_inventories(c['pins'],q['output_pins'],fq['pins'],oc['pins'],
        {str(CAPTURE/'config.json'):CAPTURE_SEAL,str(CAPTURE/'qualification.json'):life.digest(CAPTURE/'qualification.json'),
         str(FMA/'capture-result.json'):FMA_SEAL,str(FMA/'config.json'):fq['config_seal'],
         str(base.OBS/'qualification.json'):base.OBS_QUAL_SHA,str(base.OBS/'config.json'):base.OBS_SHA,
         str(base.OBS/'observers.el'):base.OBS_EL_SHA})
    wanted_observers={s:v[1] for s,v in base.observer.TARGETS.items()}
    expected=([tuple(r) for r in c['native_fsm']],wanted_observers,fma.parse_el((FMA/'first.el').read_text(),fc))
    combined=(CAPTURE/'applied.el').read_text()+(base.OBS/'observers.el').read_text()+(FMA/'first.el').read_text()
    require(records(combined,fc)==expected, 'Combined native identity differs')
    for p in (Path(__file__).resolve(),base.HERE/'test_chain_fsm_fma742.py',Path(cap.__file__).resolve(),Path(fma.__file__).resolve()):
        pins=life.merge_pins(pins,{str(p):life.digest(p)})
    life.check(pins)
    out.mkdir()
    for name in ('inputs.txt','selection.tcl'):
        with (out/name).open('x') as stream: stream.write((CAPTURE/name).read_text())
    with (out/'combined.el').open('x') as stream: stream.write(combined)
    for name in ('inputs.txt','selection.tcl','combined.el'): pins[str(out/name)]=life.digest(out/name)
    c.update(schema='FULL742_EXACT124_FSM_FOUR_OBSERVER_FMA108',output=str(out),pins=pins,
             observers=wanted_observers,fma_config=fc,fma_capture_seal=FMA_SEAL,
             fsm_qualification_seal=life.digest(CAPTURE/'qualification.json'))
    life.save(out/'config.json',c)
    seal=life.digest(out/'config.json')
    print('FULL742_PREPARED seal='+seal,flush=True)
    return seal


def verify(out,seal):
    c=life.read_bound(out/'config.json',seal);life.check(c['pins'])
    require((out/'inputs.txt').read_text().splitlines()==c['input_ledger'] and
            (out/'selected_tests.txt').read_text().splitlines()==c['expected_selected'], '742 identity differs')
    expected=([tuple(r) for r in c['native_fsm']],c['observers'],
              fma.parse_el((FMA/'first.el').read_text(),c['fma_config']))
    for name in ('applied.el','reloaded.el'):
        require(records((out/name).read_text(),c['fma_config'])==expected,'Native save/reload differs')
    for name in ('initial-empty.el','reset-empty.el','final-empty.el','cleanup-empty.el'):
        require((out/name).read_bytes()==b'','Reset not empty')
    base.native.audit_points(list(csv.reader((out/'exact-audit.tsv').open(),delimiter='\t')),c['plan'])
    reports={}
    for stage in ('raw','applied','reset','reloaded','final'):
        rows=list(csv.DictReader((out/('rooted_'+stage+'.csv')).open()))
        require(len(rows)==1 and rows[0]['Scope']==rows[0]['Token']==base.observer.SYSTEM and
                rows[0]['Name']==rows[0]['GUIPath']=='i_system' and rows[0]['Stage']==stage,'Root differs')
        reports[stage]={m:rows[0][m] for m in base.native.METRICS}
    require(reports['raw']==reports['reset']==reports['final'] and reports['applied']==reports['reloaded'],'Reset/reload metrics differ')
    gui=(out/'DVEfiles/dve_gui.log').read_text()
    require(gui.splitlines().count('EXACT742_FSM_OBSERVERS_DONE')==1 and gui.splitlines().count('DVE_COVERAGE_EXPORT_DONE')==1 and
            not re.search(r'EXPORT_FAILED|EXACT742_FAILED|Error:|Fatal:|EK-CMD-|DVTC[0-9]+|UCAPI-DLMA|DVCDT136',gui),'GUI error')
    require(gui.splitlines().count('DVE_SELECTED_TESTS: '+' '.join(c['expected_selected']))==1,'GUI population differs')
    life.check(c['pins'])
    life.save(out/'qualification.json',dict(status='FULL742_EXACT124_FSM_FOUR_OBSERVER_FMA108_REPORT_VERIFIED',
        config_seal=seal, population=742, fsm_transitions=124, fma_toggle_objects=108, observers=c['observers'],
        system=reports,input_pins=c['pins'],output_pins={str(p):life.digest(p) for p in out.iterdir() if p.is_file()}))
    print(json.dumps(reports),flush=True)


def chain(out):
    # Only this named predecessor; no retry or unrelated process polling.
    deadline=time.monotonic()+1000
    while True:
        result=subprocess.run(['systemctl','--user','show',UNIT,'--property=ActiveState','--property=ExecMainStatus'],
                              check=True,stdout=subprocess.PIPE,text=True)
        state=dict(line.split('=',1) for line in result.stdout.splitlines())
        if state['ActiveState'] not in ('active','activating','deactivating'):
            require(state['ActiveState']=='inactive' and state['ExecMainStatus']=='0','Predecessor failed; no continuation')
            break
        require(time.monotonic()<deadline,'Predecessor timeout; no continuation')
        time.sleep(20)
    seal=prepare(out)
    namespace=dict(base.run.__globals__,verify=verify)
    types.FunctionType(base.run.__code__,namespace)(out,seal)


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--output',type=Path,required=True)
    a=p.parse_args()
    try: chain(a.output.absolute())
    except Exception as exc:
        failure=a.output.absolute().with_suffix('.chain-failure.json')
        life.save(failure,dict(reason=str(exc),no_retry=True))
        raise
