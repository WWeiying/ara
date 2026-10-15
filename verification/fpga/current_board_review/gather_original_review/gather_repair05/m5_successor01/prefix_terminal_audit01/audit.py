#!/usr/bin/env python3
"""Offline source-derived oracle audit; never launch a DUT or rewrite sealed gates."""
import csv
from collections import Counter
import hashlib
import importlib.util
import itertools
import json
from pathlib import Path
import sys

sys.dont_write_bytecode = True
OUT = Path(__file__).resolve().parent
HERE = OUT.parent
GATHER = HERE.parent.parent
DATA = GATHER / 'stall_prefix2_03'
RUN = HERE / 'prefix_vcs_candidate05_01'
EXPECTED = {
    'prefix_replay.py': 'aeaa04e3bf9ba11e7302c896066f6b144bb4ec590eb2d8fb01ee5d23328c377f',
    'prefix_plan.json': '293f376e169cfd434e7988804990c58a6ae07981bf72cfd5e34b2c4eead25409',
    'focused01/acceptance.json': '6c963d2b5c1e858acb853c4a3f50ecf2dced01091bc2cc77e2cd2f1e1b735d51',
}


def require(ok, message):
    if not ok:
        raise ValueError(message)


def read(path):
    return json.loads(path.read_text())


def sha(path):
    digest = hashlib.sha256()
    with path.open('rb') as stream:
        for block in iter(lambda: stream.read(1048576), b''):
            digest.update(block)
    return digest.hexdigest()


