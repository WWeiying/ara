#!/usr/bin/env python3
"""Eight source-directed operand tests, strict Spike comparison and PASS-only DVE."""
import argparse
import csv
from concurrent.futures import ThreadPoolExecutor, as_completed
import json
import os
from pathlib import Path
import re
import shutil
import struct
import subprocess
import sys

import run_qbs_fault_layout_repair as repaired
import coverage_bitmap_delta as bitmaps

base= repaired.base
ROOT=base.ROOT
IMAGE_RUN=ROOT/'verification/out/qbs-fault-layout-repair-20261005-01'
SPIKE=Path('/home/wangwy/openproject/riscv-isa-sim-ara-dsa-vstart/build/spike')
NAMES=['vgap75_ext16_f2','vgap75_ext32_f4','vgap75_ext64_f2',
       'vgap75_ext64_f4','vgap75_ext64_f8','vgap75_red16','vgap75_red32','vgap75_red64']
sys.path.insert(0,str(ROOT/'verification'))
from ara_verify.spike_trace import compare_commit_prefix
from ara_verify.vector_commit import compare_vector_commits
from ara_verify.trace import validate_trace
from ara_verify.contract import check_contract_log
from ara_verify.random_rvv import _elf_symbol
from ara_verify.spike_trace import parse_spike_commits


