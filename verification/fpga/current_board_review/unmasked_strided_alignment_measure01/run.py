#!/usr/bin/env python3
"""One isolated M8 compile and one two-case batch. No retry or RTL changes."""
import csv
import hashlib
import json
import os
from pathlib import Path
import re
import subprocess
import time

HERE = Path(__file__).resolve().parent
ROOT = Path('/home/wangwy/fpga_runs/current_board_memory_candidate08/frozen/sources')
IMAGE = Path('/home/wangwy/fpga_runs/current_board_memory_candidate08/campaign/image')
OLD = HERE.parent / 'masked_translation/multiword_fault_liveness01/measurement01'
VCS = Path('/home/wangwy/software/synopsys/install/vcs/V-2023.12-SP1')
EXPECTED = {
    'hardware/src/vlsu/addrgen.sv': '1cc40e2669e310ae25e23f5c9ee1f7ee493dc1ac990d70d8b8122f47e93742b2',
    'hardware/src/vlsu/vldu.sv': '92f9ebbeb136cd3ff11ae1a8ea92ce31b3aac077ae0667f79d82e919a3603401',
}


def sha(p):
    return hashlib.sha256(p.read_bytes()).hexdigest()


def save(p, obj):
    with p.open('x') as f:
        json.dump(obj, f, indent=2)
        f.write('\n')


