#!/usr/bin/env python3
"""Prepare only until an explicit parent-reviewed gate receipt; GNU/Spike, no VCS."""
import argparse
import hashlib
import importlib.util
import json
from pathlib import Path
import re
import shlex
import shutil
import subprocess
import sys

sys.dont_write_bytecode = True
ROOT = Path('/home/wangwy/openproject/ara_dsa')
OUT = ROOT.parent/'ara_dsa_signoff_integration/verification/out'
HERE = Path(__file__).resolve().parent
LIVE_ARCH = Path('/home/wangwy/llama/llama.cpp/ggml/src/ggml-cpu/arch/riscv')
SNAPSHOT = OUT/'enablement_unified_build_20261111_01'
DATA = OUT/'stage2_qwen3_rows8_20261109_02/attn_q/activation_f32.bin'
DATA_SHA = '4ba6296b70be49960bcce50b09efa38afb938993e38cd710ec6cf5ca951a441c'
HELPER_SHA = '71b07f59aa44bea1102674d68fbe9fbaa36fa055f078804b4ff5dd0353fe0291'
AUDIT_PINS = 'db377ab269ba60fbd7552e3557c4c85f66fa6ea4efdd98130b25110351e49e4e'
ORIGINAL_RESULT = 'b68fdc4788e1dbb7dd00aff2115c99b7add1205713ac7caba8825fe723c1a157'
RAW_SHA = '9ae419d47fe59f8c339299ecc5f4cc8f4fef63743d04d3c38fa197106466444a'
VECTOR_SHA = 'd634dd53f7e82642790a93673ea5ad8a5d5a2ea6dc2ba92320bbdc5254d3b431'
CHECKER_SHA = '0826f7ca6192a2cb558dfe681c8fe4802cff595ace55cd1997da7576ba6e4ecc'
CC = Path('/home/wangwy/openproject/ara/install/riscv-gcc/bin/riscv64-unknown-elf-gcc')
CXX = CC.with_name('riscv64-unknown-elf-g++')
SPIKE = Path('/home/wangwy/openproject/riscv-isa-sim-ara-dsa-vstart/build/spike')
ENV = dict(PATH='/usr/bin:/bin', HOME='/home/wangwy', LC_ALL='C', PYTHONDONTWRITEBYTECODE='1')
OVERLAYS = ('q8_K-m4-preflight.h', 'q8_K-prepared-reuse.h', 'qbs.h')
UNCHANGED_HEADERS = ('q8_K-m4-packed.h', 'q8_K-prepared-cache.h', 'm4-reuse-policy.h',
                     'q8_K-m4.h', 'q8_K-m4-group-sums.h', 'rvv-byte-ops.h', 'accel-options.h')
OWN = ('adapter_run.py', 'adapter_target.cpp', 'adapter_test.py')
CASES = ('auto', 'preflight0', 'prepare0', 'cache0', 'packed0', 'parallel0', 'master0',
         'non_rne', 'vstart_abort', 'multi_worker', 'single_consumer', 'late_subnormal',
         'late_inf', 'late_qnan', 'late_snan', 'allocation_failure', 'planner_wide_reject',
         'lookup_without_fill', 'explicit_flags_master0')
SCOPE = ('Actual state.begin/prepare with metadata-only graph/capability/planner/environment stubs; '
         'bounded allocator and function-entry observation hooks; '
         'real accepted packed<true> oracle, SDK preflight producer and value_cache. '
         'K2048 first four rows of real Qwen3 attn_norm 8x2048; K4096 same activation bytes '
         'reshaped 4x4096, NOT a real K4096 operator. Direct prepare tests do not execute the '
         'complete GGML caller, hardware planner, model, or dot product; no performance claim.')


def require(ok, why):
    if not ok:
        raise ValueError(why)


def sha(path):
    h = hashlib.sha256()
    with Path(path).open('rb') as f:
        for chunk in iter(lambda: f.read(1024*1024), b''):
            h.update(chunk)
    return h.hexdigest()


def read(path):
    return json.loads(Path(path).read_text())


def save(path, value):
    with Path(path).open('x') as f:
        json.dump(value, f, indent=2, sort_keys=True); f.write('\n')


def verify(pins):
    for path, value in pins.items():
        require(sha(path) == value, 'Pin drift: '+str(path))


