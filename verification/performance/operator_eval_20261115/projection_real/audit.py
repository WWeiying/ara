#!/usr/bin/env python3
"""Host-only frozen-delivery and linked-constant audit. Never RTL/performance proof."""
import argparse
import csv
import io
import json
from pathlib import Path
import subprocess
import sys
import tarfile

sys.dont_write_bytecode=True
from contract import HERE,ROOT,TOOLCHAIN,cases,owned_output
from check import require,digest,check_run,parse_log
from test_projection import fixture


def command(argv):
    return subprocess.check_output(list(map(str,argv)),stderr=subprocess.STDOUT,timeout=120).decode()


def constants(build,work):
    elf=Path(build['elf'])
    header=command([TOOLCHAIN/'riscv64-unknown-elf-objdump','-h',elf]).splitlines()
    sections={}; load_end=0
    for index,line in enumerate(header):
        fields=line.split()
        if len(fields) < 7 or not fields[0].isdigit() or not fields[1].startswith('.'):
            continue
        size,base=int(fields[2],16),int(fields[3],16)
        flags=header[index+1]
        if 'ALLOC' in flags:
            load_end=max(load_end,base+size)
        if fields[1] in ('.data','.rodata'):
            path=work/(fields[1][1:]+'.bin')
            command([TOOLCHAIN/'riscv64-unknown-elf-objcopy','--dump-section',fields[1]+'='+str(path),elf])
            sections[fields[1]]=(base,path.read_bytes())
    require(load_end <= 0x80100000,'Archived 1MiB linker capacity exceeded')
    require('.bss.weights' not in ' '.join(header),'Duplicate BSS weight payload')
    symbols={}
    for line in command([TOOLCHAIN/'riscv64-unknown-elf-nm','-n','--defined-only',elf]).splitlines():
        fields=line.split()
        if len(fields) == 3:
            symbols[fields[2]]=int(fields[0],16)
    blobs=dict(eval_input=Path(build['plan_path']).parent/'input_f32.bin',eval_weights=Path(build['weights_path']),
        eval_expected=Path(build['comparisons']['OUT']['path']),eval_q8=Path(build['comparisons']['Q8']['path']),
        eval_packed=Path(build['comparisons']['PACK']['path']),guard_golden=Path(build['comparisons']['GUARD']['path']))
    for name,path in blobs.items():
        expected=path.read_bytes(); address=symbols[name]
        matches=[raw[address-base:address-base+len(expected)] for base,raw in sections.values()
                 if base <= address and address+len(expected) <= base+len(raw)]
        require(matches == [expected],'Linked input/golden not exact: '+name)
    base,raw=sections['.data']; offset=symbols['weights']-base
    require(symbols['eval_weights'] == symbols['weights']+64 and raw[offset:offset+64] == bytes([0xa5])*64 and
            raw[offset+64+len(blobs['eval_weights'].read_bytes()):offset+128+len(blobs['eval_weights'].read_bytes())]
            == bytes([0xa5])*64,'Single-copy weight guard layout')
    return len(blobs),load_end-0x80000000


