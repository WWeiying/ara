#!/usr/bin/env python3
"""Pinned no-build NF2 adapter. Preflight is offline; worker requires explicit review."""
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

HERE=Path(__file__).resolve().parent
REFERENCE=HERE/'reference01'
FROZEN=Path('/home/wangwy/fpga_runs/current_board_memory_candidate02/frozen')
IMAGE=FROZEN.parent/'campaign/image'
RUNNER=ref.base.BASE/'run.py'
CASE='nf2_segment4'
INNER_TIMEOUT=2400
OUTER_TIMEOUT=3000
ELF_SHA='2ddce29de6d035fb02616f7924235b03e8863a74dfad161c3b2a4219ced61a67'
SNAPSHOT_SHA='b185f9fd8cc4a75ce5ab5ef240fb621511affd673bbc8b43fb7a2e8d64bad8a9'
SIMV_SHA='6fcdf53ecf2df4526e9d35372ea6bf9d2c49fdd2fc7a6bc3b57044124aeb13b7'
EXPECTED={
    'hardware/src/vlsu/addrgen.sv':'470c6c92d26cd2e540562302788f58d8d85ae6f147886fb949668e7728be41da',
    'hardware/src/vlsu/vldu.sv':'4e46a4733530b15edb05bbaded651899511af930e2caffe77b7482528c4fc8ab',
    'hardware/src/ara_sequencer.sv':'bf5d5a9be860340ca7a6f8d8c636da67cf9650f7b7b72d1123ce983e8eea5655',
}
require=ref.base.require
sha=ref.base.sha


def read(path): return json.loads(Path(path).read_text())


def save(path,value):
    with Path(path).open('x') as stream: json.dump(value,stream,indent=2); stream.write('\n')


def inside(path):
    path=path.resolve(); require(path.is_relative_to(HERE) and path!=HERE,'Output outside owned sv39 directory')
    return path


def verify_pins(pins):
    for p,digest in pins.items(): require(sha(p)==digest,'Pinned identity drift: '+p)


def check_image():
    require(sha(FROZEN/'snapshot.json')==SNAPSHOT_SHA,'Not the reviewed candidate02 snapshot')
    snap=read(FROZEN/'snapshot.json'); require(len(snap['files'])==539,'Frozen membership differs')
    for name,digest in snap['files'].items(): require(sha(FROZEN/'sources'/name)==digest,'Frozen source drift: '+name)
    for name,digest in EXPECTED.items(): require(snap['files'][name]==digest,'Wrong candidate RTL')
    image=read(IMAGE/'image.json')
    require(image['snapshot']==str(FROZEN) and image['snapshot_sha256']==SNAPSHOT_SHA,'Wrong image snapshot')
    require(image['simv']==str(IMAGE/'_build/vcs/simv') and image['files'][image['simv']]==SIMV_SHA,'Wrong simv identity')
    verify_pins(image['files'])
    directory=Path(image['simv']).parent
    conf,manifest=directory/'simulator.conf',directory/'vcs_source_manifest.json'
    require(sha(conf)==image['configuration_sha256'] and sha(manifest)==image['manifest_sha256'],'Image metadata drift')
    config=dict(line.split('=',1) for line in conf.read_text().splitlines())
    for k,v in dict(nr_lanes='4',vlen='1024',sim_l2_bytes='2097152').items(): require(config[k]==v,'Wrong geometry')
    soc=(FROZEN/'sources/hardware/src/ara_soc.sv').read_text()
    require(re.search(r'OSSupport\s*=\s*1',soc) and 'cfg.NrPMPEntries          = 0;' in soc,'Wrong OS/PMP configuration')
    spec=importlib.util.spec_from_file_location('nf2_sealed_runner',RUNNER)
    module=importlib.util.module_from_spec(spec); spec.loader.exec_module(module)
    _,_,_,simulation_image=module.framework(FROZEN/'sources')
    require(simulation_image(Path(image['simv']))==image['files'],'Image file membership/content drift')
    from ara_verify.vcs_source_manifest import collect
    capture=read(manifest)
    require(collect(Path(capture['filelist']),FROZEN/'sources',[Path(p) for p in capture['extra_sources']])==capture['files'],
            'Compiled source manifest drift')
    return image


