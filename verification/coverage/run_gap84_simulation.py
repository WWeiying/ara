"""One source- and image-pinned old-image run; never automatically admit coverage."""
import argparse
import json
from pathlib import Path
import subprocess

from run_gap83_simulation import ROOT, digest, save
from run_gap75_operand_batch import parse_spike_commits

ELF_SHA = 'af0f998f592249a6f42472c3a05c52554227c10dd89c1ddc61c72250da4a950c'


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    output = args.output.absolute()
    if output.parent != ROOT / 'verification/out' or output.exists():
        raise ValueError('Fresh direct output required')
    preflight = ROOT / 'verification/out/gap84-div32-preflight-20261006-01'
    elf, trace = preflight / 'input.elf', preflight / 'spike.trace'
    if digest(elf) != ELF_SHA:
        raise ValueError('ELF differs from verified preflight')
    writes = {address: value for commit in parse_spike_commits(trace)
              for address, value in commit.memory_accesses if value is not None}
    if (writes.get(0x80001000) != 1 or writes.get(0x80002588) != 2970
            or writes.get(0x8000258c) != 0 or writes.get(0x80002480) != 0):
        raise ValueError('Spike preflight signature/trap gate failed')
    planfile = ROOT / 'verification/out/closure90-current-20261005-01/plan.json'
    plan = json.loads(planfile.read_bytes())
    pins = dict(plan['image'])
    for path in (elf, trace, planfile, Path(__file__).resolve(),
                 ROOT / 'verification/coverage/run_gap83_simulation.py',
                 ROOT / 'verification/coverage/run_gap75_operand_batch.py',
                 ROOT / 'apps/riscv-tests/isa/rv64uv/vgap84_div32.c'):
        pins[str(path)] = digest(path)

    def check():
        for path, expected in pins.items():
            if digest(Path(path)) != expected:
                raise ValueError('Input/image drift: ' + path)

    check()
    command = [plan['simv'], '-l', 'run.vcs.log', '+NO_FSDB', '+ntb_random_seed=1',
        '+PRELOAD=' + str(elf), '+TESTCASE=vgap84_div32', '+COMMIT_TOHOST=80001000',
        '+COMMIT_TRACE=' + str(output / 'commit_trace.csv'),
        '+VECTOR_TRACE=' + str(output / 'vector_trace.csv'),
        '-cm', 'line+cond+fsm+tgl+branch', '-cm_dir', str(output / 'code.vdb'),
        '-cm_name', 'vgap84_div32']
    output.mkdir()
    save(output / 'manifest.json', dict(pins=pins, command=command, timeout_s=600,
        spike_checks=2970, coverage_admitted=False, rtl_changed=False))
    try:
        with (output / 'console.log').open('x') as log:
            result = subprocess.run(command, cwd=output, stdout=log,
                stderr=subprocess.STDOUT, timeout=600, check=True)
        check()
        save(output / 'simulation-status.json', dict(status='SIMULATION_EXITED_NOT_ADMITTED',
            returncode=result.returncode, coverage_admitted=False))
    except Exception as error:
        save(output / 'simulation-status.json', dict(status='SIMULATION_NOT_ADMITTED',
            reason=type(error).__name__ + ': ' + str(error), coverage_admitted=False))
        raise


if __name__ == '__main__':
    main()
