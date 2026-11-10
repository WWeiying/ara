#!/usr/bin/env python3
"""Successor full-FP/PV/QBS ownership gate; host VCS, frozen FP dependencies."""
import argparse
import hashlib
import json
import os
from pathlib import Path
import re
import shutil
import subprocess
import sys

sys.dont_write_bytecode = True
HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[3]
OUT = Path('/home/wangwy/openproject/ara_dsa_signoff_integration/verification/out')
ACCEPTED = OUT / 'resident_pv_context_fp_agent_20261108_01'
FROZEN = OUT / 'chain_soc_20261107_01/source'
FILELIST = OUT / 'resident_pv_cluster_fp_20261108_02/inputs/sources.f'
ADMISSION = {
    str(ACCEPTED / 'report.json'): '0928f7de1e6e062f3cc792821bb0c2dba4cdfb21ee771ed40505cb9427500acf',
    str(ACCEPTED / 'source-pins.json'): 'ed5f0f47cd426dc638e6be62e854f0c1d382a66826eaba96f00116727043752f',
    str(FILELIST): '024e63c62fac7ab564bb9ed9044b80ed0e41c41f1e27f127b23a4f0d21974e69',
}
OVERLAY = (
    'hardware/include/ara_pkg.sv',
    'hardware/src/lane/simd_mul.sv',
    'hardware/src/lane/simd_mul_shared_product.sv',
    'hardware/src/lane/simd_mul_partition_add.sv',
    'hardware/src/lane/simd_mul_shared.sv',
    'hardware/src/lane/qbs_lane_mul_borrow.sv',
    'hardware/src/lane/vmfpu.sv',
)
PACKAGES = (
    'hardware/deps/common_cells/src/cf_math_pkg.sv',
    'hardware/deps/axi/src/axi_pkg.sv',
    'hardware/deps/fpnew/src/fpnew_pkg.sv',
    'hardware/deps/cva6/core/include/config_pkg.sv',
    'hardware/deps/cva6/core/include/cv64a6_imafdcv_sv39_config_pkg.sv',
    'hardware/deps/cva6/core/include/riscv_pkg.sv',
    'hardware/deps/cva6/core/include/ariane_pkg.sv',
    'hardware/deps/cva6/core/include/build_config_pkg.sv',
    'hardware/include/rvv_pkg.sv',
    'hardware/include/ara_pkg.sv',
)
LEAVES = (
    'hardware/deps/common_cells/src/lzc.sv',
    'hardware/deps/common_cells/src/rr_arb_tree.sv',
    'hardware/deps/common_cells/src/spill_register_flushable.sv',
    'hardware/deps/common_cells/src/spill_register.sv',
    'hardware/deps/tech_cells_generic/src/rtl/tc_clk.sv',
    'hardware/deps/cva6/core/serdiv.sv',
    'hardware/src/lane/power_gating_generic.sv',
    'hardware/src/lane/simd_div.sv',
    'hardware/src/lane/simd_fpnew.sv',
    'hardware/src/lane/simd_fma_shared.sv',
)
OWN = ('run_vmfpu_fp.py', 'vmfpu_fp_tb.sv', 'test_run_vmfpu_fp.py')
ERROR = re.compile(r'(?im)(^Error-|^Error:|^Fatal:|^FATAL|Assertion failed|\$fatal|^Error\[)')
FIELDS = ('native', 'writes', 'flags', 'nv', 'grant_stalls', 'native_held', 'pv_held',
          'pv_acquires', 'pv_releases', 'pv_returns', 'borrowed', 'returned',
          'red_tokens', 'red_completes')


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def save(path, value):
    Path(path).write_text(json.dumps(value, indent=2, sort_keys=True) + '\n')


def verify(pins):
    for name, digest in pins.items():
        if sha(name) != digest:
            raise ValueError('Pinned input/image drift: ' + name)


def copy_pin(source, destination, pins, expected=None):
    digest = sha(source)
    if expected is not None and digest != expected:
        raise ValueError('Accepted dependency drift: ' + str(source))
    destination.parent.mkdir(parents=True, exist_ok=True)
    shutil.copyfile(source, destination)
    if sha(destination) != digest:
        raise ValueError('Snapshot race: ' + str(source))
    pins[str(source)] = pins[str(destination)] = digest


def dependencies(text):
    """Select ordered FP sources only from the admitted filelist, never live deps."""
    selected = []
    for line in text.splitlines():
        path = Path(line)
        if not path.is_relative_to(FROZEN):
            continue
        rel = str(path.relative_to(FROZEN))
        if (rel.startswith(('hardware/deps/fpnew/', 'hardware/deps/fpu_div_sqrt_mvp/'))
                and rel not in PACKAGES and rel not in selected):
            selected.append(rel)
    if not any('fpu_div_sqrt_mvp/' in rel for rel in selected):
        raise ValueError('Missing frozen divider closure')
    return list(dict.fromkeys((*PACKAGES, *LEAVES, *selected, *OVERLAY)))


