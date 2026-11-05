#!/usr/bin/env python3
"""Freeze and check the production VRF routing change against HEAD and a scoreboard."""
import argparse
import hashlib
import json
from pathlib import Path
import re
import shutil
import subprocess

ROOT = Path(__file__).resolve().parents[2]
HERE = Path(__file__).resolve().parent
PACKAGES = [
    'hardware/deps/common_cells/src/cf_math_pkg.sv',
    'hardware/deps/axi/src/axi_pkg.sv', 'hardware/deps/fpnew/src/fpnew_pkg.sv',
    'hardware/deps/cva6/core/include/config_pkg.sv',
    'hardware/deps/cva6/core/include/cv64a6_imafdcv_sv39_config_pkg.sv',
    'hardware/deps/cva6/core/include/riscv_pkg.sv',
    'hardware/include/rvv_pkg.sv', 'hardware/include/ara_pkg.sv',
]
CELLS = ['lzc', 'rr_arb_tree', 'spill_register_flushable', 'spill_register',
         'stream_demux', 'stream_xbar']
VRF = 'hardware/src/lane/vector_regfile.sv'


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def save(path, data):
    temp = path.with_suffix('.tmp')
    temp.write_text(json.dumps(data, indent=2) + '\n')
    temp.replace(path)


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('output', type=Path)
    a = p.parse_args()
    out = a.output.resolve(); out.mkdir(parents=True, exist_ok=False)
    src = out/'src'; src.mkdir()
    pins = {}
    paths = PACKAGES + [f'hardware/deps/common_cells/src/{n}.sv' for n in CELLS] + [
        'hardware/deps/tech_cells_generic/src/rtl/tc_sram.sv',
        'hardware/deps/tech_cells_generic/src/rtl/tc_clk.sv', VRF]
    for path in paths:
        shutil.copy2(ROOT/path, src/Path(path).name)
    shutil.copytree(ROOT/'hardware/deps/common_cells/include', out/'include')
    shutil.copy2(HERE/'vrf_return_tb.sv', src/'vrf_return_tb.sv')
    shutil.copy2(__file__, out/'worker.py')
    ref = subprocess.check_output(['git', '-C', str(ROOT), 'rev-parse', 'HEAD'], text=True).strip()
    old = subprocess.check_output(['git', '-C', str(ROOT), 'show', f'{ref}:{VRF}'], text=True)
    (out/'baseline.sv').write_text(old)
    (src/'reference.sv').write_text(re.sub(r'\bvector_regfile\b', 'vector_regfile_reference', old))
    for f in out.rglob('*'):
        if f.is_file(): pins[str(f)] = sha(f)
    save(out/'source-pins.json', pins)
    save(out/'manifest.json', dict(reference=ref, candidate_sha256=sha(src/'vector_regfile.sv'),
        comparison='Same valid each cycle; exact four-state data when valid; SRAM byte-write oracle',
        scope='Legal onehot return domain; no selected high-impedance SRAM data'))
    state = dict(state='BUILDING')
    save(out/'status.json', state)
    def run(cmd, log):
        with (out/log).open('w') as f:
            result = subprocess.run(cmd, cwd=out, stdout=f, stderr=subprocess.STDOUT, timeout=300)
        return result.returncode, (out/log).read_text(errors='replace')
    try:
        cmd = ['vcs', '-full64', '-sverilog', '-timescale=1ns/1ps', '-top', 'vrf_return_tb',
               '-o', 'simv', '+incdir+'+str(out/'include')]
        cmd += [str(src/Path(x).name) for x in paths]
        cmd += [str(src/'reference.sv'), str(src/'vrf_return_tb.sv')]
        save(out/'command.json', dict(command=cmd))
        rc, text = run(cmd, 'compile.log')
        if rc or re.search(r'(?m)^(Error-|Error:|Fatal:)', text):
            raise RuntimeError('VCS compile failed')
        rc, text = run(['./simv', '-no_save'], 'run.log')
        if rc or 'VRF_RETURN_PASS' not in text or 'Fatal:' in text or 'Error:' in text:
            raise RuntimeError('Positive test failed')
        cases = re.findall(r'VRF_RETURN_CASE_PASS banks=(\d+) cycles=(\d+) reads=(\d+) writes=(\d+) mappings=(\d+)', text)
        if len(cases) != 3: raise RuntimeError('Incomplete parameter coverage')
        for n in range(1, 5):
            rc, text = run(['./simv', '-no_save', f'+NEGATIVE={n}'], f'negative{n}.log')
            # Some VCS runtimes return zero after $fatal; require its exact
            # production diagnostic, and never accept the testbench watchdog.
            if ('Fatal:' not in text or 'VRF_NEGATIVE_NOT_REJECTED' in text or
                    'VRF_RETURN_PASS' in text or not re.search(
                        r'VRF_RETURN_(COLLISION_OR_UNKNOWN|INVALID_TARGET|UNKNOWN_VALID)', text)):
                raise RuntimeError(f'Negative test {n} not rejected by production assertion')
        for f, digest in pins.items():
            if sha(Path(f)) != digest: raise RuntimeError('Frozen input changed: '+f)
        state.update(state='PASS', configurations=cases, rejected_invalid_inputs=4)
    except Exception as exc:
        state.update(state='FAIL', error=str(exc))
    save(out/'status.json', state)
    print(json.dumps(state, indent=2))
    return int(state['state'] != 'PASS')


if __name__ == '__main__':
    raise SystemExit(main())
