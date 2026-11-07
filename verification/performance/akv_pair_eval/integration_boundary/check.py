#!/usr/bin/env python3
"""Strict b7c9e6c3c AUTO/fallback functional gates; raw logs and traces stay unchanged."""
import argparse
from collections import Counter
import json
from pathlib import Path
import re
import sys
import types
import importlib.util

sys.dont_write_bytecode = True
HERE = Path(__file__).resolve().parent
_spec = importlib.util.spec_from_file_location('integration_boundary_contract', HERE / 'build.py')
b = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(b)
succ = b.load(b.PARENT / 'boundary/check_successor.py', 'integration_boundary_sealed_vector',
              b.SEALED['boundary/check_successor.py'])
old = succ.original
require, sha = b.require, b.sha
CAP = f'AKV_AUTO_BOUNDARY_CAP sdk={b.SDK_COMMIT} order=OFF/AUTO/OFF fallback_case=3'
DONE = 'AKV_AUTO_BOUNDARY_DONE calls=12 queries=1 autos=4 fallbacks=1 errors=0'


def make_schema(calls, info_commands=4):
    native = [word for call in calls for word in call]
    triples = {i for i, word in enumerate(native) if word == old.ROW96 and i and
               native[i - 1] in (old.COLUMN, old.PANEL)}
    return dict(native=native, extended=[succ.INFO] * info_commands + native, triples=triples,
                counts=dict(Counter(old.SIGNATURE_NAMES[w] for w in native)),
                per_call_commands=list(map(len, calls)), raw_allocations=len(native) + 2 * len(triples))


