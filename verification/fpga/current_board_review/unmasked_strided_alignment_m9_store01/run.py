#!/usr/bin/env python3
"""Four precise STORE cases; one separately measured unchanged normal control."""
import csv
import importlib.util
import json
import os
from pathlib import Path
import re
import sys
sys.dont_write_bytecode = True
HERE = Path(__file__).resolve().parent
HELPER = HERE.parent / 'unmasked_strided_alignment_m9_accept01/run.py'
spec = importlib.util.spec_from_file_location('local_load_helpers', HELPER)
h = importlib.util.module_from_spec(spec)
spec.loader.exec_module(h)
MAN = HERE.parent / 'masked_translation/vstu_prefix_guard_acceptance02/measurement_candidate01'


def check(dst, ids):
    log = (dst / 'run.log').read_text()
    assert not any(x in log for x in ('Fatal:', 'Error:', '[ASSERT FAILED]'))
    assert log.count('M9_STORE_ACCEPTANCE_COMPLETE cases='+str(len(ids))) == 1
    receipts = [x for x in log.splitlines() if x.startswith('CASE_PASS ')]
    assert len(receipts) == len(ids)
    with (dst / 'cycles.csv').open() as f:
        rows = list(csv.DictReader(f))
    assert len(rows) == 251*len(ids)
    assert all(None not in r and all(v is not None for v in r.values()) for r in rows)
    results = []
    for case in ids:
        rr = [r for r in rows if int(r['case']) == case]
        assert [int(r['cycle']) for r in rr] == list(range(5, 256))
        events = lambda key: [int(r['cycle']) for r in rr if int(r[key], 2)]
        ws = [r for r in rr if r['w_valid'] == r['w_ready'] == '1']
        bs = [r for r in rr if r['b_valid'] == r['b_ready'] == '1']
        n = [2, 1, 1, 0][case]
        assert len(events('aw_valid')) == len(ws) == len(bs) == n
        assert len(events('ack')) == len(events('response')) == len(events('done')) == len(events('store_complete')) == 1
        assert len(events('early_st')) == int(case == 3)
        if case in (1, 3):
            a = next(r for r in rr if r['ack']=='1')
            p = next(r for r in rr if r['response']=='1')
            assert a['exception'] == p['resp_exception'] == '1'
            assert a['cause'] == p['resp_cause'] == '6'
            assert int(a['tval'],16) == int(p['resp_tval'],16) == 0x80010004
            assert a['exception_start'] == p['resp_start'] == '1'
        if case == 1:
            assert [int(r['cycle']) for r in ws] == [40]
            assert [int(r['cycle']) for r in bs] == [50]
            assert events('done')[0]>50
            assert all(r['store_pending']=='1' and r['global_idle']=='0' for r in rr
                       if events('ack')[0] <= int(r['cycle']) <=50)
        assert rr[-1]['st_idle'] == rr[-1]['global_idle'] == '1'
        assert rr[-1]['store_pending'] == rr[-1]['issue_bytes'] == '0'
        results.append(dict(case=case, AW=events('aw_valid'), W=[int(r['cycle']) for r in ws],
                            B=[int(r['cycle']) for r in bs], ack=events('ack'), response=events('response'),
                            done=events('done'), store_complete=events('store_complete'),
                            early=events('early_st')))
    return dict(cases=results, receipts=receipts, csv_rows=len(rows), csv_sha256=h.sha(dst/'cycles.csv'))


