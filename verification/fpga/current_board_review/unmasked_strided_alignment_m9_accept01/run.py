#!/usr/bin/env python3
"""Single bounded candidate batch plus separately identified M8 normal controls."""
import csv
import hashlib
import json
import os
from pathlib import Path
import re
import subprocess
import time

HERE = Path(__file__).resolve().parent
WORK = HERE.parents[3]
M8 = Path('/home/wangwy/fpga_runs/current_board_memory_candidate08/frozen/sources')
MANIFEST = HERE.parent / 'masked_translation/multiword_fault_liveness01/measurement01'
OLD = HERE.parent / 'unmasked_strided_alignment_measure01/successor01/measurement01'
VCS = Path('/home/wangwy/software/synopsys/install/vcs/V-2023.12-SP1')
AG = 'hardware/src/vlsu/addrgen.sv'
M9_SHA = '3736b64136ebbf5629dadb0037457279f9bb91307356c468c9677d321c8c51c5'
M8_SHA = '1cc40e2669e310ae25e23f5c9ee1f7ee493dc1ac990d70d8b8122f47e93742b2'


def sha(p):
    return hashlib.sha256(p.read_bytes()).hexdigest()


def save(p, obj):
    with p.open('x') as f:
        json.dump(obj, f, indent=2)
        f.write('\n')


def invoke(cmd, dst, env, stage, bound):
    save(dst / (stage + '_command.json'), cmd)
    started = time.monotonic()
    with (dst / (stage + '.log')).open('x') as f:
        child = subprocess.Popen(cmd, cwd=dst, env=env, stdout=f, stderr=subprocess.STDOUT)
        save(dst / (stage + '_child.json'), dict(pid=child.pid, command=cmd))
        try:
            rc = child.wait(timeout=bound)
            receipt = dict(returncode=rc, elapsed_s=time.monotonic()-started, timeout=False)
        except subprocess.TimeoutExpired:
            child.kill()
            child.wait()
            receipt = dict(returncode=child.returncode, elapsed_s=time.monotonic()-started, timeout=True)
        save(dst / (stage + '_exit.json'), receipt)
    assert not receipt['timeout'] and receipt['returncode'] == 0, (stage, receipt)
    return receipt


