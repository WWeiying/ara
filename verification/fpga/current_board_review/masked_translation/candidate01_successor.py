#!/usr/bin/env python3
"""Independent candidate successor; never edits prior runners, inputs, or RTL."""
import argparse
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import time

sys.dont_write_bytecode = True
import final04_baseline as baseline
import stage_candidate as staging
import analyze_final04 as prior_analysis
import sv39_adapter as ref

IMAGE = staging.IMAGE
BASELINE = ref.HERE/'sv39_final04_baseline01'
STAGING = ref.HERE/'sv39_candidate01_staging01/plan.json'
REFERENCE = baseline.REFERENCE


def command(out, names, execute=False):
    cmd = [str(baseline.PYTHON),'-B',str(baseline.RUNNER),'run','--image',str(IMAGE),
           '--programs',str(REFERENCE/'soc'),'--jobs','1','--timeout','600','--out',str(out)]
    for name in names:
        cmd += ['--case',name]
    if execute:
        cmd += ['--execute']
    return cmd


def source_delta():
    before = staging.checked.sealed(staging.OLD)
    after = staging.checked.sealed(staging.CANDIDATE)
    a,b = [json.loads((root/'snapshot.json').read_text()) for root in (staging.OLD,staging.CANDIDATE)]
    ref.require(set(a['files']) == set(b['files']) and len(a['files']) == 539,
                'Frozen source membership differs')
    changed = sorted(n for n in a['files'] if a['files'][n] != b['files'][n])
    ref.require(changed == sorted(['frozen.filelist','hardware/bender','hardware/src/vlsu/addrgen.sv']),
                'Unexpected frozen source changes')
    for name in ('frozen.filelist','hardware/bender'):
        ref.require((before/name).read_text().replace(str(before),'@ROOT@') ==
                    (after/name).read_text().replace(str(after),'@ROOT@'),
                    'Non-relocation change in '+name)
    ref.require(b['files']['hardware/src/vlsu/addrgen.sv'] ==
                '470c6c92d26cd2e540562302788f58d8d85ae6f147886fb949668e7728be41da',
                'Candidate AddrGen changed')
    return dict(checked_files=539,raw_changed=changed,
                semantic_changed=['hardware/src/vlsu/addrgen.sv'],
                baseline_addrgen=a['files']['hardware/src/vlsu/addrgen.sv'],
                candidate_addrgen=b['files']['hardware/src/vlsu/addrgen.sv'])


