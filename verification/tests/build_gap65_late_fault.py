#!/usr/bin/env python3
"""Host compiler/oracle and ELF preflight only. Never launch VCS/DVE/Spike."""
import argparse
from collections import Counter
import csv
import json
from pathlib import Path
import re
import shutil
import sys
sys.dont_write_bytecode = True
ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / 'verification/coverage'))
import build_gap38_i8_f16_lane3 as common
import coverage_evidence as evidence
import gap65_late_fault_checks as checks
import run_gap65_late_fault_checked_extension as adapter

APP = ROOT / 'apps' / checks.NAME
SCRIPT = Path(__file__).resolve()
REF = ROOT / 'verification/qbs/qbs_ref.c'
FROZEN = ROOT / 'verification/out/repaired-aligned-build-20260930-01'
HISTORY = ROOT / 'verification/out/gap62-custom-fsm-analysis-20261004-01'
save, read, sha, pins, verify, require = (common.save, common.read, common.sha,
                                       common.pins, common.verify, common.require)


class Build(common.Build):
    def __init__(self, out):
        super().__init__(out)
        self.sources = pins([SCRIPT, Path(common.__file__), Path(checks.__file__),
            Path(adapter.__file__), ROOT / 'verification/tests/test_gap65_late_fault.py',
            *APP.iterdir(), REF])
        self.flags += ['-fno-strict-aliasing']
        self.tools.update(pins([Path(shutil.which('as')).resolve(), Path(shutil.which('ld')).resolve()]))
        for program in ('cc1', 'collect2'):
            result = self.run([self.host, '-print-prog-name=' + program], 'host-' + program)
            self.tools.update(pins([Path(result.stdout.decode().strip()).resolve(strict=True)]))

    def run(self, argv, label, timeout=120):
        require(0 < timeout <= 180, 'tool budget exceeded')
        require(Path(argv[0]).name not in ('simv', 'dve', 'urg', 'spike', 'verilator', 'vcs'),
                'EDA/ISA execution forbidden in this builder')
        return super().run(argv, label, timeout)


def emit_header(out, vector):
    lines = ['#ifndef GAP65_DATA_H', '#define GAP65_DATA_H', '#include <stdint.h>']
    for name in ('weight_image', 'activation_image'):
        blob = bytes.fromhex(vector[name])
        values = [int.from_bytes(blob[i:i + 8], 'little') for i in range(0, len(blob), 8)]
        lines.append('static const uint64_t gap65_' + name + '[] __attribute__((aligned(64))) = {')
        for i in range(0, len(values), 8):
            lines.append('  ' + ', '.join('UINT64_C(0x%x)' % v for v in values[i:i + 8]) + ',')
        lines.append('};')
    lines.append('static const uint32_t gap65_expected[16] = {' +
                 ','.join(hex(v) for v in vector['expected_bits']) + '};')
    lines += ['#endif', '']
    (out / 'gap65_data.h').write_text('\n'.join(lines))


def instruction_map(text):
    instructions = {}
    for line in text.splitlines():
        m = re.match(r'^([0-9a-f]+):\s+([0-9a-f]+)\s+(.+)$', line)
        if m:
            instructions[int(m[1], 16)] = m[3].strip()
    return instructions


