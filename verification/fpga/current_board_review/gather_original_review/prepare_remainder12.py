#!/usr/bin/env python3
"""Prepare twelve archived shape gaps only; no DUT launcher or RTL changes."""
import difflib
from fractions import Fraction
import itertools
from pathlib import Path
import re
import shutil
import subprocess
import sys
import time

sys.dont_write_bytecode = True
import prepare_batch as base
from prepare_successor import narrow, replacements, symbol, SPIKE
from audit_accepted8 import instructions, archived_window, OBJDUMP
from replay_candidate03 import read, require, pins_check, oracle

HERE = base.HERE
OUT = HERE / 'remainder12_01'
SELECTED = (
    'e8_mf4', 'e8_mf2_ops20', 'e8_m1_ops1', 'e8_m2_ops3',
    'e16_mf2_ops20', 'e16_m2_ops0', 'e16_m4_ops20', 'e32_mf2_ops3',
    'e32_m2_ops0', 'e32_m4_ops1', 'e64_m2_ops3', 'e64_m4_ops20',
)
FILTER = (r'^            if\(!\(seed==(\d+) && op==(\d+) && s==(\d+) && '
          r'l==(\d+) && mode==(\d+) && trial==(\d+)\)\)continue;\n')


def scalar(case):
    cap = int(Fraction(case['lmul'].replace('mf', '1/').replace('m', '')) * 1024 / case['sew'])
    op = case['selected_trial']['op']
    mask64 = (1 << 64) - 1
    rng, data = 0xe736815b449aec21, []
    for _ in range(cap):
        rng ^= (rng << 13) & mask64
        rng ^= rng >> 7
        rng ^= (rng << 17) & mask64
        data.append(rng & ((1 << case['sew']) - 1))
    first_index = 31 if op == 3 else 0
    second_index = 1 if op in (0, 20) else first_index
    require(case['selected_trial']['actual'] == (data[first_index] if first_index < cap else 0),
            case['name'] + ': historical numerical identity differs')
    expected = [91, data[second_index] if second_index < cap else 0] + [91] * (cap - 2)
    return cap, expected


