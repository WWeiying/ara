#!/usr/bin/env python3
"""Build genuine F16 SDK original/probed ABBA; never start a simulator."""
import argparse
import json
import os
from pathlib import Path
import shlex
import subprocess

from audit import digest, require, verify_pins
from prepare_wide_soc import RUNS, HERE
from run_supply_sdk import bind
from run_wide_soc_smoke import elf_admission
from build_rms_norm_native import link_archives, TOOLCHAIN
from prepare_f16_phase import SOURCE_SHA, transform

GRAPH=RUNS/'e2e_output_graph_20261106_01'
SDK=GRAPH/'sdk/software/akv'
DATA=RUNS/'e2e_qwen3_f16_native_data_20261106_02'
DATA_SHA='0fb5797dfed0d5d6bfaaf1e7b611f110b9b0a625fa1b67977ba86ce7a9e3581a'
COMMON=RUNS/'e2e_qwen3_projection_native_build_20261106_03'
CC=TOOLCHAIN/'bin/riscv64-unknown-elf-gcc'


def build(output, phase_preparation):
    out=output.absolute();prep=phase_preparation.resolve(strict=True)
    require(out==out.resolve() and out.is_relative_to(RUNS),'Fresh sole-verification output required')
    out.mkdir(parents=True,exist_ok=False)
    pins={};commands=[]
    report=dict(state='PREPARING',target_executed=False,performance_measured=False,rtl_changed=False,
                production_library_changed=False,whole_model=False)
    env={k:v for k,v in os.environ.items() if k not in ('LD_PRELOAD','CPATH','C_INCLUDE_PATH',
         'CPLUS_INCLUDE_PATH','GCC_EXEC_PREFIX','COMPILER_PATH','LIBRARY_PATH')}
    env.update(PATH='/usr/bin:/bin',LC_ALL='C')
    def pin(path,sha=None):bind(pins,path,sha)
    def run(argv,label):
        argv=list(map(str,argv));pin(argv[0]);verify_pins(pins)
        commands.append(dict(label=label,argv=argv));report['state']=label.upper()
        (out/'commands.json').write_text(json.dumps(commands,indent=2)+'\n')
        (out/'status.json').write_text(json.dumps(report,indent=2)+'\n')
        child=subprocess.run(argv,cwd=out,env=env,capture_output=True,timeout=180)
        (out/(label+'.log')).write_bytes(child.stdout+child.stderr)
        commands[-1]['returncode']=child.returncode
        require(child.returncode==0,label+' failed; retain original log')
        verify_pins(pins)
        return child.stdout.decode()
    try:
        pin(DATA/'result.json',DATA_SHA)
        data=json.loads((DATA/'result.json').read_text())
        require(data['state']=='REAL_QWEN3_F16_SUBSETS_MAPPING_PASS_NOT_NATIVE_ACCEPTED' and
                data['post_pins_match'] and data['scale_bits']==0x3db504f3,'Real data acceptance differs')
        pin(DATA/'source-pins.json',data['source_pins_sha256'])
        for group in (json.loads((DATA/'source-pins.json').read_text()),data['artifacts']):
            for path,sha in group.items():pin(path,sha)
        pin(prep/'result.json');p=json.loads((prep/'result.json').read_text())
        require(p['state']=='F16_PHASE_OBSERVATION_CLONES_PREPARED_NOT_BUILT_NOT_EXECUTED' and
                p['original_source_sha256']==SOURCE_SHA and not p['target_executed'],
                'Observation-only clone preparation required')
        pin(prep/'source-pins.json',p['source_pins_sha256'])
        for group in (json.loads((prep/'source-pins.json').read_text()),p['artifacts']):
            for path,sha in group.items():pin(path,sha)
        pin(GRAPH/'source-pins.json')
        inventory=json.loads((GRAPH/'source-pins.json').read_text())
        originals={};copies={}
        for path,sha in inventory.items():
            source=Path(path)
            if not source.is_relative_to(SDK) or source.suffix not in ('.h','.c','.S'):continue
            pin(source,sha)
            destination=out/'inputs/akv'/source.relative_to(SDK)
            destination.parent.mkdir(parents=True,exist_ok=True)
            destination.write_bytes(source.read_bytes());pin(destination,sha)
            originals[str(destination)]=sha;copies[source.relative_to(SDK)]=destination
        require(digest(copies[Path('src/akv_v2_native_riscv.c')])==SOURCE_SHA,'Native source not frozen identity')
        observed,control,changes=transform(copies[Path('src/akv_v2_native_riscv.c')].read_text())
        require(observed==(prep/'native-observed.c').read_text() and
                control==(prep/'native-control.c').read_text(),'Observation transform replay differs')
        probe=out/'inputs/akv/src/native-observed.c';probe.write_text(observed);pin(probe)
        header=out/'f16_phase_probe.h';header.write_bytes((prep/'f16_phase_probe.h').read_bytes());pin(header)
        (out/'transform.json').write_text(json.dumps(changes,indent=2)+'\n');pin(out/'transform.json')
        for path in (Path(__file__),HERE/'f16_native_main.c',HERE/'test_f16_native_data.py',
                     HERE/'prepare_f16_native_data.py',HERE/'audit.py'):pin(path)
        common=json.loads((COMMON/'build.json').read_text())
        pin(COMMON/'build.json');pin(COMMON/'source-pins.json',common['source_pins_sha256'])
        pin(COMMON/'commands.json',common['artifacts'][str(COMMON/'commands.json')])
        common_pins=json.loads((COMMON/'source-pins.json').read_text())
        objects=[]
        for i in range(3,9):
            obj=COMMON/f'{i}.o';pin(obj,common['artifacts'][str(obj)]);objects.append(obj)
        records=json.loads((COMMON/'commands.json').read_text())
        old_link=next(r['argv'] for r in records if r['label']=='link')
        linker=Path(old_link[old_link.index('-T')+1]);pin(linker,common_pins[str(linker)])
        for tool in ('cc1','as','ld','collect2'):
            path=Path(run([CC,'-print-prog-name='+tool],'tool-'+tool).strip()).resolve(strict=True)
            require(path.is_relative_to(TOOLCHAIN),'Subprogram outside selected toolchain');pin(path)
        sdk=out/'inputs/akv'
        flags=['-march=rv64gcv_zfh_zvfh','-mabi=lp64d','-mcmodel=medany','-mno-relax','-O3','-DNDEBUG',
               '-fno-fast-math','-ffp-contract=off','-ffunction-sections','-fdata-sections','-std=gnu11',
               '-Wall','-Wextra','-Wno-unknown-pragmas','-I'+str(sdk/'include'),'-I'+str(out),
               '-I'+str(COMMON.parents[2]/'apps/common')]
        # The caller only consumes this accepted printf declaration; avoid
        # relying on an incidental -I directory outside the sealed inventory.
        printf=COMMON.parents[2]/'apps/common/printf.h'
        pin(printf,common_pins[str(printf)])
        jobs=[('caller',HERE/'f16_native_main.c'),('data',DATA/'data.S'),('observed',probe)]
        for name in ('akv_runtime.c','akv_decode.c','akv_features.c','akv_prefill_reference.c',
                     'akv_native_riscv.c','akv_v2_native_riscv.c','akv_v2_attention_rvv.S',
                     'akv_attention_rvv.S'):
            jobs.append((Path(name).stem,copies[Path('src')/name]))
        for label,relative in (('paired-decode','experimental/paired_heads/attention_rvv.S'),
                               ('paired-prefill','experimental/paired_heads/f32_pv/attention_rvv.S')):
            jobs.append((label,copies[Path(relative)]))
        for label,source in jobs:
            obj=out/(label+'.o');argv=[CC,*flags,'-c',source,'-o',obj]
            deps=run([CC,*flags,'-M','-MT','object',source],'deps-'+label)
            for name in shlex.split(deps.replace('\\\n',' ').split(':',1)[1]):
                path=Path(name).resolve(strict=True)
                require(str(path) in pins or path.is_relative_to(TOOLCHAIN),'Unreviewed dependency: '+str(path))
                pin(path,pins.get(str(path)))
            run(argv,'compile-'+label);pin(obj);objects.append(obj)
        archives={}
        for name in ('libm.a','libc.a','libgcc.a','libnosys.a'):
            path=Path(run([CC,*flags[:2],'-print-file-name='+name],'locate-'+name).strip()).resolve(strict=True)
            require(path.is_relative_to(TOOLCHAIN),'Runtime archive outside target toolchain')
            pin(path);archives[str(path)]=digest(path)
        elf=out/'f16_real_attention.elf'
        run([CC,*flags[:4],'-static','-nostdlib','-nostartfiles',*objects,'-Wl,--gc-sections',
             '-Wl,-Map='+str(out/'link.map'),'-T',linker,'-Wl,--start-group','-lm','-lc','-lgcc','-lnosys',
             '-Wl,--end-group','-o',elf],'link');pin(elf)
        linked=link_archives((out/'link.map').read_text(),archives)
        dis=run([CC.with_name('riscv64-unknown-elf-objdump'),'-d',elf],'disassembly')
        for name in ('akv_attention_execute_v2_native','akv_attention_execute_v2_prefill_native',
                     'f16_phase_execute_v2_native','f16_phase_execute_v2_prefill_native',
                     'akv_v2_compute_scores_f32_d128_gqa2_panel4','akv_experimental_pv_f16_pair',
                     'akv_experimental_pv_f32_pair'):
            require('<'+name+'>:' in dis,'Missing real native SDK symbol '+name)
        require('qbs_ref_execute' not in dis and 'akv_attention_execute_v2_reference' not in dis,
                'Functional reference leaked into native executable')
        loads=elf_admission(elf.read_bytes(),16)
        verify_pins(pins);(out/'source-pins.json').write_text(json.dumps(pins,indent=2)+'\n')
        report.update(state='REAL_QWEN3_F16_PHASE_ELF_BUILT_NOT_EXECUTED',elf=str(elf),elf_sha256=digest(elf),
            source_pins_sha256=digest(out/'source-pins.json'),post_pins_match=True,data=str(DATA),
            phase_preparation=str(prep),preload_segments=loads,linked_archives=linked,
            order=[0,1,1,0],trials=8,outputs_checked=66560,q_heads=2,kv_heads=1,head_dim=128,
            prefill_queries=64,decode_visible=137,pair_heads_enabled=True,pair_pv_enabled=True,
            timing_includes_csr_completion=True,decode_preparation_included=True,
            baseline='Unchanged frozen native SDK; strongest reviewed pair leaves explicitly enabled',
            candidate='Exact-reversible observation-only native SDK clone',
            probe_perturbation_limit=.05,default_runtime_promoted=False,
            control_clone_built_or_run=False,scope='One materialized real KV group, not full GGML node or model',
            reused_runtime_objects=6,rebuilt_objects=len(jobs),original_failures_preserved=True)
    except BaseException as exc:
        report.update(state='FAIL',error=repr(exc));raise
    finally:
        if not (out/'source-pins.json').exists():
            (out/'source-pins.json').write_text(json.dumps(pins,indent=2)+'\n')
        report['artifacts']={str(p):digest(p) for p in out.rglob('*') if p.is_file() and p.name not in ('build.json','status.json')}
        (out/'build.json').write_text(json.dumps(report,indent=2)+'\n')
        (out/'status.json').write_text(json.dumps(report,indent=2)+'\n')


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--output',type=Path,required=True)
    p.add_argument('--phase-preparation',type=Path,required=True)
    a=p.parse_args();build(a.output,a.phase_preparation)
