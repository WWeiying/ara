#!/usr/bin/env python3
"""One bounded authentic Linux rebuild; supplement frozen READY without editing it."""
import ast
import hashlib
import json
from pathlib import Path
import shutil
import subprocess
import sys
import time

sys.dont_write_bytecode = True
OUT = Path(__file__).resolve().parent
PREP = OUT.parent
C = Path('/home/wangwy/fpga_runs/ara_hw_campaign_20261007_01')
PART = C/'rvv_permute_partitions01'
SOURCE = C/'rvv_small_gather02/rvv_small_gather_restart_e16_m1_ops0/original.c'
GENERATOR = Path('/home/wangwy/openproject/ara_dsa/hardware/fpga/ara_dsa_vcu118/linux/diagnostics/rvv_matrix/permutation.py')
CC = Path('/home/wangwy/openproject/cva6/cva6-sdk/buildroot/output/host/bin/riscv64-buildroot-linux-gnu-gcc')
LABEL = 'rvv_permute_restart_e8_m4_ops3'
OLD_SHA = 'f090f0d597b9e35a101a1f018a93ca9f61a04349c4243724f5c55e97094a7649'
ELF_SHA = 'a68279eaedf724eaf3efa03c71c6d039f40bc1d0c6d128b552d04e6e7ba4706b'


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def require(condition, message):
    if not condition:
        raise ValueError(message)


def save(path, value):
    with path.open('x') as stream:
        json.dump(value,stream,indent=2)
        stream.write('\n')


def verify(pins):
    for name,digest in pins.items():
        require(sha(Path(name))==digest,'Changed input: '+name)


