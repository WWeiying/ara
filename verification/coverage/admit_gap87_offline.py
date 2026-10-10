"""Strict FP64 square-root admission; preserve all previous evidence."""
import argparse
import csv
import json
from pathlib import Path
from admit_gap83_offline import ROOT, require, sha, save, bitmap
from ara_verify.spike_trace import compare_commit_prefix
from ara_verify.vector_commit import compare_vector_commits
from ara_verify.contract import check_contract_log


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', type=Path, required=True)
    out = parser.parse_args().output.absolute()
    require(out.parent == ROOT / 'verification/out' and not out.exists(), 'Fresh output required')
    run = ROOT / 'verification/out/gap87-sqrt64-old-image-20261006-01'
    pre = ROOT / 'verification/out/gap87-sqrt64-preflight-20261006-01'
    base = ROOT / 'verification/out/gap86-offline-admitted-693-20261006-01'
    formal = ROOT / 'verification/out/raw693-dve-20261006-01'
    load = lambda path: json.loads(path.read_bytes())
    require(load(run / 'simulation-status.json')['status'] == 'SIMULATION_EXITED_NOT_ADMITTED', 'Incomplete run')
    old = load(base / 'combined-bits.json')
    require(len(old['tests']) == len(set(old['tests'])) == 693, 'Wrong population')
    design = ROOT / 'verification/out/repaired-aligned-build-20260930-01/sim/simv.vdb'
    require((base / 'combined-inputs.txt').read_text().splitlines() ==
            [str(design), *old['tests']] == (formal / 'inputs.txt').read_text().splitlines(), 'Input mismatch')
    verification = load(formal / 'population-verification.json')
    require(verification['status'] == 'VERIFIED_HISTORICAL_RAW_REPORT' and
            verification['admitted_tests'] == 693, 'Formal report not verified')
    pins = dict(load(run / 'manifest.json')['pins'])
    pins.update(verification['pins'])
    for path in [Path(__file__).resolve(), ROOT / 'verification/coverage/admit_gap83_offline.py',
                 Path(bitmap.__file__), base / 'combined-bits.json', base / 'combined-inputs.txt',
                 formal / 'population-verification.json', run / 'manifest.json',
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
    require(scalar['status'] == 'TERMINAL_TOHOST_MATCH' and scalar['ara_trap_events'] == 0,
            'Scalar mismatch/trap')
    require(vector['status'] == 'PASS' and vector['compared_instructions'] == 180 and
            vector['compared_bytes'] == 27060 and vector['skipped_unknown_bytes'] == 0 and
            vector['non_bit_exact_instructions'] == 0 and not vector['incomplete_requests'] and
            not vector['unretired_requests'] and not vector['trapped_requests'], 'Vector mismatch/incomplete')
    require(not check_contract_log(run / 'run.vcs.log'), 'Contract failure')
    require((run / 'run.vcs.log').read_text().count('Core Test *** SUCCESS ***') == 1, 'Software failure')
    with (run / 'commit_trace.csv').open() as stream:
        writes = {int(row['mem_addr'], 16): (int(row['mem_wmask'], 16), int(row['mem_wdata'], 16))
                  for row in csv.DictReader(stream)
                  if row['event'] == 'retire' and int(row['mem_wmask'], 16)}
    require(writes.get(0x80002504) == (0xf0, 1530) and
            writes.get(0x80002508) == (0x0f, 0), 'DUT signature failure')
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
    save(out / 'status.json', dict(status='PASS_RAW_UNION_HISTORICAL_ONLY', aggregate_passed=694,
         new_passed=1, official_DVE_report=False, rtl_changed=False, new_RTL_signoff=False))
    print(json.dumps(dict(aggregate_passed=694, raw_delta=delta['metrics'])))


if __name__ == '__main__':
    main()