def parse(dst, cases):
    log = (dst / 'run.log').read_text()
    assert not any(s in log for s in ('Fatal:', 'Error:', '[ASSERT FAILED]'))
    assert log.count('M9_LOCAL_ACCEPTANCE_COMPLETE cases=' + str(len(cases))) == 1
    receipts = [s for s in log.splitlines() if s.startswith('CASE_PASS ')]
    assert len(receipts) == len(cases)
    tables = []
    for name in ('cycles.csv', 'context.csv'):
        with (dst / name).open() as f:
            rows = list(csv.DictReader(f))
        assert len(rows) == 251*len(cases)
        assert all(None not in r and all(v is not None for v in r.values()) for r in rows)
        assert sorted({int(r['case']) for r in rows}) == cases
        tables.append(rows)
    result = []
    for case in cases:
        rows, context = [[r for r in table if int(r['case']) == case] for table in tables]
        assert all([int(r['cycle']) for r in table] == list(range(5, 256)) for table in (rows, context))
        event = lambda k: [int(r['cycle']) for r in rows if int(r[k], 2) != 0]
        ar = [r for r in rows if r['ar_valid'] == r['ar_ready'] == '1']
        rd = [r for r in rows if r['r_valid'] == r['r_ready'] == '1']
        pop = [r for r in rows if r['desc_valid'] == r['desc_pop'] == '1']
        n = [2, 1, 1, 0, 1, 2, 2][case]
        assert len(ar) == len(rd) == n and len(pop) == n+int(case == 1)
        assert sum(int(r['desc_exception']) for r in pop) == int(case == 1)
        assert all(r['ar_len'] == '0' and int(r['ar_size']) == (4 if case == 4 else 3) for r in ar)
        assert all(r['r_last'] == '1' for r in rd)
        fault = case in (1, 3)
        ack = [r for r in context if r['ack'] == '1']
        resp = [c for r, c in zip(rows, context) if r['response'] == '1']
        assert len(ack) == len(resp) == 1
        assert all(int(r['exception']) == int(fault) for r in ack)
        assert all(int(r['resp_exception']) == int(fault) for r in resp)
        if fault:
            assert ack[0]['cause'] == resp[0]['resp_cause'] == '4'
            assert int(ack[0]['tval'], 16) == int(resp[0]['resp_tval'], 16) == 0x80010004
            assert ack[0]['exception_start'] == resp[0]['resp_start'] == '1'
        assert len(event('early_ld')) == int(case == 3)
        assert len(event('done')) == len(event('load_complete')) == 1
        assert rows[-1]['global_idle'] == rows[-1]['ld_idle'] == rows[-1]['ag_idle'] == '1'
        assert rows[-1]['issue_bytes'] == rows[-1]['commit_bytes'] == rows[-1]['vrf_count'] == '0'
        assert int(rows[-1]['written']) == [16, 8, 8, 0, 16, 16, 16][case]
        if fault and n:
            assert max(event('final_gnt')) < event('done')[0] <= event('response')[0]
        result.append(dict(case=case, ar=[dict(cycle=int(r['cycle']), addr=r['ar_addr']) for r in ar],
                           r_cycles=event('r_valid'), pop_cycles=[int(r['cycle']) for r in pop],
                           ack_cycles=event('ack'), response_cycles=event('response'),
                           final_grant_cycles=event('final_gnt'), done_cycles=event('done'),
                           first_idle_after_done=next(int(r['cycle']) for r in rows
                               if int(r['cycle'])>event('done')[0] and r['global_idle']=='1'),
                           written_bytes=int(rows[-1]['written']), exception=fault))
    return dict(cases=result, receipts=receipts, csv_rows=len(tables[0]),
                cycles_sha256=sha(dst / 'cycles.csv'), context_sha256=sha(dst / 'context.csv'))