def main():
    out = HERE / 'measurement01'
    out.mkdir(exist_ok=False)
    status = dict(state='ERROR', pid=os.getpid(), scope='Joint real M8 sequencer/AddrGen/MASKU/VLDU, no lanes/CPU/MMU; not SoC',
                  nr_lanes=4, axi_data_width=128, vlen=1024, translation_enabled=False,
                  per_case_cycles=250, compile_budget_s=90, startup_and_batch_budget_s=60)
    inputs = {}
    try:
        assert all(sha(ROOT / p) == h for p, h in EXPECTED.items()), 'M8 identity mismatch'
        files = [str(Path(p).relative_to(OLD / 'frozen')) for p in
                 json.loads((OLD / 'compile_command.json').read_text()) if p.endswith('.sv')]
        paths = {p for p in json.loads((OLD / 'pins.json').read_text())['files'] if p.startswith('hardware/')}
        sources = {p: ROOT / p for p in paths}
        sources.update({n: HERE / n for n in ('probe_tb.sv', 'run.py')})
        inputs = {str(p): sha(p) for p in sources.values()}
        for p in (OLD / 'compile_command.json', OLD / 'pins.json', IMAGE / '_build/vcs/simulator.conf', IMAGE / 'image.json'):
            inputs[str(p)] = sha(p)
        conf = (IMAGE / '_build/vcs/simulator.conf').read_text()
        assert 'nr_lanes=4' in conf and 'vlen=1024' in conf
        frozen = out / 'frozen'
        for name, p in sources.items():
            dst = frozen / name
            dst.parent.mkdir(parents=True, exist_ok=True)
            dst.write_bytes(p.read_bytes())
            dst.chmod(0o444)
        src = (frozen / 'hardware/src/ara.sv').read_text()
        types = []
        for name in ('ara_req_t', 'ara_resp_t'):
            matches = re.findall(r'typedef struct packed \{[^}]*\} ' + name + ';', src)
            assert len(matches) == 1, name
            types.append(matches[0])
        (frozen / 'sequencer_types.svh').write_text('\n'.join(types) + '\n')
        (frozen / 'sequencer_types.svh').chmod(0o444)
        frozen_pins = {str(p.relative_to(frozen)): sha(p) for p in frozen.rglob('*') if p.is_file()}
        save(out / 'input_pins.json', inputs)
        save(out / 'frozen_pins.json', frozen_pins)
        env = {k: os.environ[k] for k in ('HOME', 'USER', 'LOGNAME', 'TMPDIR') if k in os.environ}
        env.update(PATH=f'{VCS}/bin:/usr/bin:/bin', VCS_HOME=str(VCS), VCS_TARGET_ARCH='linux64',
                   SNPSLMD_LICENSE_FILE='27000@t7920', LM_LICENSE_FILE='27000@t7920', LC_ALL='C')
        save(out / 'environment.json', env)
        cmd = [str(VCS / 'bin/vcs'), '-full64', '-sverilog', '-timescale=1ns/1ps', '-top', 'probe_tb',
               *['+incdir+' + str(frozen / p) for p in ('', 'hardware/include',
                  'hardware/deps/common_cells/include', 'hardware/deps/axi/include')],
               *[str(frozen / p) for p in files], '-o', str(out / 'simv'), '-l', str(out / 'compile.log')]
        save(out / 'compile_command.json', cmd)
        start = time.monotonic()
        with (out / 'compile_console.log').open('x') as log:
            proc = subprocess.run(cmd, cwd=out, env=env, stdout=log, stderr=subprocess.STDOUT, timeout=90)
        status.update(compile_returncode=proc.returncode, compile_seconds=time.monotonic()-start)
        assert proc.returncode == 0, 'Compilation failed, no auto retry'
        cmd = [str(out / 'simv'), '-no_save']
        save(out / 'run_command.json', cmd)
        start = time.monotonic()
        with (out / 'run.log').open('x') as log:
            child = subprocess.Popen(cmd, cwd=out, env=env, stdout=log, stderr=subprocess.STDOUT)
            save(out / 'child.json', dict(pid=child.pid, command=cmd))
            try:
                rc = child.wait(timeout=60)
            except subprocess.TimeoutExpired:
                child.kill()
                child.wait()
                raise
        status.update(run_returncode=rc, run_seconds=time.monotonic()-start)
        save(out / 'process_exit.json', dict(returncode=rc, elapsed_s=status['run_seconds']))
        log = (out / 'run.log').read_text()
        assert rc == 0 and log.count('TWO_CASE_MEASUREMENT_COMPLETE') == 1, 'Batch not complete'
        assert not any(x in log for x in ('Fatal:', 'Error:', '[ASSERT FAILED]')), 'Assertion failed'
        status['receipts'] = [x for x in log.splitlines() if x.startswith(('CONTROL_COMPLETED ', 'DIAGNOSTIC_REPRODUCED_NOT_ARCH_PASS '))]
        assert len(status['receipts']) == 2
        with (out / 'cycles.csv').open() as f:
            rows = list(csv.DictReader(f))
        assert rows and all(None not in r and all(v is not None for v in r.values()) for r in rows)
        summaries = []
        for case_id, stride in ((0, 8), (1, 4)):
            rs = [r for r in rows if int(r['case']) == case_id]
            ar = [r for r in rs if r['ar_valid'] == r['ar_ready'] == '1']
            rr = [r for r in rs if r['r_valid'] == r['r_ready'] == '1']
            pp = [r for r in rs if r['desc_valid'] == r['desc_pop'] == '1']
            assert len(ar) == len(rr) == len(pp) == 2
            assert [int(r['ar_addr'], 16) for r in ar] == [0x80010000, 0x80010000+stride]
            assert all(r['ar_len'] == '0' and r['ar_size'] == '3' for r in ar)
            assert all(r['r_last'] == '1' for r in rr)
            assert all(r['exception'] == r['early_ld'] == r['early_st'] == '0' for r in rs)
            summaries.append(dict(case=case_id, stride=stride, rows=len(rs),
                                  ar_cycles=[int(r['cycle']) for r in ar],
                                  r_cycles=[int(r['cycle']) for r in rr],
                                  pop_cycles=[int(r['cycle']) for r in pp], last=rs[-1]))
        status.update(cases=summaries, csv_sha256=sha(out / 'cycles.csv'), csv_rows=len(rows))
        assert all(sha(Path(p)) == h for p, h in inputs.items()), 'Input drift'
        assert all(sha(frozen / p) == h for p, h in frozen_pins.items()), 'Snapshot drift'
        status.update(state='CONTROL_COMPLETE_AND_DIAGNOSTIC_REPRODUCED_NOT_ARCH_PASS', pins_unchanged=True)
    except Exception as e:
        status['error'] = repr(e)
    save(out / 'result.json', status)
    print(json.dumps(status, indent=2), flush=True)
    return int(status['state'] != 'CONTROL_COMPLETE_AND_DIAGNOSTIC_REPRODUCED_NOT_ARCH_PASS')


if __name__ == '__main__':
    raise SystemExit(main())
