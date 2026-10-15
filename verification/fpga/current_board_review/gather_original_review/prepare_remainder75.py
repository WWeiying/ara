#!/usr/bin/env python3
"""Reuse the twelve sealed ports, prepare sixty-three, reference all seventy-five."""
import difflib
import itertools
from pathlib import Path
import re
import shutil
import subprocess
import sys
import time

sys.dont_write_bytecode = True
import prepare_batch as base
import prepare_remainder12 as previous
from prepare_successor import narrow, replacements, symbol, SPIKE
from audit_accepted8 import instructions, archived_window, OBJDUMP
from replay_candidate03 import read, require, pins_check, oracle

HERE, OLD = base.HERE, previous.OUT
OUT = HERE / 'remainder75_01'


def main():
    require(not OUT.exists(), 'Fresh successor required; no overwrite/retry')
    started = time.monotonic()
    old_ready = read(OLD / 'ready.json')
    require(old_ready['status'] == 'PREPARED_12_HOST_SPIKE_PASS_NOT_DUT', 'Twelve not ready')
    pins = dict(read(OLD / 'source_pins.json'))
    for path in OLD.rglob('*'):
        if path.is_file():
            pins[str(path)] = base.sha(path)
    for file in (Path(__file__), HERE / 'test_remainder12.py'):
        pins[str(file)] = base.sha(file)
    pins_check(pins)
    inventory = read(HERE / 'inventory83.json')['records']
    audit = read(HERE / 'acceptance_audit01/audit.json')
    require(audit['status'] == 'PASS_8_SOURCE_FULLORACLE_IDENTITY_AUDIT', 'Accepted8 audit missing')
    accepted_names = {r['original_case']['name'] for r in audit['results']}
    old_provenance = read(OLD / 'prepared01/provenance.json')
    first = old_provenance['cases']
    first_names = {c['original_case']['name'] for c in first}
    rest = [r for r in inventory if r['case']['name'] not in accepted_names | first_names]
    remaining_names = first_names | {r['case']['name'] for r in rest}
    require(len(first) == 12 and len(rest) == 63 and len(remaining_names) == 75 and
            not remaining_names & accepted_names and
            remaining_names | accepted_names == {r['case']['name'] for r in inventory}, '8+75 union differs')
    OUT.mkdir()
    prepared, diffs = OUT / 'prepared75', OUT / 'source_diffs'
    prepared.mkdir()
    diffs.mkdir()
    host = read(OLD / 'host_semantics.json')['results']
    cases = list(first)
    for case in first:
        shutil.copytree(OLD / 'prepared01' / case['id'], prepared / case['id'])
        for label in ('adapter', 'loops'):
            shutil.copyfile(OLD / 'source_diffs' / (case['id']+'.'+label+'.diff'),
                            diffs / (case['id']+'.'+label+'.diff'))
    sys.path.insert(0, str(base.INTEGRATION))
    from prepare import adapt
    for record in rest:
        case = record['case']
        name = 'gather_' + case['name'].removeprefix('rvv_small_gather_restart_')
        folder = prepared / name / 'original'
        folder.mkdir(parents=True)
        for file in (*case['scenario_sources'], 'case.json'):
            shutil.copyfile(Path(record['source_directory']) / file, folder / file)
        archive = (folder / 'scenario.c').read_text()
        adapted = adapt(archive, name)
        op = case['selected_trial']['op']
        port = narrow(adapted, op)
        reversed_port = port
        for before, after in replacements(op):
            require(reversed_port.count(after) == 1, 'Ambiguous six-loop diff')
            reversed_port = reversed_port.replace(after, before)
        require(reversed_port == adapted, name + ': non-loop change')
        selected, = re.findall(previous.FILTER, archive, re.M)
        selected = tuple(map(int, selected))
        require(selected == (0, op, 0, 2, 0, 0), name + ': tuple differs')
        original_domain = [t for t in itertools.product(range(3), range(21), range(8), range(7), range(4), range(4))
                           if t[1] == op and t == selected]
        narrowed_domain = list(itertools.product(range(1), range(op, op+1), range(1), range(2, 3), range(1), range(1)))
        require(original_domain == narrowed_domain == [selected], name + ': executed domain differs')
        (folder.parent / 'case.c').write_text(port)
        for label, before, after in (('adapter', archive, adapted), ('loops', adapted, port)):
            (diffs / (name+'.'+label+'.diff')).write_text(''.join(difflib.unified_diff(
                before.splitlines(True), after.splitlines(True), fromfile=name+'/'+label+'_before.c',
                tofile=name+'/'+label+'_after.c')))
        cap, expected = previous.scalar(case)
        cases.append(dict(id=name, source_directory=record['source_directory'], original_case=case,
            assembly='operations.S', defines=[f"SEW={case['sew']}", 'RESTART_PERMUTATIONS=1', f'PERMUTE_OP_MASK={1 << op}'],
            pass_markers=[f'BOARD_CASE_PASS {name}', 'BOARD_REPLAY_PASS', f"RVV_PERMUTE_PASS sew={case['sew']} cases=1 errors=0"]))
        host.append(dict(name=name, status='PASS', tuple=selected, old_enumerations=56448, new_enumerations=1,
            capacity=cap, full_cap_expected=expected, guards=[91,91], expected_returned_vstart=0,
            expected_cases=1, expected_errors=0, reversible_six_loop_diff=True, full_setup_asm_oracle_retained=True))
    for file in ('runtime.c', 'startup.S', 'replay.ld'):
        shutil.copyfile(OLD / 'prepared01' / file, prepared / file)
        require(base.sha(prepared / file) == base.sha(base.INTEGRATION / file), 'Runtime drift')
    base.save(OUT / 'baseline_pins.json', pins)
    provenance = dict(cases=cases, vlen=1024, nr_lanes=4, generator_sha256=base.sha(Path(__file__)),
        adapter_sha256=base.sha(base.INTEGRATION / 'prepare.py'), reused12_provenance_sha256=base.sha(OLD / 'prepared01/provenance.json'),
        scope='75 archived exact source singles; accepted8 separate, no parent/Linux ELF closure',
        files={str(p.relative_to(prepared)):base.sha(p) for p in sorted(prepared.rglob('*')) if p.is_file()})
    base.save(prepared / 'provenance.json', provenance)
    base.save(OUT / 'host_semantics.json', dict(status='PASS_75_EXACT_TUPLES', results=host))
    fresh = OUT / 'fresh63'
    fresh.mkdir()
    base.HERE = fresh
    fresh_provenance = dict(provenance, cases=cases[12:])
    soc63 = base.build(prepared, fresh_provenance, 'soc')
    spike63 = base.build(prepared, fresh_provenance, 'spike')
    soc = dict(read(OLD / 'soc01/programs.json')['programs'], **soc63)
    spike = dict(read(OLD / 'spike01/programs.json')['programs'], **spike63)
    compiler = read(fresh / 'soc01/programs.json')['compiler']
    require(compiler == read(OLD / 'soc01/programs.json')['compiler'], 'Compiler identity differs')
    for backend, programs in (('soc75', soc), ('spike75', spike)):
        folder = OUT / backend
        folder.mkdir()
        base.save(folder / 'programs.json', dict(programs=programs, compiler=compiler, prepared=str(prepared),
            backend='vcs-soc' if backend == 'soc75' else 'spike-htif',
            provenance_sha256=base.sha(prepared / 'provenance.json'), reused12_no_rebuild=True, vcs_started=False))
    coverage = read(OLD / 'coverage83.json')
    for row in coverage['records']:
        if row['name'] not in accepted_names:
            row['status'] = 'PREPARED_NOT_DUT'
        row['original_failure_detail'] = next(r['case']['original_failure_detail'] for r in inventory if r['case']['name'] == row['name'])
    coverage.update(prepared_not_dut=75, not_prepared=0, still_unaccepted=75,
                    exact_union_accepted8_remaining75=True, accepted_unchanged=True)
    base.save(OUT / 'coverage83.json', coverage)
    reference = OUT / 'reference75'
    reference.mkdir()
    sys.path.insert(0, str(base.ROOT / 'verification'))
    from ara_verify.spike_probe import check_spike_vstart, probe_paths
    cc, probe_source = probe_paths(base.ROOT)
    require(check_spike_vstart(SPIKE, cc, reference / 'vstart_probe', probe_source)['status'] == 'PASS', 'Spike capability not PASS')
    results = []
    for case in cases:
        name, op = case['id'], case['original_case']['selected_trial']['op']
        entry, elf = spike[name], Path(spike[name]['path'])
        routine = instructions(Path(soc[name]['path']), name+'_op_'+str(op))
        archived = archived_window(Path(case['source_directory']) / 'scenario.elf', routine)
        target, = [r for r in routine if r['text'].startswith(('vrgather.', 'vrgatherei16.'))]
        csr, = [r for r in routine if r['text'].startswith('csrr\ta0,vstart')]
        spike_routine = instructions(elf, name+'_op_'+str(op))
        require([r['insn'] for r in routine] == [r['insn'] for r in spike_routine], 'SoC/Spike target routine differs')
        spike_target, = [r for r in spike_routine if r['text'].startswith(('vrgather.', 'vrgatherei16.'))]
        exit_pc, _ = symbol(elf, 'replay_exit', OBJDUMP)
        log_pc, _ = symbol(elf, 'replay_log', OBJDUMP)
        output_pc, _ = symbol(Path(soc[name]['path']), 'output', OBJDUMP)
        exit_store, = [r for r in instructions(elf, 'replay_exit') if r['text'].startswith('sd\t')]
        debug, log, commits = (reference / (name+ext) for ext in ('.cmd', '.log', '.commits.log'))
        debug.write_text(f'until pc 0 {exit_pc:x}\nreg 0 a0\nstr {log_pc:x}\nrs\n')
        command = [str(SPIKE), '-d', '--debug-cmd='+str(debug), '--isa=rv64gcv_zvl1024b', '-m2',
                   '--log-commits', '--log='+str(commits), str(elf)]
        begin = time.monotonic()
        with log.open('x') as stream:
            run = subprocess.run(command, stdout=stream, stderr=subprocess.STDOUT, timeout=30)
        text = log.read_text()
        require(run.returncode == 0 and oracle(entry, text) and re.search(r'^0x0{16}$', text, re.M), name+': Spike not full PASS/exit0')
        count, hits, exited = 0, 0, False
        for line in commits.read_text().splitlines():
            match = re.match(r'core\s+0:\s+\d\s+(0x[0-9a-f]+)\s+\((0x[0-9a-f]+)\)', line)
            if match and int(match[1],16) >= 0x80000000:
                pc = int(match[1],16)
                count += 1
                if pc == spike_target['pc']:
                    require(int(match[2],16) == int(spike_target['insn'],16), 'Spike target encoding drift')
                    hits += 1
                if pc == exit_store['pc']:
                    exited = True
                    break
        require(exited and hits == 1, 'Incomplete Spike retirement evidence')
        results.append(dict(name=name, status='PASS', returncode=0, full_oracle_markers=True, command=command,
            elapsed_s=time.monotonic()-begin, elf_sha256=entry['sha256'], soc_elf_sha256=soc[name]['sha256'],
            log_sha256=base.sha(log), commit_log_sha256=base.sha(commits), firmware_retired_to_htif_store=count,
            spike_target_hits=hits, soc_target=target, returned_vstart_pc=csr['pc'], output_address=output_pc,
            original_routine_instructions=len(routine), archived_routine_encoding_identical=True,
            archived_target_pc=hex(archived[0]['pc']), counts_are_not_dut_cycles=True))
    pins_check(pins)
    base.save(reference / 'reference.json', dict(status='SPIKE_75_FULLORACLE_PASS_NOT_DUT', results=results,
        spike_sha256=base.sha(SPIKE), old_pins_unchanged=True, fresh_reference_all75=True))
    base.save(OUT / 'prepared_ready.json', dict(status='PREPARED_75_HOST_SPIKE_PASS_NOT_DUT', vcs_started=False,
        fresh63=63, reused12=12, accepted_separate=8, source_union=83, elapsed_s=time.monotonic()-started,
        baseline_pins_sha256=base.sha(OUT / 'baseline_pins.json'), reference_sha256=base.sha(reference / 'reference.json'),
        scope='All remaining numerical-source records prepared, not DUT or full parent closure'))
    print('PREPARED_75_HOST_SPIKE_PASS_NOT_DUT', OUT, flush=True)


if __name__ == '__main__':
    main()
