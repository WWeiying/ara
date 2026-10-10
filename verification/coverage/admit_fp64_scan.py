"""Strict admission for source-pinned leading/exponent scans."""
import argparse
import csv
import json
from pathlib import Path
from admit_gap83_offline import ROOT, require, sha, save, bitmap
from ara_verify.spike_trace import compare_commit_prefix
from ara_verify.vector_commit import compare_vector_commits
from ara_verify.contract import check_contract_log

SPECS = {
    'gap89': dict(stem='gap89-div64-leading', base='gap88-offline-admitted-695',
                  count=695, instructions=84, bytes=21504, checks=952, signature=0x80002208),
    'gap90': dict(stem='gap90-div64-exp-lanes', base='gap89-offline-admitted-696',
                  count=696, instructions=240, bytes=61440, checks=2720, signature=0x80002308),
}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('case', choices=sorted(SPECS))
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    spec, out = SPECS[args.case], args.output.absolute()
    require(out.parent == ROOT / 'verification/out' and not out.exists(), 'Fresh output required')
    run = ROOT / ('verification/out/' + spec['stem'] + '-old-image-20261006-01')
    pre = ROOT / ('verification/out/' + spec['stem'] + '-preflight-20261006-01')
    base = ROOT / ('verification/out/' + spec['base'] + '-20261006-01')
    load = lambda path: json.loads(path.read_bytes())
    require(load(run / 'simulation-status.json')['status'] == 'SIMULATION_EXITED_NOT_ADMITTED', 'Incomplete run')
    state = load(base / 'status.json')
    require(state['status'] == 'PASS_RAW_UNION_HISTORICAL_ONLY' and
            state['aggregate_passed'] == spec['count'], 'Unadmitted baseline')
    old = load(base / 'combined-bits.json')
    require(len(old['tests']) == len(set(old['tests'])) == spec['count'], 'Wrong population')
    design = ROOT / 'verification/out/repaired-aligned-build-20260930-01/sim/simv.vdb'
    require((base / 'combined-inputs.txt').read_text().splitlines() ==
            [str(design), *old['tests']], 'Input mismatch')
    pins = dict(load(run / 'manifest.json')['pins'])
    for name, expected in load(base / 'evidence-pins.json').items():
        require(name not in pins or pins[name] == expected, 'Conflicting evidence pins')
        pins[name] = expected
    for path in [Path(__file__).resolve(), ROOT / 'verification/coverage/admit_gap83_offline.py',
                 Path(bitmap.__file__), base / 'combined-bits.json', base / 'combined-inputs.txt',
                 base / 'status.json', base / 'evidence-pins.json', run / 'manifest.json',
                 run / 'simulation-status.json', run / 'run.vcs.log', run / 'console.log',
                 *run.glob('*.csv'), *sorted((ROOT / 'verification/ara_verify').glob('*.py')),
                 *sorted((run / 'code.vdb').rglob('*'))]:
        if path.is_file():
            pins[str(path.resolve())] = sha(path)

    def check():
        for path, expected in pins.items():
            require(sha(Path(path)) == expected, 'Evidence drift: ' + path)

    check()
    scalar = compare_commit_prefix(pre / 'spike.trace', run / 'commit_trace.csv', 0x80000000,
        terminal_tohost_address=0x80001000, rvfi_store_data_layout='unshifted')
    vector = compare_vector_commits(pre / 'spike.trace', run / 'commit_trace.csv',
                                   run / 'vector_trace.csv', 0x80000000)
    require(scalar['status'] == 'TERMINAL_TOHOST_MATCH' and scalar['ara_trap_events'] == 0, 'Scalar mismatch/trap')
    require(vector['status'] == 'PASS' and vector['compared_instructions'] == spec['instructions'] and
            vector['compared_bytes'] == spec['bytes'] and vector['skipped_unknown_bytes'] == 0 and
            vector['non_bit_exact_instructions'] == 0 and not vector['incomplete_requests'] and
            not vector['unretired_requests'] and not vector['trapped_requests'], 'Vector mismatch/incomplete')
    require(not check_contract_log(run / 'run.vcs.log'), 'Contract failure')
    require((run / 'run.vcs.log').read_text().count('Core Test *** SUCCESS ***') == 1, 'Software failure')
    with (run / 'commit_trace.csv').open() as stream:
        writes = {int(row['mem_addr'], 16): (int(row['mem_wmask'], 16), int(row['mem_wdata'], 16))
                  for row in csv.DictReader(stream)
                  if row['event'] == 'retire' and int(row['mem_wmask'], 16)}
    require(writes.get(spec['signature']) == (0x0f, spec['checks']) and
            writes.get(spec['signature'] + 4) == (0xf0, 0), 'DUT signature failure')
    check()
    out.mkdir()
    inputs = out / 'new-inputs.txt'
    with inputs.open('x') as stream:
        stream.write(str(design) + '\n' + str(run / 'code.vdb') + '\n')
    combined = bitmap.combine(old, bitmap.collect(inputs))
    require(combined['tests'] == [*old['tests'], str(run / 'code.vdb')], 'Union membership mismatch')
    delta = bitmap.delta(old, combined)
    check()
    for name, value in (('scalar-comparison.json', scalar), ('vector-comparison.json', vector),
                        ('combined-bits.json', combined), ('raw-bitmap-delta.json', delta),
                        ('evidence-pins.json', pins)):
        save(out / name, value)
    with (out / 'combined-inputs.txt').open('x') as stream:
        stream.write('\n'.join([str(design), *combined['tests']]) + '\n')
    save(out / 'status.json', dict(status='PASS_RAW_UNION_HISTORICAL_ONLY',
         aggregate_passed=spec['count'] + 1, new_passed=1, official_DVE_report=False,
         rtl_changed=False, new_RTL_signoff=False))
    print(json.dumps(dict(aggregate_passed=spec['count'] + 1, raw_delta=delta['metrics'])))


if __name__ == '__main__':
    main()