def prepare(out):
    if out.parent != OUT or out.exists() or not shutil.which('vcs'):
        raise ValueError('Require unique signoff output and host VCS')
    branch = subprocess.check_output(
        ['git', '-C', str(OUT.parents[1]), 'branch', '--show-current'], text=True).strip()
    if branch != 'ara_dsa_signoff_integration':
        raise ValueError('Wrong signoff branch')
    verify(ADMISSION)
    receipt = json.loads((ACCEPTED / 'report.json').read_text())
    if receipt['state'] != 'PASS' or not receipt['post_pins_match'] or not receipt['post_image_match']:
        raise ValueError('Full-FP dependency admission failed')
    accepted = json.loads((ACCEPTED / 'source-pins.json').read_text())
    sources = dependencies(FILELIST.read_text())
    out.mkdir()
    inputs = out / 'inputs'
    pins = dict(ADMISSION)
    for rel in sources:
        source = (ROOT if rel in OVERLAY else FROZEN) / rel
        copy_pin(source, inputs / rel, pins, None if rel in OVERLAY else accepted[str(source)])
    headers = FROZEN / 'hardware/deps/common_cells/include'
    for source in sorted(p for p in headers.rglob('*') if p.is_file()):
        copy_pin(source, inputs / source.relative_to(FROZEN), pins, accepted[str(source)])
    for name in OWN:
        copy_pin(HERE / name, inputs / name, pins)
    filelist = inputs / 'sources.f'
    filelist.write_text('+incdir+' + str(inputs / headers.relative_to(FROZEN)) + '\n' +
        '\n'.join(str(inputs / rel) for rel in sources) + '\n' + str(inputs / 'vmfpu_fp_tb.sv') + '\n')
    pins[str(filelist)] = sha(filelist)
    vcs = shutil.which('vcs')
    pins[str(Path(vcs).resolve())] = sha(vcs)
    save(out / 'config.json', dict(vcs=vcs, branch=branch, overlay=list(OVERLAY),
        dependency_admission=ADMISSION, compile_seconds=600, run_seconds=120,
        scope='One real full-FP VMFPU lane; standard/shared integer multipliers; SharedFma=0; '
              'directed FP32/flags/VRF drain, FP16 resident PV, ordered SLDU loopback, QBS ownership. '
              'Not a four-lane reduction numerical/SoC/performance acceptance.'))
    pins[str(out / 'config.json')] = sha(out / 'config.json')
    verify(pins)
    save(out / 'source-pins.json', pins)
    save(out / 'prepared.json', dict(state='PREPARED_NOT_EXECUTED', sources=len(sources)))
    print(inputs / 'run_vmfpu_fp.py')


def check(text):
    if ERROR.search(text):
        raise ValueError('Simulator error/fatal')
    rows = re.findall(r'^STAGE2_VMFPU_FP_PASS (.*)$', text, re.M)
    if len(rows) != 1:
        raise ValueError('Missing/duplicate full-FP terminal')
    pairs = re.findall(r'(\w+)=(\d+)', rows[0])
    if tuple(k for k, _ in pairs) != FIELDS or ' '.join(k+'='+v for k, v in pairs) != rows[0]:
        raise ValueError('Malformed full-FP accounting')
    row = {k: int(v) for k, v in pairs}
    expected = dict(native=5, writes=5, flags=5, nv=1, pv_acquires=2, pv_releases=2,
                    pv_returns=2, borrowed=24, returned=24, red_tokens=1, red_completes=1)
    if any(row[k] != v for k, v in expected.items()) or row['grant_stalls'] < 40 or (
            row['native_held'] < 3 or row['pv_held'] < 8):
        raise ValueError('Incomplete full-FP accounting/held-valid coverage')
    return row


def execute(out):
    if Path(__file__).resolve() != out / 'inputs/run_vmfpu_fp.py':
        raise ValueError('Execute frozen runner only')
    config = json.loads((out / 'config.json').read_text())
    pins = json.loads((out / 'source-pins.json').read_text())
    report = dict(state='FAIL', scope=config['scope'], configurations=[])
    try:
        verify(pins)
        cgroup = Path('/proc/self/cgroup').read_text()
        if '.service' not in cgroup:
            raise ValueError('Direct systemd service ownership required')
        save(out / 'owner.json', dict(pid=os.getpid(), cgroup=cgroup, runner=str(Path(__file__).resolve())))
        for shared in (0, 1):
            work = out / f'shared{shared}'
            work.mkdir(exist_ok=False)
            argv = [config['vcs'], '-full64', '-sverilog', '-timescale=1ns/1ps', '-j4',
                    '+define+SIMULATION', '-top', 'stage2_vmfpu_fp_tb', '-o', 'simv',
                    '-f', str(out / 'inputs/sources.f')]
            if shared:
                argv.append('+define+ARA_SHARED_SIMD_MUL')
            run = [str(work / 'simv'), '-no_save']
            save(work / 'commands.json', dict(compile=argv, run=run))
            for label, command, limit in (('compile', argv, config['compile_seconds']),
                                           ('run', run, config['run_seconds'])):
                print(f'STAGE2_VMFPU_FP_{label.upper()} shared={shared}', flush=True)
                with (work / f'{label}.log').open('x') as stream:
                    subprocess.run(['timeout', '--signal=TERM', '--kill-after=10s', str(limit), *command],
                        cwd=work, stdout=stream, stderr=subprocess.STDOUT, check=True)
                verify(pins)
                if ERROR.search((work / f'{label}.log').read_text(errors='replace')):
                    raise ValueError('Tool error: ' + label)
                if label == 'compile':
                    images = {str(p): sha(p) for p in (work / 'simv.daidir').rglob('*') if p.is_file()}
                    images[str(work / 'simv')] = sha(work / 'simv')
                    save(work / 'image-pins.json', images)
            verify(images)
            report['configurations'].append(dict(shared=shared, **check((work / 'run.log').read_text())))
        verify(pins)
        report.update(state='PASS', source_pins_match=True, image_pins_match=True)
    except Exception as exc:
        report['error'] = str(exc)
    save(out / 'report.json', report)
    print('STAGE2_VMFPU_FP_' + report['state'], flush=True)
    return int(report['state'] != 'PASS')


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('output', type=Path)
    parser.add_argument('--execute', action='store_true')
    args = parser.parse_args()
    if args.execute:
        return execute(args.output.resolve())
    prepare(args.output.resolve())
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