def cost_model(out, metadata):
    """Bound loop trips in emitted C; calibrate without new ISA execution."""
    instructions = instruction_map((out / 'dut.disassembly.log').read_text())
    symbols = {r['Symbol']['Name']['Name']: r['Symbol'] for r in metadata['Symbols']}
    # Upper call/trip bounds include shorter guard/source loops and cold setup.
    settings = {'initialize': (1, 162), 'gap65_main': (1, 128), 'gap65_inspect': (2, 128),
                'guard': (12, 8), 'guard_bad': (24, 8), 'bytes_bad': (9, 162)}
    terms = []
    for name, (calls, maxtrip) in settings.items():
        require(name in symbols and symbols[name]['Size'] > 0, 'cost symbol missing: ' + name)
        start, size = symbols[name]['Value'], symbols[name]['Size']
        body = {pc: op for pc, op in instructions.items() if start <= pc < start + size}
        backs = []
        for pc, op in body.items():
            target = re.search(r'\b0x([0-9a-f]+)\b', op)
            if target and op.split()[0] in ('bnez', 'beqz', 'bne', 'beq', 'blt', 'bge', 'bltu', 'bgeu', 'j'):
                dest = int(target[1], 16)
                if start <= dest < pc:
                    backs.append(dict(first=dest, last=pc, body=sum(dest <= p <= pc for p in body)))
        for loop in backs:
            nested = any(loop['first'] <= other['first'] and other['last'] < loop['last'] for other in backs)
            loop['max_trips'] = 2 if name == 'gap65_main' and nested else maxtrip
        subtotal = calls * (len(body) + sum(x['body'] * (x['max_trips'] - 1) for x in backs))
        terms.append(dict(function=name, calls_upper=calls, instructions=len(body), loops=backs,
                          retired_upper=subtotal))
    run = ROOT / 'verification/out/gap48-current-20261004-01/results/qbs_gap49_payload_skew/summary.json'
    old = read(run)[0]
    directory = Path(old['artifact_dir'])
    trace = directory / 'commit_trace.csv'
    summary = read(directory / 'trace_summary.json')
    require(old['status'] == 'PASS' and summary['status'] == 'VALID' and summary['retire_count'] == 73320,
            'cost calibration not the existing PASS')
    rows = list(csv.DictReader(trace.open()))
    retired = [r for r in rows if r['event'] == 'retire']
    require(len(retired) == 73320, 'retire count differs')
    old_dump = ROOT / 'verification/out/gap49-payload-preflight-20261004-01/dut.disassembly.log'
    function_starts = [(int(m[1], 16), m[2]) for line in old_dump.read_text().splitlines()
                       if (m := re.fullmatch(r'([0-9a-f]+) <([^>]+)>:', line))]
    import bisect
    starts = [x[0] for x in function_starts]
    counts = Counter(function_starts[bisect.bisect_right(starts, int(r['pc'], 16)) - 1][1] for r in retired)
    printf = sum(counts[n] for n in ('printf_', '_vsnprintf', '_ntoa_format', '_out_char', '_putchar'))
    require(printf > 0, 'missing printf calibration')
    upper = sum(t['retired_upper'] for t in terms) + 3000 + 4 * printf
    # Three 128-cycle tiles (one fault/drain, one legal recovery), plus generous
    # read/FP/commit allowance independent of the retired-instruction count.
    compute_cycles = 12000
    seconds = (upper * summary['last_cycle'] / 73320 + compute_cycles) * old['elapsed_s'] / summary['last_cycle'] * 1.25
    paths = [run, trace, directory / 'trace_summary.json', old_dump, out / 'dut.disassembly.log']
    return dict(status='CONDITIONAL_STATIC_BUDGET' if seconds <= 300 else 'BUDGET_BLOCKED',
        retired_upper=upper, emitted_loop_terms=terms, printf_allowance=4 * printf,
        nonloop_allowance=3000, extra_compute_cycles=compute_cycles, host_sensitivity=1.25,
        conditional_seconds_upper=seconds, proposed_timeout_s=300 if seconds <= 300 else None,
        calibration=dict(elapsed_s=old['elapsed_s'], retired=73320, cycles=summary['last_cycle']),
        limitations=['Not measured gap65 runtime or a formal worst-case bound.',
                     'Same frozen image and ordinary checked-app instrumentation only.',
                     'UCLI polling overhead is NOT measured or included; observer-enabled launch not admitted.',
                     'No simulation, Spike, instruction replay, or timeout tuning performed.'], input_hashes=pins(paths))


