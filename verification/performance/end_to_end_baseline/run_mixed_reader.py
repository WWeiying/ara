#!/usr/bin/env python3
"""Regress legacy128 and prototype mixed-size256 QBS readers, host VCS only."""
import argparse
import json
import os
from pathlib import Path
import re
import shutil
import signal
import subprocess

from audit import digest, require, verify_pins

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[2]
VERIFY = Path('/home/wangwy/openproject/ara_dsa_signoff_integration')


def clean(text):
    require(not re.search(r'Fatal:|Error:|Assertion failed', text), 'RTL reader test failed')


def legacy_check(text, combinational):
    clean(text)
    require(text.splitlines().count('QBS read engine PASS') == 1, 'Legacy terminal missing/duplicated')
    cases = re.findall(r'^\[QBS_READ_CASE\] (\S+) PASS$', text, re.M)
    require(cases == ['nonidentity_unaligned', 'noncontiguous_pages', 'second_page_fault', 'post_fault_reuse'],
            'Legacy MMU/page/reuse contracts incomplete')
    faults = re.findall(r'^QBS stalled-AR fault PASS mode=(\d+) delay=(\d+)$', text, re.M)
    require(faults == [(str(m), str(d)) for m in range(3) for d in (0, 6)], 'Stalled-AR fault suite incomplete')
    replies = re.findall(r'^QBS_MMU_RESPONSE .*combinational=(\d+) req=(\d+)', text, re.M)
    require(replies and all(r == (str(int(combinational)), '1') for r in replies), 'Wrong MMU response mode')
    return dict(terminal_pass=True, mapped_page_contracts=cases, stalled_ar_faults=6,
                combinational_mmu=combinational, mmu_replies=len(replies))


def mixed_check(text):
    clean(text)
    sizes = re.findall(r'^MIXED_READER_SIZE_PASS size=(\d+) cases=(\d+)$', text, re.M)
    require(sizes == [(str(s), str((s+1)*32)) for s in range(6)], 'Mixed-size/phase coverage incomplete')
    terminal = re.findall(r'^MIXED_READER_COMPONENT_PASS cases=(\d+) faults=(\d+) footprint_checks=(\d+)$', text, re.M)
    require(len(terminal) == 1 and terminal[0][:2] == ('258', '4') and int(terminal[0][2]) > 258,
            'Missing mixed-reader cases or checked physical footprints')
    return dict(cases=258, fault_cases=4, footprint_checks=int(terminal[0][2]),
                physical_bus_bits=256, range_transfer_bytes=[1, 2, 4, 8, 16, 32],
                base_phases=32, legacy_and_wide_inflight=True, independent_payload_geometry=True)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    out = args.output.absolute()
    require(out == out.resolve() and out.is_relative_to(VERIFY/'verification/out'), 'Fresh sole verification output')
    out.mkdir(parents=True, exist_ok=False)
    pins, commands = {}, []
    report = dict(state='PREPARING', pid=os.getpid(), child_pid=None, soc_integrated=False,
                  per_range_default_enabled=False, new_isa=False, performance_measured=False,
                  real_mmu_pmp_tested=False, area_measured=False)
    env = dict(os.environ)
    env.update(PATH=str(Path(shutil.which('vcs') or '/no/vcs').parent)+':/usr/bin:/bin', CC='/usr/bin/gcc', CXX='/usr/bin/g++')

    def save():
        (out/'status.json').write_text(json.dumps(report, indent=2)+'\n')

    def pin(path):
        path = str(Path(path).resolve(strict=True))
        value = digest(path)
        require(path not in pins or pins[path] == value, 'Input drift')
        pins[path] = value

    def run(argv, label, bound):
        argv = list(map(str, argv))
        pin(argv[0])
        verify_pins(pins)
        command = dict(label=label, argv=argv, timeout=bound)
        commands.append(command)
        (out/'commands.json').write_text(json.dumps(commands, indent=2)+'\n')
        report['state'] = label.upper()
        with (out/(label+'.log')).open('xb') as stream:
            child = subprocess.Popen(argv, cwd=out, env=env, stdout=stream, stderr=subprocess.STDOUT, start_new_session=True)
            report['child_pid'] = child.pid
            save()
            try:
                code = child.wait(timeout=bound)
            except BaseException:
                os.killpg(child.pid, signal.SIGKILL)
                child.wait()
                raise
            finally:
                report['child_pid'] = None
                save()
        command['returncode'] = code
        (out/'commands.json').write_text(json.dumps(commands, indent=2)+'\n')
        require(code == 0, label+' process failed')
        verify_pins(pins)
        return (out/(label+'.log')).read_text()

    try:
        sources = [ROOT/'hardware/deps/axi/src/axi_pkg.sv', ROOT/'hardware/include/qbs_pkg.sv',
                   ROOT/'hardware/src/vlsu/qbs/qbs_read_engine.sv']
        benches = [ROOT/'verification/qbs/qbs_read_engine_tb.sv', HERE/'qbs_mixed_reader_tb.sv']
        for path in [Path(__file__), HERE/'test_mixed_reader.py', HERE/'audit.py',
                     ROOT/'hardware/src/vlsu/qbs_akv_shared_reader.sv', *sources, *benches]:
            pin(path)
        for path in (ROOT/'hardware/deps/axi/include').rglob('*.svh'):
            pin(path)
        vcs = shutil.which('vcs', path=env['PATH'])
        require(vcs, 'Host VCS unavailable')
        images = []
        for name, bench in zip(('legacy', 'mixed'), benches):
            build = out/name
            build.mkdir()
            image = build/'simv'
            run([vcs, '-full64', '-sverilog', '-timescale=1ns/1ps', '-assert', 'svaext',
                 '+lint=TFIPC-L', '+incdir+'+str(ROOT/'hardware/deps/axi/include'), *sources, bench,
                 '-top', 'qbs_read_engine_tb' if name == 'legacy' else 'qbs_mixed_reader_tb',
                 '-Mdir='+str(build/'csrc'), '-o', image], 'compile-'+name, 180)
            pin(image)
            for path in (build/'simv.daidir').rglob('*.so'):
                pin(path)
            images.append(image)
        (out/'source-pins.json').write_text(json.dumps(pins, indent=2)+'\n')
        old = []
        for mode in (False, True):
            argv = [images[0], '-no_save'] + (['+COMBINATIONAL_MMU'] if mode else [])
            old.append(legacy_check(run(argv, 'legacy-'+str(int(mode)), 120), mode))
        measured = mixed_check(run([images[1], '-no_save'], 'mixed', 120))
        verify_pins(pins)
        report.update(state='LEGACY128_AND_MIXED256_READER_COMPONENT_PASS', legacy=old, mixed=measured,
            source_pins_sha256=digest(out/'source-pins.json'),
            limitations=['Mixed256 uses a synthetic AXI target and physical-range permission input',
                         'Real CVA6 MMU/PMP and SoC storage width are not validated by this component bench',
                         'Legacy128 exercises mapped-page/fault contracts, not a Linux boot',
                         'Existing production shared reader still selects full bus-width transfers'])
    except BaseException as exc:
        report.update(state='FAIL', error=repr(exc))
        raise
    finally:
        save()
        report['artifacts'] = {str(p): digest(p) for p in out.iterdir() if p.is_file() and p.name not in ('result.json','status.json')}
        (out/'result.json').write_text(json.dumps(report, indent=2)+'\n')


if __name__ == '__main__':
    main()
