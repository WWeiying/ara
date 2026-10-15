#!/usr/bin/env python3
"""Independent preflight/one-shot gated worker. No rebuild and no waiting for parent."""
import argparse
import importlib.util
import json
import os
from pathlib import Path
import re
import subprocess
import sys
import time

sys.dont_write_bytecode=True
import reference as ref
import csv_check
import prepare_vcs_plan as plan

HERE=Path(__file__).resolve().parent
REFERENCE=HERE/'reference01'
CAMPAIGN=plan.FROZEN.parent/'campaign'
IMAGE=CAMPAIGN/'image'
RUNNER=ref.base.BASE/'run.py'
GROUPS={
    'sv39':['alloff_fault','active_fault_retry','alloff_valid'],
    'smokes':['rvv_vadd','rvv_vslideup','rvv_vslidedown','rvv_vrgather','rvv_vmseq',
              'rvv_vfredosum','rvv_vfwredosum','qbs_control_smoke','akv_context_smoke','qbs_akv_handoff_smoke'],
}
require=ref.base.require
sha=ref.base.sha
read=plan.read


def save(path,value):
    with path.open('x') as stream: json.dump(value,stream,indent=2); stream.write('\n')


def inside(path):
    path=path.resolve()
    require(path.is_relative_to(HERE) and path!=HERE,'Output outside owned directory')
    return path


def one_arg(argv,flag):
    require(argv.count(flag)==1 and argv.index(flag)+1<len(argv),'Missing/duplicate option '+flag)
    return argv[argv.index(flag)+1]


def validate_parent(status,stages_data,image):
    """Pure gate for tests; callers separately bind every artifact to current disk hashes."""
    require(status.get('status')=='PASS','Parent not PASS; refuse immediately, do not wait')
    stages=status.get('stages',[])
    require([s['name'] for s in stages]==['build-image','sv39','smokes'],'Parent stage membership/order differs')
    for stage in stages:
        require(stage.get('status')=='PASS' and stage.get('returncode')==0 and stage.get('completed_at'),
                'Parent stage incomplete/failed')
        if stage['name']=='build-image':
            require(stage['out']==str(IMAGE),'Parent built a different image directory')
            continue
        group=stage['name']; names=GROUPS[group]; argv=stage['argv']
        require(stage['cases']==names and stage['out']==str(CAMPAIGN/group),'Wrong parent case set/directory')
        require(argv[1]==str(RUNNER) and argv[2]=='run' and '--execute' in argv,'Parent was not an executed sealed run')
        require(one_arg(argv,'--image')==str(IMAGE),'Parent used different image')
        require([argv[i+1] for i,x in enumerate(argv) if x=='--case']==names,'Parent argv case mismatch')
        meta,summary,inputs=stages_data[group]
        require(meta['status']=='COMPLETE' and meta['tests']==names and meta['simv']==image['simv'] and
                meta['commit_trace'] is True and meta['invocation']==argv[1:],'Parent run metadata mismatch')
        require(sorted(r['name'] for r in summary)==sorted(names),'Missing/duplicate parent results')
        require(all(r['status']=='PASS' and r['returncode']==0 for r in summary),'Parent test not PASS')
        require(set(inputs)==set(names),'Missing parent input provenance')
        for name in names:
            require(inputs[name]['simv']==dict(path=image['simv'],image_sha256=image['files']),
                    'Parent test image hash mismatch: '+name)
    return True


def parent_gate(image):
    status_path=CAMPAIGN/'status.json'; status=read(status_path)
    require(status.get('status')=='PASS','Parent not PASS; refuse immediately, no polling')
    pins={str(status_path):sha(status_path),str(CAMPAIGN/'plan.json'):sha(CAMPAIGN/'plan.json')}
    require(status['plan_sha256']==pins[str(CAMPAIGN/'plan.json')],'Parent plan drift')
    data={}
    for group,names in GROUPS.items():
        directory=CAMPAIGN/group
        metadata=read(directory/'run.json'); summary=read(directory/'summary.json')
        inputs={}
        stage=next(s for s in status['stages'] if s['name']==group)
        programs_path=Path(one_arg(stage['argv'],'--programs'))/'programs.json'
        programs=read(programs_path)
        files=[directory/'run.json',directory/'summary.json',programs_path]
        for name in names:
            artifact=directory/'tests'/name; inp=read(artifact/'inputs.json')
            entry=programs['programs'][name]
            require(inp['binary']['sha256']==entry['sha256']==sha(artifact/'input.elf')==sha(entry['path']),
                    'Parent software binding mismatch: '+name)
            require(Path(inp['binary']['source']).resolve()==Path(entry['path']).resolve(),'Parent ELF source mismatch')
            inputs[name]=inp; files += [artifact/'inputs.json',artifact/'input.elf',Path(entry['path'])]
        pins.update({str(p):sha(p) for p in files})
        data[group]=(metadata,summary,inputs)
    validate_parent(status,data,image)
    verify_pins(pins)
    return dict(status='PARENT_3_SV39_10_SMOKES_PASS_SAME_IMAGE',pins=pins)


