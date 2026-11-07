#!/usr/bin/env python3
"""Host-only, exact-record reproduction receipt; neither worker nor RTL passes."""
import argparse
import hashlib
import json
import os
from pathlib import Path
import re
import subprocess
import sys

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]
RUNS = ROOT.parent/'ara_dsa_signoff_integration/verification/out'
FIRST = RUNS/'e2e_mmu_mxr_hit_20261106_01'
WORKER = RUNS/'e2e_mmu_mxr_hit_checked_20261106_01'
FIRST_SHA = '8771ee9dfab61462182af057afbcaa700f11dd9749c8d57334c7d8445c5105ea'
FIRST_PINS_SHA = '679940b262e8441821312080d0fbc857228b26b178010e94eb05036803685c72'
WORKER_SHA = '8e4379df0c7e2e40a40d6db549532703c82b8c2f7a071f713cc0d89c028fb636'
WORKER_PINS_SHA = '809f53509516f67840f3c70e63b1531fa0e0878a3050ef23029b91e2ce57ed31'
IMAGE_PINS_SHA = 'b4872341f3a0503510d6951e83c2980575346273dd9c644d21b3e6629805cefb'
LOG = WORKER/'sim/console.log'
LOG_SHA = 'cce38cd92553eadeb35d31cbfbe7db41261c56f586fc90449b323f4a37311f40'
BENCH = WORKER/'inputs/verification/cva6/mmu_mxr_hit_tb.sv'
BENCH_SHA = 'c68bbc2b393eb85b3398b6da664d8689f20627de1b316025b494636faa080a80'
DUT_SHA = '3e3f19db1ef8d3526c2e5e751c89ce923244a4ae7be617144d523c6c6480d431'
FATAL_LINE = 164
REASON = 'MXR_HIT_CONTRACT_FAILED'
KEYS = 'case mxr hit latched_hit req valid is_store va pa pte exc cause tval refills flush'.split()
HEX = {'va','pa','pte','tval'}
SCOPE = 'MMU_MXR_HIT_SCOPE pmp=0 rvh=0 sv=39 refill_only=1 cold_ptw=0 cases=5'
SUMMARY = 'MMU_MXR_HIT_COMPLETE cases=5 checks=52 errors=3 refills=2 ptw_requests=0'
STATE = 'MMU_MXR_HIT_PERMISSION_BUG_REPRODUCED'


def require(condition, message):
    if not condition:
        raise ValueError(message)


def digest(path):
    h = hashlib.sha256()
    with Path(path).open('rb') as stream:
        for block in iter(lambda: stream.read(1024*1024),b''):
            h.update(block)
    return h.hexdigest()


def bind(pins, path, expected=None):
    path = Path(path).resolve(strict=True)
    actual = digest(path)
    require(expected is None or actual==expected,'Input SHA differs: '+str(path))
    require(str(path) not in pins or pins[str(path)]==actual,'Conflicting pin: '+str(path))
    pins[str(path)] = actual


def verify(pins):
    require(bool(pins),'Empty pin inventory')
    for path, sha in pins.items():
        require(digest(path)==sha,'Pinned input drift: '+path)


def save(path, value):
    with path.open('x') as stream:
        json.dump(value,stream,indent=2,sort_keys=True)
        stream.write('\n')


def architectural_rows():
    rows = []
    for case, mxr in enumerate((0,1,1,0,1)):
        readable = case<2
        va, pa = ((0x40000108,0x80010108) if readable else (0x40001108,0x80020108))
        # Legal leaf PTE: V/A set, W/U/G/D clear, either R or X set.
        pte = ((pa >> 12) << 10) | (1 << 6) | 1 | (2 if readable else 8)
        fault = case==3
        rows.append(dict(case=case,mxr=mxr,hit=1,latched_hit=1,req=1,valid=1,is_store=0,
                         va=va,pa=pa,pte=pte,exc=int(fault),cause=13 if fault else 0,
                         tval=va if fault else 0,refills=1 if readable else 2,flush=0))
    return rows