def preflight(out):
    ref.require(not out.exists(),'Fresh independent candidate directory required')
    baseline.check_reference()
    old_pre = baseline.verify_preflight(BASELINE)
    delta = source_delta()
    plan = json.loads(STAGING.read_text())
    ref.require(ref.sha(staging.CANDIDATE/'snapshot.json') == plan['candidate_snapshot_sha256'],
                'Candidate snapshot no longer matches staged identity')
    image = json.loads((IMAGE/'image.json').read_text())
    ref.require(Path(image['snapshot']) == staging.CANDIDATE and
                image['snapshot_sha256'] == plan['candidate_snapshot_sha256'],
                'Built image is not bound to the approved candidate snapshot')
    config = dict(line.split('=',1) for line in
                  (Path(image['simv']).parent/'simulator.conf').read_text().splitlines())
    ref.require(config == old_pre['configuration'],'Candidate interface/config changed')
    programs = json.loads((REFERENCE/'soc/programs.json').read_text())
    ref.require(programs['programs'] == plan['same_elf_bindings'] and programs['backend'] == 'vcs-soc',
                'Software identity/backend changed')
    for name,entry in programs['programs'].items():
        ref.require(ref.sha(entry['path']) == old_pre['bindings'][name]['sha256'],
                    'ELF differs from measured baseline: '+name)
    old = json.loads((BASELINE/'analysis.json').read_text())['results']['alloff_fault']
    ref.require(old['classification'] == 'CONFIRMED_ALLOFF_TARGET_PAGE_FAULT_ON_UNFIXED_FINAL04' and
                old['trap_csr_reads'][0]['mcause'] == 13 and
                old['trap_csr_reads'][0]['mepc'] == 0x80000b68 and
                old['trap_csr_reads'][0]['mtval'] == 0x40001000,
                'Baseline first fault is not the expected all-off target')
    out.mkdir(parents=True)
    for name in ref.NAMES:
        for suffix in ('.symbols.json','.readelf.txt'):
            shutil.copyfile(BASELINE/(name+suffix),out/(name+suffix))
    dry = command(out/'validate_before',ref.NAMES)
    ref.save(out/'validate_command.json',dry)
    with (out/'validate_before.log').open('x') as log:
        subprocess.run(dry,cwd=ref.ROOT,stdout=log,stderr=subprocess.STDOUT,check=True,timeout=120)
    files = [Path(__file__),Path(baseline.__file__),Path(staging.__file__),Path(prior_analysis.__file__),
             Path(ref.__file__),baseline.RUNNER,ref.BASE/'prepare.py',STAGING,
             IMAGE/'image.json',staging.CANDIDATE/'snapshot.json',staging.OLD/'snapshot.json',
             BASELINE/'analysis.json',BASELINE/'preflight.json',REFERENCE/'status.json',
             REFERENCE/'soc/programs.json']
    files += [out/(n+'.symbols.json') for n in ref.NAMES]
    ref.save(out/'preflight.json',dict(status='CANDIDATE01_THREE_CASE_PREFLIGHT_PASS',
        image=str(IMAGE),image_build_elapsed_s=image.get('elapsed_s'),source_delta=delta,
        baseline_first_fault=dict(cause=13,pc='0x80000b68',tval='0x40001000',expected_target_match=True),
        pins={str(p):ref.sha(p) for p in files},bindings=programs['programs'],
        configuration=config,max_parallel=3,timeout_per_case_s=600,VCS_started=False,
        authorization='User explicitly authorized same three ELFs after build and listed local controls PASS',
        scope_limits=['Only these three Sv39 load cases','Sparse multiwindow fixture is not yet PASS',
                      'VLDU exception delayed finalgrant is not closed'],
        RTL_edited=False,RTL_built=False,original_helpers_edited=False))
    print(json.dumps(dict(status='PREFLIGHT_PASS',source_delta=delta,
                         baseline_target_fault_confirmed=True,output=str(out)),indent=2))


def verify(out):
    pre = json.loads((out/'preflight.json').read_text())
    ref.require(pre['status'] == 'CANDIDATE01_THREE_CASE_PREFLIGHT_PASS','Wrong successor preflight')
    for path,digest in pre['pins'].items():
        ref.require(ref.sha(path) == digest,'Pinned input changed: '+path)
    for entry in pre['bindings'].values():
        ref.require(ref.sha(entry['path']) == entry['sha256'],'ELF changed')
    return pre


def launch(out):
    verify(out)
    ref.require(not (out/'launch.json').exists(),'Already launched')
    cmd = [str(baseline.PYTHON),'-B',str(Path(__file__).resolve()),'worker','--out',str(out)]
    with (out/'supervisor.log').open('x') as log:
        child = subprocess.Popen(cmd,cwd=ref.ROOT,stdout=log,stderr=subprocess.STDOUT,
                                 stdin=subprocess.DEVNULL,start_new_session=True)
    ref.save(out/'launch.json',dict(pid=child.pid,command=cmd,started_unix=time.time(),
                                  max_parallel=3,timeout_per_case_s=600,scope='candidate three cases only'))
    print(json.dumps(dict(pid=child.pid,output=str(out))))


