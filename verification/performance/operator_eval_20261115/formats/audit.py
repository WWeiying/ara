#!/usr/bin/env python3
"""Host-only delivery audit. Synthetic logs here are tests, never RTL evidence."""
import argparse
import csv
import io
import json
from pathlib import Path
import subprocess
import sys
import tarfile

sys.dont_write_bytecode=True
from contract import ROOT, OUT, HERE, TOOLCHAIN, PROFILES, cases
from check import check_run, digest, parse_log, require
from test_formats import fixture


def command(argv):
    return subprocess.check_output(list(map(str,argv)),stderr=subprocess.STDOUT,timeout=120).decode()


def embedded_golden(build,work):
    elf=Path(build['elf'])
    sections=command([TOOLCHAIN/'riscv64-unknown-elf-objdump','-h',elf])
    fields=next(line.split() for line in sections.splitlines() if len(line.split()) > 3 and line.split()[1] == '.rodata')
    base=int(fields[3],16)
    symbols={}
    for line in command([TOOLCHAIN/'riscv64-unknown-elf-nm','-n','--defined-only',elf]).splitlines():
        fields=line.split()
        if len(fields) == 3:
            symbols[fields[2]]=int(fields[0],16)
    dump=work/'rodata.bin'
    command([TOOLCHAIN/'riscv64-unknown-elf-objcopy','--dump-section','.rodata='+str(dump),elf])
    raw=dump.read_bytes()
    blobs=dict(eval_input=Path(build['plan_path']).parent/'input_f32.bin',eval_weights=Path(build['weights_path']),
        eval_expected=Path(build['comparisons']['OUT']['path']),eval_q8=Path(build['comparisons']['Q8']['path']),
        eval_packed=Path(build['comparisons']['PACK']['path']),guard_golden=Path(build['comparisons']['GUARD']['path']))
    for symbol,path in blobs.items():
        offset=symbols[symbol]-base; expected=path.read_bytes()
        require(offset >= 0 and raw[offset:offset+len(expected)] == expected,'Linked golden/const mismatch: '+symbol)
    return len(blobs)


