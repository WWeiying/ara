#!/usr/bin/env python3
"""Historical-dependency, original/fixed complete commit_stage VCS test."""
import argparse
import csv
import hashlib
import json
import os
from pathlib import Path
import re
import shutil
import subprocess
import sys
import time

sys.dont_write_bytecode = True
HERE = Path(__file__).resolve().parent
ROOT = Path('/home/wangwy/openproject/ara_dsa')
OUT = ROOT.parent / 'ara_dsa_signoff_integration/verification/out'
SOC = OUT / 'resident_pv_soc_build_20261109_03'
FAILED = OUT / 'resident_pv_soc_boundary_vcs_20261109_01'
DEP = Path('hardware/deps/cva6')
TARGET = DEP / 'core/commit_stage.sv'
BEFORE = 'bf59bfa36960ec6227cb49d86e60f8b8f9507590f64ecfafffa9d8d8f94abb60'
PATCH_SHA = 'b4fe150d85074ce51acbddcb88600f359503b60427337919df3350f1acb13c00'
LOCKED_REV = 'b29fd3cf906e7f4c71da4c2f46451c4c60a4487f'
OWN = ('run.py', 'test_run.py', 'commit_dirty_tb.sv', 'accel_dirty_retirement.patch', 'README.md')
PACKAGES = tuple(DEP / 'core/include' / name for name in (
    'config_pkg.sv', 'cv64a6_imafdcv_sv39_config_pkg.sv', 'riscv_pkg.sv', 'ariane_pkg.sv'))
ANCHORS = {
    SOC / 'build.json': 'cbed1980df5d0f23164febecd95c82234036584afb3f2853c887252fc9e12b47',
    SOC / 'source-pins.json': 'fe2703bb9058983d3177191a69b3315ebc6e1fcba0da06c8a87c0e0274a3da26',
    FAILED / 'result.json': 'a6388d89233192eceffe5ebaf08171efc89a8ea1a86f5b1e4704898217439749',
}
SCOPE = ('Complete historical commit_stage original/fixed, two commit ports; '
         'not a new SoC/boundary acceptance; original FAIL and strict oracle unchanged')


def need(condition, message):
    if not condition:
        raise ValueError(message)


def sha(path):
    value = hashlib.sha256()
    with Path(path).open('rb') as stream:
        for part in iter(lambda: stream.read(1024 * 1024), b''):
            value.update(part)
    return value.hexdigest()


def save(path, data):
    with path.open('x') as stream:
        json.dump(data, stream, indent=2, sort_keys=True)
        stream.write('\n')


def verify(pins):
    for name, expected in pins.items():
        need(Path(name).is_file() and sha(name) == expected, 'Identity drift: ' + str(name))


def candidate_bytes(before):
    need(hashlib.sha256(before).hexdigest() == BEFORE, 'Unreviewed commit_stage preimage')
    old = b'      ))) | (commit_instr_i[i].fu == ACCEL && commit_instr_i[i].vfp);'
    new = (b'      ))) | (commit_ack_o[i] && !commit_drop_i[i] && !commit_instr_i[i].ex.valid &&\n'
           b'          commit_instr_i[i].fu == ACCEL && commit_instr_i[i].vfp);')
    need(before.count(old) == 1, 'Dirty expression changed')
    return before.replace(old, new)


def apply_to_snapshot(source_root):
    """Explicit successor-build hook. Only a fresh private signoff source copy."""
    root = Path(source_root).resolve()
    need(root.is_relative_to(OUT.resolve()) and not root.is_relative_to(SOC.resolve()),
         'Patch target must be a fresh private signoff copy, never shared deps/old SOC')
    target = root / TARGET
    need(target.resolve() == target and target.is_file(), 'Missing/linked patch target')
    before = target.read_bytes()
    after = candidate_bytes(before)
    patch = HERE / 'accel_dirty_retirement.patch'
    need(sha(patch) == PATCH_SHA, 'Unreviewed registered patch')
    environment = os.environ.copy()
    for name in ('GIT_DIR', 'GIT_WORK_TREE', 'GIT_INDEX_FILE'):
        environment.pop(name, None)
    # An outer signoff repository otherwise silently skips this private subtree.
    environment['GIT_CEILING_DIRECTORIES'] = str(root)
    for args in (['--check'], []):
        subprocess.run(['git', 'apply', '--no-index', *args, str(patch)],
                       cwd=root / DEP, env=environment, check=True, capture_output=True, text=True)
    need(target.read_bytes() == after, 'Patch differs from reviewed candidate')
    return dict(target=str(TARGET), dependency_revision=LOCKED_REV, before_sha256=BEFORE,
                after_sha256=sha(target), patch_sha256=PATCH_SHA,
                native_fp_expression_unchanged=True, fflags_logic_unchanged=True)