def protected_inputs():
    manifest = read(HISTORY / 'artifacts.sha256.json')
    verify({str(HISTORY / n): h for n, h in manifest.items()})
    a = read(HISTORY / 'analysis.json')
    require(a['passed'] == 647 and a['missing_arcs'] == 55, 'wrong frozen diagnostic baseline')
    verify(a['inputs_sha256'])
    before = a['raw_union'][checks.TARGET_SCOPE]
    require(format(int(before['bits'], 16), '043b')[15] == '0', 'target already hit')
    result = dict(a['inputs_sha256'])
    result.update(pins([HISTORY / 'artifacts.sha256.json', HISTORY / 'analysis.json',
                       FROZEN / 'sim/simv.daidir/vcs_rebuild',
                       ROOT / 'verification/probes/memory_gap_completion.tcl',
                       ROOT / 'verification/probes/memory_gap_fence.tcl']))
    current = evidence.Evidence()
    plan = current.plan(checks.BASE)
    collection = current.collection(checks.BASE, plan['image'])
    require(collection['status'] == 'PASS' and collection['passed'] == 648 and
            plan['image'] == a['image'], 'completed 648 frozen image differs')
    cache = current.read(checks.BASE / 'combined-bits.json')
    rows = current.ledger(checks.BASE, plan['image'])
    require(cache['tests'] == [r['vdb'] for r in rows], '648 raw membership differs')
    current.hashes(cache['input_hashes'])
    current_bits = cache['metrics']['fsm'][checks.TARGET_SCOPE]
    require(current_bits == before, '648 target FSM union differs from reviewed 647')
    for path, digest in current.files.items():
        require(path not in result or result[path] == digest, 'baseline pin drift')
        result[path] = digest
    return result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    out = args.output.resolve()
    require(ROOT == Path('/home/wangwy/openproject/ara_dsa_signoff_integration'), 'wrong worktree')
    require(out.parent == ROOT / 'verification/out' and out.name.startswith('gap65-late-fault-preflight-') and
            not out.exists(), 'new gap65 preflight directory required')
    protected = protected_inputs()
    out.mkdir()
    vector = checks.vectors()
    save(out / 'scalar-oracle.json', vector)
    emit_header(out, vector)
    b = Build(out)
    inc = [f'-I{APP}', f'-I{out}', f'-I{b.common}', '-fno-strict-aliasing']
    host_objects = [b.compile(path, 'host-' + path.stem, [*inc, '-DGAP65_HOST=1'], host=True)
                    for path in (APP / 'main.c', APP / 'host_model.c', REF)]
    host = out / 'host-check'
    b.link([b.host, *host_objects, '-lm', '-o', host], 'host.link')
    log = b.run([host], 'host-check', timeout=30).stdout.decode()
    require(log.splitlines()[-1] == 'PASSED: ' + checks.NAME + ' checks=47 errors=0', 'host oracle/checker failure')
    negative = b.run([host, '--negative'], 'host-negative', timeout=30).stdout.decode()
    require(negative.splitlines()[-1] == 'GAP65_NEGATIVE rejected=7824 pair_cancel_rejected=2', 'negative coverage incomplete')
    objects = [b.compile(b.common / name, 'dut-' + name) for name in
               ('crt0.S', 'printf.c', 'string.c', 'serial.c', 'util.c', 'print_trap_cause.c')]
    objects += [b.compile(APP / name, 'dut-' + name, inc) for name in ('main.c', 'entry.S', 'execute.S')]
    elf = out / (checks.NAME + '.elf')
    b.bind_sources([APP / 'link.ld'])
    b.link([b.cc, *b.flags, '-fuse-ld=lld', '-static', '-nostartfiles', '-Wl,--gc-sections',
            '-Wl,--orphan-handling=error', '-Wl,--build-id=none',
            f'-Wl,-Map={out / "dut.map"}', f'-T{APP / "link.ld"}', *objects,
            '-lm', f'-L{b.llvm / "lib/generic"}', '-lclang_rt.builtins-riscv64', '-o', elf], 'dut.link')
    b.run([b.llvm / 'bin/llvm-objdump', '-d', elf], 'dut.disassembly')
    meta = json.loads(b.run([b.llvm / 'bin/llvm-readobj', '--elf-output-style=JSON',
                    '--sections', '--symbols', '--program-headers', elf], 'dut.metadata').stdout)[0]
    proof = checks.elf_proof(meta, elf.read_bytes())
    proof.update(elf_sha256=sha(elf), target=checks.TARGET)
    save(out / 'elf-proof.json', proof)
    budget = cost_model(out, meta)
    save(out / 'cost-preflight.json', budget)
    protected.update(budget['input_hashes'])
    observation = dict(status='OBSERVER_LAUNCH_NOT_ADMITTED', fsdb_available=False,
        reason='Frozen image compiled with ARA_NO_FSDB; existing fault-vstart and QBS_PERF do not sample compute state.',
        read_only_ucli_api='Existing memory_gap_completion.tcl uses get SIGNAL and run 1 ns; frozen image has debug_access+all.',
        required_signals=['ara_tb.clk', 'ara_tb.rst_n', checks.TARGET_SCOPE + '.state_q',
                          checks.TARGET_SCOPE + '.state_d', checks.TARGET_SCOPE + '.fault_i'],
        witness='Consecutive reset-free samples: state_q=3, state_d=10, fault_i=1 then state_q=10.',
        raw_target=checks.TARGET, tool_launches=0,
        blocker='Existing checked-app runner has no UCLI/script argument admission; runtime/pin/trace adapter review required. '
                'Do not silently drop witness or treat aggregate counters as it.')
    save(out / 'observation-plan.json', observation)
    b.bind_sources([Path(m.__file__).resolve() for m in tuple(sys.modules.values())
        if getattr(m, '__file__', None) and Path(m.__file__).resolve().is_relative_to(ROOT / 'verification')])
    for group in (b.sources, b.tools, b.link_inputs, protected):
        verify(group)
    for name, value in [('source_hashes.json', b.sources), ('tool_hashes.json', b.tools),
                        ('link-inputs.json', b.link_inputs), ('protected-inputs.json', protected)]:
        save(out / name, value)
    record = dict(name=checks.NAME, binary=str(elf), binary_sha256=sha(elf), sources=sorted(b.sources),
        source_hashes=b.sources, host_reference=str(APP / 'host_model.c'), host_result=log.strip(),
        host_log=str(out / 'host-check.log'), host_checks=47, dut_checks=49,
        custom_instruction_execution_prechecked=False, vcs_launched=False,
        scalar_oracle=str(out / 'scalar-oracle.json'), negative_mutations=7824, pair_negatives=2,
        budget_status=budget['status'], observer_launch_admitted=False)
    record_path = out / (checks.NAME + '.precheck.json')
    save(record_path, record)
    artifacts = pins(p for p in out.iterdir() if p.is_file())
    save(out / 'artifact_hashes.json', artifacts)
    require(budget['proposed_timeout_s'] == 300, '300-second ordinary app budget not supported; no checked selection published')
    item = dict(name=adapter.CASE, binary=str(elf), binary_sha256=sha(elf), sources=sorted(b.sources),
        evidence=sorted([*artifacts, str(out / 'artifact_hashes.json')]), timeout_s=300,
        targets=[checks.TARGET_SCOPE],
        source_audit='Test-owned pre-C SP relocation and exact linker/NOBITS/orphan checks. Single high alias, WT+fence visibility. '
            'Exact trap PC/cause/tval/count; all four destination registers; scalar Fraction oracle crosschecked against qbs_ref; '
            '16 recovery outputs, zero tails, all source/guard bytes, 7824 byte negatives. Host-only, not ISA/RTL PASS.',
        rationale='M4 N5 Q4_K/Q8_K late fifth-row PMA fault; first four rows valid. Target compute FSM XML arc3/raw15 '
            'COMPUTE_TILE->FAULT_DRAIN. M4 N4 same-high-address numerical recovery. No context/payload-matrix repeat. '
            '300s conditional ordinary app budget; required observer integration remains unadmitted, no launch authorization.',
        precheck=dict(format='accel-host-v1', record=str(record_path), log=str(out / 'host-check.log')))
    draft = out / 'selection.checked-draft.json'
    save(draft, dict(status='HOST_ONLY_DRAFT_OBSERVER_LAUNCH_BLOCKED', baseline=str(checks.BASE),
         baseline_bits=str(checks.BASE / 'combined-bits.json'), cases=[item], vcs_launched=False))
    checked = evidence.Evidence()
    checked.pin(draft)
    for name in adapter.MANIFESTS:
        checked.hashes(checked.read(out / name))
    result = evidence.precheck(item, checked)
    save(out / 'checked-precheck.json', dict(status='PASS', scope='host-reference-only',
        read_only_validation=True, vcs_launched=False, observer_launch_admitted=False,
        result=result, checked_files=checked.files))
    save(out / 'draft.sha256.json', pins([draft, out / 'checked-precheck.json', out / 'artifact_hashes.json']))
    adapter.precheck(item, evidence.Evidence(), evidence.precheck)
    print(json.dumps(dict(status='HOST_PREFLIGHT_PASS_NO_LAUNCH', elf_sha256=sha(elf),
         byte_negatives=7824, paired_negatives=2, cost=budget['conditional_seconds_upper'],
         observer_launch_admitted=False, output=str(out))))


if __name__ == '__main__':
    main()
