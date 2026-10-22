"""Frozen-image square-root run, kept separate from PASS admission."""
import argparse
import json
from pathlib import Path
import subprocess
from run_gap83_simulation import ROOT, digest, save
from run_gap75_operand_batch import parse_spike_commits


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', type=Path, required=True)
    out = parser.parse_args().output.absolute()
    if out.parent != ROOT / 'verification/out' or out.exists():
        raise ValueError('Fresh independent output required')
    pre = ROOT / 'verification/out/gap85-sqrt32-preflight-20261006-01'
    elf, trace = pre / 'input.elf', pre / 'spike.trace'
    if digest(elf) != '3bc569c610e75b199485e866d1a5918089c6df79f62171abd3271ae6ebe7c9f5':
        raise ValueError('ELF drift')
    writes = {a: v for c in parse_spike_commits(trace) for a, v in c.memory_accesses if v is not None}
    if any(writes.get(a) != v for a, v in ((0x80001000, 1), (0x80002488, 2970),
                                         (0x8000248c, 0), (0x80002380, 0))):
        raise ValueError('Spike signature/trap failure')
    planfile = ROOT / 'verification/out/closure90-current-20261005-01/plan.json'
    plan = json.loads(planfile.read_bytes())
    pins = dict(plan['image'])
    for p in (elf, trace, planfile, Path(__file__).resolve(),
              ROOT / 'verification/coverage/run_gap83_simulation.py',
              ROOT / 'verification/coverage/run_gap75_operand_batch.py',
              ROOT / 'apps/riscv-tests/isa/rv64uv/vgap85_sqrt32.c'):
        pins[str(p)] = digest(p)
    def check():
        for p, value in pins.items():
            if digest(Path(p)) != value:
                raise ValueError('Pinned input changed: ' + p)
    check()
    command = [plan['simv'], '-l', 'run.vcs.log', '+NO_FSDB', '+ntb_random_seed=1',
        '+PRELOAD=' + str(elf), '+TESTCASE=vgap85_sqrt32', '+COMMIT_TOHOST=80001000',
        '+COMMIT_TRACE=' + str(out / 'commit_trace.csv'), '+VECTOR_TRACE=' + str(out / 'vector_trace.csv'),
        '-cm', 'line+cond+fsm+tgl+branch', '-cm_dir', str(out / 'code.vdb'), '-cm_name', 'vgap85_sqrt32']
    out.mkdir()
    save(out / 'manifest.json', dict(pins=pins, command=command, timeout_s=600, coverage_admitted=False))
    try:
        with (out / 'console.log').open('x') as log:
            result = subprocess.run(command, cwd=out, stdout=log, stderr=subprocess.STDOUT,
                                    timeout=600, check=True)
        check()
        save(out / 'simulation-status.json', dict(status='SIMULATION_EXITED_NOT_ADMITTED',
             returncode=result.returncode, coverage_admitted=False))
    except Exception as error:
        save(out / 'simulation-status.json', dict(status='SIMULATION_NOT_ADMITTED',
             reason=type(error).__name__ + ': ' + str(error), coverage_admitted=False))
        raise


if __name__ == '__main__':
    main()