def digest_value(value):
    require(isinstance(value, str) and re.fullmatch('[0-9a-f]{64}', value), 'Explicit SHA256 required')
    return value


def evidence_directory(value, prefix):
    require(isinstance(value, str) and bool(value) and value.strip() == value and Path(value).is_absolute(),
            'Nonempty explicit absolute evidence directory required')
    path = Path(value).resolve(strict=True)
    require(str(path) == value and path.parent == OUT and re.fullmatch(prefix+'[A-Za-z0-9_]+', path.name),
            'Canonical direct sole-signoff evidence directory required')
    return path


def load(path, name):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec); spec.loader.exec_module(module)
    return module


def reviewed_evidence(gate):
    require(gate.get('evidence_kind') == 'framing_audit_v1', 'Explicit separately scoped framing audit required')
    bench = evidence_directory(gate.get('benchmark'), 'optimization_extension_preflight_')
    audit = evidence_directory(gate.get('audit_output'), 'optimization_extension_preflight_framing_audit_')
    require(bench == OUT/'optimization_extension_preflight_20261111_02' and
            audit == OUT/'optimization_extension_preflight_framing_audit_20261111_01', 'Wrong original run/audit scope')
    require(gate.get('benchmark_result_sha256') == ORIGINAL_RESULT and
            gate.get('audit_source_pins_sha256') == AUDIT_PINS, 'Original FAIL/audit seal review identity')
    extra = {str(bench/'result.json'): ORIGINAL_RESULT, str(audit/'source-pins.json'): AUDIT_PINS,
             str(audit/'result.json'): digest_value(gate.get('audit_result_sha256'))}
    verify(extra)
    original = read(bench/'result.json'); result = read(audit/'result.json')
    require(original['state'] == 'FAIL' and original['error'] ==
            "ValueError('Malformed/duplicate/unknown trial fields')", 'Never relabel original worker PASS')
    require(result.get('benchmark') == str(bench) and result.get('original_worker_state') == 'FAIL' and
            result.get('original_result_path') == str(bench/'result.json') and
            result.get('original_result_sha256') == ORIGINAL_RESULT and
            result.get('source_pins_sha256') == AUDIT_PINS, 'Audit/original receipt binding')
    for key, path, value in (('raw_log', bench/'vcs/run.vcs.log', RAW_SHA),
                              ('vector_trace', bench/'vcs/vector.csv', VECTOR_SHA)):
        require(result.get(key+'_path') == str(path) and result.get(key+'_sha256') == value,
                'Audit raw evidence binding')
        extra[str(path)] = value
    for key, file in (('numerical', 'numerical.json'), ('canonical_log', 'numerical-framed.log'),
                      ('fragments', 'fragments.json'), ('protocol', 'protocol.json')):
        require(result.get(key+'_path') == str(audit/file), 'Audit evidence path binding')
        extra[str(audit/file)] = digest_value(result.get(key+'_sha256'))
    pins = read(audit/'source-pins.json') | extra | original['artifacts']; verify(pins)
    framing = load(audit/'inputs/framing_audit.py', 'reviewed_framing_reconstruction')
    canonical, fragments = framing.reconstruct((bench/'vcs/run.vcs.log').read_text())
    require(canonical == (audit/'numerical-framed.log').read_text() and fragments == read(audit/'fragments.json'),
            'Exact 8-trial fragment reconstruction no longer agrees with raw bytes')
    require(sha(audit/'inputs/original_check.py') == CHECKER_SHA, 'Original strict numerical checker identity')
    checker = load(audit/'inputs/original_check.py', 'reviewed_original_numerical_checker')
    numerical = checker.numerical(canonical, vcs=True, reference=read(bench/'spike-check.json'))
    require(numerical == read(audit/'numerical.json') and result['cycle_metrics'] == numerical['cycle_metrics'],
            'Full numeric/CSR/cache/guard evidence or performance metrics differ')
    plan = read(bench/'plan.json'); proof = read(audit/'protocol.json')
    elf, simv = plan['elves']['soc']['path'], plan['simv']
    require(result.get('elf_path') == elf and result.get('simv_path') == simv and
            result.get('elf_sha256') == sha(elf) == plan['elves']['soc']['sha256'] and
            result.get('simv_sha256') == sha(simv), 'ELF/simulator receipt identity')
    checker.protocol(proof, dict(elf_sha256=sha(elf), simv_sha256=sha(simv),
                                log_sha256=RAW_SHA, vector_trace_sha256=VECTOR_SHA))
    require(proof['sim_image_sha256'] == {p: h for p, h in plan['image_pins'].items()
            if p == simv or p.endswith('.so')} and result['protocol_counts'] == proof['contract_counts'],
            'Independent full-raw-log protocol/compiled-image identity')
    require(result['image_pins'] == plan['image_pins'] == framing.image_inventory(), 'Complete image pins/membership')
    verify(pins)
    return result, pins