def module(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    loaded = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(loaded)
    return loaded


def oracle(op):
    # Direct transcription of the authentic C uint64 xorshift and original loop order.
    rng, data, indices = 0xe736815b449aec21, [], []
    for i in range(512):
        rng = (rng ^ (rng << 13)) & ((1 << 64) - 1)
        rng ^= rng >> 7
        rng = (rng ^ (rng << 17)) & ((1 << 64) - 1)
        data.append(rng & 255)
        indices.append((0, 1, 511, 512, 513, rng % 544)[i % 6])
    tuples = itertools.product(range(3), range(21), range(8), range(7), range(4), range(4))
    rows = []
    for seed, opcode, scalar_index, length, mode, trial in tuples:
        if opcode != op:
            continue
        require(seed == scalar_index == 0, 'Unexpected prefix domain')
        vl = (0, 1, 2, 3, 256, 511, 512)[length]
        start = (1, vl // 2, vl if vl <= 1023 else 511, 511)[trial]
        selected = [mode == 0 or (mode == 1 and bool(i % 2)) or
                    (mode == 2 and i % 7 == 2) for i in range(512)]
        mask = [0] * 128
        values = [91] * 512
        for i, pick in enumerate(selected):
            if pick:
                mask[i // 8] |= 1 << (i % 8)
            if pick and start <= i < vl:
                index = 0 if op == 1 else indices[i]
                values[i] = data[index] if index < 512 else 0
        rows.append(dict(tuple=[seed, opcode, scalar_index, length, mode, trial],
                         vl=vl, vstart=start, scalar=0, predicate=mask, output=values))
        if len(rows) == 98:
            break
    require(rows[-1]['tuple'] == [0, op, 0, 6, 0, 1], '98-call bound changed')
    return data, indices, rows


def recalculate(spec, folder):
    data, indices, expected = oracle(spec['operation'])
    lookup = {item['pc']: i for i, item in enumerate(spec['soc_routine'])}
    regs, memory, counts, events = {}, {}, [0] * 13, Counter()
    calls, current, step, retired, last_cycle, parked = [], None, 0, 0, -1, 0
    exited, exit_row, first66 = False, None, None

    def finish():
        if current is not None:
            require(step == 0 and current['indices'] == set(range(514)), 'Incomplete call oracle/asm')
            current.pop('indices')
            require(current['fullcap'] == 512 and current['guards'] == 2, 'Incomplete fullcap/guards')

    with (folder / 'commit_trace.csv').open(newline='') as stream:
        for line, row in enumerate(csv.DictReader(stream), 2):
            cycle = int(row['cycle'])
            require(cycle >= last_cycle, 'Cycle moved backwards')
            last_cycle = cycle
            events[row['event']] += 1
            require(row['event'] != 'cvx_exception', 'CVX exception')
            if row['event'] != 'retire':
                continue
            require(int(row['order']) == retired and int(row['trap']) == 0, 'Retirement order/trap')
            retired += 1
            require(retired <= 5_000_000, 'Retired budget exceeded')
            pc, insn = int(row['pc'], 16), int(row['insn'], 16)
            address, value = int(row['mem_addr'], 16), int(row['rd_wdata'], 16)
            rd = int(row['rd'])
            rmask, wmask = int(row['mem_rmask'], 16), int(row['mem_wmask'], 16)
            if exited:
                require(pc == spec['park_pc'] and insn == int(spec['park_insn'], 16) and
                        rd == rmask == wmask == 0, 'Post-exit side effect or non-original parking')
                parked += 1
                continue
            if wmask and insn & 127 == 0x23:
                width = 1 << ((insn >> 12) & 7)
                require(width <= 8, 'Invalid scalar store width')
                raw = int(row['mem_wdata'], 16)
                for byte in range(width):
                    memory[address + byte] = (raw >> (8 * byte)) & 255
            if pc in lookup:
                i = lookup[pc]
                require(i == step and insn == int(spec['soc_routine'][i]['insn'], 16), '13asm order/encoding drift')
                if i == 0:
                    finish()
                    j = len(calls)
                    require(j < 98, 'Extra call')
                    gold = expected[j]
                    setup = {10: spec['input_address'], 11: spec['index_address'],
                             12: spec['output_address'] + 1, 13: gold['vl'], 14: 512,
                             15: spec['predicate_address'], 16: 0, 17: gold['vstart']}
                    require(all(regs.get(r) == v for r, v in setup.items()), 'Actual call register setup mismatch')
                    for base, values, width in (
                        (spec['input_address'], data, 1),
                        (spec['index_address'], indices if spec['operation'] == 20 else [v & 255 for v in indices],
                         2 if spec['operation'] == 20 else 1),
                        (spec['predicate_address'], gold['predicate'], 1),
                        (spec['output_address'], [91] * 514, 1),
                    ):
                        for k, want in enumerate(values):
                            got = [memory.get(base + k * width + b) for b in range(width)]
                            require(None not in got and sum(v << (8 * b) for b, v in enumerate(got)) == want,
                                    f'Actual source/mask/output setup mismatch call{j+1} base{base:x} index{k}')
                    current = dict(ordinal=j+1, original_tuple=gold['tuple'], fullcap=0, guards=0,
                                   indices=set(), setup_values_checked=512+512+128+514)
                    calls.append(current)
                if i in (0, 5, 10):
                    require(rd == 5 and value == (512 if i != 5 else gold['vl']), 'Actual vsetvli VL/cap mismatch')
                if i == 8:
                    require(regs.get(28) == 0 and regs.get(13) == gold['vl'] and
                            regs.get(17) == gold['vstart'], 'Actual target tuple mismatch')
                    current['target'] = dict(pc=hex(pc), insn=row['insn'], cycle=cycle,
                                             retired=retired, csv_line=line, vl=gold['vl'], vstart=gold['vstart'])
                if i == 9:
                    require(rd == 10 and value == 0, 'Returned vstart nonzero')
                    current['returned_vstart'] = 0
                counts[i] += 1
                step = (step + 1) % 13
            if current is not None and rmask and spec['output_address'] <= address < spec['output_address'] + 514:
                index = address - spec['output_address']
                require(step == 0 and insn & 127 == 3 and index not in current['indices'],
                        'Oracle before return/duplicate/not scalar load')
                want = 91 if index in (0, 513) else expected[current['ordinal']-1]['output'][index-1]
                require(value & 255 == want, f'Oracle mismatch call{current["ordinal"]} element{index-1}')
                current['indices'].add(index)
                current['guards' if index in (0, 513) else 'fullcap'] += 1
                if spec['operation'] == 20 and current['ordinal'] == 66 and index == 129:
                    first66 = dict(csv_line=line, raw_row=row, expected=want, actual=value & 255,
                                   logical_element=128, authentic_index128=indices[128],
                                   authentic_input511=data[511], wrong_shifted_index256=indices[256])
            if address == spec['exit_store_address'] and wmask:
                require(pc == spec['exit_store_pc'] and int(row['mem_wdata'], 16) == 0 and exit_row is None,
                        'CTRL exit nonzero/duplicate/wrong PC')
                finish()
                exit_row, exited = row, True
                # Avoid finishing the already validated call again at EOF.
                current = None
            if rd:
                regs[rd] = value
    require(exited and len(calls) == 98 and counts == [98] * 13, 'Missing complete98/asm/exit')
    if spec['operation'] == 20:
        require(calls[65]['original_tuple'] == [0, 20, 0, 4, 0, 1] and
                first66 and first66['authentic_index128'] == 511 and first66['expected'] == first66['actual'] == 79,
                'Original failing66 tuple not repaired')
    return dict(status='PASS_RAW_SOURCE_DERIVED98_FULLORACLE', calls=calls,
                routine_retire_counts=counts, returned_vstart_zero=98,
                fullcap_scalar_checks=sum(c['fullcap'] for c in calls),
                guards=sum(c['guards'] for c in calls), actual_output_loads=50372,
                event_counts=dict(events), csv_rows=sum(events.values()), retired=retired,
                last_cycle=last_cycle, ctrl_exit=exit_row, parked=parked, repaired_call66=first66)


def audit():
    for file, digest in EXPECTED.items():
        require(sha(HERE / file) == digest, 'Sealed worker/plan/focus drift: ' + file)
    plan = read(HERE / 'prefix_plan.json')
    require(read(RUN / 'plan.json') == plan, 'Executed plan differs')
    pins = {}
    for file in ('baseline_pins.json', 'prepared_pins.json'):
        for path, digest in read(DATA / file).items():
            require(sha(Path(path)) == digest, 'Source/prepared pin drift: ' + path)
            pins[path] = digest
    sys.path.insert(0, str(GATHER))
    import audit_accepted8 as asm
    sys.path.insert(0, str(GATHER.parent / 'integration'))
    integration = module('prefix_offline_integration', GATHER.parent / 'integration/run.py')
    adapter = module('prefix_offline_adapter', GATHER.parent / 'integration/prepare.py')
    ledger = read(Path(plan['image']) / 'image.json')
    accepted = read(HERE / 'focused01/acceptance.json')
    require(sha(Path(plan['image']) / 'image.json') == accepted['image']['image_sha256'], 'Image ledger identity drift')
    snapshot = Path(ledger['snapshot'])
    require(sha(snapshot / 'snapshot.json') == ledger['snapshot_sha256'] == accepted['image']['snapshot_sha256'], 'Snapshot drift')
    root = integration.sealed(snapshot)
    _, _, _, simulation_image = integration.framework(root)
    require(simulation_image(Path(ledger['simv'])) == ledger['files'], 'Image byte drift')
    for file, field in (('simulator.conf', 'configuration_sha256'), ('vcs_source_manifest.json', 'manifest_sha256')):
        require(sha(Path(ledger['simv']).parent / file) == ledger[field], 'Image config/manifest drift')
    from ara_verify.vcs_source_manifest import collect
    from ara_verify.trace import validate_trace
    manifest = read(Path(ledger['simv']).parent / 'vcs_source_manifest.json')
    require(collect(Path(manifest['filelist']), root, [Path(p) for p in manifest['extra_sources']]) == manifest['files'],
            'Compiled source manifest drift')
    checker = module('prefix_readonly_log_gate', GATHER / 'stall_prefix2_launch02/checker.py')
    complete, run, summary = read(RUN / 'complete.json'), read(RUN / 'replay/run.json'), read(RUN / 'replay/summary.json')
    require(complete['status'] == 'PASS_TWO_AUTHENTIC98_PREFIXES_M5' and complete['runner_returncode'] == 0 and
            complete['retries'] == 0 and complete['focus_acceptance_sha256'] == EXPECTED['focused01/acceptance.json'],
            'Worker terminal not accepted')
    names = [c['name'] for c in plan['cases']]
    require(run['status'] == 'COMPLETE' and run['completed_at'] and run['tests'] == names and
            run['jobs'] == 2 and run['timeout_s'] == 9000 and run['status_counts'] == {'PASS': 2} and
            run['commit_trace'] and not run['code_coverage'] and run['simv'] == ledger['simv'], 'Run identity/gate drift')
    programs = read(Path(plan['programs']) / 'programs.json')
    require(programs['backend'] == 'vcs-soc' and
            sha(DATA / 'prepared/provenance.json') == programs['provenance_sha256'], 'Program source provenance drift')
    require([r['name'] for r in summary] == names and complete['results'] == summary, 'Terminal membership differs')
    results = []
    for spec, terminal in zip(plan['cases'], summary):
        name = spec['name']
        folder = RUN / 'replay/tests' / name
        require(terminal['status'] == 'PASS' and terminal['returncode'] == 0 and not terminal['reason'] and
                terminal['artifact_dir'] == str(folder) and terminal['elapsed_s'] < 9000, 'Case nonPASS/nonexit0/budget')
        entry = programs['programs'][name]
        require(sha(Path(entry['path'])) == sha(folder / 'input.elf') == entry['sha256'] == spec['elf_sha256'], 'ELF drift')
        prepared = DATA / 'prepared' / name
        original = prepared / 'original'
        source = adapter.adapt((original / 'scenario.c').read_text(), name)
        anchor = '            ++cases;\n'
        require(source.count(anchor) == 1, 'Ambiguous original statistics')
        source = source.replace(anchor, anchor + '            if(cases==98)goto prefix_done;\n')
        source = source.replace('    text(errors ? "RVV_PERMUTE_FAIL sew=":"RVV_PERMUTE_PASS sew=");',
            'prefix_done:\n    if(cases!=98)++errors;\n    text(errors ? "RVV_GATHER_PREFIX_FAIL sew=":"RVV_GATHER_PREFIX_PASS sew=");')
        require(source == (prepared / 'case.c').read_text() and sha(original / 'scenario.c') == spec['source_sha256'] and
                sha(original / 'original_linux.elf') == spec['original_linux_elf_sha256'], 'Authentic source/only-bound diff drift')
        routine = asm.instructions(folder / 'input.elf', name + '_op_' + str(spec['operation']))
        require(routine == spec['soc_routine'] and len(routine) == 13, 'Actual SoC ELF disassembly drift')
        archived = asm.archived_window(original / 'original_linux.elf', routine)
        require([r['insn'] for r in archived] == [r['insn'] for r in routine], 'Archived13asm encodings drift')
        inputs = read(folder / 'inputs.json')
        require(inputs['binary'] == dict(source=entry['path'], path=str(folder / 'input.elf'), sha256=entry['sha256']) and
                inputs['simv'] == dict(path=ledger['simv'], image_sha256=ledger['files']), 'Private input/image identity drift')
        command = read(folder / 'command.json')
        argv = command['command']
        require(argv[0] == ledger['simv'] and command['cwd'] == str(folder / 'work') and '+NO_FSDB' in argv and
                not any(s in ('-cm', '-ucli') for s in argv), 'Wrong command/instrumentation')
        for prefix, value in (('+TESTCASE=', name), ('+PRELOAD=', str(folder / 'input.elf')),
                              ('+COMMIT_TRACE=', str(folder / 'commit_trace.csv'))):
            require([s for s in argv if s.startswith(prefix)] == [prefix + value], 'Wrong command binding')
        for path in (folder / 'console.log', folder / 'work/run.vcs.log'):
            checker.console_gate(path.read_text(), name)
        trace = validate_trace(folder / 'commit_trace.csv')
        require(trace['cvx_exception_count'] == 0, 'CVX exception trace')
        measured = recalculate(spec, folder)
        require((measured['csv_rows'], measured['retired'], measured['last_cycle']) ==
                (trace['rows'], trace['retire_count'], trace['last_cycle']), 'Independent trace count disagreement')
        for file in ('console.log', 'work/run.vcs.log', 'commit_trace.csv', 'input.elf', 'inputs.json', 'command.json'):
            path = folder / file
            pins[str(path)] = sha(path)
        measured.update(name=name, elapsed_s=terminal['elapsed_s'], elf_sha256=entry['sha256'],
                        source_sha256=spec['source_sha256'], trace_validation=trace,
                        original_linux_elf_sha256=spec['original_linux_elf_sha256'],
                        original13asm_identical=True, source_only_original_bound_change=True)
        results.append(measured)
        print(name, 'RAW_PASS98', measured['fullcap_scalar_checks'], measured['guards'],
              'retired', measured['retired'], 'last_cycle', measured['last_cycle'], flush=True)
    for file in ('prefix_plan.json', 'prefix_replay.py', 'focused01/acceptance.json'):
        pins[str(HERE / file)] = sha(HERE / file)
    for file in ('complete.json', 'plan.json', 'admission.json', 'replay/run.json', 'replay/summary.json'):
        pins[str(RUN / file)] = sha(RUN / file)
    pins[str(Path(plan['image']) / 'image.json')] = sha(Path(plan['image']) / 'image.json')
    return dict(status='PASS_INDEPENDENT_RAW_TWO_AUTHENTIC98_PREFIXES_M5', results=results,
                input_pins=pins, source_prepared_pins_verified=len(read(DATA / 'baseline_pins.json')) +
                len(read(DATA / 'prepared_pins.json')), snapshot_files_verified=len(read(snapshot / 'snapshot.json')['files']),
                image_files_verified=len(ledger['files']), compiled_source_files_verified=len(manifest['files']),
                existing_worker_oracle_gates_used_as_acceptance=False, image=accepted['image'],
                original_stopped_tuple=None, exact11_failure_reproduction=False, original_linux_elf_replay=False,
                original_c_entire_linux_binary_rebuild_proven=False, full_parent_closure=False,
                simulations_started=0, sealed_inputs_modified=False, auditor_sha256=sha(Path(__file__)))


if __name__ == '__main__':
    require(not (OUT / 'audit.json').exists(), 'Fresh audit output required')
    try:
        result = audit()
    except Exception as error:
        result = dict(status='NOT_ACCEPTED_OFFLINE_AUDIT', error=repr(error), simulations_started=0)
        with (OUT / 'failure.json').open('x') as stream:
            json.dump(result, stream, indent=2)
        raise
    with (OUT / 'audit.json').open('x') as stream:
        json.dump(result, stream, indent=2)
        stream.write('\n')
    print(result['status'], OUT, flush=True)
