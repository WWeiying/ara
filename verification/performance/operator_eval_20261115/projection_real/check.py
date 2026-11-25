#!/usr/bin/env python3
"""Fail-closed independent checker for the compact, exhaustive target comparator."""
import argparse
import hashlib
import json
from pathlib import Path
import re
import sys

sys.dont_write_bytecode = True
from contract import ATOL, RTOL, POLICY, cases

PHASES = tuple('phase_'+p+'_cycles' for p in
    ('setup','activation','weight','compute','overlap','drain','scheduler','commit','fault','terminal'))
TIMES = ('quant','pack','admit','execute','drain')
KINDS = ('Q8','PACK','OUT','GUARD')


def require(ok, message):
    if not ok:
        raise ValueError(message)


def digest(path):
    h = hashlib.sha256()
    with Path(path).open('rb') as f:
        for block in iter(lambda: f.read(1024*1024), b''):
            h.update(block)
    return h.hexdigest()


def fields(line, prefix, strings=()):
    result = {}
    for token in line[len(prefix):].split():
        require(token.count('=') == 1, 'Malformed field')
        key, value = token.split('=')
        require(key and value and key not in result, 'Duplicate/empty field')
        require(key in strings or re.fullmatch(r'[0-9]+', value), 'Nondecimal '+key)
        result[key] = value if key in strings else int(value)
    return result


def monitor_reports(text):
    reports, current = [], None
    for line in text.splitlines():
        if line == '[PERF] ==== Performance Report Start ====':
            require(current is None, 'Nested ROI report'); current = {}
        elif line == '[PERF] ==== Performance Report End ====':
            require(current is not None, 'Orphan ROI end'); reports.append(current); current = None
        elif line.startswith('[PERF]') and current is not None:
            match = re.fullmatch(r'\[PERF\]\s+([^:]+):\s*([0-9]+(?:\.[0-9]+)?)\s*', line)
            if match:
                key, value = match.groups(); key = key.strip()
                require(key not in current, 'Duplicate ROI metric')
                current[key] = float(value) if '.' in value else int(value)
    require(current is None and len(reports) == 2 and
            all(r.get('total_cycles',0) > 0 for r in reports), 'Two complete commit-marker ROIs required')
    return reports