def work_schema():
    calls = []
    for index, case in enumerate(b.WORK['cases']):
        d, heads, kv = (case[k] for k in ('d', 'heads', 'kv'))
        special = d == 128 and heads == 6
        for trial in range(3):
            paired = trial == 1 and index != b.WORK['missing_panel_case'] and not special
            words = []
            for start in range(0, kv, 64):
                tokens = min(64, kv - start)
                words.append(old.FULL if start == 0 else old.REFILL)
                if special:
                    words += [old.COLUMN, old.COLUMN9] * (d // 2)
                elif paired:
                    words += [old.PANEL] * ((heads // 2) * (d // 4))
                    words += [old.COLUMN] * ((heads % 2) * d)
                else:
                    words += [old.COLUMN] * (heads * d)
                row = old.ROW128_GQA6 if special else {64: old.ROW64, 96: old.ROW96, 128: old.ROW128}[d]
                words += [row] * (tokens * (1 if special else (heads + 1) // 2 if paired else heads))
            calls.append(words + [old.RELEASE])
    schema = make_schema(calls, b.WORK['info_commands'])
    require(schema['per_call_commands'] == b.WORK['per_call_commands'] and
            len(schema['native']) == b.WORK['native_commands'] and
            schema['raw_allocations'] == b.WORK['raw_custom_allocations'] and
            len(schema['triples']) == b.WORK['maintenance_groups'], 'AUTO work formula drift')
    return schema


def check_elf(path):
    symbols = old.elf_contents(path)
    for item in b.old.PAYLOADS.values():
        symbol = symbols.get(item['symbol'], {})
        require(symbol.get('bytes') == item['bytes'] and symbol.get('type') == 1 and
                symbol.get('section_flags', 0) & 2 and not symbol['section_flags'] & 1 and
                symbol['address'] % 64 == 0 and
                b.hashlib.sha256(symbol['data']).hexdigest() == item['sha256'], 'Actual ELF full payload mapping')
    required = ('main', 'boundary_body', 'boundary_route', 'capture_device', 'getenv',
                'akv_device_query', 'akv_attention_plan_create_v2', 'akv_attention_execute_v2_native',
                'akv_attention_execute_v2_native_auto')
    for name in required:
        require(name in symbols and symbols[name]['type'] == 2 and symbols[name]['bytes'] > 0,
                'Missing actual new-SDK/wrapper link: ' + name)
    helpers = {n: w for n, w in old.FUNCTION_WORDS.items()
               if n != 'akv_attention_execute_v2_with_features_native'}
    for name, wanted in helpers.items():
        require(name in symbols and all(w in [v for _, v, size in old.instructions(symbols[name]['data'])
                if size == 4] for w in wanted), 'Actual helper signature drift: ' + name)
    address_names = {v['address']: n for n, v in symbols.items() if v['type'] == 2}
    edges = {n: {address_names[t] for t in old.direct_targets(v['data'], v['address']) if t in address_names}
             for n, v in symbols.items() if v['type'] == 2}
    for caller, wanted in {
        'main': {'boundary_body'}, 'boundary_body': {'capture_device', 'boundary_route',
        'akv_attention_plan_create_v2'}, 'capture_device': {'akv_device_query'},
        'boundary_route': {'akv_attention_execute_v2_native', 'akv_attention_execute_v2_native_auto'},
    }.items():
        require(wanted <= edges[caller], 'Actual wrapper/API call edge mismatch: ' + caller)
    # The new shared static internal may be cloned/const-propagated by GNU.
    # Follow actual calls instead of requiring the old exported function layout.
    for entry in ('akv_attention_execute_v2_native', 'akv_attention_execute_v2_native_auto'):
        reached, pending = set(), [entry]
        while pending:
            name = pending.pop()
            if name in reached:
                continue
            reached.add(name)
            pending.extend(edges.get(name, set()) - reached)
        words = {w for n in reached for _, w, size in old.instructions(symbols[n]['data']) if size == 4}
        require({old.FULL, old.REFILL, old.RELEASE} <= words, 'New API does not reach native lifecycle: ' + entry)
    require(not any(n.startswith(('bench_', 'mock_', 'f16_profile_')) for n in symbols), 'Nonproduction dispatch linked')
    return dict(actual_payload_link_checked=True, new_auto_and_legacy_call_edges_checked=True,
                native_lifecycle_reachability_checked=True, knowncall_signatures_checked=True)


def verify_build(directory):
    directory = Path(directory).resolve(strict=True)
    m = b.read_json(directory / 'build.json')
    expected = dict(schema=1, kind='boundary', workload=b.WORK, state='BUILT_NOT_EXECUTED', execution='NOT_RUN',
        target_executed=False, rtl_executed=False, performance_measured=False, seal_ready=True,
        post_pins_match=True, sdk_head=b.SDK_COMMIT, sdk_tree=b.SDK_TREE, common_tree=b.old.COMMON_TREE,
        sdk_delta=b.SDK_DELTA, sdk_unmodified=True, assembly_unchanged=True, dirty_asm_excluded=True,
        all_runtime_objects_recompiled=True, objects_recompiled=16, image_contract=b.old.IMAGE,
        capture=str(b.old.CAPTURE), payloads=b.old.PAYLOADS, harness_sha256=b.old.LEGACY[b.old.HARNESS],
        toolchain=dict(target=str(b.CC), host=str(b.HOST_CC), zcc=False),
        runner=dict(entry=str(HERE / 'run.py'), owner=str(b.PARENT / 'run.py'),
                    owner_sha256=b.SEALED['run.py'], kind='boundary'))
    require(all(m.get(k) == v for k, v in expected.items()), 'New SDK boundary build/schema/version mismatch')
    pinfile, elf, inputs = directory / 'source-pins.json', directory / b.ELF_NAME, directory / 'inputs'
    require(m['source_pins'] == str(pinfile) and sha(pinfile) == m['source_pins_sha256'] and
            m['elf'] == str(elf) and sha(elf) == m['elf_sha256'], 'New ELF/source-pins identity drift')
    pins = b.read_json(pinfile)
    b.old.verify(pins)
    b.old.verify(m['artifacts'])
    required = {**b.old.validate_data(), **b.helper_pins(),
                **{str(HERE / n): sha(HERE / n) for n in b.OWN_FILES}}
    # RTL semantics are separately frozen and verified, not rebuilt as SDK inputs.
    b.old.verify(succ.SEMANTICS_PINS)
    require(all(pins.get(p) == h for p, h in required.items()), 'Missing mandatory new source/helper/data pin')
    require(not any('/akv_pair_eval/integration/' in p for p in pins), 'Do not seal the parallel integration owner')
    archives = [(inputs / 'sdk-b7c9e6c3c.tar', m['sdk_archive'], m['sdk_archive_sha256'], b.ARCHIVE_SHA),
                (inputs / 'baseline-785084122.tar', m['baseline_archive'], m['baseline_archive_sha256'], b.old.ARCHIVE_SHA)]
    for path, named, digest, wanted in archives:
        require(str(path) == named and digest == wanted and sha(path) == wanted and
                pins.get(str(path)) == wanted and m['artifacts'].get(str(path)) == wanted,
                'SDK/baseline archive substitution or missing archive pin')
    members = b.validate_archives(archives[0][0].read_bytes(), archives[1][0].read_bytes())
    require({str(p.relative_to(inputs)) for p in inputs.rglob('*') if p.is_file()} ==
            {*members, 'sdk-b7c9e6c3c.tar', 'baseline-785084122.tar'}, 'Unexpected SDK input/old object')
    for name, content in members.items():
        path = inputs / name
        h = b.hashlib.sha256(content).hexdigest()
        require(sha(path) == h and pins.get(str(path)) == h and m['artifacts'].get(str(path)) == h,
                'SDK/common/harness differs from exact archive: ' + name)
    require(m['SDKpins'] == {n: b.hashlib.sha256(c).hexdigest() for n, c in members.items()
                            if n.startswith('software/akv/')}, 'SDK pin inventory mismatch')
    for n, text in {'expected.h': b.old.expected_header(), 'data.S': b.old.data_assembly(),
                    'link.ld': b.old.linker_script(inputs / 'apps/common')}.items():
        require((directory / n).read_text() == text and pins.get(str(directory / n)) == sha(directory / n),
                'Generated capture/link/host-constant mapping changed')
    commands = b.read_json(directory / 'commands.json')
    labels = ['tree-akv', 'tree-common', 'archive', 'baseline-archive', 'gnu-version', 'hosttests'] + [
        'locate-' + n for n in ('libm.a', 'libc.a', 'libgcc.a', 'libnosys.a', 'cc1', 'as', 'ld', 'collect2')]
    labels += [f'compile-{i:02d}' for i in range(16)] + ['link', 'objdump', 'readelf']
    require([c['label'] for c in commands] == labels and all(c['returncode'] == 0 and
            c['cwd'] == str(directory) and c['env'] == commands[0]['env'] and
            set(c['env']) == {'PATH', 'HOME', 'LC_ALL', 'TMPDIR', 'PYTHONDONTWRITEBYTECODE'} and
            c['env']['PATH'] == '/usr/bin:/bin' for c in commands), 'Actual command/environment inventory')
    compiles = [c['argv'] for c in commands if c['label'].startswith('compile-')]
    require(compiles == b.compile_recipe(directory) and m['objects'] == [c[-1] for c in compiles] and
            [c['argv'] for c in commands if c['label'] == 'link'] == [b.link_recipe(directory)],
            'Not 16 fresh new-SDK compilations and exact link')
    require(m['compile_commands'] == str(directory / 'commands.json'), 'Wrong compile command receipt')
    for label, commit in (('archive', b.SDK_COMMIT), ('baseline-archive', b.old.SDK_COMMIT)):
        require([c['argv'] for c in commands if c['label'] == label] == [[str(b.GIT), '-C', str(b.ROOT),
                'archive', commit, *b.old.ARCHIVE_PATHS]], 'Archive launch mismatch')
    for c in commands:
        require(m['artifacts'].get(c['log']) == sha(c['log']), 'Unpinned command log')
        if c['label'].startswith('locate-'):
            p = Path(c['log']).read_text().strip()
            require(pins.get(str(Path(p).resolve())) == sha(p), 'Missing actual library/compiler tool pin')
    for tool, args in (('objdump', ['-d']), ('readelf', ['-lW'])):
        path = b.CC.with_name(b.CC.name.replace('gcc', tool))
        require(pins.get(str(path.resolve())) == sha(path) and [c['argv'] for c in commands
                if c['label'] == tool] == [[str(path), *args, str(elf)]], 'Actual ELF inspection tool/launch mismatch')
    for tool, h in ((b.CC, b.old.CC_SHA), (b.HOST_CC, b.old.HOST_CC_SHA), (b.GIT, b.old.GIT_SHA)):
        require(pins.get(str(tool.resolve())) == h, 'GNU tool identity changed')
    for c in compiles:
        dep = Path(c[-1]).with_suffix('.d')
        require(m['artifacts'].get(str(dep)) == sha(dep), 'Missing compiler dependency inventory')
        for p in b.old.dependency_inputs(dep):
            require(pins.get(str(p)) == sha(p), 'Unpinned actual compiler input')
    deps = b.old.dependency_inputs(Path(compiles[0][-1]).with_suffix('.d'))
    require(inputs / b.old.HARNESS in deps, 'Wrapper did not include sealed original harness')
    for p in [elf, pinfile, directory / 'commands.json', directory / 'link.map', *map(Path, m['objects'])]:
        require(m['artifacts'].get(str(p)) == sha(p), 'Missing mandatory fresh artifact: ' + str(p))
    maptext = (directory / 'link.map').read_text()
    require(all(re.search(r'^LOAD ' + re.escape(p) + '$', maptext, re.M) for p in m['objects']), 'Actual link map mismatch')
    m['elf_link_checks'] = check_elf(elf)
    return m


def numeric_work(legacy, case, trial):
    paired = trial == 1 and case != b.WORK['missing_panel_case']
    return legacy.work(legacy.CASES[case], paired)


def check_log(text, legacy):
    s = legacy.s
    cap = native_cap = suite = terminal = done = active = routed = False
    trials, records, group, severity, summary = [], [], [], set(), None
    for line in text.splitlines():
        require(not re.search(r'Fatal:|Error:|Error-|\b(?:FAIL|FAILED|TIMEOUT)\b|\$fatal', line, re.I), 'Failure text')
        if 'UVM_ERROR' in line or 'UVM_FATAL' in line:
            match = re.fullmatch(r'(UVM_ERROR|UVM_FATAL)\s*:\s*0', line)
            require(match is not None and match[1] not in severity, 'UVM failure/duplicate')
            severity.add(match[1])
        if 'Core Test' in line:
            require(line == s.TERMINAL and suite and done and not terminal, 'Bad/early core EOC')
            terminal = True
        if 'QBS_PERF' in line and not line.startswith('Command:'):
            raise ValueError('Unexpected QBS work')
        if 'AKV_PERF' in line and not line.startswith('Command:'):
            if line.startswith('[AKV_PERF] '):
                require(active and routed, 'Command outside routed call')
                case, trial = divmod(len(trials), 3)
                work = numeric_work(legacy, case, trial)
                require(len(group) < len(work), 'Extra native command')
                row = s.numeric_fields(line[len('[AKV_PERF] '):], s.PERF_FIELDS)
                expected = legacy.expected_record(legacy.CASES[case], work[len(group)], len(records) + 1)
                require(all(row[k] == v for k, v in expected.items()), 'AUTO/fallback command/work/fault mismatch')
                require(row['id'] < 8 and row['busy_cycles'] > 0 and row['read_outstanding_max'] <= 2, 'Invalid native record')
                if row['command'] in (4, 5):
                    require(row['ar'] >= row['read_ranges'] and row['r_beats'] >= row['ar'] and
                            row['read_outstanding_max'] > 0, 'Missing external traffic')
                else:
                    require(all(row[k] == 0 for k in ('ar', 'r_beats', 'read_outstanding_max',
                        'read_outstanding_occ_sum', 'read_outstanding_full_cycles')), 'Unexpected external traffic')
                records.append(row)
                group.append(row)
            elif line.startswith('[AKV_PERF_SUMMARY] '):
                require(suite and not active and summary is None, 'Bad hardware summary placement')
                summary = s.numeric_fields(line[len('[AKV_PERF_SUMMARY] '):], s.SUMMARY_FIELDS)
            else:
                raise ValueError('Malformed native hardware record')
        if 'AKV_AUTO_BOUNDARY_' in line:
            case, trial = divmod(len(trials), 3)
            if line == CAP:
                require(not cap and not native_cap and not trials, 'Duplicate/late AUTO capability')
                cap = True
            elif line.startswith('AKV_AUTO_BOUNDARY_ROUTE '):
                missing = int(case == 3 and trial == 1)
                wanted = (f'AKV_AUTO_BOUNDARY_ROUTE case={case} trial={trial} auto={int(trial == 1)} '
                          f'missing_panel={missing} panel={1 - missing}')
                require(active and not routed and not group and line == wanted, 'AUTO/fallback route/capability mismatch')
                routed = True
            else:
                require(line == DONE and suite and not done and not terminal, 'Bad AUTO completion marker')
                done = True
        if 'NATIVE_PAIR_' in line:
            case, trial = divmod(len(trials), 3)
            if line == legacy.CAP:
                require(cap and not native_cap and not trials, 'Missing new SDK identity/duplicate original CAP')
                native_cap = True
            elif line.startswith('NATIVE_PAIR_BEGIN '):
                require(native_cap and not active and not suite and case < 4 and
                        line == legacy.begin(case, trial), 'Wrong boundary call order/shape')
                active, routed, group = True, False, []
            elif line.startswith('NATIVE_PAIR_RESULT '):
                match = legacy.RESULT.fullmatch(line)
                require(active and routed and match is not None and
                        (int(match[1]), int(match[2]), int(match[3])) == (case, trial, int(trial == 1)), 'Bad call result')
                require(int(match[4]) == legacy.CASES[case]['d'] * legacy.CASES[case]['heads'] and
                        int(match[6]) <= 31 and len(group) == b.WORK['per_call_commands'][len(trials)],
                        'Incomplete numerical/output/CSR/work evidence')
                trials.append(dict(case=case, trial=trial, checksum=match[5], fcsr=int(match[6]),
                                   vcsr=5, hardware_totals=s.totals(group)))
                active = False
            else:
                require(line == legacy.SUITE and native_cap and not suite and not active and len(trials) == 12,
                        'Bad original suite marker')
                suite = True
    require(cap and native_cap and suite and done and terminal and not active and len(records) == 3968 and
            severity == {'UVM_ERROR', 'UVM_FATAL'} and summary == s.totals(records), 'Incomplete new SDK boundary evidence')
    for case in range(4):
        require(len({(r['checksum'], r['fcsr'], r['vcsr']) for r in trials if r['case'] == case}) == 1,
                'OFF/AUTO/OFF complete output bits/flags differ')
    payloads = old.check_payload_log(text, legacy)
    require(text.splitlines().index('AKV_BOUNDARY_DONE body=0 checks=3 errors=0') <
            text.splitlines().index(DONE), 'AUTO completion precedes full payload checks')
    return dict(state='PASS', sdk_head=b.SDK_COMMIT, workload=b.WORK, trials=trials, payload_checks=payloads,
                raw_hardware_summary=summary, performance_measured=False, independent_protocol_checked=False)


def check_run(log_path, build_dir):
    report = verify_build(build_dir)
    result = check_log(Path(log_path).read_text(errors='strict'), old.load_legacy(Path(build_dir) / 'inputs'))
    return dict(result, elf_sha256=report['elf_sha256'], source_pins_sha256=report['source_pins_sha256'],
                log_sha256=sha(log_path), scope='New SDK AUTO/boundary/fallback functional regression only')


def validate_groups(groups, schema):
    require(len(groups) == len(schema['native']), 'Missing/extra native architecture group')
    maintenance, raw = [], Counter()
    for index, (group, word) in enumerate(zip(groups, schema['native'])):
        allocs = group['allocations']
        require(group['word'] == word and all(int(a['insn'], 16) == word and a['arch_seq'] ==
                group['arch_seq'] for a in allocs), 'New work originalword/order mismatch')
        if index in schema['triples']:
            require(word == old.ROW96 and len(allocs) == 3 and [a['shape'] for a in allocs] ==
                    [(1, 8, 1, 64, 0), (1, 9, 1, 64, 0), (1, 8, 1, 96, 0)] and
                    max(a['done_cycle'] for a in allocs[:2]) < allocs[2]['cycle'], 'Incomplete/invalid D96 maintenance triple')
            maintenance.append(dict(native_index=index, arch_seq=group['arch_seq'], allocations=[
                {k: a[k] for k in ('line', 'cycle', 'done_cycle', 'vid', 'insn', 'shape')} for a in allocs]))
        else:
            require(len(allocs) == 1 and allocs[0]['shape'] == succ.operation_shape(word), 'Unknown duplicate/original shape mismatch')
        raw[old.SIGNATURE_NAMES[word]] += len(allocs)
    counts = dict(Counter(old.SIGNATURE_NAMES[g['word']] for g in groups))
    require(counts == schema['counts'] and sum(raw.values()) == schema['raw_allocations'], 'New native/raw work totals')
    return dict(counts=counts, raw_custom_alloc_counts=dict(raw), maintenance_groups=maintenance,
                raw_custom_allocations=sum(raw.values()), native_commands=len(groups))


def audit_vector(vector_path, elf_words, schema):
    path = Path(vector_path).resolve(strict=True)
    commit = path.with_name('commit.csv').resolve(strict=True)
    require(commit.parent == path.parent and commit != path, 'Unpaired raw commit trace')
    before = {str(p): succ.digest(p) for p in (path, commit)}
    groups, events = succ.read_vector(path)
    result = validate_groups(groups, schema)
    # Private function binding supplies the explicitly new schema. Never mutate
    # the sealed module's globals or pretend this is its 785 workload/build.
    context = dict(succ.check_commit.__globals__, expected_work=lambda: (
        schema['native'], schema['extended'], schema['triples']))
    commit_gate = types.FunctionType(succ.check_commit.__code__, context, 'new_sdk_commit_gate')
    result['commit_checks'] = commit_gate(commit, groups, events, elf_words)
    require(all(succ.digest(p) == h for p, h in before.items()), 'Raw evidence drift')
    return dict(result, trace_sha256=before[str(path)], commit_sha256=before[str(commit)],
                per_call_commands=schema['per_call_commands'], ordered_signatures_checked=True,
                life_signatures_checked=True, raw_preserved=True, performance_measured=False,
                sdk_head=b.SDK_COMMIT, independent_protocol_checked=False)


def check_vector_workcounts(vector_path, build_dir):
    report = verify_build(build_dir)
    result = audit_vector(vector_path, succ.elf_custom_instructions(report['elf']), work_schema())
    after = verify_build(build_dir)
    require(after['elf_sha256'] == report['elf_sha256'] and after['source_pins_sha256'] ==
            report['source_pins_sha256'], 'Build pins changed during audit')
    return dict(result, elf_sha256=report['elf_sha256'], source_pins_sha256=report['source_pins_sha256'])


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__, allow_abbrev=False)
    parser.add_argument('--build', type=Path, required=True)
    parser.add_argument('--log', type=Path, required=True)
    parser.add_argument('--trace', type=Path, required=True)
    args = parser.parse_args()
    result = check_run(args.log, args.build)
    result['vector_workcounts'] = check_vector_workcounts(args.trace, args.build)
    print(json.dumps(result, indent=2, sort_keys=True))
