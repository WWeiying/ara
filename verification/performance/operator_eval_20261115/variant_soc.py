#!/usr/bin/env python3
"""Same-source structural controls for cooperation, queueing and shared FMA."""
import argparse
import hashlib
import json
import os
from pathlib import Path
import re
import shutil
import subprocess
import time

OUT=Path('/home/wangwy/openproject/ara_dsa_signoff_integration/verification/out')
BASE=OUT/'operator_soc_20261115_activity_02'
QUEUE='ara_tb.dut.i_ara_soc.i_system.i_ara.i_vlsu.i_qbs_engine.i_compute_engine.IntegerResultQueueDepth'
VARIANTS=('loan_off','queue_zero','shared_fma_off')


def sha(p):
    h=hashlib.sha256()
    with Path(p).open('rb') as f:
        for b in iter(lambda:f.read(1048576),b''):
            h.update(b)
    return h.hexdigest()


def save(p,v):
    tmp=p.with_suffix('.tmp');tmp.write_text(json.dumps(v,indent=2)+'\n');tmp.replace(p)


def verify(pins):
    for p,h in pins.items():
        if sha(p)!=h:
            raise ValueError('Input drift: '+p)


def prepare(out,kind):
    baseline=json.loads((BASE/'build.json').read_text())
    if baseline['state']!='CURRENT_OPERATOR_SOC_BUILT_NOT_EXECUTED' or not baseline['post_pins_match']:
        raise ValueError('No reviewed parent image')
    original=json.loads((BASE/'source-pins.json').read_text());verify(original)
    out.mkdir()
    for name in ('source','inputs'):
        shutil.copytree(BASE/name,out/name)
    (out/'sim').mkdir()
    for name in ('elfloader.o','gate-receipt.json','production-source.tar'):
        shutil.copyfile(BASE/name,out/name)
    text=(BASE/'sources.f').read_text().replace(str(BASE),str(out))
    before=text
    config=dict(baseline['configuration'],control_variant=kind)
    if kind=='loan_off':
        line='+define+ARA_QBS_LANE_MUL_ENABLE=1\n'
        if text.count(line)!=1:
            raise ValueError('Loan define missing/ambiguous')
        text=text.replace(line,'');config['qbs_lane_multiplier']=0
    elif kind=='shared_fma_off':
        line='+define+ARA_SHARED_FMA=1\n'
        if text.count(line)!=1:
            raise ValueError('FMA define missing/ambiguous')
        text=text.replace(line,'');config['shared_fma']=0
    elif kind!='queue_zero':
        raise ValueError('Unknown control')
    (out/'sources.f').write_text(text)
    plan=json.loads((BASE/'plan.json').read_text())
    command=[arg.replace(str(BASE),str(out)) for arg in plan['command']]
    if kind=='queue_zero':
        command.append('-pvalue+'+QUEUE+'=0')
    config['integer_result_queue_depth']=0 if kind in ('loan_off','queue_zero') else 16
    (out/'sim/simulator.conf').write_text(''.join(f'{k}={v}\n' for k,v in config.items()))
    # The passive probe proves that VCS actually selected each internal setting.
    probe=out/'inputs/variant_probe.sv'
    coop=int(kind!='loan_off');depth=config['integer_result_queue_depth']
    probe.write_text('module operator_variant_probe #(parameter bit Coop=0, parameter int Depth=0) ();\n'
        'initial begin\n'
        f'  assert (Coop=={coop} && Depth=={depth}) else $fatal(1,"Wrong structural control");\n'
        '  $display("OPERATOR_VARIANT %m coop=%0d depth=%0d",Coop,Depth);\n'
        'end\nendmodule\n'
        'bind qbs_compute_engine operator_variant_probe #(.Coop(CooperativeWaves), '
        '.Depth(IntegerResultQueueDepth)) i_operator_variant_probe();\n')
    command.append(str(probe))
    production=[]
    for name,h in original.items():
        p=Path(name)
        if p.is_relative_to(BASE/'source'):
            counterpart=out/p.relative_to(BASE)
            if sha(counterpart)!=h:
                raise ValueError('Structural control changed production bytes')
            production.append(str(counterpart.relative_to(out)))
    plan.update(command=command,configuration=config,structural_control=kind,
                same_source_as=str(BASE),same_production_files=len(production),
                single_switch_or_parameter=True)
    save(out/'plan.json',plan)
    pins={str(p):sha(p) for n in ('source','inputs') for p in (out/n).rglob('*') if p.is_file()}
    for n in ('elfloader.o','gate-receipt.json','production-source.tar','sources.f','plan.json','sim/simulator.conf'):
        pins[str(out/n)]=sha(out/n)
    save(out/'source-pins.json',pins)
    return plan,pins


def compile_variant(out,kind):
    plan,pins=prepare(out,kind)
    report=dict(state='FAIL',configuration=plan['configuration'],revision=plan['revision'],
                same_source_as=str(BASE),structural_control=kind,whole_model=False)
    try:
        with (out/'compile.log').open('x') as f:
            proc=subprocess.Popen(plan['command'],cwd=out/'sim',env=plan['environment'],stdout=f,stderr=subprocess.STDOUT)
            save(out/'status.json',dict(state='VCS_COMPILING',child_pid=proc.pid))
            try:
                rc=proc.wait(timeout=7200)
            except BaseException:
                proc.terminate();proc.wait(timeout=20);raise
        if rc or re.search(r'(?m)^\s*(?:Error-|Fatal-|Error:|Fatal:)',(out/'compile.log').read_text(errors='replace')):
            raise ValueError('Variant compile failed')
        verify(pins)
        images={str(p):sha(p) for p in (out/'sim/simv.daidir').rglob('*') if p.is_file()}
        images[str(out/'sim/simv')]=sha(out/'sim/simv')
        report.update(state='CURRENT_OPERATOR_SOC_BUILT_NOT_EXECUTED',post_pins_match=True,
                      image_pins=images,simv=str(out/'sim/simv'))
        save(out/'image-pins.json',images)
    except Exception as exc:
        report['error']=repr(exc)
    save(out/'build.json',report);save(out/'status.json',dict(state=report['state'],child_pid=None))
    if report['state']=='FAIL':
        raise ValueError(report['error'])


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--output',type=Path,required=True)
    a=p.parse_args();out=a.output.resolve()
    if out.parent!=OUT or not out.name.startswith('operator_variants_20261115_'):
        raise ValueError('Wrong output scope')
    out.mkdir();report=dict(state='FAIL',completed=[])
    save(out/'source-pins.json',{str(Path(__file__).resolve()):sha(__file__)})
    try:
        for kind in VARIANTS:
            compile_variant(out/kind,kind);report['completed'].append(kind)
            save(out/'status.json',dict(state='COMPILING_CONTROLS',completed=report['completed']))
        report['state']='STRUCTURAL_CONTROLS_BUILT_NOT_EXECUTED'
    except Exception as exc:
        report['error']=repr(exc)
    save(out/'result.json',report);save(out/'status.json',report)
    print(json.dumps(report),flush=True)
    return report['state']=='FAIL'


if __name__=='__main__':
    raise SystemExit(main())
