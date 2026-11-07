#!/usr/bin/env python3
"""Finish the sealed F16 build using function-byte, not section-padding identity."""
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
from relink_f16_native import FAILED

DECODE=('akv_experimental_qk_f16_pair_panel4','akv_experimental_pv_f16_pair')
PREFILL=('akv_experimental_pv_f32_pair',)


def function_bytes(raw,symbols,names,only=False):
    found={}
    rows=[r.split() for r in symbols.splitlines() if r.strip()]
    if only:require({r[0] for r in rows}==set(names),'Unexpected duplicate object symbols')
    for row in rows:
        if row[0] not in names:continue
        require(len(row)==4 and row[1]=='T' and row[0] not in found,'Unique sized text function required')
        start,size=int(row[2],16),int(row[3],16)
        require(size>0 and start+size<=len(raw),'Function outside actual text section')
        found[row[0]]=raw[start:start+size]
    require(set(found)==set(names),'Missing paired functions')
    return found


def run(output):
    out=output.absolute();require(out==out.resolve() and out.is_relative_to(RUNS),'Fresh sole verification output')
    out.mkdir(parents=True,exist_ok=False);pins={};commands=[]
    result=dict(state='PREPARING',target_executed=False,performance_measured=False,rtl_changed=False,
                production_library_changed=False,whole_model=False)
    def pin(p,sha=None):bind(pins,p,sha)
    env={k:v for k,v in os.environ.items() if k not in ('LD_PRELOAD','LIBRARY_PATH','COMPILER_PATH','GCC_EXEC_PREFIX')}
    env.update(PATH='/usr/bin:/bin',LC_ALL='C')
    def command(argv,label):
        argv=list(map(str,argv));pin(argv[0]);verify_pins(pins)
        commands.append(dict(label=label,argv=argv));(out/'commands.json').write_text(json.dumps(commands,indent=2)+'\n')
        child=subprocess.run(argv,cwd=out,env=env,capture_output=True,timeout=180)
        (out/(label+'.log')).write_bytes(child.stdout+child.stderr)
        require(child.returncode==0,label+' failed');verify_pins(pins)
        return child.stdout.decode()
    try:
        pin(FAILED/'build.json');old=json.loads((FAILED/'build.json').read_text())
        require(old['state']=='FAIL' and old['error']=="ValueError('link failed; retain original log')",'Wrong original failure')
        for values in (json.loads((FAILED/'source-pins.json').read_text()),old['artifacts']):
            for p,sha in values.items():pin(p,sha)
        for p in (Path(__file__),HERE/'test_complete_f16_native.py',HERE/'check_f16_native.py',
                  HERE/'test_f16_native_check.py',HERE/'run_f16_native.py',HERE/'test_run_f16_native.py'):pin(p)
        pin(DATA/'result.json',DATA_SHA)
        groups={}
        for name,names,only in (('akv_v2_attention_rvv',DECODE+PREFILL,False),
                                ('paired-decode',DECODE,True),('paired-prefill',PREFILL,True)):
            obj=FAILED/(name+'.o');target=out/(name+'.text.bin')
            command([CC.with_name('riscv64-unknown-elf-objcopy'),'--dump-section','.text='+str(target),
                     obj,out/(name+'.audit-copy.o')],name+'-section');pin(target)
            symbols=command([CC.with_name('riscv64-unknown-elf-nm'),'-S','--format=posix','-g','--defined-only',obj],name+'-symbols')
            reloc=command([CC.with_name('riscv64-unknown-elf-readelf'),'-rW',obj],name+'-relocations')
            require('There are no relocations in this file.' in reloc,'Relocations require separate identity analysis')
            groups[name]=function_bytes(target.read_bytes(),symbols,names,only)
        require(groups['akv_v2_attention_rvv']=={**groups['paired-decode'],**groups['paired-prefill']},
                'Function instruction bytes differ; do not substitute arithmetic')
        recipes=json.loads((FAILED/'commands.json').read_text());links=[r['argv'] for r in recipes if r['label']=='link']
        require(len(links)==1,'Unique original link recipe required');link=list(links[0])
        dropped=[str(FAILED/(n+'.o')) for n in ('paired-decode','paired-prefill')]
        require(all(link.count(p)==1 for p in dropped),'Duplicate object inventory changed')
        link=[v for v in link if v not in dropped];elf=out/'f16_real_attention.elf'
        link[link.index('-o')+1]=str(elf)
        link=['-Wl,-Map='+str(out/'link.map') if v.startswith('-Wl,-Map=') else v for v in link]
        command(link,'link');pin(elf)
        archives={p:sha for p,sha in pins.items() if Path(p).name in ('libm.a','libc.a','libgcc.a','libnosys.a')}
        linked=link_archives((out/'link.map').read_text(),archives)
        dis=command([CC.with_name('riscv64-unknown-elf-objdump'),'-d',elf],'disassembly')
        for name in (*DECODE,*PREFILL,'akv_attention_execute_v2_native','akv_attention_execute_v2_prefill_native',
                     'f16_phase_execute_v2_native','f16_phase_execute_v2_prefill_native',
                     'akv_v2_compute_scores_f32_d128_gqa2_panel4'):
            require(dis.count('<'+name+'>:')==1,'Missing/duplicate actual native implementation')
        require('qbs_ref_execute' not in dis and 'akv_attention_execute_v2_reference' not in dis,'Reference path leaked into ELF')
        loads=elf_admission(elf.read_bytes(),16)
        verify_pins(pins);(out/'source-pins.json').write_text(json.dumps(pins,indent=2)+'\n')
        result.update(state='REAL_QWEN3_F16_PHASE_ELF_BUILT_NOT_EXECUTED',elf=str(elf),elf_sha256=digest(elf),
            source_pins_sha256=digest(out/'source-pins.json'),post_pins_match=True,data=str(DATA),
            parent_failed_build=str(FAILED),parent_failure_preserved=True,
            duplicate_function_bytes_identical=True,standalone_trailing_alignment_padding_excluded=True,
            dropped_duplicate_objects=dropped,preload_segments=loads,linked_archives=linked,
            phase_preparation=str(RUNS/'e2e_f16_phase_prepare_20261106_01'),
            order=[0,1,1,0],trials=8,outputs_checked=66560,q_heads=2,kv_heads=1,head_dim=128,
            prefill_queries=64,decode_visible=137,pair_heads_enabled=True,pair_pv_enabled=True,
            timing_includes_csr_completion=True,decode_preparation_included=True,probe_perturbation_limit=.05,
            default_runtime_promoted=False,control_clone_built_or_run=False,recompiled_objects=0,
            baseline='Unchanged frozen native SDK, paired heads and PV enabled',
            candidate='Exact-reversible observation-only native SDK clone',
            scope='One real materialized KV group, not a full GGML node or model')
    except BaseException as exc:
        result.update(state='FAIL',error=repr(exc));raise
    finally:
        if not (out/'source-pins.json').exists():(out/'source-pins.json').write_text(json.dumps(pins,indent=2)+'\n')
        result['artifacts']={str(p):digest(p) for p in out.iterdir() if p.is_file() and p.name!='build.json'}
        (out/'build.json').write_text(json.dumps(result,indent=2)+'\n')


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--output',type=Path,required=True)
    run(p.parse_args().output)
