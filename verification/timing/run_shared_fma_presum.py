#!/usr/bin/env python3
"""Bounded VCS cycle miter against the exact attempt_03 FMA (no synthesis).

Reuses the existing random/edge scoreboard without modifying it. Five concurrent
instances check 3/4/5/6-stage compact and 5-stage noncompact pipelines, including
all externally observable handshake cycles. Both old wrapper AND old arithmetic
are frozen independently; the old side cannot accidentally pick up the new hook.
"""
import argparse
import hashlib
import json
from pathlib import Path
import re
import shutil
import subprocess

ROOT = Path(__file__).resolve().parents[2]
SNAPSHOT = Path('/home/wangwy/dc_runs/ara_main_870cadb9_all_on_20261111_01/'
                'attempt_03/sources/home/wangwy/openproject/ara_dsa_dc_20261110')
FMA = 'hardware/deps/fpnew/src/fpnew_fma_multi.sv'
WRAPPER = 'hardware/src/lane/simd_fma_shared.sv'
TB = 'verification/timing/shared_fma_tb.sv'
SOURCES = [
    'hardware/deps/common_cells/src/cf_math_pkg.sv',
    'hardware/deps/common_cells/src/lzc.sv',
    'hardware/deps/common_cells/src/stream_register.sv',
    'hardware/deps/fpnew/src/fpnew_pkg.sv',
    'hardware/deps/fpnew/src/fpnew_classifier.sv',
    'hardware/deps/fpnew/src/fpnew_rounding.sv',
    'hardware/deps/fpnew/src/fpnew_fma.sv', FMA, WRAPPER,
]


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def replace_once(text, old, new):
    if text.count(old) != 1:
        raise ValueError('Unexpected source boundary: ' + old)
    return text.replace(old, new)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('output', type=Path)
    parser.add_argument('--snapshot', type=Path, default=SNAPSHOT)
    parser.add_argument('--vcs', default='/home/wangwy/software/synopsys/install/'
                        'vcs/V-2023.12-SP1/bin/vcs')
    args = parser.parse_args()
    out = args.output.resolve()
    out.mkdir(parents=True, exist_ok=False)
    src = out / 'src'
    src.mkdir()
    pins = {}
    for rel in SOURCES:
        current, old = ROOT / rel, args.snapshot / rel
        if rel not in (FMA, WRAPPER) and sha(current) != sha(old):
            raise ValueError('Unreviewed reference dependency drift: ' + rel)
        shutil.copy2(current, src / current.name)
        pins[str(current)] = sha(current)
        pins[str(old)] = sha(old)
    expected = {FMA: '73fee010682853487671fdbafda6b36553ca99fda91802bded7233ec9e51000d',
                WRAPPER: '8ce53feaa587563d260fce01570966be0a5ec60f0625883da141141de3410a31'}
    for rel, digest in expected.items():
        if sha(args.snapshot / rel) != digest:
            raise ValueError('Not the reviewed attempt_03 reference: ' + rel)
    old_fma = replace_once((args.snapshot / FMA).read_text(),
                           'module fpnew_fma_multi', 'module fpnew_fma_multi_prior')
    old_wrapper = replace_once((args.snapshot / WRAPPER).read_text(),
                               'module simd_fma_shared', 'module simd_fma_prior')
    old_wrapper = replace_once(old_wrapper, 'fpnew_fma_multi #(',
                               'fpnew_fma_multi_prior #(')
    (src / 'fpnew_fma_multi_prior.sv').write_text(old_fma)
    (src / 'simd_fma_prior.sv').write_text(old_wrapper)
    tb = replace_once((ROOT / TB).read_text(), 'module shared_fma_tb;',
                     'module shared_fma_tb #(parameter int Stages=5, '
                     'parameter bit Compact=1)(output logic done=0);')
    for module in ('simd_fma_shared', 'simd_fma_prior'):
        tb = replace_once(tb, module + ' #(.TagType(logic [31:0]))',
                          module + ' #(.NumPipeRegs(Stages), .CompactPipeline(Compact), '
                          '.TagType(logic [31:0]))')
    tb = replace_once(tb, '    $finish;', '    done=1;')
    (src / 'shared_fma_tb.sv').write_text(tb)
    (src / 'presum_matrix_tb.sv').write_text('''module presum_matrix_tb;
  wire [4:0] done;
  shared_fma_tb #(.Stages(3)) s3(done[0]);
  shared_fma_tb #(.Stages(4)) s4(done[1]);
  shared_fma_tb #(.Stages(5)) s5(done[2]);
  shared_fma_tb #(.Stages(6)) s6(done[3]);
  shared_fma_tb #(.Stages(5), .Compact(0)) legacy(done[4]);
  initial begin
    wait (&done);
    $display("PRESUM_MATRIX_PASS configs=5");
    $finish;
  end
endmodule
''')
    shutil.copytree(ROOT / 'hardware/deps/common_cells/include', out / 'include')
    shutil.copy2(__file__, out / 'worker.py')
    for rel in (TB, 'verification/patches/fpnew-local-fixes.patch',
                'verification/patches/dependencies.json'):
        pins[str(ROOT / rel)] = sha(ROOT / rel)
    pins.update({str(p): sha(p) for p in out.rglob('*') if p.is_file()})
    (out / 'source-pins.json').write_text(json.dumps(pins, indent=2) + '\n')
    command = [args.vcs, '-full64', '-sverilog', '-timescale=1ns/1ps',
               '+define+SHARED_FMA_CYCLE_MITER', '+incdir+include',
               '-top', 'presum_matrix_tb', '-o', 'simv',
               *['src/' + Path(p).name for p in SOURCES],
               'src/fpnew_fma_multi_prior.sv', 'src/simd_fma_prior.sv',
               'src/shared_fma_tb.sv', 'src/presum_matrix_tb.sv']
    (out / 'command.json').write_text(json.dumps(command, indent=2) + '\n')
    report = {'state': 'FAIL', 'scope': 'Component cycle equivalence; not STA or SoC signoff'}
    try:
        for cmd, log in ((command, 'compile.log'), (['./simv', '-no_save'], 'run.log')):
            with (out / log).open('w') as stream:
                subprocess.run(cmd, cwd=out, stdout=stream, stderr=subprocess.STDOUT,
                               timeout=600, check=True)
        text = (out / 'run.log').read_text()
        checks = re.findall(r'^SHARED_FMA_CYCLE_CHECKS (\d+)$', text, re.M)
        if ('PRESUM_MATRIX_PASS configs=5' not in text or len(checks) != 5
                or min(map(int, checks)) < 15000
                or text.count('SHARED_FMA_PASS accepted=') != 5):
            raise ValueError('Incomplete matrix')
        for path, digest in pins.items():
            if sha(Path(path)) != digest:
                raise ValueError('Input changed: ' + path)
        report.update(state='PASS', cycle_checks=list(map(int, checks)),
                      configurations=['compact3', 'compact4', 'compact5', 'compact6', 'noncompact5'])
    except Exception as exc:
        report['error'] = str(exc)
        raise
    finally:
        (out / 'report.json').write_text(json.dumps(report, indent=2) + '\n')
        print(json.dumps(report), flush=True)


if __name__ == '__main__':
    main()
