"""Single-test native qualification of three source-proven scalar DWC FSM points."""
import argparse
import csv
import json
from pathlib import Path
import re
import shutil
import types
import inventory_operand_debug as inventory

import review_scalar_dwc_write_fsm as proof
import capture_scalar_radix158 as scalar
import audit_fsm741_exact as native
from inventory_operand_debug import Design

life, require, tools = scalar.life, scalar.require, scalar.tools
HERE = Path(__file__).resolve().parent
REVIEW = life.OUT/'scalar-dwc-write-fsm-source-review762-agent-20261007-01.json'
REVIEW_SHA = '742c1dc647c1077e98704a60334e0067d488adaef531773faadd1e60bfc93348'
HOOK = HERE/'capture_scalar_dwc3.tcl'


def groups(review):
    rows = review['candidate_points'] + review['protected_points']
    require(len(rows) == 31 and len({p['raw_index'] for p in rows}) == 31, 'Incomplete protection partition')
    result = []
    for machine in dict.fromkeys(p['machine'] for p in sorted(rows, key=lambda p:p['raw_index'])):
        for kind, mode in (('state', 'State'), ('transition', 'Transition')):
            subset = sorted((p for p in rows if p['machine'] == machine and p['kind'] == kind), key=lambda p:p['raw_index'])
            names = [p['state'] if kind == 'state' else p['from_state']+'->'+p['to_state'] for p in subset]
            result.append(dict(scope=review['scope'], machine=machine, mode=mode, names=names,
                targets=[name for name,p in zip(names,subset) if p['candidate']]))
    require(sum(len(g['targets']) for g in result) == 3, 'Not exact three source points')
    return result


def expected(review, module):
    records = []
    for p in review['candidate_points']:
        state = p['kind'] == 'state'
        name = p['state'] if state else p['from_state']+'->'+p['to_state']
        signature = str(int(p['enum_value'],16)) if state else str(int(p['from_enum'],16))+'->'+str(int(p['to_enum'],16))
        records.append((module,review['scope_checksum'],p['scope'],p['machine'],p['machine_checksum'],
            native.ANNOTATION,'State' if state else 'Transition',name,signature))
    require(len(set(records)) == 3 and all(p['machine']=='w_state_d' and not p['hit'] for p in review['candidate_points']),
        'Source candidate identity differs')
    return sorted(records)


def semantics(text, c):
    actual = native.native_records(text)
    wanted = set(tuple(r) for r in c['expected'])
    require(set(actual) <= wanted, 'Extra native identity/attribute or protected point excluded')
    states = {r for r in wanted if r[6]=='State'}
    require(len(states)==1 and states <= set(actual), 'Source-proven state absent')
    # DVE may omit the two explicitly selected incident arcs because the state absorbs them.
    closure = set(actual)
    for state in states:
        closure.update(r for r in wanted if r[6]=='Transition' and state[7] in r[7].split('->'))
    require(closure == wanted, 'Native semantic closure differs')
    return actual


def prepare(out):
    require(out.parent==life.OUT and out.resolve()==out and not out.exists(), 'Fresh output required')
    r = life.read_bound(REVIEW, REVIEW_SHA)
    require(r['status']=='SCALAR_DWC_W_UPSIZE_SOURCE_CANDIDATES_R_INJECTION_PROTECTED' and
        r['candidate_states']==1 and r['candidate_transitions']==2 and r['protected_positions']==28 and
        r['source_contract']['aw_len']==0 and r['source_contract']['aw_atop_not_constant_zero'], 'Wrong source review')
    life.check(r['pins'])
    require(proof.collect()==r, 'Source induction/compiled partition changed')
    qpath=scalar.fixture.QUAL/'qualification.json'
    q=life.read_bound(qpath,scalar.QUAL_SHA)
    pins=life.merge_pins(r['pins'],life.merge_pins(q['input_pins'],q['output_pins']))
    pins=life.merge_pins(pins,{str(REVIEW):REVIEW_SHA,str(qpath):scalar.QUAL_SHA})
    design=scalar.fixture.old.BUILD/'sim/simv.vdb'
    vdb=scalar.fixture.RUN/'code.vdb'
    tests=list((vdb/'snps/coverage/db/testdata').iterdir())
    require(len(tests)==1 and tests[0].name=='scalar_divsqrt_finite', 'Single historical PASS test differs')
    selected=str(vdb.with_suffix('')/tests[0].name)
    d=Design(design)
    wanted=expected(r,d.hierarchy[r['scope']].get('chksum'))
    identity=tools.prepare(shutil.which('dve'),'/usr/bin/xvfb-run')
    dependencies=[Path(__file__).resolve(),HOOK,HERE/'test_capture_scalar_dwc3.py',Path(native.__file__).resolve(),
        Path(scalar.__file__).resolve(),Path(inventory.__file__).resolve(),
        Path(scalar.launch.__file__).resolve(),Path(tools.__file__).resolve(),
        HERE/'fsm741_transition_batch.tcl',HERE/'fsm741_native_singleton.tcl',HERE/'fsm741_native_probe.tcl',
        HERE/'discover_ptw_pmp0_fsm_v2.tcl',HERE/'apply_points740_v4.tcl']
    pins=life.merge_pins(pins,{str(p):life.digest(p) for p in dependencies})
    pins=life.merge_pins(pins,{f['path']:f['sha256'] for f in identity['files']})
    life.check(pins)
    g=groups(r)
    atom=lambda s:'{'+s+'}'
    values=dict(dwc_design=str(design),dwc_sample=str(vdb),dwc_selected=selected)
    require(all(not any(ch in value for ch in '{}\\\n\r') for value in values.values()), 'Unsafe Tcl value')
    text=''.join('set '+k+' '+atom(v)+'\n' for k,v in values.items())+'set fx_groups {}\n'
    for item in g:
        values=[item['scope'],str(life.ROOT/'hardware/deps/axi/src/axi_dw_upsizer.sv'),item['machine'],item['mode']]
        text+='lappend fx_groups [list '+' '.join(atom(v) for v in values)+' [list '+ ' '.join(atom(v) for v in item['names'])+'] [list '+' '.join(atom(v) for v in item['targets'])+']]\n'
    c=dict(pins=pins,identity=identity,expected=wanted,groups=g,selected=selected,scope=r['scope'],
        source_review_sha256=REVIEW_SHA,points=3,protected=28,population_application=False,timeout_seconds=600)
    out.mkdir()
    for name,value in (('selection.tcl',text),('capture.tcl',HOOK.read_text())):
        scalar.launch.primitive.one.common.save(out/name,value);pins[str(out/name)]=life.digest(out/name)
    life.save(out/'config.json',c)
    print(json.dumps(dict(output=str(out),seal=life.digest(out/'config.json'),pins=len(pins))),flush=True)


