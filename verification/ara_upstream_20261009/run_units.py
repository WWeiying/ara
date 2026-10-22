#!/usr/bin/env python3
"""Bounded host VCS units; every invocation requires a fresh output directory."""
import argparse
import hashlib
import json
import os
from pathlib import Path
import re
import subprocess
import tarfile
import time

ROOT = Path(__file__).resolve().parents[2]
HERE = Path(__file__).resolve().parent
ARCHIVE = Path('/tmp/ara-signoff-upstream-before-20261009.tgz')
RTL = ['hardware/src/lane/simd_mul.sv', 'hardware/src/vlsu/vldu.sv',
       'hardware/src/ara.sv']
PACKAGES = ['hardware/deps/common_cells/src/cf_math_pkg.sv',
            'hardware/deps/cva6/core/include/config_pkg.sv',
            'hardware/deps/cva6/core/include/cv64a6_imafdcv_sv39_config_pkg.sv',
            'hardware/deps/cva6/core/include/riscv_pkg.sv',
            'hardware/include/rvv_pkg.sv', 'hardware/deps/axi/src/axi_pkg.sv',
            'hardware/deps/fpnew/src/fpnew_pkg.sv', 'hardware/include/ara_pkg.sv']


def sha(data):
    return hashlib.sha256(data).hexdigest()


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--output', type=Path, required=True)
    p.add_argument('--suite', choices=['vldu', 'mul', 'guard'], required=True)
    p.add_argument('--baseline', action='store_true')
    p.add_argument('--baseline-archive', type=Path,
                   help='original-source archive; default is the dated /tmp backup when available')
    p.add_argument('--reference-simd-mul', type=Path,
                   help='explicit original simd_mul.sv for candidate-only equivalence without archive')
    p.add_argument('--focused', action='store_true')
    p.add_argument('--split-focused', action='store_true')
    p.add_argument('--small-only', action='store_true')
    p.add_argument('--vlen', type=int, default=256)
    p.add_argument('--lanes', type=int, default=4)
    a = p.parse_args()
    if sum((a.focused, a.split_focused, a.small_only)) > 1:
        p.error('VLDU test selectors are mutually exclusive')
    if (a.focused or a.split_focused or a.small_only) and a.suite != 'vldu':
        p.error('VLDU test selectors require --suite vldu')
    archive = a.baseline_archive.resolve() if a.baseline_archive else ARCHIVE
    out = a.output.resolve()
    out.mkdir(parents=True, exist_ok=False)
    env = os.environ.copy()
    vcs = '/home/wangwy/software/synopsys/install/vcs/V-2023.12-SP1'
    verdi = '/home/wangwy/software/synopsys/install/verdi/V-2023.12-SP1'
    env.update(VCS_HOME=vcs, VERDI_HOME=verdi, SNPSLMD_LICENSE_FILE='27000@t7920',
               PATH=f'{vcs}/bin:{verdi}/bin:/usr/local/bin:/usr/bin:/bin',
               LD_LIBRARY_PATH=f'/usr/lib:{verdi}/share/PLI/VCS/linux64')
    status = {'state': 'STARTED', 'pid': os.getpid(), 'start': time.time(),
              'suite': a.suite, 'baseline': a.baseline,
              'archive_requested': str(archive), 'baseline_fingerprints': {}}
    pins = {}

    def copy_source(path, data=None, name=None):
        if data is None:
            data = (ROOT / path).read_bytes()
        target = out / (name or path)
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(data)
        pins[str(target.relative_to(out))] = {'source': path, 'sha256': sha(data)}
        return str(target)

    try:
        originals = {}
        if archive.is_file():
            status.update(archive=str(archive), archive_sha256=sha(archive.read_bytes()))
            with tarfile.open(archive) as tf:
                for path in RTL:
                    originals[path] = tf.extractfile(path).read()
                    status['baseline_fingerprints'][path] = sha(originals[path])
                    copy_source(path, originals[path], 'before/' + path)
        elif a.baseline or a.baseline_archive:
            raise FileNotFoundError('Requested baseline archive: ' + str(archive))
        if a.reference_simd_mul:
            if a.baseline or a.suite != 'mul':
                raise ValueError('--reference-simd-mul requires candidate --suite mul')
            originals[RTL[0]] = a.reference_simd_mul.read_bytes()
            status['reference_simd_mul'] = str(a.reference_simd_mul.resolve())
            status['baseline_fingerprints'][RTL[0]] = sha(originals[RTL[0]])
        if a.suite == 'mul' and RTL[0] not in originals:
            raise ValueError('Equivalence requires --baseline-archive or --reference-simd-mul; no self-reference')
        for path in RTL:
            copy_source(path, originals[path] if a.baseline else None)
        sources = [copy_source(path) for path in PACKAGES]
        includes = []
        for directory in ['hardware/include/ara', 'hardware/deps/common_cells/include/common_cells']:
            for path in sorted((ROOT / directory).glob('*.svh')):
                copy_source(str(path.relative_to(ROOT)))
        includes = [f'+incdir+{out}/hardware/include',
                    f'+incdir+{out}/hardware/deps/common_cells/include']
        if a.suite == 'vldu':
            top = 'vldu_burst_tb'
            sources += [copy_source('hardware/deps/common_cells/src/spill_register_flushable.sv'),
                        str(out / RTL[1]),
                        copy_source(str((HERE / 'vldu_burst_tb.sv').relative_to(ROOT)))]
        elif a.suite == 'mul':
            top = 'simd_mul_equivalence_tb'
            reference = originals[RTL[0]].decode().replace('module simd_mul ', 'module simd_mul_reference ')
            reference = reference.replace('endmodule : simd_mul', 'endmodule : simd_mul_reference')
            sources += [copy_source(RTL[0], reference.encode(), 'simd_mul_reference.sv'),
                        str(out / RTL[0]),
                        copy_source('verification/timing/simd_mul_equivalence_tb.sv'),
                        copy_source(str((HERE / 'simd_mul_default_monitor.sv').relative_to(ROOT)))]
        else:
            top = 'ara_guard_tb'
            status['scope'] = 'Extracted actual ara.sv assertions only; NOT full Ara elaboration'
            # Compile the actual unchanged assertion statements, not a reimplementation.
            source = (out / RTL[2]).read_text()
            assertions = source[source.index('  if (NrLanes == 0)'):source.index('endmodule : ara')]
            wrapper = (f'module {top} import ara_pkg::*; ();\n'
                       f'localparam int NrLanes={a.lanes}, VLEN={a.vlen};\n' + assertions +
                       '\ninitial begin #1; $display("GUARD_ACCEPT lanes=%0d vlen=%0d stride=%0d", '
                       'NrLanes, VLEN, vaddr(1,NrLanes,VLEN)); $finish; end\nendmodule\n')
            sources += [copy_source(RTL[2], wrapper.encode(), 'ara_guard_tb.sv')]
        copy_source(str(Path(__file__).resolve().relative_to(ROOT)))
        (out / 'pins.json').write_text(json.dumps(pins, indent=2) + '\n')
        command = ['vcs', '-full64', '-sverilog', '-assert', 'svaext',
                   '-timescale=1ns/1ps', '-debug_access+all', '-top', top,
                   *includes, *sources, '-o', str(out / 'simv'), '-l', str(out / 'compile.log')]
        if a.small_only:
            command += ['-pvalue+vldu_burst_tb.VLEN=1024']
        (out / 'command.json').write_text(json.dumps(command, indent=2) + '\n')
        with (out / 'compile.console.log').open('w') as log:
            result = subprocess.run(command, cwd=out, env=env, stdout=log, stderr=subprocess.STDOUT, timeout=180)
        status['compile_exit'] = result.returncode
        if result.returncode:
            status['state'] = 'COMPILE_FAILED'
        else:
            status['image_sha256'] = sha((out / 'simv').read_bytes())
            status['runtime_objects'] = {str(path.relative_to(out)): sha(path.read_bytes())
                                         for path in sorted((out / 'simv.daidir').rglob('*.so'))}
            run = [str(out / 'simv'), '-l', str(out / 'run.log')]
            if a.focused:
                run += ['+FOCUSED']
            if a.split_focused:
                run += ['+SPLIT_FOCUSED']
            if a.small_only:
                run += ['+SMALL_ONLY']
            if a.baseline and a.suite == 'mul':
                run += ['+OBSERVE_OLD_R']
            (out / 'run_command.json').write_text(json.dumps(run, indent=2) + '\n')
            with (out / 'run.console.log').open('w') as log:
                result = subprocess.run(run, cwd=out, env=env, stdout=log, stderr=subprocess.STDOUT, timeout=120)
            status['run_exit'] = result.returncode
            text = (out / 'run.console.log').read_text()
            marker = {'vldu': 'VLDU_SUITE_PASS', 'mul': 'SIMD MUL equivalence PASS configurations=24',
                      'guard': 'GUARD_ACCEPT'}[a.suite]
            diagnostics = re.search(r'(?m)^(?:Error|Fatal)(?:-|:|\[)', text)
            status['state'] = 'PASS' if result.returncode == 0 and marker in text and not diagnostics else 'FAIL'
            if sha((out / 'simv').read_bytes()) != status['image_sha256']:
                raise RuntimeError('Image changed during execution')
            for name, digest in status['runtime_objects'].items():
                if sha((out / name).read_bytes()) != digest:
                    raise RuntimeError('Runtime shared object changed: ' + name)
        for path in out.rglob('*'):
            if path.is_file() and str(path.relative_to(out)) in pins:
                if sha(path.read_bytes()) != pins[str(path.relative_to(out))]['sha256']:
                    raise RuntimeError('Input snapshot drift: ' + str(path))
    except Exception as exc:
        status.update(state='ERROR', error=repr(exc))
    finally:
        status['finish'] = time.time()
        (out / 'status.json').write_text(json.dumps(status, indent=2) + '\n')
        print(json.dumps(status, indent=2))
    return 0 if status['state'] == 'PASS' else 1


if __name__ == '__main__':
    raise SystemExit(main())
