#!/usr/bin/env python3
"""One bounded mixed-scale experiment: host IEEE oracle and original FPnew RTL."""
import argparse
import json
import os
from pathlib import Path
import re
import shutil
import signal
import subprocess
import sys

from audit import digest, require, verify_pins
from run_supply_sdk import bind
from prepare_wide_soc import HERE, ROOT, RUNS
from build_trace_context_library import dependencies

FROZEN = RUNS/'e2e_physical_wide_soc_inputs_20261106_01'
DEP_SOURCES = ('common_cells/src/cf_math_pkg.sv', 'fpnew/src/fpnew_pkg.sv',
               'common_cells/src/lzc.sv', 'fpnew/src/lfsr_sr.sv',
               'fpnew/src/fpnew_classifier.sv', 'fpnew/src/fpnew_rounding.sv', 'fpnew/src/fpnew_fma.sv')
RTL = ROOT/'hardware/src/vlsu/qbs/experimental/qbs_mixed_scale.sv'


def run(output):
    out = output.absolute()
    require(out == out.resolve() and out.is_relative_to(RUNS), 'Fresh sole-verification output required')
    out.mkdir(parents=True, exist_ok=False); (out/'src').mkdir()
    pins = {}; commands = []
    result = dict(state='PREPARING', child_pid=None, component_only=True, production_rtl_changed=False,
                  full_controller_integrated=False, performance_measured=False, synthesis_run=False)
    def pin(path, sha=None): bind(pins, path, sha)
    def save(): (out/'status.json').write_text(json.dumps(result, indent=2)+'\n')
    def command(argv, name, bound):
        argv = list(map(str, argv)); pin(argv[0]); verify_pins(pins)
        result['state'] = name; commands.append(dict(label=name, argv=argv, timeout_seconds=bound)); save()
        with (out/(name.lower()+'.log')).open('xb') as log:
            child = subprocess.Popen(argv, cwd=out, env=env, stdout=log, stderr=subprocess.STDOUT)
            result['child_pid'] = child.pid; save()
            try: code = child.wait(timeout=bound)
            except BaseException:
                child.kill(); child.wait(); raise
        result['child_pid'] = None; commands[-1]['returncode'] = code
        require(code == 0, name+' failed; retain original output'); verify_pins(pins)
        return (out/(name.lower()+'.log')).read_text()
    env = {k:v for k,v in os.environ.items() if k not in
           ('LD_PRELOAD','CPATH','C_INCLUDE_PATH','CPLUS_INCLUDE_PATH','GCC_EXEC_PREFIX','COMPILER_PATH','LIBRARY_PATH')}
    env.update(PATH='/usr/bin:/bin', LC_ALL='C', PYTHONDONTWRITEBYTECODE='1')
    try:
        for path in (Path(__file__), HERE/'mixed_scale_oracle.c', HERE/'qbs_mixed_scale_tb.sv', RTL, Path(sys.executable)):
            pin(path)
        inventory = json.loads((FROZEN/'source-pins.json').read_text()); pin(FROZEN/'source-pins.json')
        sources = []
        for rel in DEP_SOURCES:
            source = FROZEN/'source/hardware/deps'/rel
            require(str(source) in inventory, 'Reference source absent from accepted SoC snapshot')
            pin(source, inventory[str(source)])
            target = out/'src'/source.name; shutil.copyfile(source, target); pin(target, inventory[str(source)])
            sources.append(target)
        inc = FROZEN/'source/hardware/deps/common_cells/include'
        for source in inc.rglob('*'):
            if not source.is_file(): continue
            require(str(source) in inventory, 'Unpinned reference include')
            pin(source, inventory[str(source)]); target = out/'include'/source.relative_to(inc)
            target.parent.mkdir(parents=True, exist_ok=True); shutil.copyfile(source, target); pin(target)
        for source in (RTL, HERE/'qbs_mixed_scale_tb.sv'):
            target = out/'src'/source.name; shutil.copyfile(source, target); pin(target, digest(source)); sources.append(target)
        source = out/'src/mixed_scale_oracle.c'; shutil.copyfile(HERE/source.name, source); pin(source)
        cc = Path('/usr/bin/gcc')
        flags = ['-std=c11','-O2','-fno-fast-math','-ffp-contract=off','-frounding-math','-Wall','-Wextra','-Werror']
        dep = command([cc, *flags, '-M', '-MT', 'object', source], 'HOST_DEPS', 30)
        for path in dependencies(dep, out): pin(path)
        command([cc, *flags, source, '-lm', '-o', out/'oracle'], 'HOST_BUILD', 60); pin(out/'oracle')
        text = command([out/'oracle', out/'vectors.txt'], 'HOST_ORACLE', 60); pin(out/'vectors.txt')
        marker = re.fullmatch(r'MIXED_SCALE_ORACLE_PASS total=(\d+) admitted=(\d+) rejected=(\d+) exact=(\d+) '
                              r'tie_even=(\d+) tie_odd=(\d+) carry=(\d+)\n', text)
        require(marker is not None, 'Independent host numerical oracle failed')
        host = dict(zip(('total','admitted','rejected','exact','tie_even','tie_odd','carry'), map(int, marker.groups())))
        require(host['total'] == 110025 and host['admitted']+host['rejected'] == host['total'] and
                min(host[k] for k in ('exact','tie_even','tie_odd','carry')) > 0, 'Host numerical classes incomplete')
        vcs = Path('/home/wangwy/software/synopsys/install/vcs/V-2023.12-SP1/bin/vcs')
        pin(vcs); pin(vcs.parent.parent/'linux64/bin/vcs1')
        argv = [vcs, '-full64', '-sverilog', '-timescale=1ns/1ps', '-top', 'qbs_mixed_scale_tb',
                '-Mdir='+str(out/'csrc'), '-o', out/'simv', '+incdir+'+str(out/'include'), *sources]
        (out/'source-pins.json').write_text(json.dumps(pins, indent=2)+'\n')
        command(argv, 'VCS_COMPILE', 600); pin(out/'simv')
        for lib in Path(str(out/'simv')+'.daidir').rglob('*.so'): pin(lib)
        text = command([out/'simv','-no_save','+VECTORS='+str(out/'vectors.txt')], 'SIMULATION', 300)
        require(not re.search(r'Fatal:|Error:|\bFAIL\b|\bError-\[', text), 'Simulator failure diagnostic')
        rows = re.findall(r'^MIXED_SCALE_RTL_PASS total=(\d+) admitted=(\d+) rejected=(\d+) checked=(\d+) '
            r'cancelled=(\d+) bubbles=(\d+) resets=(\d+) clears=(\d+) longest_ii1=(\d+) '
            r'latency=3 host_bits=1 fpnew_bits=1 flags=1$', text, re.M)
        require(len(rows) == 1, 'Unique complete RTL acceptance required')
        measured = dict(zip(('total','admitted','rejected','checked','cancelled','bubbles','resets','clears','longest_ii1'),
                            map(int, rows[0])))
        require(all(measured[k] == host[k] for k in ('total','admitted','rejected')) and
                measured['admitted'] == measured['checked']+measured['cancelled'] and
                measured['longest_ii1'] >= 16 and min(measured[k] for k in ('bubbles','resets','clears')) > 0,
                'Host/reference/DUT work and flush conservation differs')
        verify_pins(pins)
        result.update(state='MIXED_SCALE_HOST_AND_FPNEW_COMPONENT_PASS', host=host, measured=measured,
            post_pins_match=True, multiply_significand_widths=[24,11], latency=3, initiation_interval=1,
            rounding='RNE with NX; finite normal admitted domain only',
            fallback='Zero/subnormal/nonfinite/non-binary16 weights and boundary exponents retain original FPU',
            limits=['Not integrated into the QBS scheduler/controller; no new model or SoC performance result',
                    'Multiplier bit widths are not a cell-area measurement; no synthesis performed'])
    except BaseException as exc:
        result.update(state='FAIL', error=repr(exc)); raise
    finally:
        save(); (out/'commands.json').write_text(json.dumps(commands, indent=2)+'\n')
        (out/'source-pins.json').write_text(json.dumps(pins, indent=2)+'\n')
        result['source_pins_sha256'] = digest(out/'source-pins.json')
        result['artifacts'] = {str(p):digest(p) for p in out.iterdir() if p.is_file() and
            p.name not in ('result.json','status.json')}
        (out/'result.json').write_text(json.dumps(result, indent=2)+'\n')


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__); parser.add_argument('--output', type=Path, required=True)
    def stop(sig, _frame): raise InterruptedError('Signal '+str(sig))
    for sig in (signal.SIGINT, signal.SIGTERM): signal.signal(sig, stop)
    run(parser.parse_args().output)