def command(out,execute=False):
    result=['/usr/bin/python3','-B',str(RUNNER),'run','--image',str(IMAGE),
            '--programs',str(out/'programs'),'--out',str(out/('run' if execute else 'dryrun')),
            '--jobs','1','--timeout',str(INNER_TIMEOUT),'--case',CASE]
    return result+(['--execute'] if execute else [])


def validate_review(review,preflight_sha,image_sha):
    require(review.get('parent_authorized') is True and review.get('no_overlap_confirmed') is True,
            'Parent authorization/no-overlap confirmation required')
    require(review.get('preflight_sha256')==preflight_sha and review.get('image_json_sha256')==image_sha
            and review.get('soc_elf_sha256')==ELF_SHA,'Review binds different preflight/image/ELF')
    disposition=review.get('extended8',{})
    require(disposition.get('disposition') in ('REVIEWED_PASS','REVIEWED_TIMEOUT','REVIEWED_FAILURE'),
            'Parent extended8 disposition/review required; do not infer or poll')
    evidence=Path(disposition.get('evidence_path','')).resolve()
    require(evidence.is_relative_to(ref.MT/'sv39_extended'),'Extended8 evidence must be in its owned directory')
    require(bool(re.fullmatch('[0-9a-f]{64}',disposition.get('evidence_sha256',''))),'Missing extended8 evidence identity')
    require(bool(disposition.get('review_note','').strip()),'Missing explicit parent disposition note')
    return evidence


