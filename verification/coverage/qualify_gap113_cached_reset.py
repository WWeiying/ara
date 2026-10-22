"""Bounded terminal waiter: cancelled epoch + unchanged full cached oracle + measured742 gain."""
import argparse
import csv
import json
import re
import sys
import time
from pathlib import Path
from types import FunctionType
import run_gap113_cached_reset as run
import coverage_bitmap_delta as bitmap
import targeted_toggle_evidence_v2 as toggle

life, require = run.life, run.t.require
RUN_SEAL = '5bbb8d66b4fa869c92919f3d8832be02258fcc7e2e0389d3d3642e606a62017b'
OUT = life.OUT / 'gap113-cached-reset-qualified-742-agent-20261007-01'
sys.path.insert(0, str(life.ROOT/'verification'))
from ara_verify.uvm_dut import check_real_uvm_log


def read_csv(path):
    with path.open() as stream:
        reader = csv.DictReader(stream); rows = list(reader)
    require(rows and all(None not in r and all(v is not None for v in r.values()) for r in rows),
            'Empty/truncated CSV: '+str(path))
    return reader.fieldnames, rows


def split_epochs(commit, vector):
    cuts = [i for i in range(1, len(commit)) if int(commit[i]['cycle']) < int(commit[i-1]['cycle'])]
    resets = [i for i, r in enumerate(vector) if r['event'] == 'reset']
    require(len(cuts) == len(resets) == 1 and vector[0]['event'] == 'config', 'Exactly2 epochs required')
    c, v = cuts[0], resets[0]; cycle = int(vector[v]['cycle'])
    require(max(int(r['cycle']) for r in commit[:c]) <= cycle and int(commit[c]['cycle']) < cycle,
            'Commit/vector reset boundary differs')
    epochs = [(commit[:c], vector[:v]), (commit[c:], [vector[0]]+vector[v+1:])]
    for cr, vr in epochs:
        retired = [r for r in cr if r['event'] == 'retire']
        require(retired and [int(r['order']) for r in retired] == list(range(len(retired))) and
                all(int(r['trap']) == 0 for r in retired), 'Incomplete/trapped epoch retirement')
        require(all(int(cr[i]['cycle']) <= int(cr[i+1]['cycle']) for i in range(len(cr)-1)),
                'Nonmonotonic epoch')
    return epochs, cycle


def write_csv(path, fields, rows):
    with path.open('x', newline='') as stream:
        writer = csv.DictWriter(stream, fieldnames=fields); writer.writeheader(); writer.writerows(rows)