def verify_pins(pins):
    for p,h in pins.items(): require(sha(p)==h,'Pinned input drift: '+p)


def check_image():
    staged=read(HERE/'vcs_plan01/plan.json')
    require(sha(plan.FROZEN/'snapshot.json')==staged['frozen_snapshot_sha256'],'Frozen snapshot changed')
    snapshot=read(plan.FROZEN/'snapshot.json')
    require(len(snapshot['files'])==539,'Frozen membership changed')
    for n,h in snapshot['files'].items(): require(sha(plan.FROZEN/'sources'/n)==h,'Frozen source drift: '+n)
    for n,h in plan.EXPECTED.items(): require(snapshot['files'][n]==h,'Wrong candidate input')
    image=read(IMAGE/'image.json')
    require(image['snapshot']==str(plan.FROZEN) and image['snapshot_sha256']==staged['frozen_snapshot_sha256'],
            'Image bound to a different snapshot')
    verify_pins(image['files'])
    simv=Path(image['simv']); conf=simv.parent/'simulator.conf'; manifest=simv.parent/'vcs_source_manifest.json'
    require(sha(conf)==image['configuration_sha256'] and sha(manifest)==image['manifest_sha256'],'Image metadata drift')
    config=dict(line.split('=',1) for line in conf.read_text().splitlines())
    for k,v in dict(nr_lanes='4',vlen='1024',sim_l2_bytes='2097152').items(): require(config[k]==v,'Geometry differs')
    soc=(plan.FROZEN/'sources/hardware/src/ara_soc.sv').read_text()
    require(re.search(r'OSSupport\s*=\s*1',soc) and 'cfg.NrPMPEntries          = 0;' in soc,'OS/PMP interface differs')
    # The sealed module only defines functions on import. Framework checks do not execute simv.
    spec=importlib.util.spec_from_file_location('extended_sealed_runner',RUNNER)
    module=importlib.util.module_from_spec(spec); spec.loader.exec_module(module)
    _,_,_,simulation_image=module.framework(plan.FROZEN/'sources')
    require(simulation_image(simv)==image['files'],'Image membership/content drift')
    from ara_verify.vcs_source_manifest import collect
    capture=read(manifest)
    require(collect(Path(capture['filelist']),plan.FROZEN/'sources',[Path(p) for p in capture['extra_sources']])==capture['files'],
            'Compiled source manifest drift')
    return image


def command(out,execute=False):
    cmd=['/usr/bin/python3','-B',str(RUNNER),'run','--image',str(IMAGE),
         '--programs',str(out/'programs'),'--out',str(out/('run' if execute else 'dryrun')),
         '--jobs','1','--timeout','1200','--case','extended8']
    return cmd+(['--execute'] if execute else [])