def check_log(text, bench_source):
    require(hashlib.sha256(bench_source.encode()).hexdigest()==BENCH_SHA,'Bench identity differs')
    source_lines = bench_source.splitlines()
    require(source_lines[FATAL_LINE-1].strip()=='if (errors) $fatal(1, "'+REASON+'");' and
            bench_source.count('"'+REASON+'"')==1,'Fatal is not uniquely source-bound')
    lines = text.splitlines()
    require('\r' not in text,'Unreviewed raw-log line endings')
    require(lines.count(SCOPE)==1 and lines.count(SUMMARY)==1,'Scope/terminal summary differs')
    require(len(re.findall(r'\bFatal:',text))==1,'Expected exactly one global Fatal')
    require(lines.count(REASON)==1,'Expected exactly one standalone fatal reason')
    require(not re.search(r'Error-\[|\bERROR\b|\bError:|UVM_(?:ERROR|FATAL)|\$stop|assertion[^\n]*fail',
                          text,re.I),'Unexpected simulator error')
    observed, observation_lines = [], []
    for line in lines:
        if not line.startswith('MMU_MXR_HIT_OBS'):
            continue
        require(line.startswith('MMU_MXR_HIT_OBS '),'Malformed observation prefix')
        pairs = [word.split('=') for word in line.split()[1:]]
        require(all(len(pair)==2 for pair in pairs) and [p[0] for p in pairs]==KEYS,
                'Observation field order/identity differs')
        row = {}
        for key,value in pairs:
            require(re.fullmatch(r'[0-9a-f]{16}' if key in HEX else r'[0-9]+',value),
                    'Unknown or malformed observation value')
            row[key] = int(value,16 if key in HEX else 10)
        observed.append(row); observation_lines.append(line)
    require(len(observed)==5,'Exactly five observations required')
    failures = []
    for actual,wanted in zip(observed,architectural_rows()):
        for key in KEYS:
            if actual[key]!=wanted[key]:
                failures.append(dict(case=wanted['case'],field=key,actual=actual[key],expected=wanted[key]))
    exact_failures = [dict(case=3,field=key,actual=0,expected=value)
                      for key,value in (('exc',1),('cause',13),('tval',0x40001108))]
    require(failures==exact_failures,'Not the exact MXR-only permission failure')
    mismatch_lines = [f'MMU_MXR_MISMATCH case=3 field={key} got={0:016x} expected={value:016x}'
                      for key,value in (('EXCEPTION',1),('CAUSE',13),('TVAL',0x40001108))]
    require([line for line in lines if line.startswith('MMU_MXR_MISMATCH')]==mismatch_lines,
            'Mismatch noise or SV/independent accounting differs')
    fatal = f'Fatal: "{BENCH}", {FATAL_LINE}: mmu_mxr_hit_tb: at time 186000 ps'
    finish = f'$finish called from file "{BENCH}", line {FATAL_LINE}.'
    expected_lines = [
        'Chronologic VCS simulator copyright 1991-2023',
        'Contains Synopsys proprietary information.',
        'Compiler version V-2023.12-SP1_Full64; Runtime version V-2023.12-SP1_Full64;  Nov  6 17:20 2026',
        SCOPE,*observation_lines[:3],*mismatch_lines,*observation_lines[3:],SUMMARY,
        fatal,REASON,finish,'$finish at simulation time               186000',
        '           V C S   S i m u l a t i o n   R e p o r t ','Time: 186000 ps',
    ]
    # Admit only this exact existing format, including the inline scope. Never
    # manufacture a Scope: line, project the log, or broaden origin matching.
    require(lines==expected_lines and text.endswith('\n'),'Unexpected log text/order or fatal/finish origin')
    return dict(state=STATE,rtl_functional_status='FAIL',observed=observed,failures=failures,
                cases=5,checks=52,mismatches=3,passing_controls=4,refills=2,ptw_requests=0,
                global_fatals=1,fatal_source=str(BENCH),fatal_line=FATAL_LINE,
                cold_ptw_covered=False,verified_coverage=False,
                format_scope='Existing quoted filename + inline scope + immediate unique reason + matching finish')


