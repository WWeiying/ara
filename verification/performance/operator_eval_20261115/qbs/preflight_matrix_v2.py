#!/usr/bin/env python3
"""Successor host-only full runnable QBS matrix preflight; no EDA or RTL run."""
import argparse
import json
from pathlib import Path
import re
import sys

sys.dont_write_bytecode = True
import prepare


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--output', required=True, type=Path)
    a = p.parse_args()
    out = a.output.resolve()
    base = prepare.helper()
    cat = prepare.catalog()
    base.require(out.parent == prepare.OUT.resolve() and not out.exists() and
                 re.fullmatch(r'operator_qbs_prepare_20261115_[A-Za-z0-9_]+',out.name), 'Fresh owned output required')
    out.mkdir()
    b = base.Builder(out)
    for file in (__file__, prepare.__file__, prepare.BASE, prepare.HERE/'oracle.c',
                 prepare.HERE/'cases.json', prepare.ROOT/'AGENTS.md'):
        b.pin(file)
    head = b.run('sdk-head',['git','-C',prepare.ROOT,'rev-parse','HEAD']).decode().strip()
    base.require(head == cat['sdk_policy']['commit'],'Unreviewed SDK source revision')
    sdk = out/'inputs/sdk'
    b.archive(prepare.ROOT,head,['software/qbs','apps/common/qbs_abi.h',
        'verification/qbs/qbs_ref.c','verification/qbs/qbs_ref.h'],sdk)
    for file in sdk.rglob('*'):
        if file.is_file():
            b.pin(file)
    flags = ['-std=c11','-O2','-fno-fast-math','-ffp-contract=off','-frounding-math',
             '-Wall','-Wextra','-Werror','-I'+str(sdk/'software/qbs/include'),
             '-I'+str(sdk/'verification/qbs')]
    reference, runtime = out/'reference.o',out/'runtime.o'
    b.compile('/usr/bin/gcc',flags,sdk/'verification/qbs/qbs_ref.c',reference)
    b.compile('/usr/bin/gcc',flags,sdk/'software/qbs/src/qbs_runtime.c',runtime)
    for name in ('qbs_context_admission_test','qbs_context_cost_test','qbs_cooperative_test'):
        obj,exe = out/(name+'.o'),out/name
        b.compile('/usr/bin/gcc',flags,sdk/('software/qbs/tests/'+name+'.c'),obj)
        b.run(name+'-link',['/usr/bin/gcc',obj,runtime,'-lm','-o',exe])
        b.run(name,[exe])
        b.pin(exe)
    results, seen = [], {}
    for case in cat['cases']:
        key = (case['source'],case['operator'],case['m'],case['n'],case['tile'])
        if key not in seen:
            directory = out/('shape_'+str(len(seen)))
            directory.mkdir()
            provenance = prepare.capture(case,b,base,directory)
            config = directory/'config.h'
            config.write_text(''.join(f'#define {k} {v}\n' for k,v in dict(
                EVAL_M=case['m'],EVAL_N=case['n'],EVAL_TILE=case['tile'],
                EVAL_STORAGE={1:1,4:2,8:3}[case['tile']],
                EVAL_PROFILE=case['profile'],EVAL_WB=144 if case['profile']==1 else 210).items()))
            obj,exe = directory/'oracle.o',directory/'oracle'
            b.compile('/usr/bin/gcc',flags+['-I'+str(directory)],prepare.HERE/'oracle.c',obj)
            b.run('oracle-link-'+str(len(seen)),['/usr/bin/gcc',obj,reference,runtime,'-lm','-o',exe])
            plan = json.loads(b.run('oracle-'+str(len(seen)),[exe,directory/'input_f32.bin',directory/'weights_row.bin',directory]))
            base.require(plan['context_eligible'] == (1 if case['m']==1 else 0),
                         'Unexpected full-K context admission')
            base.write_json(directory/'plan.json',plan)
            for file in directory.iterdir():
                if file.is_file():
                    b.pin(file)
            seen[key] = dict(plan=plan,provenance=provenance,data=str(directory))
        record = seen[key]
        results.append(dict(id=case['id'],backend=case['backend'],shape_key=list(key),
            data=record['data'],planned_commands=len(record['plan']['commands']),
            context_eligible=record['plan']['context_eligible'],requested_reuse=case['reuse'],
            effective_reuse=case['reuse'] if record['plan']['context_eligible'] else 'direct',
            native_flags=record['plan']['flags'],provenance=case['provenance']))
    for path,sha in b.pins.items():
        base.require(base.digest(path)==sha,'Host preflight source drift: '+path)
    base.write_json(out/'source-pins.json',b.pins)
    base.write_json(out/'report.json',dict(state='HOST_MATRIX_PREFLIGHT_PASS_NOT_EXECUTED',
        rtl_executed=False,performance_measured=False,sdk_commit=head,
        case_count=len(results),distinct_shape_count=len(seen),cases=results,
        format_gaps=[f for f in cat['format_coverage'] if f['status']=='gap_not_runnable'],
        host_test_logs=[str(out/(name+'.log')) for name in
            ('qbs_context_admission_test','qbs_context_cost_test','qbs_cooperative_test')],
        source_pins_sha256=base.digest(out/'source-pins.json')))
    print(str(out/'report.json'))


if __name__ == '__main__':
    main()