def main():
    out = HERE / 'measurement01'
    out.mkdir(exist_ok=False)
    status = dict(state='ERROR', pid=os.getpid(), versions=[], scope='Local LOAD-only; translation disabled; not SoC',
                  nr_lanes=4, axi_data_width=128, per_case_cycles=250, startup_batch_s=60)
    try:
        assert sha(WORK / AG) == M9_SHA and sha(M8 / AG) == M8_SHA
        assert sha(M8 / 'hardware/src/vlsu/vldu.sv') == '92f9ebbeb136cd3ff11ae1a8ea92ce31b3aac077ae0667f79d82e919a3603401'
        assert sha(OLD / 'cycles.csv') == '6edb1777a39c6b81af06e62f2e49a7823c4e73726e9abc9496f4c684ddc93f1b'
        names = {p for p in json.loads((MANIFEST / 'pins.json').read_text())['files'] if p.startswith('hardware/')}
        order = [str(Path(p).relative_to(MANIFEST / 'frozen')) for p in
                 json.loads((MANIFEST / 'compile_command.json').read_text()) if p.endswith('.sv')]
        originals = [M8 / p for p in names] + [WORK / AG, HERE / 'run.py', HERE / 'probe_tb.sv',
                     MANIFEST / 'pins.json', MANIFEST / 'compile_command.json', OLD / 'cycles.csv']
        pins = {str(p): sha(p) for p in originals}
        save(out / 'input_pins.json', pins)
        env = {k: os.environ[k] for k in ('HOME', 'USER', 'LOGNAME', 'TMPDIR') if k in os.environ}
        env.update(PATH=f'{VCS}/bin:/usr/bin:/bin', VCS_HOME=str(VCS), VCS_TARGET_ARCH='linux64',
                   SNPSLMD_LICENSE_FILE='27000@t7920', LM_LICENSE_FILE='27000@t7920', LC_ALL='C')
        save(out / 'environment.json', env)
        for version, cases in (('candidate', list(range(7))), ('m8_normals', [4, 5, 6])):
            dst = out / version
            frozen = dst / 'frozen'
            for name in sorted(names | {'probe_tb.sv', 'run.py'}):
                src = M8 / name if name.startswith('hardware/') else HERE / name
                if name == AG and version == 'candidate':
                    src = WORK / AG
                target = frozen / name
                target.parent.mkdir(parents=True, exist_ok=True)
                target.write_bytes(src.read_bytes())
                target.chmod(0o444)
            src = (frozen / 'hardware/src/ara.sv').read_text()
            types = []
            for name in ('ara_req_t', 'ara_resp_t'):
                matches = re.findall(r'typedef struct packed \{[^}]*\} ' + name + ';', src)
                assert len(matches) == 1
                types.append(matches[0])
            (frozen / 'sequencer_types.svh').write_text('\n'.join(types) + '\n')
            fpins = {str(p.relative_to(frozen)): sha(p) for p in frozen.rglob('*') if p.is_file()}
            save(dst / 'pins.json', fpins)
            cmd = [str(VCS / 'bin/vcs'), '-full64', '-sverilog', '-timescale=1ns/1ps', '-top', 'probe_tb',
                   *['+incdir+' + str(frozen / p) for p in ('', 'hardware/include',
                      'hardware/deps/common_cells/include', 'hardware/deps/axi/include')],
                   *[str(frozen / p) for p in order], '-o', str(dst / 'simv')]
            entry = dict(version=version)
            status['versions'].append(entry)
            entry['compile'] = invoke(cmd, dst, env, 'compile', 90)
            cmd = [str(dst / 'simv'), '-no_save'] + (['+BASELINE_NORMALS'] if version=='m8_normals' else [])
            entry['run'] = invoke(cmd, dst, env, 'run', 60)
            entry.update(parse(dst, cases))
            assert all(sha(frozen / p) == h for p, h in fpins.items()), 'Frozen drift'
        candidate = out / 'candidate'
        baseline = out / 'm8_normals'
        cp = json.loads((candidate / 'pins.json').read_text())
        bp = json.loads((baseline / 'pins.json').read_text())
        assert sorted(p for p in cp if cp[p] != bp[p]) == [AG]
        for name in ('cycles.csv', 'context.csv'):
            lines = (candidate / name).read_bytes().splitlines(keepends=True)
            normal = b''.join(lines[:1] + [s for s in lines[1:] if s.split(b',')[0] in (b'4', b'5', b'6')])
            assert normal == (baseline / name).read_bytes(), 'Normal full-cycle difference: ' + name
        oldlines = (OLD / 'cycles.csv').read_bytes().splitlines(keepends=True)
        newlines = (candidate / 'cycles.csv').read_bytes().splitlines(keepends=True)
        select0 = lambda lines: b''.join(lines[:1] + [s for s in lines[1:] if s.split(b',')[0] == b'0'])
        assert select0(oldlines) == select0(newlines), 'Original stride8 cycle drift'
        assert all(sha(Path(p)) == h for p, h in pins.items()), 'Input drift'
        status.update(state='SEVEN_M9_CASES_PASS_NORMAL_CYCLES_IDENTICAL_NOT_SOC',
                      pins_unchanged=True, only_changed_rtl=AG, addrgen_sha256=M9_SHA,
                      original_stride8_full_cycles_identical=True, three_new_controls_full_cycles_identical=True)
    except Exception as e:
        status['error'] = repr(e)
    save(out / 'result.json', status)
    print(json.dumps(status, indent=2), flush=True)
    return int(status['state'] != 'SEVEN_M9_CASES_PASS_NORMAL_CYCLES_IDENTICAL_NOT_SOC')


if __name__ == '__main__':
    raise SystemExit(main())
