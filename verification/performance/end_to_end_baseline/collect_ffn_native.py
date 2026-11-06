#!/usr/bin/env python3
"""Re-audit the actual full-K FFN SDK pair before reporting cycle ratios."""
import argparse
import json
from pathlib import Path

from audit import digest, require, verify_pins
from check_ffn_native import check
from check_projection_native import fields
from collect_projection_native import COUNTERS, PHASES
from run_ffn_native import oracle


def collect(root, wide):
    from collect_matrix_soc import audit_build
    from run_output_native import s, accepted
    root = root.resolve(strict=True); report = json.loads((root/'result.json').read_text())
    require(report['state'] == 'PASS' and report['wide'] == wide and report['performance_measured'] and
            report['independent_protocol_checked'] and report['post_pins_match'], 'Incomplete FFN run')
    require(digest(root/'source-pins.json') == report['source_pins_sha256'], 'Pin-map drift')
    pins = json.loads((root/'source-pins.json').read_text()); checked = verify_pins(pins)
    build = Path(report['build']); program = json.loads((build/'build.json').read_text())
    require(program['state'] == 'REAL_QWEN3_FFN_SDK_BUILT_NOT_EXECUTED' and
            pins.get(str(build/'build.json')) == digest(build/'build.json') and
            report['elf_sha256'] == program['elf_sha256'] == digest(program['elf']), 'FFN build binding')
    simv = Path(json.loads((root/'status.json').read_text())['simv']); soc = audit_build(simv.parent.parent)
    require(soc['wide'] == wide and soc['image_pins'] == report['image_pins'] and
            s.hashes(s.image_files(simv)) == report['image_pins'], 'Image binding')
    text = (root/'work/run.vcs.log').read_text(); measured = check(text, wide, *oracle(build))
    require(measured == report['measured'], 'Raw SDK replay differs')
    accepted.protocol(root/'work', report['elf_sha256'], report['image_pins'])
    rows = [fields(line,'[QBS_PERF]') for line in text.splitlines() if line.startswith('[QBS_PERF] ')]
    require(all(k in row for row in rows for k in COUNTERS), 'Missing detailed counter')
    activity = [dict(part=p,counters={k:sum(c[k] for c in rows[p*4:p*4+4]) for k in COUNTERS},
                     phases={phase:sum(c['phase_'+phase+'_cycles'] for c in rows[p*4:p*4+4]) for phase in PHASES})
                for p in range(3)]
    verify_pins(pins)
    return dict(wide=wide,run=str(root),build=str(build),elf_sha256=report['elf_sha256'],
                measured=measured,activity=activity,checked_inputs=checked,
                result_sha256=digest(root/'result.json'),source_pins_sha256=report['source_pins_sha256'],
                log_sha256=digest(root/'work/run.vcs.log'),protocol_sha256=digest(root/'work/uvm_result.json'))


def compare(base, wide):
    require(base['wide'] == 0 and wide['wide'] == 1 and base['build'] == wide['build'] and
            base['elf_sha256'] == wide['elf_sha256'], 'Different workloads')
    a, b = base['measured'], wide['measured']
    require(a['commands'] == b['commands'] == 12 and a['useful_pairs'] == b['useful_pairs'] == 5242880 and
            a['dot_issue_count'] == 2*b['dot_issue_count'], 'Different useful work')
    for tag in ('parts','preparation'):
        require([(r['checksum'],r['fcsr']) for r in a[tag]] == [(r['checksum'],r['fcsr']) for r in b[tag]],
                'Output/payload/flags differ')
    for key in ('payload_bytes','weight_bytes','activation_bytes','useful_pairs','fp_uop_issue','accumulator_updates'):
        require(sum(r['counters'][key] for r in base['activity']) == sum(r['counters'][key] for r in wide['activity']),
                'Different service work: '+key)
    return dict(region_ratio=a['total']['region']/b['total']['region'],
                execution_ratio=a['total']['execution']/b['total']['execution'],
                preparation_cycles=[a['total']['preparation'],b['total']['preparation']],
                parts=[dict(part=p,baseline_execution=a['parts'][p]['execution'],
                            candidate_execution=b['parts'][p]['execution'],
                            ratio=a['parts'][p]['execution']/b['parts'][p]['execution']) for p in range(3)])


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--base',type=Path,required=True); parser.add_argument('--wide',type=Path,required=True)
    parser.add_argument('--output',type=Path,required=True); args = parser.parse_args()
    out = args.output.resolve(); out.mkdir(parents=True,exist_ok=False)
    result = dict(state='CHECKING',whole_model=False,area_measured=False,full_n=False,full_k=True)
    try:
        reports = [collect(args.base,0),collect(args.wide,1)]
        result.update(state='REAL_QWEN3_FFN_SDK_PAIR_REAUDITED',reports=reports,comparison=compare(*reports),
                      collector_sha256=digest(__file__),preparation_included=True,
                      scope='Real gate/up/down inputs, M4/N128/full K2048/2048/6144; not full-model timing')
    except BaseException as exc: result.update(state='FAIL',error=repr(exc)); raise
    finally: (out/'result.json').write_text(json.dumps(result,indent=2)+'\n')


if __name__ == '__main__': main()
