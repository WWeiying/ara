#!/usr/bin/env python3
"""Preserve the first fixture and require a sampled stalled AR before injection."""
import argparse
import json
import os
from pathlib import Path
import shutil

from audit import digest, require
from build_trace_context_library import Build, write
from run_mixed_reader import HERE, ROOT, VERIFY, legacy_check, mixed_check


BEFORE = 'MIXED_READER_AR_BEFORE_ERROR size=5 stalled='
AFTER = 'MIXED_READER_AR_SAMPLED size=5 stalled=1'


def fixture(text):
    old = 'module qbs_mixed_reader_tb;'
    anchor = '      inject_error = 1;\n      hold_responses = 0;'
    require(text.count(old) == text.count(anchor) == 1, 'Unexpected original mixed-reader fixture')
    witness = '''      if (stalled_fault) begin
        $display("MIXED_READER_AR_BEFORE_ERROR size=%0d stalled=%0b", ar.size, dut.ar_stalled_q);
        @(posedge clk);
        if (!av || ardy || ar.size != 5) $fatal(1, "AR not sampled as stalled before error");
        @(negedge clk);
        if (!dut.ar_stalled_q) $fatal(1, "Missing registered stalled AR witness");
        $display("MIXED_READER_AR_SAMPLED size=%0d stalled=%0b", ar.size, dut.ar_stalled_q);
      end
'''
    return text.replace(old, 'module qbs_mixed_reader_checked_tb;', 1).replace(anchor, witness+anchor, 1)


def check(text):
    result = mixed_check(text)
    lines = [line for line in text.splitlines() if line.startswith(BEFORE)]
    require(len(lines) == 1 and lines[0] in (BEFORE+'0', BEFORE+'1') and
            text.splitlines().count(AFTER) == 1, 'Missing unique pre-fault AR edge witness')
    result.update(held_ar_sampled_before_fault=True, ar_stalled_before_extra_edge=int(lines[0][-1]))
    return result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    out = args.output.absolute()
    require(out == out.resolve() and out.is_relative_to(VERIFY/'verification/out'), 'Fresh verification output')
    out.mkdir(parents=True, exist_ok=False)
    b = Build(out)
    # VCS licensing/environment is inherited selectively, never a compiler or
    # include search path from an unrelated cross toolchain.
    for name in ('VCS_HOME','SNPSLMD_LICENSE_FILE','LM_LICENSE_FILE','LD_LIBRARY_PATH'):
        if name in os.environ:
            b.environment[name] = os.environ[name]
    vcs = shutil.which('vcs')
    require(vcs, 'Host VCS unavailable')
    b.environment.update(PATH=str(Path(vcs).parent)+':/usr/bin:/bin', CC='/usr/bin/gcc', CXX='/usr/bin/g++')
    report = dict(state='PREPARING', soc_integrated=False, per_range_default_enabled=False,
                  performance_measured=False, area_measured=False, real_mmu_pmp_tested=False,
                  original_failure_preserved=True, rtl_changed_after_first_simulation=False)
    try:
        sources = [ROOT/'hardware/deps/axi/src/axi_pkg.sv', ROOT/'hardware/include/qbs_pkg.sv',
                   ROOT/'hardware/src/vlsu/qbs/qbs_read_engine.sv']
        first = VERIFY/'verification/out/e2e_mixed_reader_20261106_01'
        prior = json.loads((first/'result.json').read_text())
        require(prior['state'] == 'FAIL' and prior['error'] == "ValueError('RTL reader test failed')", 'Wrong preserved first failure')
        b.pin(first/'result.json')
        b.pin(first/'source-pins.json')
        old = json.loads((first/'source-pins.json').read_text())
        for path, expected in old.items():
            b.pin(path, expected)
        for path, expected in prior['artifacts'].items():
            b.pin(path, expected)
        for path in (Path(__file__), HERE/'test_mixed_reader_checked.py', HERE/'run_mixed_reader.py',
                     HERE/'audit.py', HERE/'build_trace_context_library.py'):
            b.pin(path)
        original = HERE/'qbs_mixed_reader_tb.sv'
        generated = out/'qbs_mixed_reader_checked_tb.sv'
        generated.write_text(fixture(original.read_text()))
        b.pin(generated)
        report['original_failed_worker'] = str(first)
        report['original_rtl_sha256'] = old[str(sources[-1])]
        images = []
        for name, bench, top in (('legacy', ROOT/'verification/qbs/qbs_read_engine_tb.sv','qbs_read_engine_tb'),
                                 ('mixed', generated,'qbs_mixed_reader_checked_tb')):
            build = out/name
            build.mkdir()
            image = build/'simv'
            b.run([vcs, '-full64','-sverilog','-timescale=1ns/1ps','-assert','svaext','+lint=TFIPC-L',
                   '+incdir+'+str(ROOT/'hardware/deps/axi/include'), *sources, bench,
                   '-top', top, '-Mdir='+str(build/'csrc'), '-o', image], 'compile-'+name, bound=180)
            b.pin(image)
            for path in (build/'simv.daidir').rglob('*.so'):
                b.pin(path)
            images.append(image)
        old_results = []
        for mode in (False, True):
            args = [images[0],'-no_save']+(['+COMBINATIONAL_MMU'] if mode else [])
            old_results.append(legacy_check(b.run(args, 'legacy-'+str(int(mode)), bound=120), mode))
        measured = check(b.run([images[1],'-no_save'], 'mixed', bound=120))
        b.verify()
        report.update(state='LEGACY128_AND_MIXED256_READER_COMPONENT_PASS', legacy=old_results, mixed=measured,
            limitations=['Only a pre-fault stimulus edge was added; original failed worker remains FAIL',
                         'Synthetic AXI target and permission input, not real CVA6 PMP or full SoC acceptance',
                         'Existing production shared-reader selection remains full bus width'])
    except BaseException as exc:
        report.update(state='FAIL', error=repr(exc))
        raise
    finally:
        write(out/'source-pins.json', b.pins)
        write(out/'path-identities.json', b.identities)
        write(out/'commands.json', b.commands)
        report['source_pins_sha256'] = digest(out/'source-pins.json')
        report['artifacts'] = {str(p):digest(p) for p in out.iterdir() if p.is_file() and p.name!='result.json'}
        write(out/'result.json', report)


if __name__ == '__main__':
    main()