def main():
    require(not OUT.exists(), 'Fresh output required; never overwrite sealed records')
    started = time.monotonic()
    accepted = read(HERE / 'acceptance_audit01/audit.json')
    require(accepted['status'] == 'PASS_8_SOURCE_FULLORACLE_IDENTITY_AUDIT', 'Accepted audit missing')
    pins = dict(read(HERE / 'acceptance_audit01/pins.json'))
    for file in ('inventory83.json', 'lineage83.json', 'acceptance_audit01/audit.json',
                 'acceptance_audit01/pins.json', 'prepare_successor.py', 'prepare_batch.py',
                 'audit_accepted8.py', 'replay_candidate03.py', 'prepare_remainder12.py'):
        pins[str(HERE / file)] = base.sha(HERE / file)
    inventory = read(HERE / 'inventory83.json')
    lineage = read(HERE / 'lineage83.json')
    mapping = Path(lineage['parent_mapping'])
    require(base.sha(mapping) == lineage['parent_mapping_sha256'], 'Parent mapping drift')
    pins[str(mapping)] = base.sha(mapping)
    groups = read(mapping)['parents']
    children = {c['name']: (g['parent'], c) for g in groups for c in g['partitions']}
    accepted_names = {r['original_case']['name'] for r in accepted['results']}
    selected_names = {'rvv_small_gather_restart_' + suffix for suffix in SELECTED}
    require(len(accepted_names) == 8 and len(selected_names) == 12 and
            not accepted_names & selected_names, 'Selection overlap')
    ledger, chosen = [], {}

    def pin(path, digest=None):
        actual = base.sha(path)
        require(digest is None or actual == digest, 'Identity drift: ' + str(path))
        pins[str(path)] = actual
        return dict(path=str(path), sha256=actual)

    for file, key in (('source_manifest.json', 'manifest_sha256'), ('symptoms.json', 'symptoms_sha256'),
                      ('original_report.json', 'original_report_sha256'), ('board_report.json', 'board_report_sha256')):
        pin(base.ARCHIVE / file, inventory[key])
    for record in inventory['records']:
        case = record['case']
        name, original_name = case['name'], case['original_name']
        folder = Path(record['source_directory'])
        family, = [r for r in lineage['records'] if r['name'] == name]
        for file, digest in case['scenario_sources'].items():
            pin(folder / file, digest)
        pin(folder / 'case.json')
        pin(folder / 'scenario.elf', case['sha256'])
        pin(folder / 'original.elf', case['original_elf_sha256'])
        original_c = pin(Path(family['original_c']), family['original_c_sha256'])
        source = (folder / 'scenario.c').read_text()
        restored, count = re.subn(FILTER, '', source, flags=re.M)
        require(count == 1 and restored == Path(family['original_c']).read_text(), name + ': reduction differs')
        require(read(folder / 'case.json')['case'] == case and case['configurations'] == 1 and
                record['raw_board']['exit_code'] == record['raw_original']['exit_code'] == 1 and
                case['original_failure_detail'] in record['raw_board']['output'] and
                case['original_failure_detail'] in record['raw_original']['output'], name + ': archive evidence differs')
        cap, expected = scalar(case)
        parent = family['parent'] or dict(name=original_name, sha256=case['original_elf_sha256'], configurations=56448)
        if family['parent']:
            full, child = children[original_name]
            require(full['name'] == parent['name'] and full['sha256'] == parent['sha256'] and
                    child['sha256'] == case['original_elf_sha256'] and
                    child['operation_ids'] == [case['selected_trial']['op']], name + ': partition mapping differs')
        aliases = [pin(base.CAMPAIGN / 'rvv_small_gather02/overlay/opt/ara-tests' / name, case['sha256']),
                   pin(base.CAMPAIGN / 'rvv_small_gather02' / name / 'original_rebuilt.elf', case['original_elf_sha256']),
                   pin(base.CAMPAIGN / 'rvv_permute_restart01/overlay/opt/ara-tests' / parent['name'], parent['sha256']),
                   pin(base.CAMPAIGN / 'rvv_additions36/binaries' / parent['name'], parent['sha256'])]
        if family['parent']:
            aliases.append(pin(base.CAMPAIGN / 'rvv_permute_partitions01/overlay/opt/ara-tests' / original_name,
                               case['original_elf_sha256']))
        state = 'ACCEPTED_SOURCE_SINGLE' if name in accepted_names else \
                'PREPARED_NOT_DUT' if name in selected_names else 'NOT_PREPARED'
        ledger.append(dict(name=name, status=state, shape_opcode=[case['sew'], case['lmul'], case['selected_trial']['op']],
            source_directory=str(folder), source_sha256=case['scenario_sources'], original_c=original_c,
            selected_trial=case['selected_trial'], fullcap=cap, expected_first_two=expected[:2],
            reduced_linux_elf_sha256=case['sha256'], original_linux_elf_name=original_name,
            original_linux_elf_sha256=case['original_elf_sha256'], parent=parent,
            partition_configurations=2688 if family['parent'] else None,
            verified_duplicate_aliases=aliases, duplicate_aliases_add_coverage=False, parent_closed=False))
        if name in selected_names:
            chosen[name] = record
    require(len(ledger) == 83 and len(chosen) == 12, 'Incomplete inventory/selection')
    old_shapes = {(r['original_case']['sew'], r['original_case']['lmul']) for r in accepted['results']}
    new_shapes = {(r['case']['sew'], r['case']['lmul']) for r in chosen.values()}
    require(len(old_shapes) == 7 and len(new_shapes) == 12 and not old_shapes & new_shapes and
            len(old_shapes | new_shapes) == 19, 'Selection does not fill shape gaps')
    pins_check(pins)
    OUT.mkdir()
    prepared, diffs = OUT / 'prepared01', OUT / 'source_diffs'
    prepared.mkdir()
    diffs.mkdir()
    sys.path.insert(0, str(base.INTEGRATION))
    from prepare import adapt
    cases, host = [], []
    for suffix in SELECTED:
        record = chosen['rvv_small_gather_restart_' + suffix]
        case, name = record['case'], 'gather_' + suffix
        folder = prepared / name / 'original'
        folder.mkdir(parents=True)
        for file in (*case['scenario_sources'], 'case.json'):
            shutil.copyfile(Path(record['source_directory']) / file, folder / file)
        archive = (folder / 'scenario.c').read_text()
        adapted = adapt(archive, name)
        op = case['selected_trial']['op']
        port = narrow(adapted, op)
        reverse = port
        for before, after in replacements(op):
            require(reverse.count(after) == 1, 'Ambiguous loop diff')
            reverse = reverse.replace(after, before)
        require(reverse == adapted, name + ': non-loop semantic change')
        selected, = re.findall(FILTER, archive, re.M)
        selected = tuple(map(int, selected))
        require(selected == (0, op, 0, 2, 0, 0), name + ': unexpected tuple')
        old_domain = [t for t in itertools.product(range(3), range(21), range(8), range(7), range(4), range(4))
                      if t[1] == op and t == selected]
        new_domain = list(itertools.product(range(1), range(op, op+1), range(1), range(2, 3), range(1), range(1)))
        require(old_domain == new_domain == [selected], name + ': executed domain changed')
        (folder.parent / 'case.c').write_text(port)
        for label, before, after in (('adapter', archive, adapted), ('loops', adapted, port)):
            (diffs / (name + '.' + label + '.diff')).write_text(''.join(difflib.unified_diff(
                before.splitlines(True), after.splitlines(True), fromfile=name+'/'+label+'_before.c',
                tofile=name+'/'+label+'_after.c')))
        cap, expected = scalar(case)
        cases.append(dict(id=name, source_directory=record['source_directory'], original_case=case,
            assembly='operations.S', defines=[f"SEW={case['sew']}", 'RESTART_PERMUTATIONS=1', f'PERMUTE_OP_MASK={1 << op}'],
            pass_markers=[f'BOARD_CASE_PASS {name}', 'BOARD_REPLAY_PASS', f"RVV_PERMUTE_PASS sew={case['sew']} cases=1 errors=0"]))
        host.append(dict(name=name, status='PASS', tuple=selected, old_enumerations=56448, new_enumerations=1,
            capacity=cap, full_cap_expected=expected, guards=[91, 91], expected_returned_vstart=0,
            expected_cases=1, expected_errors=0, reversible_six_loop_diff=True, full_setup_asm_oracle_retained=True))
    for file in ('runtime.c', 'startup.S', 'replay.ld'):
        pin(base.INTEGRATION / file)
        shutil.copyfile(base.INTEGRATION / file, prepared / file)
    pin(base.INTEGRATION / 'prepare.py')
    base.save(OUT / 'source_pins.json', pins)
    base.save(OUT / 'coverage83.json', dict(records=ledger, accepted=8, prepared_not_dut=12, not_prepared=63,
        still_unaccepted=75, unique_shapes=19, accepted_shapes=7, prepared_new_shapes=12,
        parent_records=3, partition_records=80, parent_closure=False, alias_inventory_exhaustive=False,
        scope='83 archived shape/op source singles, not 83 distinct numerical tuples or full parent acceptance'))
    provenance = dict(cases=cases, vlen=1024, nr_lanes=4,
        scope='12 exact archived single source ports; prepared only, not original Linux ELF or parent closure',
        source_pins_sha256=base.sha(OUT / 'source_pins.json'), generator_sha256=base.sha(Path(__file__)),
        adapter_sha256=base.sha(base.INTEGRATION / 'prepare.py'),
        files={str(p.relative_to(prepared)): base.sha(p) for p in sorted(prepared.rglob('*')) if p.is_file()})
    base.save(prepared / 'provenance.json', provenance)
    base.save(OUT / 'host_semantics.json', dict(status='PASS_12_EXACT_TUPLES', results=host))
    base.HERE = OUT
    soc = base.build(prepared, provenance, 'soc')
    programs = base.build(prepared, provenance, 'spike')
    reference = OUT / 'reference01'
    reference.mkdir()
    sys.path.insert(0, str(base.ROOT / 'verification'))
    from ara_verify.spike_probe import check_spike_vstart, probe_paths
    cc, source = probe_paths(base.ROOT)
    require(check_spike_vstart(SPIKE, cc, reference / 'vstart_probe', source)['status'] == 'PASS',
            'Spike vstart capability not PASS')
    results = []
    for case in cases:
        name, op = case['id'], case['original_case']['selected_trial']['op']
        entry, elf = programs[name], Path(programs[name]['path'])
        routine = instructions(Path(soc[name]['path']), name+'_op_'+str(op))
        archived = archived_window(Path(case['source_directory']) / 'scenario.elf', routine)
        target, = [r for r in routine if r['text'].startswith(('vrgather.', 'vrgatherei16.'))]
        spike_routine = instructions(elf, name+'_op_'+str(op))
        spike_target, = [r for r in spike_routine if r['text'].startswith(('vrgather.', 'vrgatherei16.'))]
        exit_pc, _ = symbol(elf, 'replay_exit', OBJDUMP)
        log_pc, _ = symbol(elf, 'replay_log', OBJDUMP)
        exit_store, = [r for r in instructions(elf, 'replay_exit') if r['text'].startswith('sd\t')]
        debug, log, commits = (reference / (name + ext) for ext in ('.cmd', '.log', '.commits.log'))
        debug.write_text(f'until pc 0 {exit_pc:x}\nreg 0 a0\nstr {log_pc:x}\nrs\n')
        command = [str(SPIKE), '-d', '--debug-cmd='+str(debug), '--isa=rv64gcv_zvl1024b', '-m2',
                   '--log-commits', '--log='+str(commits), str(elf)]
        begin = time.monotonic()
        with log.open('x') as stream:
            run = subprocess.run(command, stdout=stream, stderr=subprocess.STDOUT, timeout=30)
        text = log.read_text()
        require(run.returncode == 0 and oracle(entry, text) and re.search(r'^0x0{16}$', text, re.M),
                name + ': Spike full oracle/exit not PASS')
        count, hits, store_seen = 0, 0, False
        for line in commits.read_text().splitlines():
            match = re.match(r'core\s+0:\s+\d\s+(0x[0-9a-f]+)\s+\((0x[0-9a-f]+)\)', line)
            if not match:
                continue
            pc = int(match[1], 16)
            if pc >= 0x80000000:
                count += 1
                if pc == spike_target['pc']:
                    require(int(match[2], 16) == int(spike_target['insn'], 16), 'Spike target encoding differs')
                    hits += 1
                if pc == exit_store['pc']:
                    store_seen = True
                    break
        require(store_seen and hits == 1, name + ': incomplete Spike retirement evidence')
        results.append(dict(name=name, status='PASS', returncode=run.returncode, command=command,
            elapsed_s=time.monotonic()-begin, full_oracle_markers=True, log_sha256=base.sha(log),
            commit_log_sha256=base.sha(commits), elf_sha256=entry['sha256'], soc_elf_sha256=soc[name]['sha256'],
            firmware_retired_to_htif_store=count, spike_target_hits=hits, soc_target=target,
            archived_target_pc=hex(archived[0]['pc']), archived_routine_encoding_identical=True,
            original_routine_instructions=len(routine), counts_are_not_dut_cycles=True))
    pins_check(pins)
    base.save(reference / 'reference.json', dict(status='SPIKE_12_FULLORACLE_PASS_NOT_DUT', results=results,
        spike_sha256=base.sha(SPIKE), old_pins_unchanged=True))
    base.save(OUT / 'ready.json', dict(status='PREPARED_12_HOST_SPIKE_PASS_NOT_DUT', vcs_started=False,
        elapsed_s=time.monotonic()-started, source_pins_sha256=base.sha(OUT / 'source_pins.json'),
        coverage_sha256=base.sha(OUT / 'coverage83.json'), reference_sha256=base.sha(reference / 'reference.json'),
        accepted_stays_8_of_83=True, no_parent_closure=True))
    print('PREPARED_12_HOST_SPIKE_PASS_NOT_DUT', OUT, flush=True)


if __name__ == '__main__':
    main()