def preflight(out):
    require(not out.exists(),'Fresh preflight output required')
    verify_pins(read(REFERENCE/'input_pins.json'))
    result=read(REFERENCE/'status.json')
    require(result['status']=='HOST_SPIKE_PASS_NOT_DUT' and result['cases']==list(ref.NAMES),'Reference case set/status differs')
    require(sha(REFERENCE/'soc.elf')==result['elf_sha256']['soc']==ELF_SHA,'Original accepted SoC ELF changed')
    ref.base.prepare.check(REFERENCE/'prepared')
    image=check_image()
    symbols=read(REFERENCE/'soc.symbols.json'); require('tohost' not in symbols,'Spike ELF forbidden')
    nm=subprocess.check_output([str(ref.base.CC.with_name('riscv64-unknown-elf-nm')),'-n',str(REFERENCE/'soc.elf')],
                               text=True,timeout=15)
    actual_symbols={m[3]:int(m[1],16) for m in re.finditer(r'^([0-9a-f]+)\s+(\w)\s+(\S+)$',nm,re.M)}
    require(actual_symbols==symbols,'Observer symbols do not match accepted ELF')
    readelf=ref.base.CC.with_name('riscv64-unknown-elf-readelf')
    header=subprocess.check_output([str(readelf),'-h',str(REFERENCE/'soc.elf')],text=True,timeout=15)
    layout=subprocess.check_output([str(readelf),'-Wl',str(REFERENCE/'soc.elf')],text=True,timeout=15)
    require('ELF64' in header and 'RISC-V' in header and re.search(r'Entry point address:\s+0x80000000',header),'Wrong ELF ABI/entry')
    loads=re.findall(r'^\s*LOAD\s+0x[0-9a-f]+\s+(0x[0-9a-f]+)\s+(0x[0-9a-f]+)\s+0x[0-9a-f]+\s+(0x[0-9a-f]+)',layout,re.M)
    require(loads and all(int(v,16)==int(p,16) and 0x80000000<=int(p,16) and int(p,16)+int(n,16)<=0x80200000 for v,p,n in loads),
            'ELF LOAD segment outside sealed L2')
    out.mkdir(); (out/'programs').mkdir()
    with (out/'offline_tests.log').open('x') as log:
        subprocess.run(['/usr/bin/python3','-B',str(HERE/'test_vcs_adapter.py'),'--out',str(out/'offline_tests')],
                       cwd=HERE,stdout=log,stderr=subprocess.STDOUT,check=True,timeout=120)
    require(read(out/'offline_tests/tests.json')['status']=='OFFLINE_TESTS_PASS_NOT_DUT','Offline tests not PASS')
    save(out/'programs/programs.json',dict(schema_version=1,backend='vcs-soc',prepared=str(REFERENCE/'prepared'),
        provenance_sha256=sha(REFERENCE/'prepared/provenance.json'),programs={CASE:dict(path=str(REFERENCE/'soc.elf'),
        sha256=ELF_SHA,cases=list(ref.NAMES),pass_markers=['SEGMENT_SV39_PASS'])}))
    cmd=command(out); save(out/'dryrun_command.json',cmd)
    with (out/'dryrun.log').open('x') as log:
        subprocess.run(cmd,cwd=ref.base.ROOT,stdout=log,stderr=subprocess.STDOUT,check=True,timeout=120)
    summary=read(out/'dryrun/summary.json')
    require(len(summary)==1 and summary[0]['name']==CASE and summary[0]['status']=='DRY_RUN','Unexpected dry-run result')
    files=[Path(__file__),HERE/'csv_check.py',HERE/'test_vcs_adapter.py',HERE/'reference.py',
           REFERENCE/'soc.elf',REFERENCE/'soc.symbols.json',REFERENCE/'status.json',REFERENCE/'linux_provenance.json',
           REFERENCE/'input_pins.json',REFERENCE/'negative_oracle.json',IMAGE/'image.json',FROZEN/'snapshot.json',RUNNER,
           out/'programs/programs.json',out/'offline_tests/tests.json',out/'dryrun/summary.json']
    pins={str(p):sha(p) for p in files}
    pins.update(read(REFERENCE/'input_pins.json'))
    pins.update({str(REFERENCE/'prepared'/name):digest for name,digest in read(REFERENCE/'prepared/provenance.json')['files'].items()})
    pins[str(REFERENCE/'prepared/provenance.json')]=sha(REFERENCE/'prepared/provenance.json')
    save(out/'preflight.json',dict(status='NF2_PREFLIGHT_PASS_NOT_LAUNCHED',pins=pins,image_files=image['files'],
        image_json_sha256=sha(IMAGE/'image.json'),soc_elf_sha256=ELF_SHA,subcases=list(ref.NAMES),single_elf=True,
        inner_timeout_s=INNER_TIMEOUT,outer_service_timeout_s=OUTER_TIMEOUT,jobs=1,
        calibration=dict(spike_commits=result['commits'],extended8_observed_commits=740000,extended8_wall_s=1200,
                         linear_estimate_s=round(result['commits']/740000*1200,1)),VCS_started=False,recompiled=False,
        authorization='Requires fresh explicit parent extended8 disposition and --authorize-run; never auto-waits'))
    save(out/'review.template.json',dict(parent_authorized=False,no_overlap_confirmed=False,
        preflight_sha256=sha(out/'preflight.json'),image_json_sha256=sha(IMAGE/'image.json'),soc_elf_sha256=ELF_SHA,
        extended8=dict(disposition='PENDING',evidence_path='',evidence_sha256='',review_note='')))
    service=['systemd-run','--user','--unit=ara-nf2-candidate02','--property=Type=exec',
             f'--property=RuntimeMaxSec={OUTER_TIMEOUT}','--property=TimeoutStopSec=60','--property=KillMode=control-group',
             '/usr/bin/python3','-B',str(Path(__file__).resolve()),'worker','--out',str(out),
             '--review',str(out/'parent_review.json'),'--authorize-run']
    save(out/'service_command.NOT_EXECUTED.json',service)
    verify_pins(pins)
    print(json.dumps(dict(status='NF2_PREFLIGHT_PASS_NOT_LAUNCHED',output=str(out),inner_s=INNER_TIMEOUT,outer_s=OUTER_TIMEOUT)))


