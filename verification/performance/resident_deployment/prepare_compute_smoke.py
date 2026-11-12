#!/usr/bin/env python3
"""Prepare one real-data compute smoke; does not run a simulator or Linux."""
import argparse
import hashlib
import importlib.util
import json
from pathlib import Path
import shutil
import struct
import subprocess

ROOT = Path(__file__).resolve().parents[3]
OUT = ROOT.parent/'ara_dsa_signoff_integration/verification/out'
HERE = Path(__file__).resolve().parent
PLATFORM = ROOT/'software/llama/platform/linux'
GNU = Path('/home/wangwy/llama/platforms/cva6-qemu/tools/bin')
ORACLE = ROOT/'verification/performance/resident_rvv/qk_shared/full_call_sdk/fixture.py'


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def main():
    p=argparse.ArgumentParser()
    p.add_argument('--compute-output', type=Path, required=True)
    p.add_argument('--core-sha256', required=True)
    p.add_argument('--output', type=Path, required=True)
    a=p.parse_args()
    out, compute=a.output.resolve(), a.compute_output.resolve()
    assert out.parent==compute.parent==OUT and out.name.startswith('resident_deployment_compute_smoke_') and not out.exists()
    core=compute/'module/sdk/ara_resident_compute_core.o'
    assert sha(core)==a.core_sha256
    out.mkdir()
    inputs=out/'inputs';inputs.mkdir()
    spec=importlib.util.spec_from_file_location('accepted_resident_oracle',ORACLE)
    oracle=importlib.util.module_from_spec(spec);spec.loader.exec_module(oracle)
    source,pins=oracle.inputs()
    pins={str(path):value for path,value in pins.items()}
    pins[str(ORACLE)]=sha(ORACLE)
    pins[str(core)]=sha(core)
    pins[str(Path(__file__).resolve())]=sha(__file__)
    case=dict(name='real_qwen3_prefix65',requested=1,dimension=128,heads=2,kv_heads=1,
              tokens=65,capacity=256,initial_flags=0)
    golden=oracle.reference(case,source[0])
    pins.update(golden['oracle_pins'])
    data=dict(query=bytes.fromhex(golden['query_half']), key=source[0]['key'][:65*256],
              value=source[0]['value'][:65*256],mask=source[0]['mask'][:130],
              output=oracle.pack(golden['bits'],32), flags=struct.pack('<I',golden['natural_flags']))
    assert struct.unpack('<I',struct.pack('<f',float.fromhex('0x1.6a09e6p-4')))[0]==0x3db504f3
    assembly=['.section .rodata',' .balign 64']
    for name,raw in data.items():
        file=inputs/(name+'.bin');file.write_bytes(raw)
        symbol='expected_'+name if name in ('output','flags') else 'capture_'+name
        assembly+=['.balign 64','.global '+symbol,symbol+':','.incbin '+json.dumps(str(file))]
        pins[str(file)]=sha(file)
    (inputs/'data.S').write_text('\n'.join(assembly)+'\n.section .note.GNU-stack,"",@progbits\n')
    for name in ('compute_smoke.c','compute_start.S','client.ld'):
        shutil.copyfile(HERE/name,inputs/name);pins[str(HERE/name)]=sha(HERE/name)
    shutil.copyfile(compute/'module/sdk/kernel_compute.h',inputs/'kernel_compute.h')
    shutil.copyfile(core,inputs/'compute.o')
    for file in inputs.iterdir():pins[str(file)]=sha(file)
    commands=[]
    def run(name,argv):
        rc=subprocess.run(list(map(str,argv)),cwd=out,text=True,stdout=subprocess.PIPE,
                          stderr=subprocess.STDOUT,timeout=120)
        (out/(name+'.log')).write_text(rc.stdout)
        commands.append(dict(name=name,argv=list(map(str,argv)),returncode=rc.returncode))
        assert not rc.returncode,(name,rc.stdout[-3000:])
        return rc.stdout
    flags=['-O2','-march=rv64gcv_zfh_zvfh','-mabi=lp64','-mcmodel=medany','-mno-relax',
        '-msmall-data-limit=0','-ffreestanding','-fno-builtin','-fno-stack-protector',
        '-fno-tree-loop-distribute-patterns','-fno-tree-vectorize','-fno-tree-slp-vectorize',
        '-I'+str(inputs),'-I'+str(PLATFORM/'sdk/shim'),'-fno-fast-math','-ffp-contract=off']
    objects=[inputs/'compute.o']
    for name in ('compute_smoke.c','compute_start.S','data.S'):
        obj=out/(name+'.o');run('build-'+name,[GNU/'riscv64-linux-gcc',*flags,'-c',inputs/name,'-o',obj]);objects.append(obj)
    elf=out/'compute-smoke.elf'
    run('link',[GNU/'riscv64-linux-gcc',*flags,'-nostdlib','-static','-T'+str(inputs/'client.ld'),*objects,'-o',elf])
    readelf=run('elf',[GNU/'riscv64-linux-readelf','-h',elf])
    assert 'soft-float ABI' in readelf
    assert all(sha(path)==value for path,value in pins.items())
    (out/'source-pins.json').write_text(json.dumps(pins,indent=2)+'\n')
    (out/'commands.json').write_text(json.dumps(commands,indent=2)+'\n')
    receipt=dict(state='REAL_KERNEL_COMPUTE_SMOKE_BUILT_NOT_EXECUTED',elf=str(elf),elf_sha256=sha(elf),
        core_sha256=sha(core),data_capture=str(oracle.DATA),dimension=128,heads=2,tokens=65,
        scale_bits=0x3db504f3,expected_flags=golden['natural_flags'],expected_outputs=golden['bits'],
        kernel_booted=False,board_executed=False,source_pins_sha256=sha(out/'source-pins.json'))
    (out/'build.json').write_text(json.dumps(receipt,indent=2)+'\n')
    print(json.dumps({k:v for k,v in receipt.items() if k!='expected_outputs'}))


if __name__=='__main__':main()