def inputs(pins):
    bind(pins,FIRST/'result.json',FIRST_SHA)
    bind(pins,FIRST/'source-pins.json',FIRST_PINS_SHA)
    bind(pins,WORKER/'result.json',WORKER_SHA)
    bind(pins,WORKER/'source-pins.json',WORKER_PINS_SHA)
    bind(pins,WORKER/'image-pins.json',IMAGE_PINS_SHA)
    bind(pins,LOG,LOG_SHA); bind(pins,BENCH,BENCH_SHA)
    first = json.loads((FIRST/'result.json').read_text())
    worker = json.loads((WORKER/'result.json').read_text())
    require(first['state']=='FAIL' and first['error']=="ValueError('VCS compile failed')" and
            first['compile_count']==1 and first['simulation_count']==0 and first['post_pins_match'] and
            first['source_pins_sha256']==FIRST_PINS_SHA,'First compile FAIL scope differs')
    require(worker['state']=='FAIL' and worker['error']==
            "ValueError('Failure lacks one exact originating bench fatal')" and
            worker['post_pins_match'] and worker['source_pins_sha256']==WORKER_PINS_SHA and
            worker['compile_count']==1 and worker['simulation_count']==1 and
            worker['campaign_compile_count']==2 and worker['campaign_simulation_count']==1 and
            worker['original_result_sha256']==FIRST_SHA and worker['original_worker_state']=='FAIL' and
            worker['original_worker_relabelled'] is False and worker['rtl_changed'] is False and
            worker['cold_ptw_covered'] is False and worker['full_soc'] is False and
            worker['dut_sha256']==DUT_SHA,'Actual worker FAIL scope differs')
    checked_pins = json.loads((WORKER/'source-pins.json').read_text())
    images = json.loads((WORKER/'image-pins.json').read_text())
    require(len(checked_pins)==45 and len(worker['artifacts'])==28 and len(images)==3 and
            images==worker['image_pins'],'45 pins/28 artifacts/3 images differ')
    for group in (json.loads((FIRST/'source-pins.json').read_text()),first['artifacts'],
                  checked_pins,worker['artifacts'],images):
        for path,sha in group.items(): bind(pins,path,sha)
    commands = json.loads((WORKER/'commands.json').read_text())
    require(len(commands)==2 and [r['returncode'] for r in commands]==[0,0] and
            [r['timeout_seconds'] for r in commands]==[300,30] and
            all(0<=r['elapsed_seconds']<=r['timeout_seconds'] for r in commands) and
            commands[1]['argv']==[str(WORKER/'build/simv'),'-no_save'],
            'Original actual bounded compile/simulation accounting differs')
    return dict(worker_pins=45,worker_artifacts=28,worker_images=3,
                first_worker_pins=len(json.loads((FIRST/'source-pins.json').read_text())),
                first_worker_artifacts=len(first['artifacts']),original_simulation_returncode=0)


def collect(output):
    out = output.absolute()
    require(out==out.resolve() and out.is_relative_to(RUNS) and out!=RUNS,'Fresh sole-verification output required')
    out.mkdir(parents=True,exist_ok=False)
    pins = {}
    result = dict(state='FAIL',rtl_functional_status='FAIL',verified_coverage=False,
                  original_worker_state='FAIL',first_compile_worker_state='FAIL',
                  original_worker_relabelled=False,new_compiles=0,new_simulations=0,
                  rtl_changed=False,performance_measured=False,cold_ptw_covered=False,full_soc=False)
    try:
        counts = inputs(pins)
        for path in (Path(__file__),HERE/'test_collect_mmu_mxr_hit.py',Path(sys.executable)):
            bind(pins,path)
        verify(pins)
        command = [sys.executable,'-B',str(HERE/'test_collect_mmu_mxr_hit.py')]
        save(out/'host-command.json',dict(argv=command,cwd=str(HERE),timeout_seconds=30))
        env = dict(os.environ,PYTHONDONTWRITEBYTECODE='1')
        test = subprocess.run(command,cwd=HERE,env=env,stdout=subprocess.PIPE,
                              stderr=subprocess.STDOUT,timeout=30)
        (out/'host-tests.log').write_bytes(test.stdout)
        matches = re.findall(rb'^Ran ([0-9]+) tests? in [^\n]+$',test.stdout,re.M)
        require(test.returncode==0 and len(matches)==1 and test.stdout.rstrip().endswith(b'OK'),
                'Host checker tests failed')
        audit = check_log(LOG.read_text(),BENCH.read_text())
        verify(pins)
        save(out/'audit.json',audit)
        save(out/'source-pins.json',pins)
        result.update(state=STATE,pre_post_pins_match=True,checked_inputs=len(pins),
                      source_pins_sha256=digest(out/'source-pins.json'),
                      original_worker_result=str(WORKER/'result.json'),original_worker_result_sha256=WORKER_SHA,
                      first_compile_result=str(FIRST/'result.json'),first_compile_result_sha256=FIRST_SHA,
                      raw_log=str(LOG),raw_log_sha256=LOG_SHA,dut_sha256=DUT_SHA,
                      observed_cases=5,checks=52,mismatches=3,passing_controls=4,
                      host_tests_passed=int(matches[0]),inherited_counts=counts,
                      limitations=['Refill-input injection with real DTLB hits; no cold PTW walk',
                                   'Permission bug reproduced, not design PASS or verified coverage',
                                   'No SoC/AXI/CSR-write integration, RTL repair, or performance acceptance'],
                      scope='Exact existing fatal formatting only; independent field replay; raw log unchanged')
    except BaseException as exc:
        result['error'] = repr(exc)
        raise
    finally:
        result['artifacts'] = {str(path):digest(path) for path in out.iterdir() if path.is_file()}
        save(out/'result.json',result)
    print(json.dumps(dict(state=result['state'],rtl_functional_status=result['rtl_functional_status'],
                          result=str(out/'result.json'),result_sha256=digest(out/'result.json')),indent=2))


if __name__=='__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output',type=Path,required=True)
    collect(parser.parse_args().output)