def cancelled_epoch(path, cr, vr, q, symbols, sites):
    pending, starts = {}, {}
    for r in cr:
        key, cycle = int(r['trans_id']), int(r['cycle'])
        if r['event'] == 'arch_start':
            seq = int(r['order']); require(seq not in starts, 'Duplicate epoch0 owner')
            starts[seq] = (int(r['insn'], 16), key, cycle)
        elif r['event'] == 'cvx_req':
            require(key not in pending, 'Duplicate epoch0 request')
            pending[key] = int(r['insn'], 16)
        elif r['event'] == 'cvx_resp':
            require(key in pending and int(r['trap']) == 0, 'Orphan/trapped epoch0 response')
            pending.pop(key)
    require(not pending and not any(r['event'] == 'cvx_req' and int(r['insn'],16) == q.WORD for r in cr),
            'Epoch0 accepted CVXIF pending/custom request; expected backend-only cancellation')
    lanes, vlen, acts = q.inherited.support._parse_vector_trace(path/'vector_trace.csv')
    require((lanes, vlen) == (4, 1024) and len(acts) == 5, 'Epoch0 complete4seed + cancelled custom required')
    selected = sorted(acts, key=lambda s: starts[s][2])
    retired = [r for r in cr if r['event'] == 'retire']
    owners, windows = {}, {}
    for r in vr:
        if r['event'] == 'config': continue
        seq, vid, cycle = int(r['arch_seq']), int(r['vid']), int(r['cycle'])
        require(seq in starts and seq in acts, 'Unbound epoch0 activity')
        if r['event'] == 'alloc':
            require(seq not in owners and seq not in windows, 'Duplicate epoch0 allocation')
            require(cycle >= starts[seq][2], 'Allocation precedes owner')
            owners[seq] = (vid, cycle)
        else:
            require(r['event'] in ('write', 'done') and seq in owners and owners[seq][0] == vid and
                    cycle >= owners[seq][1], 'Epoch0 owner/VID/window drift')
            if r['event'] == 'done': windows[seq] = (owners.pop(seq)[1], cycle)
    custom = selected[4]
    require(set(owners) == {custom} and starts[custom][0] == q.WORD and
            not acts[custom].writes and
            acts[custom].allocations == 1 and acts[custom].completions == 0,
            'Cancelled custom wrote/completed or wrong owner')
    require((acts[custom].vd, acts[custom].vl) == (8, 256), 'Cancelled custom shape differs')
    for i, seq in enumerate(selected[:4]):
        a = acts[seq]; pc = sites[0][i]['pc']
        matches = [r for r in retired if int(r['pc'], 16) == pc and int(r['insn'], 16) == a.instruction]
        require(len(matches) == 1 and a.instruction == starts[seq][0] and a.vd == i*8 and
                a.vl == 256 and windows[seq][1] < owners[custom][1], 'Epoch0 seed binding differs')
        image = q.inherited.seed_image(0)
        expected = {(reg, b): image[reg*128+b] for reg in range(i*8, i*8+8) for b in range(128)}
        q.activity_bytes(a, expected, *windows[seq])
    cu = sorted((r['event'], int(r['order']), int(r['port']), int(r['cycle'])) for r in cr
                if r['event'] in ('uop_alloc', 'uop_done'))
    vu = sorted(('uop_'+r['event'], int(r['arch_seq']), int(r['vid']), int(r['cycle'])) for r in vr
                if r['event'] in ('alloc', 'done'))
    require(cu == vu, 'Epoch0 independent lifecycle differs')
    require(not any(int(r['pc'], 16) == symbols['gap110_qbexec_site0'][0] for r in retired),
            'Cancelled custom retired')
    return dict(status='CANCELLED_FIRST_COMMAND_EXACT4SEEDS_NO_CUSTOM_WRITE_OR_COMPLETION',
                cancelled_arch_seq=custom, cancelled_vid=owners[custom][0], seed_bytes_checked=4096)


def prepare():
    path = run.RUN.with_name(run.RUN.name+'.prepared.json')
    record = life.read_bound(path, RUN_SEAL)
    require(record['command'][-4:] == run.ARGS and record['timeout_s'] == 600, 'Run reset binding differs')
    pins = life.merge_pins(record['pins'], {str(path): RUN_SEAL})
    q = run.cached.qualifier(RUN_SEAL)
    q.independent_native(); view = q.adapter(); symbols, data, sites = view.elf_view()
    for module in list(sys.modules.values()):
        name = getattr(module, '__file__', None)
        if name:
            p = Path(name).resolve()
            if p.suffix == '.py' and str(p).startswith(str(life.ROOT/'verification')+'/'):
                pins = life.merge_pins(pins, {str(p): life.digest(p)})
    p = Path(__file__).with_name('test_qualify_gap113_cached_reset.py')
    pins = life.merge_pins(pins, {str(p): life.digest(p)})
    base = life.read_bound(run.BASE/'admission-manifest.json', run.BASE_SHA)
    pins = life.merge_pins(pins, base['input_pins'])
    pins = life.merge_pins(pins, base['output_pins'])
    ranking = life.OUT/'toggle741-capacity-ranking-agent-20261007-01.json'
    pins = life.merge_pins(pins, {str(ranking):life.digest(ranking)})
    pins = life.merge_pins(pins, json.loads(ranking.read_bytes())['input_pins'])
    life.check(pins)
    return dict(pins=pins, run_seal=RUN_SEAL, baseline_seal=run.BASE_SHA,
                wait_interval_s=60, wait_budget_s=900, coverage_admitted=False)


