"""Run the leading-position scan against the frozen image, not current RTL."""
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
    pre = ROOT / 'verification/out/gap89-div64-leading-preflight-20261006-01'
    elf, trace = pre / 'input.elf', pre / 'spike.trace'
    if digest(elf) != '97c6f2683433350e0ffdb9bfebe373d7c70de50b72c8f84a4a39e6a9a1f7931e':
        raise ValueError('ELF drift')
    writes = {a: v for c in parse_spike_commits(trace)
              for a, v in c.memory_accesses if v is not None}
    for address, expected in ((0x80001000, 1), (0x80002208, 952),
                              (0x8000220c, 0), (0x80002180, 0)):
        if writes.get(address) != expected:
            raise ValueError('Spike signature/trap failure')
    planfile = ROOT / 'verification/out/closure90-current-20261005-01/plan.json'
    plan = json.loads(planfile.read_bytes())
    pins = dict(plan['image'])
    for path in (elf, trace, planfile, Path(__file__).resolve(),
                 ROOT / 'verification/coverage/run_gap83_simulation.py',
                 ROOT / 'verification/coverage/run_gap75_operand_batch.py',
                 ROOT / 'apps/riscv-tests/isa/rv64uv/vgap89_div64_leading.c'):
        pins[str(path)] = digest(path)

    def check():
        for path, expected in pins.items():
            if digest(Path(path)) != expected:
                raise ValueError('Pinned input changed: ' + path)

    check()
    command = [plan['simv'], '-l', 'run.vcs.log', '+NO_FSDB', '+ntb_random_seed=1',
               '+PRELOAD=' + str(elf), '+TESTCASE=vgap89_div64_leading', '+COMMIT_TOHOST=80001000',
               '+COMMIT_TRACE=' + str(out / 'commit_trace.csv'),
               '+VECTOR_TRACE=' + str(out / 'vector_trace.csv'),
               '-cm', 'line+cond+fsm+tgl+branch', '-cm_dir', str(out / 'code.vdb'),
               '-cm_name', 'vgap89_div64_leading']
    out.mkdir()
    save(out / 'manifest.json', dict(pins=pins, command=command,
                                   timeout_s=600, coverage_admitted=False))
    try:
        with (out / 'console.log').open('x') as log:
            result = subprocess.run(command, cwd=out, stdout=log,
                                    stderr=subprocess.STDOUT, timeout=600, check=True)
        check()
        save(out / 'simulation-status.json', dict(status='SIMULATION_EXITED_NOT_ADMITTED',
             returncode=result.returncode, coverage_admitted=False))
    except Exception as error:
        save(out / 'simulation-status.json', dict(status='SIMULATION_NOT_ADMITTED',
             reason=str(error), coverage_admitted=False))
        raise


if __name__ == '__main__':
    main()