def main():
    out = HERE / 'measurement01'
    out.mkdir(exist_ok=False)
    result = dict(status='ERROR', pid=os.getpid(), versions=[], scope='Local STORE, translation disabled; not SoC')
    try:
        assert h.sha(h.WORK/h.AG) == h.M9_SHA
        assert h.sha(h.M8/'hardware/src/vlsu/vstu.sv') == '37880822b8066fa13e66619dd335cb42db84cdc5730c6f4dff9a3f2fd0af46a0'
        names = {p for p in json.loads((MAN/'pins.json').read_text())['files'] if p.startswith('hardware/')}
        order = [str(Path(p).relative_to(MAN/'frozen')) for p in json.loads((MAN/'compile_command.json').read_text())
                 if p.endswith('.sv') and '/frozen/hardware/' in p] + ['probe_tb.sv']
        sources = [h.M8/p for p in names] + [h.WORK/h.AG, HERE/'run.py', HERE/'probe_tb.sv',
                  HELPER, MAN/'pins.json', MAN/'compile_command.json']
        pins = {str(p): h.sha(p) for p in sources}
        h.save(out/'input_pins.json', pins)
        env = {k:os.environ[k] for k in ('HOME','USER','LOGNAME','TMPDIR') if k in os.environ}
        env.update(PATH=f'{h.VCS}/bin:/usr/bin:/bin', VCS_HOME=str(h.VCS), VCS_TARGET_ARCH='linux64',
                   SNPSLMD_LICENSE_FILE='27000@t7920', LM_LICENSE_FILE='27000@t7920', LC_ALL='C')
        h.save(out/'environment.json',env)
        for version, ids in (('candidate',list(range(4))),('m8_normal',[0])):
            dst=out/version; frozen=dst/'frozen'
            for name in sorted(names|{'run.py','probe_tb.sv'}):
                src=h.M8/name if name.startswith('hardware/') else HERE/name
                if name==h.AG and version=='candidate': src=h.WORK/name
                target=frozen/name;target.parent.mkdir(parents=True,exist_ok=True)
                target.write_bytes(src.read_bytes());target.chmod(0o444)
            src=(frozen/'hardware/src/ara.sv').read_text();types=[]
            for name in ('ara_req_t','ara_resp_t'):
                matches=re.findall(r'typedef struct packed \{[^}]*\} '+name+';',src)
                assert len(matches)==1;types.append(matches[0])
            (frozen/'sequencer_types.svh').write_text('\n'.join(types)+'\n')
            fpins={str(p.relative_to(frozen)):h.sha(p) for p in frozen.rglob('*') if p.is_file()}
            h.save(dst/'pins.json',fpins)
            cmd=[str(h.VCS/'bin/vcs'),'-full64','-sverilog','-timescale=1ns/1ps','-top','probe_tb',
                 *['+incdir+'+str(frozen/p) for p in ('','hardware/include','hardware/deps/common_cells/include','hardware/deps/axi/include')],
                 *[str(frozen/p) for p in order],'-o',str(dst/'simv')]
            entry=dict(version=version);result['versions'].append(entry)
            entry['compile']=h.invoke(cmd,dst,env,'compile',90)
            cmd=[str(dst/'simv'),'-no_save']+(['+BASELINE_NORMAL'] if version=='m8_normal' else [])
            entry['run']=h.invoke(cmd,dst,env,'run',60)
            entry.update(check(dst,ids))
            assert all(h.sha(frozen/p)==v for p,v in fpins.items())
        candidate=(out/'candidate/cycles.csv').read_bytes().splitlines(keepends=True)
        normal=b''.join(candidate[:1]+[r for r in candidate[1:] if r.split(b',')[0]==b'0'])
        assert normal==(out/'m8_normal/cycles.csv').read_bytes(), 'Normal cycle difference'
        cp=json.loads((out/'candidate/pins.json').read_text())
        bp=json.loads((out/'m8_normal/pins.json').read_text())
        assert sorted(p for p in cp if cp[p]!=bp[p])==[h.AG]
        assert all(h.sha(Path(p))==v for p,v in pins.items())
        result.update(status='FOUR_STORE_CASES_PASS_NORMAL_CYCLES_IDENTICAL_NOT_SOC',pins_unchanged=True,
                      only_changed_rtl=h.AG,addrgen_sha256=h.M9_SHA,normal_full_cycles_identical=True)
    except Exception as e: result['error']=repr(e)
    h.save(out/'result.json',result);print(json.dumps(result,indent=2),flush=True)
    return int(result['status']!='FOUR_STORE_CASES_PASS_NORMAL_CYCLES_IDENTICAL_NOT_SOC')


if __name__=='__main__': raise SystemExit(main())