def gate_contract(gate, result):
    require(gate.get('state') == 'M4_ADAPTER_GATE_REVIEWED', 'Explicit parent-reviewed gate receipt required')
    enabled = gate.get('enabled_k')
    require(isinstance(enabled, list) and all(type(k) is int for k in enabled) and
            enabled == sorted(set(enabled)) and 1536 in enabled and
            set(enabled) <= {1536, 2048, 4096}, 'Reviewed gate must preserve 1536 and name only bounded shapes')
    require(set(gate.get('live_overlays', {})) == set(OVERLAYS) and all(
        isinstance(h, str) and re.fullmatch('[0-9a-f]{64}', h) for h in gate['live_overlays'].values()),
        'Exact reviewed live header identities required, never qbs.cpp')
    require(result.get('state') == 'M4_PREFLIGHT_FRAMING_AUDIT_CHECKED' and
            result.get('post_pins_match') is True and result.get('post_image_match') is True and
            result.get('original_worker_state') == 'FAIL' and result.get('original_result_sha256') == ORIGINAL_RESULT and
            result.get('raw_log_sha256') == RAW_SHA and result.get('vector_trace_sha256') == VECTOR_SHA and
            result.get('original_report_preserved') is True and result.get('simulation_rerun') is False and
            result.get('complete_numerical') is True and result.get('complete_raw_protocol') is True and
            result.get('performance_measured') is True and
            (result.get('trials'), result.get('uart_fragments'), result.get('csr_probe_interruptions')) == (8, 24, 16),
            'Only the explicitly bound complete independent audit, never a generic PASS')
    metrics = result['cycle_metrics']
    require([m['k'] for m in metrics] == [2048, 4096], 'Missing shape measurements')
    for k in set(enabled) - {1536}:
        metric = next(m for m in metrics if m['k'] == k)
        require(metric['baseline_mean'] > metric['candidate_mean'] > 0 and
                metric['cycle_reduction_fraction'] > 0, 'No measured positive benefit for enabled K')
    return enabled


