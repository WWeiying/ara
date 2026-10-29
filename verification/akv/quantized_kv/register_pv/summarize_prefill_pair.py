#!/usr/bin/env python3
"""Accept a completed grouped-Prefill versus register-PV pair, not partial logs."""
import argparse
import json
from pathlib import Path
import sys

HERE=Path(__file__).resolve().parent
ROOT=HERE.parents[3]
sys.path.insert(0,str(HERE.parent))
from summarize_optimization_pair import digest,numeric_summary
from check_prefill_native import check_log


def require_build(build):
    if (build.get('state')!='BUILT_NOT_EXECUTED' or
        build.get('register_prefill') is not True or
        build.get('whole_call') is not True or
        build.get('value_binding')!='shared_rvv_q8_0' or
        build.get('kind') not in ('q4_0','q8_0') or
        build.get('commands_per_trial')!=4 or build.get('outputs_per_trial')!=1024 or
        build.get('rebuilt_objects')!=17 or build.get('reused_objects')!=0):
        raise ValueError('Not the complete grouped Prefill register-PV build')


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--run',type=Path,required=True)
    run=parser.parse_args().run.resolve(strict=True)
    receipt_path=run/'result.json'
    if not receipt_path.is_file():
        print(json.dumps(dict(state='NO_FINAL_RESULT',performance_accepted=False)))
        return
    receipt=json.loads(receipt_path.read_text())
    summary=numeric_summary(receipt,'prefill')
    pins=json.loads((run/'source-pins.json').read_text())
    for source,expected in pins.items():
        if digest(source)!=expected:raise ValueError('Changed sealed input: '+source)
    state=json.loads((run/'status.json').read_text())
    build=json.loads((Path(state['build'])/'build.json').read_text())
    require_build(build)
    if digest(build['elf'])!=receipt['elf_sha256'] or build['elf_sha256']!=receipt['elf_sha256']:
        raise ValueError('ELF identity')
    golden=ROOT/'verification/out/quant-prefill-capture-20261028-01'/build['kind']/'prefill/block/kqv_out-0.bin'
    log=run/'work/run.vcs.log'
    measured=check_log(log.read_text(),golden.read_bytes(),int(build['kind']=='q4_0'))
    if measured!=receipt['measured']:raise ValueError('Replayed measurement disagrees')
    summary.update(mechanism='register-prefill',baseline='current_grouped_shared_rvv',
        key_format=build['kind'],value_format='q8_0',run=str(run),
        checker_replayed=True,elf_sha256=receipt['elf_sha256'],
        receipt_sha256=digest(receipt_path),log_sha256=digest(log))
    print(json.dumps(summary,indent=2))


if __name__=='__main__':main()
