"""Bounded independent763 native Show Ratio diagnostic; never infer bit counts."""
import argparse
import csv
from decimal import Decimal
import json
import os
from pathlib import Path
import re
import signal
import subprocess
import time

import report_native_batch763 as report
import dve_tool_identity as tools

life,require,merge=report.life,report.require,report.merge
HERE=Path(__file__).resolve().parent
TCL=Path(__file__).with_suffix('.tcl')
BASE=life.OUT/'native-batch-full763-agent-20261007-01'
BASE_SHA='150ac4a03e2692367900551e054246fb0a7591d6c22d44e85bb3d72645668ce7'
OUT=life.OUT/'native-toggle-ratio763-agent-20261007-01'
MAJOR={'i_system','i_ara','i_ariane','i_vlsu','i_qbs_engine','i_akv_engine',
       'i_compute_engine','i_fp_accumulator','i_sequencer','i_dispatcher','i_vmfpu','i_valu'}
STAGES=('raw','applied','reset')


def parse_ratio(text,percent):
    m=re.fullmatch(r'\s*([0-9]+(?:,[0-9]{3})*)\s*/\s*([0-9]+(?:,[0-9]{3})*)\s*',text)
    require(m is not None,'Native Toggle field is not an explicit numerator/denominator ratio: '+repr(text))
    hit,total=(int(v.replace(',','')) for v in m.groups())
    require(0<=hit<=total and total>0,'Invalid native ratio counts')
    require(re.fullmatch(r'[0-9]+(?:\.[0-9]+)?%',percent) is not None,'Missing percentage counterpart')
    require(abs(Decimal(hit)*100/Decimal(total)-Decimal(percent[:-1]))<=Decimal('0.0051'),
            'Native counts do not reproduce displayed official percentage')
    return dict(native_numerator=hit,native_denominator=total,uncovered=total-hit,
                native_raw_text=text,displayed_percentage=percent)


def prepare():
    require(not OUT.exists(),'Fresh independent diagnostic only')
    q=life.read_bound(BASE/'qualification.json',BASE_SHA)
    require(q['status']=='SEALED_POPULATION_CANONICAL_NATIVE_UNION_REPORT_VERIFIED' and q['population']==763,
            'Actual qualified763 required')
    c=life.read_bound(BASE/'config.json',q['config_seal'])
    report.check(BASE,q['config_seal'])
    pins=merge(c['pins'],q['output_pins'],{str(BASE/'qualification.json'):BASE_SHA,str(BASE/'config.json'):q['config_seal']})
    roots=[r for r in c['hierarchy_roots'] if r['name'] in MAJOR]
    require(len(roots)>=13 and len({r['scope'] for r in roots})==len(roots),'Major bound roots missing/ambiguous')
    require(all(all(r['scope'] in q['module_reports'][stage] for r in roots) for stage in STAGES),
            'Major root absent from actual sealed report')
    for path in [Path(__file__).resolve(),TCL,HERE/'test_diagnose_native_toggle_ratios763.py',
                 HERE/'native_toggle_ratio_hook.tcl',HERE/'apply_points740_v4.tcl',Path(tools.__file__).resolve()]:
        pins[str(path)]=life.digest(path)
    life.check(pins);tools.revalidate(c['tool_identity'])
    atom=report.old.frozen.prior.old.base.capture.tcl_atom
    ledger=c['input_ledger']
    dirs=[db for db in ledger if list((Path(db)/'snps/coverage/db/testdata').glob('*'))]
    selected=[str(Path(db).with_suffix('')/test.name) for db in dirs
              for test in sorted((Path(db)/'snps/coverage/db/testdata').glob('*')) if test.is_dir()]
    require(selected==c['expected_selected'] and len(selected)==763,'Exact actual763 selection differs')
    lines=['set ratio_design '+atom(ledger[0])+'\n',
           'set ratio_testdirs [list '+' '.join(map(atom,dirs))+']\n',
           'set ratio_tests [list '+' '.join(map(atom,selected))+']\n',
           'set p740_scopes {}\nset ::native_ratio_roots {}\n']
    for root in roots:
        scope,name=root['scope'],root['name']
        lines+=['lappend p740_scopes '+atom(scope)+'\n',
                'set '+atom('p740_root_names('+scope+')')+' '+atom(name)+'\n',
                'lappend ::native_ratio_roots [list '+atom(scope)+' '+atom(name)+']\n']
    OUT.mkdir()
    for name,text in [('selection.tcl',''.join(lines)),('combined.el',(BASE/'combined.el').read_text())]:
        with (OUT/name).open('x') as stream:stream.write(text)
        pins[str(OUT/name)]=life.digest(OUT/name)
    report.old.generated.evaluate(OUT/'selection.tcl',{str(OUT/'selection.tcl'):pins[str(OUT/'selection.tcl')]},
                                 ('ratio_design','ratio_testdirs','ratio_tests','p740_scopes','native_ratio_roots'))
    life.save(OUT/'config.json',dict(schema='QUALIFIED763_NATIVE_RATIO_DIAGNOSTIC_V1',output=str(OUT),
        predecessor=str(BASE),predecessor_qualification_seal=BASE_SHA,predecessor_config=c,
        roots=roots,expected_selected=selected,expected_percentages=q['module_reports'],pins=pins,
        tool_identity=c['tool_identity'],budget_seconds=300,population=763,no_new_exclusions=True,
        does_not_modify765=True,automatic_retry=False))
    print(json.dumps(dict(status='PREPARED_NO_EDA',output=str(OUT),seal=life.digest(OUT/'config.json'),roots=len(roots))),flush=True)


