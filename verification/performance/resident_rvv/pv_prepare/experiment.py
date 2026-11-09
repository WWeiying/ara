#!/usr/bin/env python3
"""Real-call preparation diagnostic on the unchanged, frozen SoC image."""
import argparse
import importlib.util
import json
from pathlib import Path
import re
import signal
import sys

sys.dont_write_bytecode = True
HERE=Path(__file__).resolve().parent


def load(path, name):
    spec=importlib.util.spec_from_file_location(name,path)
    module=importlib.util.module_from_spec(spec)
    sys.modules[name]=module
    spec.loader.exec_module(module)
    return module


rotation=load(HERE.parent/'rotation/experiment.py','prepare_rotation')
reference=load(HERE.parent/'ordered_reference.py','prepare_reference')
contract=rotation.contract
require=contract.require
old_recipes=rotation.recipes
old_baseline=rotation.baseline
rotation.HERE=HERE
rotation.SCHEMA='resident-pv-real-preparation-cost-v1'
rotation.OWN=('experiment.py','main.c','pv_rotation.S','prepare.S',
              'test_prepare.py','test_experiment.py','HELPER.md','README.md')


def baseline():
    meta,pins=old_baseline()
    extra=reference.OrderedReference().identity()
    for path in (HERE.parent/'rotation/experiment.py',HERE.parent/'rotation/main.c',
                 HERE.parent/'rotation/pv_rotation.S'):
        extra[str(path)]=contract.sha(path)
    for path,digest in extra.items():
        require(path not in pins or pins[path]==digest,'Preparation helper pin conflict')
        pins[path]=digest
    contract.verify(pins)
    return meta,pins


rotation.baseline=baseline


def recipes(output):
    commands=old_recipes(output)
    assembly=next(c for c in commands if c['label']=='compile-rotation')['argv']
    extra=[]
    for label,source,obj,flags in (
        ('compile-prepare',HERE/'prepare.S','prepare',[]),
        ('compile-strong-control',HERE.parent/'rotation/pv_rotation.S','strong_control',[
            '-D__wrap_akv_experimental_pv_f16_pair=resident_pv_rotation_body',
            '-Dresident_pv_rotation_selected=resident_pv_rotation_always'])):
        argv=list(assembly)
        for flag,value in (('-c',source),('-o',output/(obj+'.o')),('-MF',output/(obj+'.d'))):
            argv[argv.index(flag)+1]=str(value)
        argv+=flags
        extra.append(dict(label=label,argv=argv))
    link=next(c for c in commands if c['label']=='link')['argv']
    at=link.index('-o')
    link[at:at]=[str(output/'prepare.o'),str(output/'strong_control.o')]
    disassembly=next(c for c in commands if c['label']=='disassembly')['argv']
    disassembly[1:1]=['-M','no-aliases,numeric']
    return commands[:2]+extra+commands[2:]


rotation.recipes=recipes


def verify_build(output):
    result=rotation.verify_build(output)
    require(result.get('baseline_arm')=='rotated RVV' and
            result.get('candidate_arm')=='rotated RVV plus redundant preparation/capture' and
            result.get('objects_recompiled')==[str(Path(output)/name) for name in
                ('main.o','rotation.o','prepare.o','strong_control.o')],
            'Incorrect preparation build receipt')
    return result


def build(output):
    result=rotation.build(output)
    result.update(baseline_arm='rotated RVV',
                  candidate_arm='rotated RVV plus redundant preparation/capture',
                  objects_recompiled=[str(output/name) for name in
                      ('main.o','rotation.o','prepare.o','strong_control.o')],
                  complete_call_speedup=False)
    (output/'build.json').write_text(json.dumps(result,indent=2)+'\n')
    return verify_build(output)