def historical_target_hits(current, historical, zeros, old_sources, new_sources):
    hits=[]
    for point in zeros:
        if point['module'] not in ('operand_queue','ara_sequencer'):continue
        source=point['source'];scope=point['scope'];metric=point['metric']
        if old_sources.get(source)!=new_sources.get(source) or source not in new_sources:
            raise RuntimeError('target RTL changed; historical zeros are not comparable')
        before=historical['metrics'][metric][scope]
        after=current['metrics'][metric][scope]
        if (before['width'],before['checksum'])!=(after['width'],after['checksum']):
            raise RuntimeError('target coverage shape changed')
        index=int(point['raw_index']);bit=1 << (before['width']-1-index)
        if int(before['bits'],16)&bit:raise RuntimeError('historical zero inventory drift')
        if int(after['bits'],16)&bit:hits.append(point)
    return dict(scope='diagnostic hits of unchanged-module historical zeros; not a merged coverage percentage',
                count=len(hits),points=hits)


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output',type=Path,required=True)
    parser.add_argument('--cases',nargs='+',choices=NAMES,default=NAMES)
    args=parser.parse_args()
    names=list(dict.fromkeys(args.cases))
    base.check_service()
    out=base.checked_output(args.output);out.mkdir(exist_ok=False)
    state=dict(status='PREPARING',phase='freeze',workers=min(8,len(names)),total=len(names),cases={},
               image=str(IMAGE_RUN/'image/sim/simv'),historical_654_reused=False,
               coverage_status='PENDING')
    def save():base.save(out/'status.json',state)
    save()
    try:
        previous=base.read(IMAGE_RUN/'status.json')
        if previous['status']!='PASS' or len(previous['cases'])!=5:
            raise RuntimeError('five-case repaired-image gate required')
        image=IMAGE_RUN/'image/sim/simv';design=Path(str(image)+'.vdb')
        pins=base.read(IMAGE_RUN/'regression-source-pins.json')
        pins.update(base.read(IMAGE_RUN/'image/build-image.json'))
        pins.update(base.pins([Path(__file__),Path(bitmaps.__file__),SPIKE,
             ROOT/'verification/ara_verify/spike_trace.py',
             ROOT/'verification/ara_verify/vector_commit.py',
             ROOT/'verification/coverage/run_dve_coverage.sh',
             ROOT/'verification/coverage/export_dve_coverage.tcl']))
        source=ROOT/'apps/riscv-tests/isa/rv64uv'
        pins.update(base.pins([source/(name+'.c') for name in NAMES]))
        pins.update(base.pins([source/'vgap75_ext_body.h',source/'vgap75_red_body.h']))
        baseline=[]
        for name in repaired.NAMES:
            directory=IMAGE_RUN/'results'/name
            repaired.audit(directory,name)
            baseline.append(directory/'code.vdb')
            pins.update(base.pins([directory/'audit.json',directory/'input.elf',
                directory/'commit_trace.csv',directory/'vector_trace.csv',directory/'run.vcs.log']))
        for db in [design,*baseline]:
            pins.update(base.pins(p for p in db.rglob('*') if p.is_file()))
        readelf=Path('/home/wangwy/openproject/ara/install/riscv-llvm/bin/llvm-readelf')
        pins.update(base.pins([readelf]))
        historical=ROOT/'verification/out/closure90-current-20261005-01/combined-bits.json'
        zero_file=ROOT/'verification/out/closure90-zero-inventory-654-20261005-01/zeros.csv'
        old_source_file=ROOT/'verification/out/repaired-aligned-build-20260930-01/build-source-pins.json'
        pins.update(base.pins([historical,zero_file,old_source_file]))
        compiler=readelf.parent/'clang'
        startup=ROOT/'verification/tests/gap75_start.S'
        linker=ROOT/'verification/tests/gap75.ld'
        pins.update(base.pins([compiler,startup,linker]))
        pins.update(base.pins(p for p in (ROOT/'apps/riscv-tests/isa/macros').rglob('*') if p.is_file()))
        for name in names:
            directory=out/'results'/name;directory.mkdir(parents=True)
            compile_cmd=[str(compiler),'--target=riscv64-unknown-elf','-march=rv64gcv_zfh_zvfh',
                '-mabi=lp64d','-mcmodel=medany','-mno-relax','-msmall-data-limit=0',
                '-O2','-fno-vectorize','-fno-slp-vectorize','-ffreestanding',
                '-DG75_NO_PRINT','-D__SPIKE__','-DVLEN=1024','-DNR_LANES=4',
                '-I'+str(ROOT/'apps/riscv-tests/isa/macros/vector'),
                '-I'+str(ROOT/'apps/riscv-tests/env'),'-I'+str(ROOT/'apps/common'),
                '-fuse-ld=lld','-nostdlib','-T'+str(linker),
                str(startup),str(source/(name+'.c')),'-o',str(directory/'input.elf')]
            base.save(directory/'compile.command.json',dict(command=compile_cmd,timeout_s=120))
            with (directory/'compile.log').open('w') as stream:
                subprocess.run(compile_cmd,stdout=stream,stderr=subprocess.STDOUT,timeout=120,check=True)
            if struct.unpack_from('<Q',(directory/'input.elf').read_bytes(),24)[0]!=0x80000000:
                raise RuntimeError('ELF entry does not match VCS fixed boot address')
            data=(directory/'input.elf').read_bytes()
            phoff=struct.unpack_from('<Q',data,32)[0]
            phsize,phnum=struct.unpack_from('<HH',data,54)
            for i in range(phnum):
                segment=struct.unpack_from('<IIQQQQQQ',data,phoff+i*phsize)
                if segment[0]==1 and segment[5] and segment[4]%128:
                    raise RuntimeError('file-backed ELF segment violates SRAM preload alignment')
            pins.update(base.pins([directory/'input.elf']))
        base.save(out/'source-pins.json',pins);base.check(pins)
        state.update(status='RUNNING',phase='Spike preflight and VCS workers',
                     cases={name:dict(status='RUNNING',directory=str(out/'results'/name)) for name in names});save()

        def run(name):
            directory=out/'results'/name;elf=directory/'input.elf'
            row=dict(status='RUNNING',directory=str(directory))
            try:
                spike_cmd=[str(SPIKE),'--isa=rv64gcv_zfh_zvfh_zvl1024b','--priv=msu',
                           '--pmpregions=0','-l','--log-commits',str(elf)]
                base.save(directory/'spike.command.json',dict(command=spike_cmd,timeout_s=120))
                with (directory/'spike.stdout').open('w') as stdout,(directory/'spike.trace').open('w') as stderr:
                    subprocess.run(spike_cmd,stdout=stdout,stderr=stderr,timeout=120,check=True)
                tohost=_elf_symbol(elf,readelf,'tohost')
                result_address=_elf_symbol(elf,readelf,'g75_result')
                commits=parse_spike_commits(directory/'spike.trace')
                writes={address:value for c in commits for address,value in c.memory_accesses if value is not None}
                if writes.get(tohost)!=1 or not writes.get(result_address,0) or writes.get(result_address+4)!=0:
                    raise RuntimeError('Spike self-check signature/tohost did not pass')
                entry=struct.unpack_from('<Q',elf.read_bytes(),24)[0]
                command=[str(image),'-l','run.vcs.log','+ntb_random_seed=1',
                         '+PRELOAD='+str(elf),'+TESTCASE='+name,'+NO_FSDB',
                         '+COMMIT_TRACE='+str(directory/'commit_trace.csv'),
                         '+COMMIT_TOHOST=%x'%tohost,
                         '+VECTOR_TRACE='+str(directory/'vector_trace.csv'),
                         '-cm','line+cond+fsm+tgl+branch','-cm_dir',str(directory/'code.vdb'),
                         '-cm_name',name]
                base.save(directory/'rtl.command.json',dict(command=command,cwd=str(directory),timeout_s=1800))
                with (directory/'console.log').open('w') as stream:
                    subprocess.run(command,cwd=directory,stdout=stream,stderr=subprocess.STDOUT,
                                   timeout=1800,check=True)
                log=(directory/'run.vcs.log').read_text()
                self_check='Core Test *** SUCCESS ***' in log
                contract_errors=check_contract_log(directory/'run.vcs.log')
                scalar=compare_commit_prefix(directory/'spike.trace',directory/'commit_trace.csv',entry,
                    terminal_tohost_address=tohost,rvfi_store_data_layout='unshifted')
                base.save(directory/'scalar-comparison.json',scalar)
                vector=compare_vector_commits(directory/'spike.trace',directory/'commit_trace.csv',
                                              directory/'vector_trace.csv',entry)
                base.save(directory/'vector-comparison.json',vector)
                if not self_check or contract_errors:
                    raise RuntimeError('DUT self-check/contract did not pass; comparison evidence saved')
                if scalar['status'] not in ('MATCH','TERMINAL_TOHOST_MATCH'):
                    raise RuntimeError('scalar complete comparison: '+scalar['status'])
                if vector['status']!='PASS':raise RuntimeError('vector complete comparison: '+vector['status'])
                trace=validate_trace(directory/'commit_trace.csv')
                base.check(pins)
                row.update(status='PASS',scalar=scalar['status'],vector='PASS',trace=trace,
                    checks=writes[result_address],errors=0,
                    vector_bytes=vector['compared_bytes'],vdb=str(directory/'code.vdb'))
            except Exception as error:
                row.update(status='TIMEOUT' if isinstance(error,subprocess.TimeoutExpired) else 'FAIL',
                           reason=f'{type(error).__name__}: {error}')
            base.save(directory/'audit.json',row)
            return name,row

        with ThreadPoolExecutor(max_workers=min(8,len(names))) as pool:
            for future in as_completed([pool.submit(run,n) for n in names]):
                name,row=future.result();state['cases'][name]=row;save()
        base.check(pins)
        passed=[Path(state['cases'][n]['vdb']) for n in names if state['cases'][n]['status']=='PASS']
        state.update(phase='PASS-only DVE export',new_passed=len(passed),new_total=len(names));save()
        datasets={}
        for label,dbs in [('baseline',baseline),('combined',baseline+passed)]:
            listing=out/(label+'-vdbs.txt')
            listing.write_text(''.join(str(p)+'\n' for p in [design,*dbs]))
            datasets[label]=bitmaps.collect(listing)
            base.save(out/(label+'-bitmap.json'),datasets[label])
            with (out/(label+'-dve.log')).open('w') as stream:
                subprocess.run(['bash',str(ROOT/'verification/coverage/run_dve_coverage.sh'),
                    str(out/(label+'-report')),'--inputs-file',str(listing)],
                    cwd=ROOT,stdout=stream,stderr=subprocess.STDOUT,timeout=660,
                    env=dict(os.environ,DVE_COVERAGE_TIMEOUT='600',DVE_WAIVERS='off'),check=True)
        base.save(out/'raw-bitmap-delta.json',bitmaps.delta(datasets['baseline'],datasets['combined']))
        with zero_file.open() as stream:zeros=list(csv.DictReader(stream))
        base.save(out/'historical-target-hits.json',historical_target_hits(datasets['combined'],
            base.read(historical),zeros,base.read(old_source_file),
            base.read(IMAGE_RUN/'image/build-source-pins.json')))
        base.check(pins)
        state.update(status='COMPLETE',phase='complete',coverage_status='COMPLETE',
                     aggregate_passed=5+len(passed),
                     scope='current repaired RTL only; previous 654-case aggregate is historical')
        save()
    except Exception as error:
        state.update(status='STOPPED',reason=f'{type(error).__name__}: {error}');save();raise


if __name__=='__main__':main()