def parse_log(text, build):
    c, plan = build['case'], build['plan']
    m,n,k,kb = c['m'],c['n'],c['k'],c['k_blocks']
    native = c['backend'] == 'native'
    commands = plan['commands'] if native else []
    require(text.count('Core Test *** SUCCESS ***') == 1, 'Missing/duplicate firmware success')
    perf, trials, comparisons = [], [], {}
    meta = done = None
    for line in text.splitlines():
        if re.match(r'\s*UVM_(?:ERROR|FATAL)\b', line):
            require(re.fullmatch(r'\s*UVM_(?:ERROR|FATAL)\s*:\s*0\s*',line), 'UVM error')
        require(not re.search(r'(?i)(?:^\s*(?:Error[-:]|Fatal:)|Assertion failed|\$fatal|\bTIMEOUT\b|\bTIMED OUT\b)',line),
                'Simulation error/timeout')
        if line.startswith('[QBS_PERF] '):
            require(native and meta is None and len(perf) < 2*len(commands), 'Unexpected native command')
            p = fields(line,'[QBS_PERF] ')
            require(p['seq'] == len(perf)+1 and p['success'] == 1 and all(p[key] == 0 for key in
                ('fault','validation_fault','validation_error','read_fault','context_validation_fault_count')),
                'Command sequence/fault')
            require(sum(p[key] for key in PHASES) == p['busy_cycles'] > 0 and p['phase_fault_cycles'] == 0,
                    'Engine phase partition')
            require(p['probe_compute_without_dot_issue_cycles']+p['dot_active_cycles'] ==
                    p['phase_compute_cycles']+p['phase_overlap_cycles'], 'Compute accounting')
            cmd = commands[len(perf) % len(commands)]
            cm,cn = cmd['m'],cmd['n']
            require((p['m'],p['n'],p['lanes'],p['vlen']) == (cm,cn,4,1024), 'Command geometry')
            require(p['weight_bytes'] == cn*kb*c['weight_block_bytes'] and
                    p['activation_bytes'] == cm*kb*c['activation_block_bytes'] and
                    p['useful_pairs'] == cm*cn*k and p['tiles'] == kb*(cn//4), 'Profile-specific work')
            require(p['pair_capacity'] == 32*p['dot_active_cycles'] == p['useful_pairs'], 'Dot issue capacity')
            require(all(p[key] == 0 for key in ('activation_access','context_fill_count','context_reuse_count',
                'activation_axi_bytes_saved','context_reuse_block_count','context_read_bytes')),
                'Unexpected context reuse in direct suite')
            perf.append(p)
        elif line.startswith('OPR_META '):
            require(meta is None and done is None and len(perf) == 2*len(commands), 'Duplicate/early metadata')
            meta = fields(line,'OPR_META ',('id',))
            require(meta == dict(id=build['build_id'],m=m,n=n,k=k,profile=c['profile'],ap=c['activation_profile'],
                kb=kb,ab=c['activation_block_bytes'],rvv=int(not native),trials=2,policy=1), 'Build/scope mismatch')
        elif line.startswith('OPR_TRIAL '):
            require(meta is not None and done is None and len(trials) < 2, 'Early/late trial')
            r = fields(line,'OPR_TRIAL ')
            require(set(r) == {'trial','status','commands','quant_fcsr','quant_vcsr','fcsr','vcsr','vstart',
                               *(f't{i}' for i in range(6))}, 'Trial schema')
            t = len(trials)
            require(r['trial'] == t and r['status'] == 0 and r['commands'] == len(commands), 'SDK admission/work')
            ts = [r[f't{i}'] for i in range(6)]
            require(all(0 <= a < b < 2**64 for a,b in zip(ts,ts[1:])), 'Phase boundaries')
            require(not t or ts[0] > trials[0]['t5'], 'Overlapping trials')
            require(r['quant_vcsr'] == c['quant_vcsr'] and r['vcsr'] == r['quant_vcsr'] and
                    r['vstart'] == 0 and r['quant_fcsr'] & ~3 == 0, 'Quant/post-execute CSR preservation')
            seed = build['flag_seeds'][t]
            if native:
                require(r['fcsr'] == plan['flags'] | seed, 'Native exact/sticky flags')
            else:
                require(r['fcsr'] in (seed,seed|1), 'RVV unexpected/lost sticky flags')
            trials.append(r)
        elif line.startswith('OPR_CHECK '):
            require(meta is not None and done is None and trials, 'Early/late comparison')
            r = fields(line,'OPR_CHECK ',('kind',))
            require(set(r) == {'trial','kind','count','mismatches','first','expected_hash','actual_hash',
                'raw_differences','first_actual','first_expected'}, 'Comparison schema')
            key = (r['trial'],r['kind'])
            require(r['trial'] == len(trials)-1 and r['kind'] in KINDS and key not in comparisons,
                    'Duplicate/out-of-scope comparison')
            gold = build['comparisons'][r['kind']]
            require(r['count'] == gold['count'] and r['expected_hash'] == gold['expected_hash'],
                    'Golden comparison identity/extent')
            require(r['mismatches'] == 0 and r['first'] == 0xffffffff and
                    r['first_actual'] == r['first_expected'] == 0, 'Exhaustive comparator mismatch')
            require(0 <= r['actual_hash'] <= 0xffffffff and 0 <= r['raw_differences'] <= r['count'], 'Bad comparator range')
            if native or r['kind'] != 'OUT':
                require(r['raw_differences'] == 0 and r['actual_hash'] == r['expected_hash'], 'Nonexact bytes/output')
            else:
                require(r['raw_differences'] != 0 or r['actual_hash'] == r['expected_hash'], 'Inconsistent RVV raw summary')
            comparisons[key] = r
        elif line.startswith('OPR_RAW '):
            require(build['diagnostic'], 'Failure-only raw evidence present on passing run')
            r = fields(line,'OPR_RAW ',('kind','hex'))
            require(set(r) == {'trial','kind','offset','hex'} and r['trial'] in (0,1) and r['kind'] in KINDS
                    and re.fullmatch(r'(?:[0-9a-f]{2}){1,16}',r['hex']), 'Diagnostic raw schema')
        elif line.startswith('OPR_DONE '):
            require(done is None and len(trials) == 2, 'Duplicate/early footer')
            done = fields(line,'OPR_DONE ')
            require(done == {'errors':0}, 'Firmware comparison/status failure')
        elif line.startswith('OPR_'):
            raise ValueError('Unknown workload record')
    require(meta is not None and done is not None and len(trials) == 2 and len(perf) == 2*len(commands)
            and set(comparisons) == {(t,kind) for t in range(2) for kind in KINDS}, 'Incomplete evidence')
    rows = []
    for t,r in enumerate(trials):
        observed = perf[t*len(commands):(t+1)*len(commands)]
        sw = {key:r[f't{i+1}']-r[f't{i}'] for i,key in enumerate(TIMES)}
        busy = sum(p['busy_cycles'] for p in observed)
        require(busy <= sw['execute'], 'Busy exceeds execution ROI')
        rows.append(dict(trial=t,label=('first','repeat')[t],software_cycles=sw,total_cycles=r['t5']-r['t0'],
            native_busy_cycles=busy,execute_outside_engine_cycles=sw['execute']-busy,
            engine_phase_cycles={key:sum(p[key] for p in observed) for key in PHASES},
            engine_counters={key:sum(p[key] for p in observed) for key in
                ('weight_bytes','activation_bytes','useful_pairs','pair_capacity','dot_active_cycles')},
            csr=r,commands=observed,comparisons={kind:comparisons[t,kind] for kind in KINDS}))
    return dict(state='PASS',metrics=dict(case_id=c['id'],backend=c['backend'],format=c['format'],
        baseline_kind=c['baseline_kind'],primary_eligible=c['primary_eligible'],m=m,n=n,k=k,
        provenance=c['provenance'],native_format_model_capture=True,original_f16_weights=False,
        trials=rows,commit_roi_monitor=monitor_reports(text),
        output_values_checked=2*m*n,q8_bytes_checked=2*m*kb*c['activation_block_bytes'],
        packed_bytes_checked=2*m*kb*c['activation_block_bytes'],guard_bytes_checked=1280,
        output_policy=POLICY,hash_only_acceptance=False,numerical_contract=build['numeric_contract'],
        whole_model=False,protocol_checked=False,current_image_checked=False,
        scope='Pinned exhaustive target comparison; parent must independently check image/protocol/commit traces',
        counter_semantics='Exclusive phases partition busy; 32 pairs/dot issue is capacity, not physical utilization'))


def check_run(log_path, build_dir):
    path = Path(build_dir)
    path = path if path.name == 'build.json' else path/'build.json'
    build = json.loads(path.read_text())
    require(build['state'] == 'BUILT_NOT_EXECUTED' and build['rtl_executed'] is False and
            build['post_pins_match'] is True and build['reused_objects'] == 0, 'Untrusted build')
    require(build['case'] in cases() and build['output_policy'] == POLICY and
            build['flag_seeds'] == [0,8] and isinstance(build['diagnostic'],bool) and
            build['numeric_contract'] == dict(native='bit_exact_ordered_qbs_ref',rvv_atol=ATOL,rvv_rtol=RTOL),
            'Build contract drift')
    require(digest(build['elf']) == build['elf_sha256'] and
            digest(build['source_pins']) == build['source_pins_sha256'], 'ELF/inventory drift')
    pins = json.loads(Path(build['source_pins']).read_text())
    require(pins.get(str(Path(__file__).resolve())) == digest(__file__), 'Unpinned checker')
    for name,sha in pins.items():
        require(digest(name) == sha, 'Pinned input/artifact drift: '+name)
    require(digest(build['golden_archive']) == build['golden_archive_sha256'] and
            build['comparator_tests']['state'] == 'PASS' and
            digest(build['comparator_tests']['log']) == build['comparator_tests']['log_sha256'] and
            pins.get(build['comparator_tests']['test']) == digest(build['comparator_tests']['test']),
            'Golden archive/comparator tests')
    from contract import fnv
    c=build['case']
    ab=c['m']*c['k_blocks']*c['activation_block_bytes']
    counts=dict(Q8=ab,PACK=ab,OUT=c['m']*c['n'],GUARD=640)
    require(set(build['comparisons']) == set(counts),'Golden comparison kinds')
    for name,gold in build['comparisons'].items():
        data = Path(gold['path']).read_bytes()
        require(gold['count'] == counts[name] and len(data) == gold['count']*(4 if name == 'OUT' else 1) and
                fnv(data) == gold['expected_hash'] and pins.get(gold['path']) == digest(gold['path']),
                'Golden summary not independently reproducible')
    require(pins.get(build['plan_path']) == digest(build['plan_path']) and
            json.loads(Path(build['plan_path']).read_text()) == build['plan'], 'Plan drift')
    result = parse_log(Path(log_path).read_text(),build)
    result.update(build=str(path.resolve()),build_sha256=digest(path),log=str(Path(log_path).resolve()),
        log_sha256=digest(log_path),elf_sha256=build['elf_sha256'],source_pins_sha256=build['source_pins_sha256'])
    return result


def main():
    p=argparse.ArgumentParser(description=__doc__,allow_abbrev=False)
    p.add_argument('--build',required=True,type=Path)
    p.add_argument('--log',required=True,type=Path)
    p.add_argument('--output',required=True,type=Path)
    a=p.parse_args()
    require(not a.output.exists(),'Refusing to overwrite evidence')
    try:
        result=check_run(a.log,a.build)
    except (ValueError,KeyError,OSError,TypeError) as error:
        a.output.write_text(json.dumps(dict(state='FAIL',metrics={},error=str(error)),indent=2)+'\n')
        raise SystemExit(str(error)) from error
    a.output.write_text(json.dumps(result,indent=2,sort_keys=True)+'\n')
    print(result['state'])


if __name__ == '__main__':
    main()