def historical_evidence():
    verify(ANCHORS)
    build = json.loads((SOC / 'build.json').read_text())
    need(build['state'] == 'RESIDENT_PV_SOC_BUILT_NOT_EXECUTED' and
         build['post_image_match'] and build['post_pins_match'], 'Old SoC receipt not accepted')
    # Deliberately do not verify inherited live paths: this is a historical-image
    # identity, not a claim about current HEAD. Selected frozen inputs remain exact.
    frozen_pins = json.loads((SOC / 'source-pins.json').read_text())
    selected = {str(SOC / 'source' / rel): frozen_pins[str(SOC / 'source' / rel)]
                for rel in (*PACKAGES, TARGET, Path('Bender.lock'))}
    verify(selected)
    verify(build['image_pins'])
    failed = json.loads((FAILED / 'result.json').read_text())
    need(failed['state'] == 'FAIL', 'Original FAIL was changed')
    original = {str(FAILED / 'work' / name): failed['artifacts'][str(FAILED / 'work' / name)]
                for name in ('run.vcs.log', 'commit.csv', 'vector_trace.csv')}
    verify(original)
    text = (FAILED / 'work/run.vcs.log').read_text()
    need(text.count('PV_BOUNDARY_DONE cases=21 successes=21 rejected=12 compat=1 errors=2') == 1,
         'Unexpected original target result')
    rows = re.findall(r'^.*PV_BOUNDARY_CASE id=16 phase=0 .*$', text, re.M)
    need(len(rows) == 1, 'Missing original FS-off row')
    fields = dict(re.findall(r'(\w+)=([^\s]+)', rows[0]))
    need(int(fields['trap_csrs_valid']) == 1 and
         int(fields['before_mstatus'], 16) & 0x6000 == 0 and
         int(fields['trap_mstatus'], 16) & 0x6000 == 0x6000 and
         int(fields['after_mstatus'], 16) & 0x6000 == 0x6000, 'FS-off failure signature changed')
    wanted = {3545357: (0x8000025c, 0x8000000a00000680),
              3545395: (0x80000380, 0x8000000a00007e00),
              3545418: (0x800003a8, 3),
              3545520: (0x8000028c, 0x8000000a00006680)}
    actual = {}
    pv_events = []
    with (FAILED / 'work/commit.csv').open(newline='') as stream:
        for row in csv.DictReader(stream):
            cycle = int(row['cycle'])
            if cycle > max(wanted):
                break
            if cycle in wanted and row['event'] == 'retire':
                if (int(row['pc'], 16), int(row['rd_wdata'], 16)) == wanted[cycle]:
                    actual[cycle] = row
            if 3545357 <= cycle <= 3545520 and int(row['insn'], 16) == 0x0485705b:
                pv_events.append(row)
    need(set(actual) == set(wanted) and not pv_events, 'Original actual CSR/PV trace signature changed')
    return dict(scope='Historical frozen image only; no live production equivalence asserted',
                soc=str(SOC), original_failure=str(FAILED), image_files=len(build['image_pins']),
                source_inputs=selected, original_fs_off=fields,
                actual_csr_retirements=actual, pv_retire_or_request_in_fault_window=pv_events), {
                    **{str(p): digest for p, digest in ANCHORS.items()},
                    **selected, **original, **build['image_pins']}


def check_log(text):
    need(not re.search(r'(?im)(?:fatal|error|assertion failed|timeout)', text), 'VCS runtime failure')
    rows = re.findall(r'^DIRTY_CASE cache=(WT|WB) id=(\d+) name=(\w+) ack=([01]{2}) old=([01]) fixed=([01]) '
                      r'flags_write=([01]) flags=([0-9a-f]{2}) reproduced=([01])$', text, re.M)
    need(len(rows) == 72, 'Wrong directed case count')
    for cache, failures in (('WT', 11), ('WB', 12)):
        selected = [r for r in rows if r[0] == cache]
        need([int(r[1]) for r in selected] == list(range(1, 37)), 'Missing/duplicate directed cases')
        need(len({r[2] for r in selected}) == 36, 'Duplicate named case')
        need(sum(int(r[8]) for r in selected) == failures, 'Original defect not reproduced')
    for _, _, name, _, old, fixed, _, _, defect in rows:
        need((old != fixed) == (defect == '1'), 'Wrong original/fixed difference: ' + name)
        if defect == '1':
            need(old == '1' and fixed == '0', 'Wrong dirty defect direction')
    marker = 'COMMIT_DIRTY_PASS configurations=2 checks=72 original_failures=23 fixed_failures=0 non_dirty_equal=72'
    need(text.count(marker) == 1, 'Missing/duplicate completion')
    return dict(configurations=2, checks=72, original_failures=23, fixed_failures=0, non_dirty_equal=72)