def worker(out):
    verify(out)
    ref.require(not (out/'worker.json').exists(),'Duplicate worker')
    ref.save(out/'worker.json',dict(pid=os.getpid(),started_unix=time.time()))
    streams, processes, children = {}, {}, {}
    try:
        for name in ref.NAMES:
            cmd = command(out/name,[name],True)
            streams[name] = (out/(name+'.runner.log')).open('x')
            processes[name] = subprocess.Popen(cmd,cwd=ref.ROOT,stdout=streams[name],
                        stderr=subprocess.STDOUT,stdin=subprocess.DEVNULL)
            children[name] = dict(pid=processes[name].pid,command=cmd,started_unix=time.time())
        ref.save(out/'children.json',children)
        results = {}
        for name,process in processes.items():
            results[name] = dict(returncode=process.wait(),completed_unix=time.time())
            ref.save(out/'progress.json',results)
        verify(out)
        baseline.check_reference()
        ref.save(out/'complete.json',dict(status='CANDIDATE01_THREE_CASE_RUNS_COMPLETE',results=results,
                    completed_unix=time.time(),scope='three cases only; delayed finalgrant remains open'))
    except Exception as error:
        ref.save(out/'failure.json',dict(error=str(error),time=time.time()))
        raise
    finally:
        for stream in streams.values():
            stream.close()


def analyze(out):
    verify(out)
    ref.require((out/'complete.json').exists(),'Runs not complete')
    ref.require(not (out/'analysis.json').exists(),'Do not overwrite existing evidence')
    before = json.loads((BASELINE/'analysis.json').read_text())['results']
    results = {}
    for name in ref.NAMES:
        item = prior_analysis.analyze(out,name)
        item.pop('architectural_candidate_pass')
        item['candidate_case_pass'] = item['runner']['status'] == 'PASS'
        item['classification'] = 'CANDIDATE_THREE_CASE_ORACLE_PASS' if item['candidate_case_pass'] else \
            'CANDIDATE_CASE_NOT_PASS_NO_PREMATURE_ROOT_CAUSE'
        if item['candidate_case_pass']:
            s = json.loads((out/(name+'.symbols.json')).read_text())
            satp = (8 << 60) | ((s['mt_pages']+8192) >> 12)
            for record in item['trap_records']:
                ref.require(all(record.get(k) == v for k,v in dict(satp=satp,vl=8,vtype=8,vstart=0,
                                                                  fcsr=117,vcsr=5).items()),
                            'Candidate exact recorded CSR state differs')
                ref.require(record['mstatus'] & 0x8000031888 == 0x800,'Not an S-mode trap')
            if name != 'active_fault_retry':
                expected_pte = 0 if name == 'alloff_fault' else ((s['mt_pages']+4096) >> 12 << 10) | 0xc7
                ref.require(len(item['trap_records']) == 1 and
                            item['trap_records'][0]['target_pte'] == expected_pte and
                            item['trap_records'][0]['marker'] == 1 and
                            item['last_scalar_values']['mt_mask'] == '0x0',
                            'All-off completion changed mask/PTE or missed younger progress')
                sites = [v['site'] for v in item['sites'] if v['site'] != 'mt_ecall']
                ref.require(sites == ['mt_target','mt_recovery_load','mt_younger_store'],
                            'All-off target or younger retirement missing')
        item['baseline_status'] = before[name]['runner']['status']
        item['baseline_target_events'] = before[name]['target_front_events']
        results[name] = item
    passed = all(item['candidate_case_pass'] for item in results.values())
    ref.save(out/'analysis.json',dict(status='CANDIDATE_SV39_THREE_CASE_PASS' if passed else
                    'CANDIDATE_SV39_NOT_ALL_PASS',results=results,
                    pins=dict(preflight=ref.sha(out/'preflight.json'),completion=ref.sha(out/'complete.json'),
                              baseline=ref.sha(BASELINE/'analysis.json'),successor=ref.sha(Path(__file__))),
                    VLDU_delayed_finalgrant_closed=False,sparse_multiwindow_closed=False,
                    Linux_closed=False,broader_nonindexed_family_closed=False))
    print(json.dumps({name:dict(status=item['runner']['status'],elapsed_s=item['runner']['elapsed_s'],
                         traps=item['trap_records'],sites=item['sites'],last_cycle=item['last_cycle'])
                     for name,item in results.items()},indent=2))


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('command',choices=['preflight','launch','worker','analyze'])
    p.add_argument('--out',type=Path,required=True)
    args = p.parse_args()
    globals()[args.command](ref.inside(args.out))


if __name__ == '__main__':
    main()