def main():
    require(not (OUT/'command.json').exists() and not (OUT/'error.json').exists()
            and not (PREP/'READY02.json').exists(),'Fresh supplemental proof only; no retry')
    require(sha(PREP/'READY.json')==OLD_SHA,'Old READY identity changed')
    old=json.loads((PREP/'READY.json').read_text())
    verify(old['pins'])
    manifest=json.loads((PART/'manifest.json').read_text())
    case,=[c for c in manifest['cases'] if c['name']==LABEL]
    require(case['sha256']==ELF_SHA and case['operation_ids']==[3] and case['sew']==8
            and case['lmul']=='m4' and case['configurations']==2688,'Wrong archive child')
    require(sha(GENERATOR)==manifest['source_sha256']['permutation.py'],
            'Actual generator not archive hash')
    require(sha(SOURCE)==manifest['source_sha256']['permutation_oracle.c'],
            'Original C differs')
    archived_elf=PART/'release/binaries'/LABEL
    require(sha(archived_elf)==ELF_SHA,'Archived ELF differs')
    original=PREP/'prepared/gather_prefix_e8_m4_ops3/original'
    require(sha(original/'scenario.c')==sha(SOURCE) and
            sha(original/'operations.S')==sha(PART/LABEL/'operations.S') and
            sha(original/'operations.h')==sha(PART/LABEL/'operations.h'),
            'Old prepared original is not exact source/assembly/header')
    baseline=dict(old['pins'])
    for p in [PREP/'READY.json',PART/'manifest.json',SOURCE,GENERATOR,archived_elf,
              PART/LABEL/'operations.S',PART/LABEL/'operations.h',CC,
              CC.resolve(strict=True),CC.with_name(CC.name+'.br_real'),Path(__file__)]:
        baseline[str(p)]=sha(p)
    save(OUT/'input_pins.json',baseline)
    inputs=OUT/'original'
    inputs.mkdir()
    for src,name in [(SOURCE,'permutation_oracle.c'),
                     (PART/LABEL/'operations.S','operations.S'),
                     (PART/LABEL/'operations.h','operations.h')]:
        shutil.copyfile(src,inputs/name)
        require(sha(inputs/name)==sha(src),'Original copy differs')
    text=GENERATOR.read_text()
    candidates=[]
    for node in ast.walk(ast.parse(text)):
        if isinstance(node,ast.Call) and isinstance(node.func,ast.Attribute) and \
                isinstance(node.func.value,ast.Name) and node.func.value.id=='subprocess' \
                and node.func.attr=='run':
            segment=ast.get_source_segment(text,node)
            if "cross+'gcc'" in segment:
                candidates.append((node,segment))
    require(len(candidates)==1,'Ambiguous actual archive compiler command')
    node,segment=candidates[0]
    (OUT/'archived_command_source.txt').write_text(segment+'\n')
    binary=OUT/(LABEL+'.elf')
    # Evaluate only the hash-matched generator's command-list expression, never its build body.
    context=dict(cross=str(CC)[:-3],sew=8,restart=True,directory=inputs,
                 partitioned=True,ids=[3],source=inputs/'permutation_oracle.c',
                 asm=inputs/'operations.S',binary=binary)
    command=eval(compile(ast.Expression(node.args[0]),str(GENERATOR),'eval'),
                 {'__builtins__':{},'str':str,'int':int,'sum':sum},context)
    require(command[0]==str(CC) and '-DPERMUTE_OP_MASK=8' in command,
            'Derived command identity/opmask differs')
    version=subprocess.check_output([str(CC),'--version'],text=True,timeout=5)
    require('(Buildroot 2026.02) 14.3.0' in version,'Compiler version wrong')
    (OUT/'compiler_version.txt').write_text(version)
    save(OUT/'command.json',dict(command=command,timeout_seconds=30,
        generator=str(GENERATOR),generator_sha256=sha(GENERATOR),line=node.lineno,
        derivation='Actual hash-matched generator AST command, original shape/opmask substituted',
        compile_attempts=1,no_adapters=True,no_SoC_build=True,no_Spike_or_reference=True))
    started=time.monotonic()
    with (OUT/'compile.log').open('x') as stream:
        result=subprocess.run(command,stdout=stream,stderr=subprocess.STDOUT,timeout=30)
    elapsed=time.monotonic()-started
    save(OUT/'actual_exit.json',dict(returncode=result.returncode,elapsed_s=elapsed,
        command=command,compile_attempts=1,validated=False,automatic_retry=False))
    require(result.returncode==0,'Original rebuild actual nonzero exit')
    digest=sha(binary)
    proof=dict(status='PASS_FULL_ORIGINAL_LINUX_ELF_BYTE_IDENTICAL' if digest==ELF_SHA
        else 'BLOCKED_FULL_ORIGINAL_LINUX_ELF_MISMATCH',source_label=LABEL,
        original_linux_elf=str(archived_elf),original_linux_elf_sha256=ELF_SHA,
        rebuilt_linux_elf=str(binary),rebuilt_linux_elf_sha256=digest,
        entire_original_linux_binary_rebuild_proven=digest==ELF_SHA,
        actual_numeric_returncode=result.returncode,elapsed_s=elapsed,command=command,
        generator_sha256=sha(GENERATOR),compiler_driver=str(CC),
        compiler_wrapper_sha256=sha(CC),compiler_backend_sha256=sha(CC.with_name(CC.name+'.br_real')),
        original_c_sha256=sha(SOURCE),original_assembly_sha256=sha(inputs/'operations.S'),
        original_header_sha256=sha(inputs/'operations.h'),original_opmask=8,
        original_ready_sha256=OLD_SHA,old_ready_unchanged=True,
        compile_attempts=1,SoC_builds=0,Spike_launches=0,reference_reruns=0,
        original_scope_full_child2688_binary_identity_only=True,
        full_child_execution_accepted=False,unknown_stopped_tuple=None)
    verify(baseline)
    require(sha(PREP/'READY.json')==OLD_SHA,'Old READY changed during compile')
    proof['pins']={str(p):sha(p) for p in sorted(OUT.rglob('*')) if p.is_file()}
    save(OUT/'proof.json',proof)
    require(digest==ELF_SHA,'Exact ELF mismatch; stop, no second compile')
    successor=dict(old)
    successor.update(original_ready_path=str(PREP/'READY.json'),original_ready_sha256=OLD_SHA,
        supplement='Buildroot exact-original Linux ELF identity; retained SoC/reference unchanged',
        supersedes_only_old_unproven_full_binary_rebuild=True,
        entire_original_linux_binary_rebuild_proven=True,
        full_linux_rebuild_proof_path=str(OUT/'proof.json'),
        full_linux_rebuild_proof_sha256=sha(OUT/'proof.json'),
        new_Linux_compile_attempts=1,new_SoC_builds=0,new_Spike_launches=0,new_reference_reruns=0)
    successor['pins']=dict(baseline)
    successor['pins'].update({str(p):sha(p) for p in sorted(OUT.rglob('*')) if p.is_file()})
    verify(successor['pins'])
    save(PREP/'READY02.json',successor)
    print(proof['status'],'READY02_SHA='+sha(PREP/'READY02.json'),
          'PROOF_SHA='+sha(OUT/'proof.json'),'elapsed_s='+str(elapsed),flush=True)


if __name__=='__main__':
    try:
        main()
    except Exception as error:
        if not (OUT/'error.json').exists():
            save(OUT/'error.json',dict(status='SUPPLEMENT_STOPPED_NO_RETRY',error=repr(error)))
        raise