def check_log(text, k, case, gate):
    require(len(re.findall(r'^0x0000000000000000$', text, re.M)) == 1 and
            not re.search(r'FAIL|TRAP|UNEXPECTED', text), 'Spike exit/trap/target failure')
    lines = [line for line in text.splitlines() if 'M4_ADAPTER_' in line]
    if case == 8:
        require(lines == ['M4_ADAPTER_VSTART_PASS k='+str(k)+
                ' candidate_delta=0 generic_delta=0 cache_queries_delta=0 untouched=1 vstart=1'],
                'VSTART must abort before cache, candidate or generic operations')
        return dict(k=k, case=case, state='PASS', vstart_aborted_before_side_effects=True)
    require(len(lines) == (2 if case == 0 else 1), 'Missing/extra adapter record')
    if case == 0:
        require(lines[0] == 'M4_ADAPTER_INVALIDATION_PASS k='+str(k)+
                ' quartet_last_byte=1 epoch=1 source=1 computations=4', 'Missing invalidation extent')
    keys = ('k case selected checks candidate_entries generic_entries computations queries hits misses stores '
            'allocation_failures planner_calls '
            'bytes payload_hash guards input_preserved errors').split()
    match = re.fullmatch('M4_ADAPTER_PASS'+''.join(' '+key+r'=(\d+)' for key in keys), lines[-1])
    require(match is not None, 'Malformed/duplicate/unknown adapter fields')
    row = dict(zip(keys, map(int, match.groups())))
    rejected = case in (7, 9, 10, 16)
    selected = int(bool(gate) and case not in (1, 2, 3, 4, 5, 6, 9, 10, 16))
    computations = 0 if rejected else 4 if case == 0 else 2 if case == 17 else 1
    hits = 0 if rejected or 11 <= case <= 15 else 256 if case == 0 else 1
    queries = 0 if rejected else 261 if case == 0 else 4 if case == 17 else 1 if 11 <= case <= 15 else 3
    stores = 0 if rejected or 11 <= case <= 15 else 4 if case == 0 else 1
    expected = dict(k=k, case=case, selected=selected, candidate_entries=0 if rejected else selected*computations,
                    generic_entries=int(11 <= case <= 14), computations=computations,
                    queries=queries, hits=hits, misses=queries-hits, stores=stores,
                    allocation_failures=int(case == 15),
                    bytes=k//256*1168, guards=1, input_preserved=1, errors=0)
    require(all(row[key] == value for key, value in expected.items()), 'Adapter counters/shape contract')
    require(row['checks'] > 0 and (row['planner_calls'] > 0 or case == 9) and
            0 < row['payload_hash'] < 2**64, 'Empty adapter evidence')
    return dict(row, state='PASS')


def build(out, receipt, receipt_sha):
    out = out.resolve(); receipt = receipt.resolve(strict=True)
    require(out.parent == OUT and re.fullmatch(r'optimization_extension_preflight_adapter_[A-Za-z0-9_]+', out.name)
            and not out.exists(), 'Fresh sole-signoff adapter output required')
    require(receipt.is_relative_to(OUT) and sha(receipt) == receipt_sha, 'Explicit immutable gate receipt identity')
    gate = read(receipt); evidence, evidence_pins = reviewed_evidence(gate)
    enabled = gate_contract(gate, evidence)
    # No snapshot, target compilation or target execution happens before the parent gate above.
    out.mkdir(); inputs = out/'inputs'; inputs.mkdir(); pins = evidence_pins.copy(); commands = []
    report = dict(state='FAIL', scope=SCOPE, performance_measured=False, vcs_launched=False,
                  gate_receipt_sha256=receipt_sha, enabled_k=enabled, automatic_retry=False)

    def pin(path):
        path = Path(path).resolve(strict=True); value = sha(path)
        require(str(path) not in pins or pins[str(path)] == value, 'Pin drift: '+str(path))
        pins[str(path)] = value

    def copy(src, dst, inventory=None):
        if inventory is not None:
            require(inventory.get(str(src)) == sha(src), 'Unsealed snapshot: '+str(src))
        pin(src); dst.parent.mkdir(parents=True, exist_ok=True); shutil.copyfile(src, dst); pin(dst)

    def run(label, argv, timeout=120):
        argv = list(map(str, argv)); pin(argv[0])
        commands.append(dict(label=label, argv=argv, cwd=str(out), environment=ENV, timeout_seconds=timeout))
        with (out/(label+'.log')).open('x') as log:
            proc = subprocess.run(argv, cwd=out, env=ENV, stdin=subprocess.DEVNULL,
                                  stdout=log, stderr=subprocess.STDOUT, timeout=timeout)
        commands[-1]['returncode'] = proc.returncode
        require(proc.returncode == 0, 'Failed '+label+'; no blind retry')
        return (out/(label+'.log')).read_text().strip()

    try:
        pin(receipt)
        verify({str(LIVE_ARCH/name): gate['live_overlays'][name] for name in OVERLAYS})
        for name in OWN:
            copy(HERE/name, inputs/name)
        inventory = read(SNAPSHOT/'source-pins.json'); pin(SNAPSHOT/'source-pins.json')
        for rel, dest in (('inputs/llama/ggml', 'ggml'), ('inputs/sdk/software/qbs', 'sdk/software/qbs')):
            for src in sorted((SNAPSHOT/rel).rglob('*')):
                if src.is_file() and src.suffix in ('.h', '.hpp', '.cpp', '.c', '.S', '.inc'):
                    copy(src, inputs/dest/src.relative_to(SNAPSHOT/rel), inventory)
        arch = inputs/'ggml/src/ggml-cpu/arch/riscv'
        # Overlay before pinning destination headers; preserve both predecessor and reviewed identities.
        for name in OVERLAYS:
            dst = arch/name; pins.pop(str(dst), None); copy(LIVE_ARCH/name, dst)
        for name in UNCHANGED_HEADERS:
            require(sha(LIVE_ARCH/name) == sha(arch/name), 'Unreviewed transitive adapter drift: '+name)
            pin(LIVE_ARCH/name)
        helper = inputs/'sdk/software/qbs/experimental/m4_preflight/m4_preflight.h'
        require(sha(helper) == HELPER_SHA, 'Same bounded SDK producer as benchmark')
        require(sha(DATA) == DATA_SHA and DATA.stat().st_size == 65536, 'Same complete real input as benchmark')
        copy(DATA, inputs/'activation_f32.bin')
        old = ROOT/'verification/performance/next_mechanism/stage4/m4_preflight'
        for name in ('start.S', 'runtime.cpp', 'link.ld'):
            copy(old/name, inputs/name)
        data = inputs/'data.S'
        data.write_text('.section .rodata\n.balign 64\n.global adapter_input\nadapter_input:\n.incbin '+
                        json.dumps(str(inputs/'activation_f32.bin'))+'\n'); pin(data)
        run('host-tests', [sys.executable, '-B', inputs/'adapter_test.py', '-v'])
        includes = []
        for p in (inputs, helper.parent, inputs/'sdk/software/qbs/include', inputs/'ggml/include',
                  inputs/'ggml/src', inputs/'ggml/src/ggml-cpu', arch):
            includes += ['-isystem', str(p)]
        flags = ['-std=c++17', '-O2', '-DNDEBUG', '-march=rv64gcv_zfh_zvfh', '-mabi=lp64d', '-mcmodel=medany',
                 '-mno-relax', '-msmall-data-limit=0', '-fno-fast-math', '-ffp-contract=off',
                 '-ffunction-sections', '-fdata-sections', '-fno-exceptions', '-fno-rtti',
                 '-fno-threadsafe-statics', '-fno-stack-protector', '-fno-tree-vectorize', '-fno-tree-slp-vectorize',
                 '-DGGML_RISCV_ACCEL_AUTO=1', *includes]
        for name in ('cc1plus', 'as', 'ld', 'collect2'):
            path = run('locate-'+name, [CXX, '-print-prog-name='+name])
            pin(shutil.which(path, path=ENV['PATH']) or path)
        libgcc = Path(run('libgcc', [CXX, '-print-libgcc-file-name'])); pin(libgcc)

        def compile_one(label, source, extra=()):
            obj = out/(label+'.o')
            run(label+'-compile', [CXX, *flags, *extra, '-MD', '-MF', out/(label+'.d'), '-c', source, '-o', obj])
            pin(obj); return obj

        objects = [compile_one('generic', inputs/'ggml/src/ggml-cpu/repack.cpp',
                    ['-Dggml_quantize_mat_q8_K_4x1_ara_generic=frozen_generic']),
                   compile_one('runtime', inputs/'runtime.cpp',
                    ['-ffreestanding', '-fno-builtin', '-fno-tree-loop-distribute-patterns']),
                   compile_one('start', inputs/'start.S'), compile_one('data', data)]
        tests = []
        for mode in ('on', 'header_off'):
            extra = ['-finstrument-functions'] + (['-DGGML_USE_RISCV_QBS_M4_PREFLIGHT'] if mode == 'on' else [])
            target = compile_one('target-'+mode, inputs/'adapter_target.cpp', extra)
            for k in (2048, 4096):
                for case in range(len(CASES)) if mode == 'on' else (0,):
                    label = mode+'-'+str(k)+'-'+str(case); selected = int(mode == 'on' and k in enabled)
                    source = inputs/(label+'.S')
                    source.write_text('.section .rodata\n.balign 4\n'+''.join(
                        '.global '+name+'\n'+name+':\n.word '+str(value)+'\n' for name, value in
                        (('adapter_case', case), ('adapter_k', k), ('adapter_gate', selected))))
                    pin(source); config = compile_one(label, source)
                    elf = out/(label+'.elf')
                    run(label+'-link', [CXX, *flags, '-nostdlib', '-static', *objects, target, config,
                        '-Wl,--gc-sections', '-Wl,--build-id=none', '-T', inputs/'link.ld', libgcc, '-o', elf]); pin(elf)
                    names = run(label+'-symbols', [CC.with_name('riscv64-unknown-elf-nm'), '-n', elf])
                    def symbol(name):
                        rows = re.findall(r'^([0-9a-f]+) \w '+name+'$', names, re.M)
                        require(len(rows) == 1, 'Missing symbol '+name); return rows[0]
                    cmd = inputs/(label+'.cmd')
                    cmd.write_text('until pc 0 '+symbol('test_exit')+'\nreg 0 a0\nstr '+symbol('test_log')+'\nrs\n'); pin(cmd)
                    tests.append((label, k, case, selected, elf, cmd))
        for dep in out.glob('*.d'):
            for name in shlex.split(dep.read_text().replace('\\\n', '').split(':', 1)[1]):
                p = Path(name).resolve(strict=True)
                require(not p.is_relative_to(ROOT/'software') and not p.is_relative_to(LIVE_ARCH),
                        'Unexpected live compiler dependency')
                pin(p)
        off_dep = (out/'target-header_off.d').read_text()
        require('m4_preflight.h' not in off_dep, 'Header-off build must not depend on experimental producer')
        pin(SPIKE); verify(pins); save(out/'source-pins.json', pins)
        cases = []
        for label, k, case, selected, elf, cmd in tests:
            text = run(label+'-spike', [SPIKE, '-d', '--debug-cmd='+str(cmd),
                '--isa=rv64gcv_zfh_zvfh_zicntr_zvl1024b', '-m2', elf], 90)
            checked = check_log(text, k, case, selected)
            cases.append(dict(label=label, name=CASES[case], evidence=checked, elf_sha256=sha(elf),
                              log_sha256=sha(out/(label+'-spike.log'))))
        verify(pins)
        report.update(state='M4_ADAPTER_GNU_SPIKE_CHECKED', post_pins_match=True, cases=cases,
                      source_pins_sha256=sha(out/'source-pins.json'), data_sha256=DATA_SHA,
                      helper_sha256=HELPER_SHA, metadata_stubs_only=True, numerical_cache_real=True,
                      allocator_test_hook=True, function_entry_instrumentation=True,
                      full_runtime_claim=False, model_executed=False)
    except BaseException as exc:
        report['error'] = repr(exc)
        if not (out/'source-pins.json').exists(): save(out/'source-pins.json', pins)
    save(out/'commands.json', commands); save(out/'result.json', report)
    return report


def main():
    parser = argparse.ArgumentParser(allow_abbrev=False)
    sub = parser.add_subparsers(dest='action', required=True)
    sub.add_parser('plan', allow_abbrev=False)
    build_parser = sub.add_parser('seal-build-spike', allow_abbrev=False)
    build_parser.add_argument('--output', type=Path, required=True)
    build_parser.add_argument('--gate-receipt', type=Path, required=True)
    build_parser.add_argument('--gate-sha256', required=True)
    args = parser.parse_args()
    if args.action == 'plan':
        print(json.dumps(dict(state='DRAFT_NOT_SEALED_NOT_COMPILED', scope=SCOPE, shapes=[2048, 4096],
            cases=list(enumerate(CASES)), live_overlays=list(OVERLAYS),
            receipt_state_required='M4_ADAPTER_GATE_REVIEWED', sdk_helper_sha256=HELPER_SHA,
            receipt_template=dict(state='M4_ADAPTER_GATE_REVIEWED',
                evidence_kind='framing_audit_v1', benchmark=str(OUT/'optimization_extension_preflight_20261111_02'),
                benchmark_result_sha256=ORIGINAL_RESULT,
                audit_output=str(OUT/'optimization_extension_preflight_framing_audit_20261111_01'),
                audit_result_sha256='<reviewed independent audit result.json SHA256>', audit_source_pins_sha256=AUDIT_PINS,
                enabled_k=[1536, 2048, 4096],
                live_overlays={name: '<reviewed final header SHA256>' for name in OVERLAYS}),
            data_sha256=DATA_SHA, target_compiled=False, vcs_launched=False), indent=2)); return 0
    report = build(args.output, args.gate_receipt, args.gate_sha256)
    print(json.dumps(report), flush=True)
    return int(report['state'] != 'M4_ADAPTER_GNU_SPIKE_CHECKED')


if __name__ == '__main__':
    raise SystemExit(main())
