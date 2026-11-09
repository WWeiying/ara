#!/usr/bin/env python3
"""Replay the sealed PV corpus through the actual VMFPU borrowing interface.

This is a lane integration gate, not a whole-SoC performance measurement.
Dependencies come only from the admitted frozen SoC. The old arithmetic oracle,
stimulus and PV protocol checker are retained without weakening their checks.
"""
import argparse
import hashlib
import importlib.util
import json
from pathlib import Path
import re
import shutil
import subprocess
import sys

sys.dont_write_bytecode = True
HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[3]
OUT = Path('/home/wangwy/openproject/ara_dsa_signoff_integration/verification/out')
BASE = OUT/'chain_soc_20261107_01'
CORPUS = OUT/'resident_pv_lane_20261108_03'


def helper(path):
    spec = importlib.util.spec_from_file_location('resident_pv_gate', path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def adapt_bench(text):
    substitutions = (
        ('fpnew_opgroup_fmt_slice #(\n', 'resident_vmfpu_adapter #(\n'),
        ('.clk_i(clk), .rst_ni(rst), .operands_i(operands)',
         '.clk_i(clk), .rst_ni(rst), .borrow_busy_i(busy), .operands_i(operands)'),
        ('$finish;', 'borrowed_fpu.finish_gate();\n    $finish;'),
        ('task automatic reset_all;\n    @(negedge clk);\n',
         'task automatic reset_all;\n'),
    )
    for old, new in substitutions:
        if text.count(old) != 1:
            raise ValueError('Unrecognized sealed bench: '+old)
        text = text.replace(old, new)
    return text


def filelist(text, replacement, pins):
    result = []
    changed = 0
    for raw in text.splitlines():
        line = raw.strip()
        if not line:
            continue
        if line.startswith('/'):
            if line not in pins:
                raise ValueError('Unpinned baseline source: '+line)
            if '/hardware/tb/' in line:
                # SoC monitors contain absolute ara_tb references; this gate's
                # top is the independent resident_pv_tb, not that SoC harness.
                continue
            if line.endswith('/hardware/src/lane/vmfpu.sv'):
                result.append(str(replacement))
                changed += 1
            else:
                result.append(line)
        elif line.startswith(('+define+', '+incdir+')):
            result.append(line)
        else:
            raise ValueError('Unsupported file-list entry: '+line)
    if changed != 1:
        raise ValueError('Expected exactly one VMFPU definition')
    return '\n'.join(result)+'\n'


def check_owner(text):
    matches = re.findall(r'^VMFPU_OWNER_COVERAGE (.+)$', text, re.M)
    if len(matches) != 1:
        raise ValueError('Missing/duplicate VMFPU ownership coverage')
    counters = dict((k, int(v)) for k, v in re.findall(r'(\w+)=(\d+)', matches[0]))
    for name in ('native_done', 'acquires', 'releases', 'native_stalls', 'private_stalls',
                 'acquire_collisions', 'miter_cycles', 'native_grant_stalls',
                 'native_flag_events', 'reset_owned', 'native_fma', 'native_mul',
                 'native_div', 'native_max'):
        if counters.get(name, 0) <= 0:
            raise ValueError('Unexercised ownership condition: '+name)
    for accepted, returned, cancelled in (
            ('native_accepted', 'native_done', 'native_cancelled'),
            ('private_issued', 'private_returned', 'private_cancelled'),
            ('acquires', 'releases', 'reset_owned')):
        if any(key not in counters for key in (accepted, returned, cancelled)) or (
                counters[accepted] != counters[returned]+counters[cancelled]):
            raise ValueError('Unbalanced ownership accounting: '+accepted)
    return counters


def baseline_module(text):
    old = 'module vmfpu import ara_pkg::*;'
    ending = 'endmodule : vmfpu\n'
    if text.count(old) != 1 or text.count(ending) != 1:
        raise ValueError('Unexpected original VMFPU declaration')
    return text.replace(old, 'module vmfpu_baseline import ara_pkg::*;').replace(
        ending, 'endmodule : vmfpu_baseline\n')


def baseline_pins(original, baseline, inputs, out):
    """Recover the historical build helper, never waive a compiler input drift."""
    pins = {}
    historical = ROOT/'verification/performance/chain_profile/build_soc.py'
    audit = []
    revision = json.loads((BASE/'build.json').read_text())['revision']
    for name, expected in baseline.items():
        actual = original.sha(name)
        if actual == expected:
            pins[name] = expected
            continue
        if name != str(historical):
            raise ValueError('Frozen source/dependency drift: '+name)
        # This script is provenance only; this runner does not execute it.
        # Reconstruct its exact old content from the recorded build revision.
        content = subprocess.check_output(['git', 'show',
            revision+':verification/performance/chain_profile/build_soc.py'], cwd=ROOT)
        if hashlib.sha256(content).hexdigest() != expected:
            raise ValueError('Cannot reconstruct original build helper')
        recovered = inputs/'historical_build_soc.py'
        recovered.write_bytes(content)
        pins[str(recovered)] = expected
        pins[name] = actual
        audit.append(dict(path=name, expected=expected, current=actual,
                          recovered=str(recovered), recovered_revision=revision,
                          executed=False, scope='Historical build helper; not compiler input'))
    original.save(out/'historical-provenance.json', dict(
        original_manifest_matches_current_paths=not audit, recovered_metadata=audit,
        rtl_and_dependencies_match=True, original_receipt_rewritten=False))
    return pins


def copy_pinned(original, path, destination, pins, accepted):
    name = str(path)
    if name in pins and name in accepted and pins[name] != accepted[name]:
        raise ValueError('Conflicting existing input identities: '+name)
    expected = pins.get(name, accepted.get(name))
    if expected is None:
        expected = original.sha(path)
    if original.sha(path) != expected:
        raise ValueError('Input changed before snapshot: '+name)
    pins[name] = expected
    shutil.copyfile(path, destination)
    if original.sha(destination) != expected:
        raise ValueError('Input changed during snapshot: '+name)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('output', type=Path)
    parser.add_argument('--shared', type=int, choices=(0, 1), nargs='+', default=[0, 1])
    parser.add_argument('--prepare-only', action='store_true')
    args = parser.parse_args()
    out = args.output.resolve()
    if not out.is_relative_to(OUT) or len(set(args.shared)) != len(args.shared):
        parser.error('Fresh verification output and distinct configurations required')
    out.mkdir(parents=True, exist_ok=False)
    original = helper(HERE.parent/'pv_unit/run.py')
    report = dict(state='FAIL', scope='Real VMFPU sharing; no SoC/FPGA/performance claim',
                  synthesis=False, configurations=[])
    pins = {}
    try:
        manifests = {}
        for path in (BASE/'source-pins.json', CORPUS/'report.json'):
            content = path.read_bytes()
            pins[str(path)] = hashlib.sha256(content).hexdigest()
            manifests[path] = json.loads(content)
        baseline = manifests[BASE/'source-pins.json']
        source_receipt = manifests[CORPUS/'report.json']
        if source_receipt['state'] != 'PASS':
            raise ValueError('Original corpus not accepted')
        original.verify(source_receipt['artifacts'])
        inputs = out/'inputs'
        inputs.mkdir()
        pins.update(baseline_pins(original, baseline, inputs, out))
        accepted_pins = json.loads((CORPUS/'original-pins.json').read_text())
        for path in (HERE.parent/'pv_unit/run.py', HERE.parent/'pv_unit/tb.sv',
                     HERE.parent/'pv_unit/akv_resident_pv_lane.sv'):
            if accepted_pins.get(str(path)) != original.sha(path):
                raise ValueError('Previous PV checker/controller changed: '+str(path))
        copies = [(BASE/'sources.f', 'sources.f'),
                  (BASE/'source-pins.json', 'baseline-pins.json'),
                  (CORPUS/'report.json', 'corpus-receipt.json'),
                  (HERE/'run.py', 'driver.py'), (HERE/'adapter.sv', 'adapter.sv'),
                  (ROOT/'hardware/src/lane/vmfpu.sv', 'vmfpu.sv'),
                  (HERE.parent/'pv_unit/akv_resident_pv_lane.sv', 'akv_resident_pv_lane.sv'),
                  (HERE.parent/'pv_unit/run.py', 'pv_checker.py'),
                  (HERE.parent/'pv_unit/tb.sv', 'tb.sv')]
        for path, name in copies:
            copy_pinned(original, path, inputs/name, pins, accepted_pins)
        # Keep the originally accepted stimulus and SoftFloat outputs verbatim.
        for name in ('vectors.txt', 'vectors.json'):
            source = CORPUS/'vectors'/name
            digest = original.sha(source)
            if source_receipt['artifacts'].get(str(source)) != digest:
                raise ValueError('Unsealed stimulus: '+name)
            pins[str(source)] = digest
            shutil.copyfile(source, inputs/name)
        tb_original = (inputs/'tb.sv').read_text()
        (inputs/'tb-original.sv').write_text(tb_original)
        (inputs/'tb.sv').write_text(adapt_bench(tb_original))
        (inputs/'sources.f').write_text(filelist((BASE/'sources.f').read_text(), inputs/'vmfpu.sv', baseline))
        original.save(out/'source-selection.json', dict(
            top='resident_pv_tb', replaced_rtl=['hardware/src/lane/vmfpu.sv'],
            excluded_soc_testbench_sources=sorted(set(line.strip() for line in
                (BASE/'sources.f').read_text().splitlines()
                if line.strip().startswith('/') and '/hardware/tb/' in line))))
        old_vmfpu = BASE/'source/hardware/src/lane/vmfpu.sv'
        if baseline.get(str(old_vmfpu)) != original.sha(old_vmfpu):
            raise ValueError('Unsealed original VMFPU')
        (inputs/'vmfpu_baseline.sv').write_text(baseline_module(old_vmfpu.read_text()))
        pins.update({str(p): original.sha(p) for p in inputs.iterdir() if p.is_file()})
        original.save(out/'source-pins.json', pins)
        original.verify(pins)
        corpus = json.loads((inputs/'vectors.json').read_text())
        vcs = shutil.which('vcs')
        if not vcs:
            raise ValueError('Host VCS not found')
        report.update(cases=corpus['cases'], real_cases=corpus['real_cases'])
        if args.prepare_only:
            report['state'] = 'PREPARED_NOT_EXECUTED'
        else:
            frozen_checker = helper(inputs/'pv_checker.py')
            for shared in args.shared:
                work = out/f'shared{shared}'
                work.mkdir()
                argv = [vcs, '-full64', '-sverilog', '-timescale=1ns/1ps',
                        '-top', 'resident_pv_tb', '-j8', '-o', 'simv',
                        '+define+SIMULATION', '+define+ARA_SHARED_SIMD_MUL',
                        f'+define+RESIDENT_TEST_SHARED_FMA={shared}',
                        '-f', str(inputs/'sources.f'),
                        str(inputs/'vmfpu_baseline.sv'),
                        str(inputs/'akv_resident_pv_lane.sv'), str(inputs/'adapter.sv'),
                        str(inputs/'tb.sv')]
                run = [str(work/'simv'), '-no_save', '+VECTORS='+str(inputs/'vectors.txt')]
                original.save(work/'commands.json', dict(compile=argv, run=run))
                print(f'VMFPU_COMPILING shared={shared}', flush=True)
                original.command(argv, work, work/'compile.log', 600)
                original.verify(pins)
                image = {str(work/'simv'): original.sha(work/'simv')}
                original.save(work/'image-pins.json', image)
                print(f'VMFPU_RUNNING shared={shared}', flush=True)
                text = original.command(run, work, work/'run.log', 600)
                checked = frozen_checker.check_log(text, corpus, 3)
                ownership = check_owner(text)
                if ownership['private_issued'] != checked['totals']['issued']:
                    raise ValueError('Private FPU and controller issue counts differ')
                original.verify(pins)
                original.verify(image)
                checked.update(state='PASS', shared_fma=shared, ownership=ownership)
                original.save(work/'report.json', checked)
                report['configurations'].append(dict(shared_fma=shared,
                    totals=checked['totals'], ownership=ownership))
                print(f'VMFPU_PASS shared={shared} cases={corpus["cases"]}', flush=True)
            report['state'] = 'PASS'
        original.verify(pins)
        report['post_pins_match'] = True
    except Exception as exc:
        report.update(state='FAIL', error=str(exc))
        print('VMFPU_FAIL '+str(exc), flush=True)
    report['artifacts'] = {str(p): original.sha(p) for p in out.rglob('*')
                           if p.is_file() and p.suffix in ('.json', '.log', '.sv', '.txt', '.f')}
    original.save(out/'report.json', report)
    print(json.dumps(report), flush=True)
    return int(report['state'] == 'FAIL')


if __name__ == '__main__':
    raise SystemExit(main())
