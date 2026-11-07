#!/usr/bin/env python3
"""Reuse exact compiled objects after diagnosing duplicated included assembly."""
import argparse
import json
import os
from pathlib import Path
import subprocess

from audit import digest, require, verify_pins
from prepare_wide_soc import RUNS, HERE
from run_supply_sdk import bind
from run_wide_soc_smoke import elf_admission
from build_rms_norm_native import link_archives
from build_f16_native import DATA, DATA_SHA, CC

FAILED=RUNS/'e2e_qwen3_f16_phase_build_20261106_01'


def run(output):
    out=output.absolute()
    require(out==out.resolve() and out.is_relative_to(RUNS),'Fresh sole-verification output required')
    out.mkdir(parents=True,exist_ok=False);pins={};commands=[]
    report=dict(state='PREPARING',target_executed=False,performance_measured=False,rtl_changed=False,
                production_library_changed=False,whole_model=False)
    env={k:v for k,v in os.environ.items() if k not in ('LD_PRELOAD','LIBRARY_PATH','COMPILER_PATH','GCC_EXEC_PREFIX')}
    env.update(PATH='/usr/bin:/bin',LC_ALL='C')
    def pin(path,sha=None):bind(pins,path,sha)
    def command(argv,label):
        argv=list(map(str,argv));pin(argv[0]);verify_pins(pins)
        commands.append(dict(label=label,argv=argv));(out/'commands.json').write_text(json.dumps(commands,indent=2)+'\n')
        child=subprocess.run(argv,cwd=out,env=env,capture_output=True,timeout=180)
        (out/(label+'.log')).write_bytes(child.stdout+child.stderr)
        require(child.returncode==0,label+' failed');verify_pins(pins)
        return child.stdout.decode()
    try:
        pin(FAILED/'build.json');old=json.loads((FAILED/'build.json').read_text())
        require(old['state']=='FAIL' and old['error']=="ValueError('link failed; retain original log')",
                'Only the diagnosed original link failure is admissible')
        for collection in (json.loads((FAILED/'source-pins.json').read_text()),old['artifacts']):
            for path,sha in collection.items():pin(path,sha)
        pin(DATA/'result.json',DATA_SHA)
        for path in (Path(__file__),HERE/'f16_native_main.c',HERE/'check_f16_native.py',
                     HERE/'test_f16_native_check.py',HERE/'run_f16_native.py',HERE/'test_run_f16_native.py'):pin(path)
        native=FAILED/'inputs/akv/src/akv_v2_attention_rvv.S'
        text=native.read_text()
        for include in ('#include "../experimental/paired_heads/attention_rvv.S"',
                        '#include "../experimental/paired_heads/f32_pv/attention_rvv.S"'):
            require(text.count(include)==1,'Actual native assembly must include paired implementation exactly once')
        # Prove that the objects being dropped duplicate code already emitted
        # into native assembly, rather than changing the chosen arithmetic.
        objcopy=CC.with_name('riscv64-unknown-elf-objcopy')
        blobs=[]
        for name in ('akv_v2_attention_rvv','paired-decode','paired-prefill'):
            target=out/(name+'.text.bin')
            command([objcopy,'--dump-section','.text='+str(target),FAILED/(name+'.o'),
                     out/(name+'.audit-copy.o')],name+'-section')
            pin(target);blobs.append(target.read_bytes())
        require(all(blobs) and blobs[0]==blobs[1]+blobs[2],
                'Included pair code is not byte-identical to duplicated standalone objects')
        recipes=json.loads((FAILED/'commands.json').read_text())
        links=[r['argv'] for r in recipes if r['label']=='link'];require(len(links)==1,'Unique original link command')
        link=list(links[0]);dropped=[str(FAILED/(n+'.o')) for n in ('paired-decode','paired-prefill')]
        require(all(link.count(p)==1 for p in dropped),'Unique duplicate objects required')
        link=[v for v in link if v not in dropped]
        elf=out/'f16_real_attention.elf';link[link.index('-o')+1]=str(elf)
        link=['-Wl,-Map='+str(out/'link.map') if v.startswith('-Wl,-Map=') else v for v in link]
        command(link,'link');pin(elf)
        archives={p:sha for p,sha in pins.items() if Path(p).name in ('libm.a','libc.a','libgcc.a','libnosys.a')}
        linked=link_archives((out/'link.map').read_text(),archives)
        dis=command([CC.with_name('riscv64-unknown-elf-objdump'),'-d',elf],'disassembly')
        required=('akv_attention_execute_v2_native','akv_attention_execute_v2_prefill_native',
                  'f16_phase_execute_v2_native','f16_phase_execute_v2_prefill_native',
                  'akv_v2_compute_scores_f32_d128_gqa2_panel4','akv_experimental_pv_f16_pair',
                  'akv_experimental_pv_f32_pair')
        require(all(dis.count('<'+name+'>:')==1 for name in required),'Missing/duplicate native implementation')
        require('qbs_ref_execute' not in dis and 'akv_attention_execute_v2_reference' not in dis,
                'Functional reference leaked into native executable')
        loads=elf_admission(elf.read_bytes(),16)
        verify_pins(pins);(out/'source-pins.json').write_text(json.dumps(pins,indent=2)+'\n')
        report.update(state='REAL_QWEN3_F16_PHASE_ELF_BUILT_NOT_EXECUTED',elf=str(elf),elf_sha256=digest(elf),
            source_pins_sha256=digest(out/'source-pins.json'),post_pins_match=True,data=str(DATA),
            parent_failed_build=str(FAILED),parent_failure_preserved=True,
            duplicate_assembly_code_byte_identical=True,dropped_duplicate_objects=dropped,
            phase_preparation=str(RUNS/'e2e_f16_phase_prepare_20261106_01'),
            preload_segments=loads,linked_archives=linked,order=[0,1,1,0],trials=8,outputs_checked=66560,
            q_heads=2,kv_heads=1,head_dim=128,prefill_queries=64,decode_visible=137,
            pair_heads_enabled=True,pair_pv_enabled=True,timing_includes_csr_completion=True,
            decode_preparation_included=True,probe_perturbation_limit=.05,default_runtime_promoted=False,
            control_clone_built_or_run=False,recompiled_objects=0,
            baseline='Unchanged frozen native SDK; reviewed pair leaves explicitly enabled',
            candidate='Exact-reversible observation-only native SDK clone',
            scope='One materialized real KV group, not complete GGML node or model')
    except BaseException as exc:
        report.update(state='FAIL',error=repr(exc));raise
    finally:
        if not (out/'source-pins.json').exists():
            (out/'source-pins.json').write_text(json.dumps(pins,indent=2)+'\n')
        report['artifacts']={str(p):digest(p) for p in out.iterdir() if p.is_file() and p.name!='build.json'}
        (out/'build.json').write_text(json.dumps(report,indent=2)+'\n')


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--output',type=Path,required=True)
    run(p.parse_args().output)