def worker(out,review_path,authorized):
    require(authorized and review_path is not None,'Explicit parent review and --authorize-run required')
    pre=read(out/'preflight.json'); verify_pins(pre['pins'])
    require(pre['status']=='NF2_PREFLIGHT_PASS_NOT_LAUNCHED','Wrong preflight')
    review=read(review_path)
    evidence=validate_review(review,sha(out/'preflight.json'),pre['image_json_sha256'])
    require(sha(evidence)==review['extended8']['evidence_sha256'],'Reviewed extended8 evidence changed')
    image=check_image()
    require(sha(IMAGE/'image.json')==pre['image_json_sha256'] and image['files']==pre['image_files'],'Image changed after review')
    pins={str(review_path.resolve()):sha(review_path),str(evidence):sha(evidence)}
    save(out/'worker.json',dict(pid=os.getpid(),started_unix=time.time(),review=review,review_pins=pins,command=command(out,True)))
    started=time.monotonic()
    with (out/'worker.log').open('x') as log:
        # Runner bounds simv at 2400s; the independent service owns teardown/observer headroom.
        child=subprocess.Popen(command(out,True),cwd=ref.base.ROOT,stdout=log,stderr=subprocess.STDOUT,stdin=subprocess.DEVNULL)
        code=child.wait()
    artifact=out/'run/tests'/CASE
    analysis=csv_check.analyze(artifact/'commit_trace.csv',read(REFERENCE/'soc.symbols.json'))
    save(out/'csv_analysis.json',analysis)
    try:
        verify_pins(pre['pins']); verify_pins(pins); check_image()
        metadata=read(out/'run/run.json'); summary=read(out/'run/summary.json'); inputs=read(artifact/'inputs.json')
        require(metadata['status']=='COMPLETE' and metadata['tests']==[CASE] and metadata['commit_trace'] is True
                and metadata['simv']==image['simv'] and metadata['invocation']==command(out,True)[2:], 'Runner metadata differs')
        require(inputs['simv']==dict(path=image['simv'],image_sha256=image['files']),'Executed image differs')
        require(inputs['binary']['sha256']==sha(artifact/'input.elf')==ELF_SHA
                and Path(inputs['binary']['source']).resolve()==REFERENCE/'soc.elf','Executed ELF differs')
        console=(artifact/'console.log').read_text()
        require(console.count('SEGMENT_SV39_PASS')==1 and 'SEGMENT_SV39_FAIL' not in console,'Firmware marker differs')
        require(code==0 and len(summary)==1 and summary[0]['name']==CASE and summary[0]['status']=='PASS'
                and summary[0]['returncode']==0 and analysis['status']=='NF2_CSV_ORACLE_PASS','Runner/observer not PASS')
        result=dict(status='CANDIDATE02_NF2_FOUR_PASS',returncode=code,summary=summary)
    except (ValueError,KeyError,OSError) as error:
        result=dict(status='CANDIDATE02_NF2_NOT_PASS',returncode=code,error=str(error))
    result.update(elapsed_s=time.monotonic()-started,analysis_sha256=sha(out/'csv_analysis.json'),
                  image_json_sha256=pre['image_json_sha256'],soc_elf_sha256=ELF_SHA,
                  scope='Only four selected NF2 trials; not Linux execution or broad segment closure')
    save(out/'complete.json',result)
    return int(result['status']!='CANDIDATE02_NF2_FOUR_PASS')


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('command',choices=['preflight','worker']); p.add_argument('--out',type=Path,required=True)
    p.add_argument('--review',type=Path); p.add_argument('--authorize-run',action='store_true')
    args=p.parse_args(); out=inside(args.out)
    if args.command=='preflight': preflight(out)
    else: sys.exit(worker(out,args.review,args.authorize_run))