def verify(seal):
    c=life.read_bound(OUT/'config.json',seal);life.check(c['pins'])
    require(not (OUT/'error.txt').exists(),'Native ratio session failed')
    for name in ('initial-empty.el','reset-empty.el','cleanup-empty.el'):
        require((OUT/name).read_bytes()==b'','Nonempty reset')
    require(report.records((OUT/'applied.el').read_text(),c['predecessor_config'])==
            c['predecessor_config']['expected_union'],'Exact qualified763 EL changed')
    result={}
    for stage in STAGES:
        percent=list(csv.DictReader((OUT/('percentages_'+stage+'.csv')).open()))
        require([(r['Scope'],r['Name']) for r in percent]==[(r['scope'],r['name']) for r in c['roots']],
                'Percentage roots differ')
        for row in percent:
            require(row['Stage']==stage and row['Token']==row['Scope'] and row['GUIPath']==row['Name'] and
                    all(row[m]==c['expected_percentages'][stage][row['Scope']][m] for m in report.old.frozen.prior.old.base.native.METRICS),
                    '763 percentage or identity differs')
        rows=list(csv.DictReader((OUT/('ratios_'+stage+'.csv')).open()))
        wanted=[(r['scope'],r['name'],m) for r in c['roots'] for m in ('Score','Line','Toggle','FSM','Condition','Branch')]
        require([(r['Scope'],r['Name'],r['Metric']) for r in rows]==wanted,'Ratio full column/root set differs')
        require(all(r['Stage']==stage and r['Scope']==r['Token'] and r['GUIPath']==r['Name'] and
                    r['Handle'] not in ('','0') and 5<=int(r['Column'])<32 for r in rows),'Ratio identities differ')
        result[stage]={r['Scope']:parse_ratio(r['NativeRawText'],c['expected_percentages'][stage][r['Scope']]['Toggle'])
                       for r in rows if r['Metric']=='Toggle'}
    require(result['raw']==result['reset'],'Native raw/reset count mismatch')
    gui=(OUT/'DVEfiles/dve_gui.log').read_text()
    require(gui.splitlines().count('RATIO763_RAW_APPLIED_RESET_DONE')==1 and
            not re.search(r'RATIO763_FAILED|Error:|Fatal:|EK-CMD-',gui),'Native ratio GUI failure')
    life.check(c['pins'])
    life.save(OUT/'result.json',dict(status='ACTUAL763_NATIVE_TOGGLE_DISPLAY_RATIO_COUNTS_VERIFIED',
        population=763,predecessor_qualification_seal=BASE_SHA,config_seal=seal,counts=result,
        exact_qualified_EL=True,raw_reset_parity=True,percentage_correspondence=True,
        no_serialized_bit_inference=True,not765_counts=True,no_coverage_application_approval=True,
        input_pins=c['pins'],output_pins={str(p):life.digest(p) for p in OUT.rglob('*')
                                       if p.is_file() and p.name not in ('result.json','service.log')}))
    print(json.dumps(dict(status='NATIVE_RATIO_COUNTS_VERIFIED',seal=life.digest(OUT/'result.json'),counts=result)),flush=True)


def run(seal):
    c=life.read_bound(OUT/'config.json',seal);life.check(c['pins']);tools.revalidate(c['tool_identity'])
    require(c['output']==str(OUT) and c['budget_seconds']==300,'Diagnostic identity differs')
    command=tools.launch_command(c['tool_identity'],TCL)
    life.save(OUT/'execution.json',dict(command=command,cwd=str(OUT),budget_seconds=300,automatic_retry=False))
    env=tools.controlled_environment(c['tool_identity'],os.environ);env['DVE_COVERAGE_OUTPUT']=str(OUT)
    env.pop('DVE_REVIEWED_WAIVERS',None)
    with (OUT/'launcher.log').open('x') as log:
        p=subprocess.Popen(command,cwd=OUT,env=env,stdout=log,stderr=subprocess.STDOUT,start_new_session=True)
        time.sleep(10);live=[]
        for proc in Path('/proc').iterdir():
            if not proc.name.isdigit():continue
            try:
                if (proc/'exe').resolve(strict=True)==Path(c['tool_identity']['executable']) and (proc/'cwd').resolve(strict=True)==OUT:
                    live.append(dict(pid=int(proc.name),exe=str((proc/'exe').resolve()),cwd=str(OUT)))
            except (OSError,ValueError):pass
        life.save(OUT/'live-identity.json',live);print(json.dumps(dict(actual_dve=live)),flush=True)
        timeout=False
        try:code=p.wait(timeout=300)
        except subprocess.TimeoutExpired:
            timeout=True;os.killpg(p.pid,signal.SIGTERM)
            try:p.wait(timeout=10)
            except subprocess.TimeoutExpired:os.killpg(p.pid,signal.SIGKILL);p.wait()
            code=p.returncode
    life.save(OUT/'terminal.json',dict(returncode=code,timeout=timeout,actual_dve_confirmed=len(live)==1))
    try:
        require(code==0 and not timeout and len(live)==1,'Native ratio lifecycle failed')
        verify(seal)
    except Exception as error:
        life.save(OUT/'failure.json',dict(status='NATIVE_RATIO_DIAGNOSTIC_HOLD',error=str(error),
            config_seal=seal,returncode=code,timeout=timeout,counts_inferred=False,no_retry=True))
        print(json.dumps(dict(status='NATIVE_RATIO_DIAGNOSTIC_HOLD',error=str(error))),flush=True)


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('mode',choices=('prepare','run','verify'))
    p.add_argument('--seal');a=p.parse_args()
    if a.mode=='prepare':prepare()
    else:require(a.seal,'Sealed config required');(run if a.mode=='run' else verify)(a.seal)