def audit(path):
    path=owned_output(path)
    work=path/'asset-audit'; require(not work.exists(),'Fresh audit evidence required')
    pins=json.loads((path/'runner-source-pins.json').read_text())
    for name,sha in pins.items():
        require(digest(name) == sha,'Frozen asset drift: '+name)
    require(not any('/operator_eval_20261115/formats/' in name or name.endswith(('PLAN.md','EXPERIMENT_MATRIX_ZH.md'))
                    for name in pins),'Sealed sibling/parent plan dependency')
    local=[name for name in pins if name.startswith(str(ROOT)+'/') and not name.startswith(str(HERE)+'/')]
    require(local == [str(ROOT/'AGENTS.md')],'Working production software dependency')
    manifest=json.loads((path/'manifest.json').read_text())['cases']
    require({c['id'] for c in manifest} == {c['id'] for c in cases()},'Expected four pairs only')
    work.mkdir(); pairs={}; checked=0; rows=[]
    for entry in manifest:
        args=entry['checker']; directory=Path(args[args.index('--build')+1])
        build=json.loads((directory/'build.json').read_text()); c=build['case']
        require(pins.get(str(directory/'build.json')) == digest(directory/'build.json'),'Unsealed receipt')
        casework=work/c['id']; casework.mkdir()
        count,footprint=constants(build,casework); checked+=count
        _,text=fixture(c,build)
        log=casework/'synthetic-host-test.log'; log.write_text(text)
        require(check_run(log,directory)['state'] == 'PASS','Synthetic checker positive self-test')
        try:
            parse_log(text.replace('mismatches=0','mismatches=1',1),build)
        except ValueError:
            pass
        else:
            raise ValueError('Comparator mutation accepted')
        pairs.setdefault((c['phase'],c['operator']),{})[c['backend']]=(directory,build)
        rows.append(dict(id=c['id'],operator=c['operator'],phase=c['phase'],format=c['format'],m=c['m'],n=c['n'],
            k=c['k'],backend=c['backend'],k_blocks=c['k_blocks'],full_k=True,requantized=False,
            expected_fflags=build['plan']['flags'],expected_quant_vcsr=2,image_bytes=footprint,
            state='BUILT_NOT_EXECUTED',measured_cycles=''))
    for pair in pairs.values():
        nd,nb=pair['native']; rd,rb=pair['rvv_x32']
        for name in ('input_f32.bin','weights_row.bin','expected_q8.bin','expected.bin'):
            require((nd/name).read_bytes() == (rd/name).read_bytes(),'Unequal pair source/golden')
        require(nb['output_policy'] == rb['output_policy'] and nb['numeric_contract'] == rb['numeric_contract'],
                'Unequal pair comparison policy')
    with tarfile.open(path/'goldens.tar') as tar:
        for member in tar.getmembers():
            require(member.isfile() and tar.extractfile(member).read() == (path/member.name).read_bytes(),
                    'Golden archive mismatch')
    report=dict(state='ASSETS_READY_NOT_EXECUTED',pairs=4,firmware_cases=8,linked_blobs_checked=checked,
        host_unit_tests='python-tests.log',comparator_mutations=dict(bytes=28032,outputs=256),
        synthetic_checks=dict(positive=8,rejected=8,scope='HOST SELF-TEST ONLY; synthetic cycles/counters NOT RTL results'),
        cases=rows,production_working_software_inputs=[],sealed_formats_dependency=False,parent_plan_pinned=False,
        source_pins_sha256=digest(path/'source-pins.json'),runner_source_pins_sha256=digest(path/'runner-source-pins.json'),
        memory='Single guarded .data weight copy, each ELF fits archived 1MiB link region; no enlarged RAM/configuration',
        flags_and_csr='Independent native flags in case table; seeds0/8; postquant VCSR2 preserved, VSTART0. Runtime pending.',
        timing='Full quant/pack/admit/execute/drain; all comparisons/UART outside ROI; no measured cycles',
        limitations=['Historical emulator captures establish operands only, not current RTL correctness/performance',
            'Real Decode position40; Prefill captures first four distinct rows, not Decode duplication',
            'Native quantized GGUF tensors, not original F16; no requantization',
            'N64/128 independent output crops retain full K; not full output width or whole-model execution',
            'Current parent image identity, protocol and actual QBS command/ROI gates still required'])
    (path/'asset-audit.json').write_text(json.dumps(report,indent=2,sort_keys=True)+'\n')
    data=io.StringIO(); writer=csv.DictWriter(data,fieldnames=list(rows[0])); writer.writeheader(); writer.writerows(rows)
    (path/'preparation.csv').write_text(data.getvalue())
    print(json.dumps({key:report[key] for key in ('state','pairs','firmware_cases','linked_blobs_checked',
        'synthetic_checks','production_working_software_inputs')},indent=2))


if __name__ == '__main__':
    p=argparse.ArgumentParser(description=__doc__,allow_abbrev=False)
    p.add_argument('--build',type=Path,required=True)
    audit(p.parse_args().build)