def preflight(out):
    require(not out.exists(),'Fresh preflight directory required')
    verify_pins(read(REFERENCE/'input_pins.json'))
    result=read(REFERENCE/'status.json'); require(result['status']=='HOST_SPIKE_PASS_NOT_DUT','Reference not PASS')
    require(sha(REFERENCE/'soc.elf')==result['elf_sha256']['soc'],'Original ELF changed')
    image=check_image()
    readelf=ref.base.CC.with_name('riscv64-unknown-elf-readelf')
    header=subprocess.check_output([str(readelf),'-h',str(REFERENCE/'soc.elf')],text=True,timeout=15)
    layout=subprocess.check_output([str(readelf),'-Wl',str(REFERENCE/'soc.elf')],text=True,timeout=15)
    require('ELF64' in header and 'RISC-V' in header and re.search(r'Entry point address:\s+0x80000000',header),'Wrong ELF ABI/entry')
    loads=re.findall(r'^\s*LOAD\s+0x[0-9a-f]+\s+(0x[0-9a-f]+)\s+(0x[0-9a-f]+)\s+0x[0-9a-f]+\s+(0x[0-9a-f]+)',layout,re.M)
    require(bool(loads),'No ELF LOAD segments')
    require(all(int(v,16)==int(p,16) and 0x80000000<=int(p,16) and int(p,16)+int(n,16)<=0x80200000 for v,p,n in loads),
            'ELF outside frozen L2')
    symbols=read(REFERENCE/'soc.symbols.json'); require('tohost' not in symbols,'HTIF ELF forbidden')
    ref.base.prepare.check(REFERENCE/'prepared')
    out.mkdir(); (out/'programs').mkdir()
    save(out/'programs/programs.json',dict(schema_version=1,backend='vcs-soc',prepared=str(REFERENCE/'prepared'),
        provenance_sha256=sha(REFERENCE/'prepared/provenance.json'),programs=dict(extended8=dict(
            path=str(REFERENCE/'soc.elf'),sha256=result['elf_sha256']['soc'],cases=list(ref.NAMES),pass_markers=['MX_SV39_PASS']))))
    cmd=command(out); save(out/'dryrun_command.json',cmd)
    with (out/'dryrun.log').open('x') as log:
        subprocess.run(cmd,cwd=ref.base.ROOT,stdout=log,stderr=subprocess.STDOUT,check=True,timeout=120)
    require(read(out/'dryrun/summary.json')[0]['status']=='DRY_RUN','Unexpected dry run result')
    files=[Path(__file__),HERE/'csv_check.py',HERE/'test_successor.py',HERE/'reference.py',HERE/'prepare_vcs_plan.py',
           HERE/'vcs_plan01/plan.json',REFERENCE/'soc.elf',REFERENCE/'soc.symbols.json',REFERENCE/'status.json',
           REFERENCE/'input_pins.json',IMAGE/'image.json',plan.FROZEN/'snapshot.json',RUNNER,
           ref.base.BASE/'prepare.py',out/'programs/programs.json',out/'dryrun/summary.json']
    try: parent=parent_gate(image); parent_state=parent['status']
    except (ValueError,FileNotFoundError) as error: parent_state='NOT_READY: '+str(error)
    save(out/'preflight.json',dict(status='STATIC_PREFLIGHT_PASS_NOT_LAUNCHED',pins={str(p):sha(p) for p in files},
        image_sha256=sha(IMAGE/'image.json'),image_files=image['files'],parent_observed=parent_state,
        timeout_s=1200,jobs=1,elf_sha256=result['elf_sha256']['soc'],VCS_started=False,
        gate='worker re-reads once; parent not PASS => immediate refusal; no waiting'))
    print(json.dumps(dict(status='STATIC_PREFLIGHT_PASS_NOT_LAUNCHED',parent=parent_state,output=str(out))))


def worker(out,authorized):
    require(authorized,'Explicit --authorize-run required after review')
    pre=read(out/'preflight.json'); verify_pins(pre['pins'])
    verify_pins(read(REFERENCE/'input_pins.json'))
    image=check_image()
    require(sha(IMAGE/'image.json')==pre['image_sha256'] and image['files']==pre['image_files'],'Image changed after review')
    try: gate=parent_gate(image)
    except Exception as error:
        save(out/('gate_refusal_'+str(time.time_ns())+'.json'),dict(status='REFUSED_NOT_LAUNCHED',error=str(error)))
        raise
    # Exclusive ownership is acquired only after a successful one-shot parent gate.
    save(out/'worker.json',dict(pid=os.getpid(),started_unix=time.time(),gate=gate,command=command(out,True)))
    cmd=command(out,True); started=time.monotonic()
    with (out/'worker.log').open('x') as log:
        # The sealed runner owns a bounded simulator process group and kills it on timeout.
        # This wait is not polling the parent or reading an in-flight simulation trace.
        child=subprocess.Popen(cmd,cwd=ref.base.ROOT,stdout=log,stderr=subprocess.STDOUT,stdin=subprocess.DEVNULL)
        code=child.wait()
    elapsed=time.monotonic()-started
    trace=out/'run/tests/extended8/commit_trace.csv'
    analysis=csv_check.analyze(trace,read(REFERENCE/'soc.symbols.json')) if trace.exists() else dict(status='NO_TRACE_NOT_PASS')
    save(out/'csv_analysis.json',analysis)
    verify_pins(pre['pins']); verify_pins(gate['pins']); check_image()
    summary=read(out/'run/summary.json')
    passed=code==0 and len(summary)==1 and summary[0]['name']=='extended8' and summary[0]['status']=='PASS' and \
        summary[0]['returncode']==0 and analysis['status']=='EXTENDED8_CSV_ORACLE_PASS'
    save(out/'complete.json',dict(status='CANDIDATE02_EXTENDED8_PASS' if passed else 'CANDIDATE02_EXTENDED8_NOT_PASS',
        returncode=code,elapsed_s=elapsed,summary=summary,analysis_sha256=sha(out/'csv_analysis.json'),
        image_sha256=pre['image_sha256'],scope='only these 8 cases; not Linux or fault-epoch closure'))
    return int(not passed)


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('command',choices=['preflight','worker']); p.add_argument('--out',type=Path,required=True)
    p.add_argument('--authorize-run',action='store_true')
    a=p.parse_args(); out=inside(a.out)
    if a.command=='preflight': preflight(out)
    else: sys.exit(worker(out,a.authorize_run))