def prepare(out):
    need(out.parent == OUT and not out.exists(), 'Use a unique direct signoff output')
    vcs = shutil.which('vcs')
    need(vcs, 'Host VCS unavailable')
    evidence, pins = historical_evidence()
    out.mkdir()
    inputs = out / 'inputs'
    for rel in (*PACKAGES, TARGET):
        source, dest = SOC / 'source' / rel, inputs / rel
        dest.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(source, dest)
    local = inputs / 'test'
    local.mkdir()
    for name in OWN:
        source, dest = HERE / name, local / name
        digest = sha(source)
        shutil.copyfile(source, dest)
        pins[str(source)] = pins[str(dest)] = digest
    before = inputs / 'commit_stage_before.sv'
    raw = (inputs / TARGET).read_bytes()
    need(raw.count(b'module commit_stage\n') == 1, 'Reference module declaration changed')
    before.write_bytes(raw.replace(b'module commit_stage\n', b'module commit_stage_before\n'))
    overlay = apply_to_snapshot(inputs)
    filelist = inputs / 'sources.f'
    filelist.write_text('\n'.join(map(str, (
        *(inputs / p for p in PACKAGES), before, inputs / TARGET, local / 'commit_dirty_tb.sv'))) + '\n')
    save(out / 'historical-evidence.json', evidence)
    save(out / 'overlay.json', overlay)
    selection = dict(vcs=str(Path(vcs).resolve()), local=str(local), timeout_seconds=300,
                     service_seconds=420, scope=SCOPE)
    save(out / 'selection.json', selection)
    for path in (*inputs.rglob('*'), out / 'historical-evidence.json', out / 'overlay.json',
                 out / 'selection.json', Path(vcs).resolve()):
        if path.is_file():
            pins[str(path)] = sha(path)
    need(not any(str(p).startswith(str(ROOT / 'hardware')) for p in pins), 'Live production execution pin')
    verify(pins)
    save(out / 'source-pins.json', pins)
    save(out / 'prepared.json', dict(state='PREPARED_NOT_EXECUTED', scope=SCOPE,
                                     frozen_runner=str(local / 'run.py')))
    print(json.dumps(dict(output=str(out), frozen_runner=str(local / 'run.py'), overlay=overlay)))


def execute(out):
    selection = json.loads((out / 'selection.json').read_text())
    need(Path(__file__).resolve() == Path(selection['local']) / 'run.py', 'Use frozen direct-owner runner')
    work = out / 'work'
    work.mkdir()
    pins = json.loads((out / 'source-pins.json').read_text())
    report = dict(state='FAIL', scope=SCOPE, automatic_retry=False, soc_acceptance=False)
    deadline = time.monotonic() + selection['timeout_seconds']

    def command(argv, name):
        save(work / (name + '.command.json'), argv)
        with (work / (name + '.log')).open('x') as log:
            subprocess.run(argv, cwd=work, stdout=log, stderr=subprocess.STDOUT, check=True,
                           timeout=max(1, deadline - time.monotonic()))

    try:
        cgroup = Path('/proc/self/cgroup').read_text()
        need('.service' in cgroup, 'Worker must be directly owned by systemd')
        save(out / 'owner.json', dict(pid=os.getpid(), ppid=os.getppid(), cgroup=cgroup,
                                      invocation_id=os.getenv('INVOCATION_ID')))
        verify(pins)
        command([sys.executable, '-B', str(HERE / 'test_run.py')], 'host-tests')
        print('COMMIT_DIRTY_COMPILING', flush=True)
        command([selection['vcs'], '-full64', '-sverilog', '-timescale=1ns/1ps', '-j2',
                 '-top', 'commit_dirty_tb', '-o', 'simv', '-f', str(out / 'inputs/sources.f')], 'compile')
        verify(pins)
        image = {str(p): sha(p) for p in work.rglob('*')
                 if p.is_file() and (p.name == 'simv' or 'simv.daidir' in p.parts)}
        need(str(work / 'simv') in image, 'No executable produced')
        save(out / 'image-pins.json', image)
        print('COMMIT_DIRTY_SIMULATING', flush=True)
        command([str(work / 'simv'), '-no_save'], 'simulation')
        report.update(check_log((work / 'simulation.log').read_text()))
        verify(pins)
        verify(image)
        report.update(state='PASS', post_pins_match=True, post_image_match=True,
                      original_bug_reproduced=True, native_fp_and_fflags_unchanged=True)
    except Exception as exc:
        report['error'] = repr(exc)
    report['source_pins_sha256'] = sha(out / 'source-pins.json')
    report['overlay'] = json.loads((out / 'overlay.json').read_text())
    report['artifacts'] = {str(p): sha(p) for p in work.rglob('*') if p.is_file()}
    save(out / 'report.json', report)
    print(json.dumps(report, sort_keys=True))
    return 0 if report['state'] == 'PASS' else 1


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('action', choices=('prepare', 'exec'))
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    need(args.output.is_absolute() and args.output.parent == OUT, 'Wrong output root')
    if args.action == 'prepare':
        prepare(args.output)
        return 0
    return execute(args.output)


if __name__ == '__main__':
    raise SystemExit(main())
