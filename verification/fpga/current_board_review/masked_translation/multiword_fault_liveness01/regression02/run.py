#!/usr/bin/env python3
"""Two frozen local builds; one fixed batch invocation per build; fail first."""
import csv
import hashlib
import json
import os
from pathlib import Path
import subprocess
import time

HERE = Path(__file__).resolve().parent
BASE = HERE.parent / 'measurement01'
CAND = HERE.parent / 'successor01/measurement01/frozen/hardware/src/vlsu/vldu.sv'
EXPECTED = '92f9ebbeb136cd3ff11ae1a8ea92ce31b3aac077ae0667f79d82e919a3603401'
VCS = Path('/home/wangwy/software/synopsys/install/vcs/V-2023.12-SP1')


def sha(p):
    return hashlib.sha256(p.read_bytes()).hexdigest()


def save(p, value):
    with p.open('x') as f:
        json.dump(value, f, indent=2)
        f.write('\n')


def main():
    out = HERE / 'measurement01'
    out.mkdir(exist_ok=False)
    status = {'state': 'ERROR', 'pid': os.getpid(), 'versions': [],
              'scope': 'Local four-module AXI/VRF models; not SoC/Linux',
              'host_bound_per_batch_s': 60, 'progress_bound_per_instruction_cycles': 200}
    pins = {}
    try:
        oldpins = json.loads((BASE / 'pins.json').read_text())['files']
        assert all(sha(BASE / 'frozen' / p) == h for p, h in oldpins.items())
        assert sha(CAND) == EXPECTED
        originals = [BASE / 'frozen' / p for p in oldpins]
        originals += [CAND, HERE / 'probe_tb.sv', HERE / 'run.py', HERE / 'PLAN.md']
        pins = {str(p): sha(p) for p in originals}
        save(out / 'input_pins.json', pins)
        env = {k: os.environ[k] for k in ('HOME', 'USER', 'LOGNAME', 'TMPDIR') if k in os.environ}
        env.update(PATH=f'{VCS}/bin:/usr/bin:/bin', VCS_HOME=str(VCS), VCS_TARGET_ARCH='linux64',
                   SNPSLMD_LICENSE_FILE='27000@t7920', LM_LICENSE_FILE='27000@t7920', LC_ALL='C')
        save(out / 'environment.json', env)
        file_order = [str(Path(arg).relative_to(BASE / 'frozen')) for arg in
                      json.loads((BASE / 'compile_command.json').read_text()) if arg.endswith('.sv')]
        for version, n in (('baseline', 2), ('candidate', 7)):
            dst = out / version
            frozen = dst / 'frozen'
            frozen.mkdir(parents=True)
            for name in oldpins:
                src = BASE / 'frozen' / name
                if name in ('run.py', 'probe_tb.sv'):
                    src = HERE / name
                elif name == 'hardware/src/vlsu/vldu.sv' and version == 'candidate':
                    src = CAND
                target = frozen / name
                target.parent.mkdir(parents=True, exist_ok=True)
                target.write_bytes(src.read_bytes())
                target.chmod(0o444)
            snapshot = {str(p.relative_to(frozen)): sha(p) for p in frozen.rglob('*') if p.is_file()}
            save(dst / 'pins.json', snapshot)
            cmd = [str(VCS / 'bin/vcs'), '-full64', '-sverilog', '-timescale=1ns/1ps',
                   '-top', 'probe_tb', '+incdir+' + str(frozen),
                   '+incdir+' + str(frozen / 'hardware/include'),
                   '+incdir+' + str(frozen / 'hardware/deps/common_cells/include'),
                   '+incdir+' + str(frozen / 'hardware/deps/axi/include'),
                   *[str(frozen / p) for p in file_order], '-o', str(dst / 'simv'),
                   '-l', str(dst / 'compile.log')]
            save(dst / 'compile_command.json', cmd)
            entry = {'version': version}
            status['versions'].append(entry)
            started = time.monotonic()
            with (dst / 'compile_console.log').open('x') as f:
                proc = subprocess.run(cmd, cwd=dst, env=env, stdout=f, stderr=subprocess.STDOUT, timeout=90)
            entry.update(compile_returncode=proc.returncode, compile_seconds=time.monotonic()-started)
            assert proc.returncode == 0, 'compile failed: ' + version
            run = [str(dst / 'simv'), '-no_save'] + (['+BASELINE'] if version == 'baseline' else [])
            save(dst / 'run_command.json', run)
            started = time.monotonic()
            with (dst / 'run.log').open('x') as f:
                proc = subprocess.run(run, cwd=dst, env=env, stdout=f, stderr=subprocess.STDOUT, timeout=60)
            entry.update(returncode=proc.returncode, run_seconds=time.monotonic()-started)
            log = (dst / 'run.log').read_text()
            entry['instruction_receipts'] = [s for s in log.splitlines() if s.startswith('INSTRUCTION_PASS ')]
            entry['scenario_receipts'] = [s for s in log.splitlines() if s.startswith('SCENARIO_PASS ')]
            save(dst / 'outcome.json', entry)
            assert proc.returncode == 0, 'simulator failed: ' + version
            assert log.count(f'JOINT_REGRESSION_PASS scenarios={n}') == 1
            assert len(entry['instruction_receipts']) == 2*n and len(entry['scenario_receipts']) == n
            assert not any(s in log for s in ('Fatal:', 'Error:', '[ASSERT FAILED]'))
            with (dst / 'cycles.csv').open() as f:
                rows = list(csv.DictReader(f))
            assert rows and all(None not in row and all(v is not None for v in row.values()) for row in rows)
            assert sorted({int(row['case']) for row in rows}) == list(range(n))
            entry['csv_rows'] = len(rows)
            entry['csv_sha256'] = sha(dst / 'cycles.csv')
            assert all(sha(frozen / p) == h for p, h in snapshot.items()), 'snapshot drift'
        bp = json.loads((out / 'baseline/pins.json').read_text())
        cp = json.loads((out / 'candidate/pins.json').read_text())
        changed = [p for p in bp if bp[p] != cp[p]]
        assert changed == ['hardware/src/vlsu/vldu.sv'], changed
        before = (out / 'baseline/cycles.csv').read_bytes()
        after = (out / 'candidate/cycles.csv').read_bytes().splitlines(keepends=True)
        normal = after[:1] + [line for line in after[1:] if line.split(b',', 1)[0] in (b'0', b'1')]
        assert before == b''.join(normal), 'Normal full-cycle traces differ'
        assert all(sha(Path(p)) == h for p, h in pins.items()), 'original input drift'
        status.update(state='NORMAL_AB_IDENTICAL_AND_SEVEN_CANDIDATE_SCENARIOS_PASS_NOT_SOC',
                      pins_unchanged=True, normal_complete_cycle_bytes_identical=True,
                      normal_trace_sha256=hashlib.sha256(before).hexdigest(), changed_inputs=changed)
    except Exception as e:
        status['error'] = repr(e)
        if pins:
            status['pins_unchanged'] = all(sha(Path(p)) == h for p, h in pins.items())
    save(out / 'result.json', status)
    print(json.dumps(status, indent=2), flush=True)
    return int(status['state'] != 'NORMAL_AB_IDENTICAL_AND_SEVEN_CANDIDATE_SCENARIOS_PASS_NOT_SOC')


if __name__ == '__main__':
    raise SystemExit(main())