def verify(out,seal):
    c=life.read_bound(out/'config.json',seal);life.check(c['pins']);tools.revalidate(c['identity'])
    terminal=json.loads((out/'terminal.json').read_bytes())
    require(terminal['returncode']==0 and not terminal['timeout'] and len(terminal['actual_dve'])==1,'Native terminal failed')
    log=(out/'DVEfiles/dve_gui.log').read_text()
    require(log.splitlines().count('SCALAR_DWC3_NATIVE_DONE')==1 and
        log.splitlines().count('SCALAR_DWC3_SELECTED '+c['selected'])==1 and
        not re.search(r'Error:|Fatal:|EK-CMD-|DVTC[0-9]+|UCAPI-DLMA|DVCDT136|SCALAR_DWC3_FAILED',log),'GUI/load/selected identity error')
    first=semantics((out/'first.el').read_text(),c)
    require(first==semantics((out/'second.el').read_text(),c),'Native full identity/attribute roundtrip differs')
    for name in ('initial.el','reset.el','final-empty.el','cleanup-empty.el'):
        require((out/name).read_bytes()==b'','Not globally empty')
    with (out/'exact-audit.tsv').open() as f:rows=list(csv.reader(f,delimiter='\t'))
    keys={(stage,g['scope'],g['machine'],g['mode'],name) for stage in ('initial','applied','reset','reloaded','final')
        for g in c['groups'] for name in g['names']}
    require(len(rows)==len(keys)==155 and {tuple(r[:5]) for r in rows}==keys and
        all(len(r)==6 and r[5] in ('0','1') for r in rows),'Incomplete native protected inventory/diagnostics')
    require(all(r[5]=='0' for r in rows if r[0] in ('initial','reset','final')),'Reset query not empty')
    tables={stage:list(csv.DictReader((out/('rooted_'+stage+'.csv')).open()))
        for stage in ('raw','applied','reset','reloaded','final')}
    def metrics(stage):
        rows=tables[stage]
        require(len(rows)==1 and rows[0]['Stage']==stage and rows[0]['Scope']=='ara_tb.dut.i_ara_soc.i_system' and
            rows[0]['Name']=='i_system' and rows[0]['Token']==rows[0]['Scope'],'Rooted identity differs')
        return {m:rows[0][m] for m in native.METRICS}
    stats={s:metrics(s) for s in tables}
    require(stats['raw']==stats['reset']==stats['final'] and stats['applied']==stats['reloaded'],'Stats roundtrip/reset differs')
    require(all(stats['raw'][m]==stats['applied'][m] for m in ('Line','Toggle','Condition','Branch')),'Non-FSM metrics changed')
    result=dict(status='SCALAR_DWC3_NATIVE_SEMANTIC_ROUNDTRIP_QUALIFIED',config_seal=seal,source_review_sha256=REVIEW_SHA,
        semantic_points=3,explicit_native_records=first,protected_points=28,native_extra_records=0,
        query_is_diagnostic_not_direct_membership=True,system_single_test=stats,population_application=False,
        all_other_machines_and_descendants_protected=True,
        pins=life.merge_pins(c['pins'],{str(p):life.digest(p) for p in out.rglob('*') if p.is_file()}))
    life.check(result['pins']);life.save(out/'capture-result.json',result)
    print('QUALIFIED '+life.digest(out/'capture-result.json'),flush=True)


def run(out,seal):
    worker=types.FunctionType(scalar.launch.run.__code__,dict(scalar.launch.run.__globals__,verify=verify))
    worker(out,seal)


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('mode',choices=('prepare','run','verify'))
    p.add_argument('--output',type=Path,required=True);p.add_argument('--seal');a=p.parse_args()
    if a.mode=='prepare':prepare(a.output.absolute())
    else:
        require(a.seal,'Config seal required');(run if a.mode=='run' else verify)(a.output.absolute(),a.seal)