def parse_preparation(text):
    metas=[]
    data={}
    records=[]
    terminals=[]
    keys=('id','tokens','dimension','heads','issue','dump','fcsr_before','fcsr_after')
    for raw in text.splitlines():
        if raw.startswith('PV_PREP_'): records.append(raw)
        if raw.startswith('PV_PREP_META '):
            match=re.fullmatch('PV_PREP_META '+' '.join(k+r'=(\d+)' for k in keys),raw)
            require(match is not None,'Malformed preparation timing')
            metas.append(dict(zip(keys,map(int,match.groups()))))
        elif raw.startswith('PV_PREP_DATA '):
            match=re.fullmatch(r'PV_PREP_DATA id=(\d+) kind=(probability|scale|seed|source) bits=([0-9a-f]+)',raw)
            require(match is not None,'Malformed preparation source')
            cid,kind,bits=match.groups()
            key=(int(cid),kind)
            require(key not in data,'Duplicate preparation source')
            width=8 if kind in ('probability','scale') else 4
            n=dict(probability=128,scale=2,seed=256,source=384)[kind]
            require(len(bits)==width*n,'Preparation source length mismatch')
            data[key]=[int(bits[i:i+width],16) for i in range(0,len(bits),width)]
        elif raw.startswith('PV_PREP_COMPLETE '):
            match=re.fullmatch(r'PV_PREP_COMPLETE records=(\d+) errors=(\d+)',raw)
            require(match is not None,'Malformed preparation terminal')
            terminals.append((len(records)-1,*map(int,match.groups())))
        elif raw.startswith('PV_PREP_'):
            raise ValueError('Unknown/malformed preparation record')
    require([m['id'] for m in metas]==list(range(6)),'Missing or duplicate preparation timings')
    require(set(data)=={(i,k) for i in range(3) for k in ('probability','scale','seed','source')},
            'Missing/extra preparation source records')
    require(terminals==[(len(records)-1,6,0)],
            'Missing checked preparation terminal')
    sf=reference.OrderedReference().sf
    prepared=[]
    for m in metas:
        i=m['id']; t=m['tokens']; d=m['dimension']; rm=m['fcsr_before']>>5
        require((t,d,m['heads'])==((64,64,9)[i%3],128,2),'Real model shape drift')
        require(0<m['issue']<=m['dump'] and rm in range(5),'Invalid preparation timing/CSR')
        require(m['fcsr_after']>>5==rm,'Preparation changed rounding mode')
        source=data[i%3,'source']; probability=data[i%3,'probability']
        scale=data[i%3,'scale']; seed=data[i%3,'seed']; flags=0
        for head in range(2):
            alpha,ex=sf.evaluate('cast',32,16,rm,scale[head]); flags|=ex
            for k in range(d):
                value,ex=sf.evaluate('mul',16,16,rm,seed[128*head+k],alpha); flags|=ex
                require(source[128*head+k]==value,'Prepared seed differs from independent SoftFloat')
            for k in range(t):
                value,ex=sf.evaluate('cast',32,16,rm,probability[64*head+k]); flags|=ex
                require(source[256+2*k+head]==value,'Prepared coefficient layout/value mismatch')
        require(m['fcsr_after']==m['fcsr_before']|flags,'Prepared exception flags differ from SoftFloat')
        prepared.append(dict(m,prepared_flags=flags,active_halfwords=256+2*t))
    return dict(records=prepared,oracle_pins=reference.OrderedReference().identity(),
                issue_interval_includes_final_normalization_issue=True,
                dump_interval_includes_diagnostic_store=True,
                complete_call_speedup=False,hardware_changed=False)


def check_run(log_path,build_dir):
    verify_build(build_dir)
    result=rotation.check_run(log_path,build_dir)
    result['preparation']=parse_preparation(Path(log_path).read_text())
    result.update(diagnostic_only=True,baseline_arm='rotated RVV',
                  candidate_arm='rotated RVV plus redundant preparation/capture',
                  complete_call_speedup=False)
    return result


def check_vector_workcounts(path,build_dir):
    # Both arms use the same stronger control, not the old single-destination PV.
    verify_build(build_dir)
    original=rotation.expected_signatures
    def wanted():
        values=[]
        for _ in range(4):
            for tokens in (64,64,9):
                values += [0x0205745B]*32
                values += [0x0205355B if k%2 else 0x0205345B for k in range(tokens)]
        return values
    rotation.expected_signatures=wanted
    try:
        return rotation.vector_work(path)
    finally:
        rotation.expected_signatures=original


def run(args):
    owner=contract.load(rotation.PRIMARY/'run.py','prepare_direct_owner')
    owner.load_checker=lambda kind:(HERE/'experiment.py',sys.modules[__name__])
    return owner.run(args)


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('action',choices=('build','run'))
    p.add_argument('--output',required=True,type=Path)
    p.add_argument('--build',type=Path)
    p.add_argument('--soc-build',type=Path,default=contract.OUT/'chain_soc_admitted_20261107_01')
    p.add_argument('--timeout',type=int,default=10800)
    p.add_argument('--preflight-only',action='store_true')
    args=p.parse_args(); args.kind='qwen3_abba'
    if args.action=='build':
        result=build(args.output)
        print(json.dumps({k:result[k] for k in ('state','elf','elf_sha256')}))
    else:
        require(args.build is not None,'--build required')
        def interrupted(sig,_frame):
            raise InterruptedError('Signal '+str(sig))
        for sig in (signal.SIGINT,signal.SIGTERM): signal.signal(sig,interrupted)
        run(args)


if __name__=='__main__': main()
