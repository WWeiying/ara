#!/usr/bin/env python3
"""Bounded discrimination of illegal reset-vtype versus initialized timing drain."""
import argparse
import os
from pathlib import Path
import re
import subprocess
import sys

sys.dont_write_bytecode=True
HERE=Path(__file__).resolve().parent
ROOT=HERE.parents[2]
sys.path.insert(0,str(ROOT/'verification/akv/paired_heads'))
import attention_run as s


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--build',type=Path,required=True)
    parser.add_argument('--output',type=Path,required=True)
    args=parser.parse_args(); build=args.build.resolve(strict=True); out=args.output.resolve()
    out.mkdir(parents=True,exist_ok=False)
    report=s.read_json(build/'build.json')
    s.require(report['state']=='PROBE_BUILT_NOT_EXECUTED' and report['post_pins_match'] is True and
        s.digest(build/'source-pins.json')==report['source_pins_sha256'],'Wrong probe build')
    pins=s.read_json(build/'source-pins.json'); s.merge_pins(pins,report['artifact_sha256'])
    image,accepted=s.checked_image(ROOT/'verification/out/qbacc-soc-accept-20261023-02',Path(report['simv']))
    s.require(image==report['accepted_image_pins'],'Wrong probe image'); s.merge_pins(pins,accepted)
    old=[]
    for tag in ('q8','q4'):
        path=ROOT/f'verification/out/akv-quantkv-attention-{tag}-20261024-02/work/console.log'
        text=path.read_text()
        matches=re.findall(r'^\[ARA_CONTRACT_TRACE\].*cycle=([0-9]+).*insn=42802057.*exc=1.*$',text,re.M)
        s.require(len(matches)==1 and 'QUANT_ATTN_BEGIN trial=0 shared=0' in text and
                  'QUANT_ATTN_RESULT' not in text,'Archived entry exception not established')
        old.append(dict(kind=tag,cycle=int(matches[0]),log=str(path),sha256=s.digest(path)))
        s.merge_pins(pins,s.hashes([path]))
    s.merge_pins(pins,s.hashes([Path(__file__),build/'build.json',build/'source-pins.json']))
    s.verify_pins(pins); s.atomic_json(out/'source-pins.json',pins)
    commands=[]
    def execute(argv,label,timeout=180):
        argv=list(map(str,argv)); commands.append(dict(argv=argv,cwd=str(out)))
        s.atomic_json(out/'commands.json',commands)
        with (out/(label+'.log')).open('x') as log:
            subprocess.run(argv,cwd=out,stdout=log,stderr=subprocess.STDOUT,check=True,timeout=timeout,
                env=dict(os.environ,PYTHONPATH=str(ROOT/'verification'),PYTHONDONTWRITEBYTECODE='1'))
        return (out/(label+'.log')).read_text()
    simv=Path(report['simv']); elf=Path(report['elf']); trace=out/'vector_trace.csv'
    execute([sys.executable,'-B','-m','ara_verify.vcs_source_manifest','--output',
        simv.parent/'vcs_source_manifest.json','--check'],'manifest-before',300)
    execute(['bash',ROOT/'hardware/scripts/llama_q4km_extract/check-sim-l2.sh',simv.parent,elf],'image-contract')
    text=execute([simv,'-no_save','+PRELOAD='+str(elf),'+TESTCASE=quant_attention_startup',
        '+NO_FSDB','+NO_INSTR_TRACE','+VECTOR_TRACE='+str(trace),
        '+ARA_CONTRACT_TRACE_LIMIT=2000000','+ARA_UVM_TRACE_LIMIT=2000000'],'simulation')
    expected='QUANT_ATTN_STARTUP before=8000000000000000 after=00000000000000d0 vl=1 fcsr=0 vcsr=5 errors=0'
    s.require(text.splitlines().count(expected)==1 and
        'Core Test *** SUCCESS *** (tohost = 0)' in text and
        not re.search(r'Fatal:|Error:|\b(?:FAIL|FAILED|TIMEOUT)\b',text,re.I),'Probe failed')
    for severity in ('UVM_ERROR','UVM_FATAL'):
        s.require(len(re.findall(r'^'+severity+r'\s*:\s*0$',text,re.M))==1,'Probe UVM failure')
    # This CSR/vector-only probe has no VLSU memory operation. Complete Attention
    # retains its independent require-axi/read/write gates in run_attention.py.
    execute([sys.executable,'-B','-m','ara_verify.uvm_dut','--require-events','--require-backend',
        '--vector-trace',trace,'--log',out/'simulation.log','--simv',simv,'--elf',elf,
        '--output',out/'uvm_result.json'],'checker',600)
    s.check_result(out/'uvm_result.json',report['elf_sha256'],image)
    uvm=s.read_json(out/'uvm_result.json')
    s.require(uvm['log_sha256']==s.digest(out/'simulation.log') and
        uvm['vector_trace_sha256']==s.digest(trace),'Protocol input mismatch')
    execute([sys.executable,'-B','-m','ara_verify.vcs_source_manifest','--output',
        simv.parent/'vcs_source_manifest.json','--check'],'manifest-after',300)
    s.verify_pins(pins)
    s.atomic_json(out/'result.json',dict(state='STARTUP_PROBE_PASS',simulator_exit_code=0,
        before_vill=1,after_vtype='d0',after_vl=1,fcsr=0,vcsr=5,
        vlsu_memory_work_in_probe=False,
        archived_entry_exceptions=old,post_pins_match=True,independent_protocol_checked=True,
        elf_sha256=report['elf_sha256'],source_pins_sha256=s.digest(out/'source-pins.json'),
        evidence_sha256=s.hashes([out/'simulation.log',trace,out/'uvm_result.json']),
        scope='Measurement helper startup only; no Attention numerical/performance acceptance'))
    print('STARTUP_PROBE_PASS reset_vill=1 initialized_drain_legal=1')


if __name__=='__main__':
    main()