def collect(plan):
    require(not OUT.exists(), 'Fresh output required'); OUT.mkdir()
    pins = plan['pins']; result = dict(status='RESET_QUALIFICATION_HOLD_NOT_ADMITTED', coverage_admitted=False)
    try:
        life.check(pins)
        status, sha = run.cached.frozen_qual.inherited.terminal(run.RUN)
        reviewed = life.read_bound(run.RUN.with_name(run.RUN.name+'.prepared.json'), RUN_SEAL)
        require(json.loads((run.RUN/'manifest.json').read_bytes()) == reviewed, 'Actual manifest drift')
        started = json.loads((run.RUN/'started.json').read_bytes())
        require(started['command'] == reviewed['command'] and started['elf_sha256'] == run.cached.ELF_SHA and
                started['image_sha256'] == run.cached.frozen_run.reused.IMAGE_SEAL and started['budget_s'] == 600,
                'Actual execution binding drift')
        require(not Path('/proc/%d'%started['pid']).exists(), 'Simulator still live')
        files = [run.RUN/n for n in ('simulation-status.json','manifest.json','started.json','run.vcs.log',
                                     'console.log','commit_trace.csv','vector_trace.csv')]
        files += [p for p in (run.RUN/'code.vdb').rglob('*') if p.is_file()]
        pins = life.merge_pins(pins, {str(p): life.digest(p) for p in files}); life.check(pins)
        log = (run.RUN/'run.vcs.log').read_text()
        require(log.count('kind=state observed=1 target=qbs_compute_final_drain actual=QBS_FINAL_DRAIN') == 1 and
                log.count('kind=state released=1') == 1, 'Exact target reset not observed')
        global_audit = check_real_uvm_log(run.RUN/'run.vcs.log', require_events=True, require_backend=True,
            require_axi=True, vector_trace=run.RUN/'vector_trace.csv', reset_kind='state')
        life.save(OUT/'global-reset-audit.json', global_audit)
        require(global_audit['status'] == 'PASS' and global_audit['uvm_counts']['aborted'] == 0 and
                global_audit['backend_counts']['aborted'] == 1, 'Global reset lifecycle rejected')
        cf, cr = read_csv(run.RUN/'commit_trace.csv'); vf, vr = read_csv(run.RUN/'vector_trace.csv')
        epochs, reset_cycle = split_epochs(cr, vr)
        q = run.cached.qualifier(RUN_SEAL); view = q.adapter(); symbols, data, sites = view.elf_view()
        native = q.independent_native(); audits = []
        for i, (commits, vectors) in enumerate(epochs):
            ep = OUT/('epoch%d'%i); ep.mkdir()
            write_csv(ep/'commit_trace.csv', cf, commits); write_csv(ep/'vector_trace.csv', vf, vectors)
            (ep/'run.vcs.log').write_text(log)
            if i == 0: audits.append(cancelled_epoch(ep, commits, vectors, q, symbols, sites))
            else:
                fn = FunctionType(q.runtime.__code__, dict(q.runtime.__globals__, RUN=ep))
                audits.append(fn(view, symbols, data, sites, native))
        life.save(OUT/'epoch-audits.json', dict(reset_cycle=reset_cycle, epochs=audits))
        design = run.BUILD/'sim/simv.vdb'
        (OUT/'single-inputs.txt').write_text(str(design)+'\n'+str(run.RUN/'code.vdb')+'\n')
        single = bitmap.collect(OUT/'single-inputs.txt')
        before = json.loads((run.BASE/'combined-bits.json').read_bytes())
        require(single['tests'] == [str(run.RUN/'code.vdb')], 'Wrong candidate native identity')
        require(all(pins.get(p) == h for p,h in single['input_hashes'].items()), 'Raw input drift')
        after = bitmap.combine(before, single); delta = bitmap.delta(before, after)
        targets = []
        for target in reviewed['targets']:
            row = single['metrics']['fsm'][run.SCOPE]
            index = target['compiled_serialized_position']
            hit = bool(int(row['bits'],16) >> (row['width']-1-index) & 1)
            targets.append(dict(target, measured_hit=hit))
        # Exact742 binary Toggle baseline is sealed741 union + admitted cached singleton.
        rank = json.loads((life.OUT/'toggle741-capacity-ranking-agent-20261007-01.json').read_bytes())
        scopes = list(q.SCOPES)+[run.SCOPE]
        cached_files = list((run.cached.RUN/'code.vdb/snps/coverage/db/testdata').glob('*/tgl.verilog.data.xml'))
        reset_files = list((run.RUN/'code.vdb/snps/coverage/db/testdata').glob('*/tgl.verilog.data.xml'))
        require(len(cached_files) == len(reset_files) == 1, 'Ambiguous Toggle native data')
        normal, _ = toggle.rows(cached_files[0], scopes); sample, _ = toggle.rows(reset_files[0], scopes)
        baseline = {s:{k:rank['instances'][s][k] for k in ('width','checksum','bits')} for s in scopes}
        gains = toggle.gains(toggle.union(baseline, normal), toggle.union(toggle.union(baseline,normal), sample))
        for p, sha in rank['input_pins'].items(): require(life.digest(Path(p)) == sha, '741 Toggle pin drift')
        pins = life.merge_pins(pins, rank['input_pins'])
        pins = life.merge_pins(pins, {str(cached_files[0]):life.digest(cached_files[0]),
            str(life.OUT/'toggle741-capacity-ranking-agent-20261007-01.json'):life.digest(life.OUT/'toggle741-capacity-ranking-agent-20261007-01.json')})
        life.check(pins)
        for name, value in [('single-bits.json',single),('raw-delta.json',delta),('fsm-targets.json',targets),
                            ('binary-toggle-gain.json',dict(scopes=gains, arrays_not_decoded=True))]:
            life.save(OUT/name,value)
        result.update(status='RESET_TWO_EPOCH_NATIVE_PASS_RAW742_DIAGNOSTIC_NOT_ADMITTED',
            baseline=742, actual_new_fsm=delta['metrics']['fsm'],
            actual_target_hits=sum(t['measured_hit'] for t in targets), targets_total=len(targets),
            actual_binary_toggle_gain=sum(map(len,gains.values())), raw_delta=delta['metrics'],
            full_scalar_ISA_verified=False, spike_custom_ISA_PASS=False, official_toggle_percentage=False)
    except Exception as e:
        result['reason'] = type(e).__name__+': '+str(e)
    life.save(OUT/'evidence-pins.json',pins)
    result['output_pins'] = {str(p):life.digest(p) for p in OUT.rglob('*') if p.is_file()}
    life.save(OUT/'qualification.json',result)
    print(json.dumps(dict(output=str(OUT), seal=life.digest(OUT/'qualification.json'), result=result['status'])),flush=True)


def main():
    p = argparse.ArgumentParser(description=__doc__); p.add_argument('mode',choices=('prepare','worker'))
    p.add_argument('--plan-seal'); a=p.parse_args(); path=OUT.with_name(OUT.name+'.prepared.json')
    if a.mode == 'prepare':
        require(not path.exists() and not OUT.exists(), 'Fresh plan only')
        life.save(path,prepare()); print(json.dumps(dict(plan=str(path),seal=life.digest(path))))
    else:
        plan=life.read_bound(path,a.plan_seal)
        plan['pins']=life.merge_pins(plan['pins'],{str(path):a.plan_seal})
        life.check(plan['pins']); deadline=time.monotonic()+plan['wait_budget_s']
        while not (run.RUN/'simulation-status.json').exists():
            if time.monotonic() >= deadline:
                require(not OUT.exists(),'Output exists'); OUT.mkdir()
                life.save(OUT/'qualification.json',dict(status='TERMINAL_WAIT_HOLD',coverage_admitted=False)); return
            time.sleep(plan['wait_interval_s'])
        collect(plan)


if __name__ == '__main__': main()