def audit(directory):
    directory=directory.resolve()
    require(directory.parent == OUT.resolve() and directory.name.startswith('operator_formats_prepare_20261115_'),
            'Owned preparation directory required')
    work=directory/'asset-audit'
    require(not work.exists(),'Fresh audit evidence required')
    pins=json.loads((directory/'runner-source-pins.json').read_text())
    for path,sha in pins.items():
        require(digest(path) == sha,'Pinned delivery drift: '+path)
    require(not any('EXPERIMENT_MATRIX_ZH.md' in path or path.endswith('/operator_eval_20261115/PLAN.md')
                    for path in pins),'Parent plan must not be pinned')
    local=[path for path in pins if path.startswith(str(ROOT)+'/') and not path.startswith(str(HERE)+'/')]
    require(local == [str(ROOT/'AGENTS.md')],'Dirty production workspace input: '+repr(local))
    manifest=json.loads((directory/'manifest.json').read_text())['cases']
    require({c['id'] for c in manifest} == {c['id'] for c in cases()},'Expected minimal full pair matrix')
    work.mkdir()
    pairs={}; golden_symbols=0; synthetic_checks=0; rejection_checks=0
    rows=[]
    for entry in manifest:
        checker=entry['checker']
        build_dir=Path(checker[checker.index('--build')+1])
        path=build_dir/'build.json'
        require(pins.get(str(path)) == digest(path),'Unsealed build receipt')
        build=json.loads(path.read_text()); c=build['case']
        casework=work/c['id']; casework.mkdir()
        golden_symbols+=embedded_golden(build,casework)
        _,text=fixture(c,build)
        log=casework/'synthetic-host-test.log'; log.write_text(text)
        result=check_run(log,build_dir)
        require(result['state'] == 'PASS','Synthetic parser positive test failed')
        synthetic_checks+=1
        bad=text.replace('mismatches=0','mismatches=1',1)
        try:
            parse_log(bad,build)
        except ValueError:
            rejection_checks+=1
        else:
            raise ValueError('Mutation incorrectly accepted')
        pairs.setdefault((c['format'],c['m']),{})[c['backend']]=(build_dir,build)
        rows.append(dict(case_id=c['id'],format=c['format'],m=c['m'],n=c['n'],k=c['k'],backend=c['backend'],
            baseline_kind=c['baseline_kind'],kernel=c['kernel_symbol'] if c['backend'] != 'native' else 'qbs_execute_with_options',
            input_class='actual_Q4_K_dequantized_then_requantized_prefill_slice',k_blocks=c['k_blocks'],
            activation_block_bytes=c['activation_block_bytes'],expected_fflags=build['plan']['flags'],
            expected_postquant_vcsr=c['quant_vcsr'],state=build['state'],measured_cycles=''))
    for (fmt,m),pair in pairs.items():
        nd,nb=pair['native']; rd,rb=pair['rvv_x32']
        for name in ('input_f32.bin','weights_row.bin','expected_q8.bin','expected.bin'):
            require((nd/name).read_bytes() == (rd/name).read_bytes(),'Unequal pair inputs/golden: '+fmt)
        require(nb['output_policy'] == rb['output_policy'] and nb['numeric_contract'] == rb['numeric_contract'],
                'Unequal pair acceptance policy')
    with tarfile.open(directory/'goldens.tar') as tar:
        for member in tar.getmembers():
            require(member.isfile(),'Non-file golden archive member')
            path=directory/member.name
            require(str(path) in pins and tar.extractfile(member).read() == path.read_bytes(),'Golden archive drift')
    report=dict(state='ASSETS_READY_NOT_EXECUTED',rtl_executed=False,performance_measured=False,
        host_unit_tests='python-tests.log; ten tests with all-profile schema/work/CSR/compact-proof mutations',
        c_comparator_mutations=dict(bytes=9344,outputs=256,nonfinite_rejection=True),
        synthetic_log_tests=dict(positive=synthetic_checks,rejected_mutations=rejection_checks,
            scope='HOST SELF-TEST ONLY; fabricated cycles and command counters are NOT performance/RTL results'),
        linked_const_symbols_byte_checked=golden_symbols,pairs_checked=len(pairs),compiled_firmware_cases=len(manifest),
        profiles=[dict(PROFILES[fmt],classification='controlled_two_stage_requantization_NOT_native_model_capture',
            m1_pair=[pair['case']['id'] for _,pair in pairs[fmt,1].values()],
            m4_pair=[pair['case']['id'] for _,pair in pairs[fmt,4].values()]) for fmt in PROFILES],
        independent_output_reference='Archived qbs_ref; not the upstream quantizer or RVV kernel',
        flags='Independent qbs_ref expects NX=1; native FCSR=1/9 with seeds0/8; runtime verification pending',
        vcsr='Q8_K postquant 2 (VXRM=1), Q8_0 postquant0; executor must preserve; VSTART=0; runtime verification pending',
        production_working_software_inputs=[],sdk_commit=next(iter(pairs.values()))['native'][1]['sdk_commit'],
        llama_commit=next(iter(pairs.values()))['native'][1]['llama_commit'],
        source_pins_sha256=digest(directory/'source-pins.json'),runner_source_pins_sha256=digest(directory/'runner-source-pins.json'),
        parent_plan_pinned=False,parent_image='operator_soc_20261115_activity_02',
        required_external_gates=['central max4 runner','current image identity','protocol closure','actual command/ROI traces',
            'target comparator PASS for all bytes/elements','first/repeat full-call metrics'],
        scope_gaps=['M1 is a prefill row slice, NOT real decode','N64 slice, not full output width or whole model',
            'Four new x32 candidates are not established/primary performance baselines',
            'No RTL or hardware execution; no speedup or FPGA admission claim'])
    (directory/'asset-audit.json').write_text(json.dumps(report,indent=2,sort_keys=True)+'\n')
    csv_text=io.StringIO(); writer=csv.DictWriter(csv_text,fieldnames=list(rows[0])); writer.writeheader(); writer.writerows(rows)
    (directory/'preparation.csv').write_text(csv_text.getvalue())
    print(json.dumps({key:report[key] for key in ('state','pairs_checked','compiled_firmware_cases',
        'linked_const_symbols_byte_checked','synthetic_log_tests','production_working_software_inputs')},indent=2))


if __name__ == '__main__':
    p=argparse.ArgumentParser(description=__doc__,allow_abbrev=False)
    p.add_argument('--build',type=Path,required=True)
    audit(p.parse_args().build)
