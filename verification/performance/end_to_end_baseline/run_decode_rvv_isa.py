#!/usr/bin/env python3
"""Run the exact RVV performance ELF in golden Spike, with IO-only adapters.

No instruction semantics or target code is replaced. Results are functional
reference words and CSR records, never hardware performance measurements.
"""
import argparse
import json
import os
from pathlib import Path
import re
import shlex
import subprocess
import sys

from audit import digest, require, verify_pins
from prepare_wide_soc import HERE, ROOT, RUNS
from collect_decode_rvv_build import BASE, BUILD, ELF_SHA
from run_supply_sdk import bind
from check_decode_rvv import check

SPIKE_ROOT = Path('/home/wangwy/openproject/riscv-isa-sim-ara-dsa-vstart')
SPIKE = SPIKE_ROOT / 'build/spike'
SPIKE_SHA = 'c03c5a84f2313b2e0bb28be7aba496836b8d7b29e472c918457bca21f8abc7d2'
ACCEPTED = RUNS / 'e2e_decode_rvv_build_audit_20261106_01'
ACCEPTED_SHA = 'a5301ebbbfc665fea08563b28b5a8095e29909bc67457acbfdc313e215938124'


def libraries(text):
    require('not found' not in text, 'Unresolved host dynamic library')
    paths = re.findall(r'(?m)(?:=>\s+|^\s*)(/\S+)', text)
    require(len(paths) >= 2, 'No dynamic host library inventory')
    return sorted(set(str(Path(path).resolve(strict=True)) for path in paths))


def spike_command(plugin, elf):
    return [str(SPIKE), '--isa=rv64gcv_zfh_zicntr_zvfh_zvl1024b', '--priv=MSU', '--pmpregions=1',
            '-m0x80000000:0x1000000,0xbf000000:0x1000000', '--extlib='+str(plugin),
            '--device=spike_soc_ports', '--instructions=20000000', str(elf)]


def plugin_command(source, plugin):
    # Keep fesvr qualified through the repository root. A bare -I<root>/fesvr
    # shadows the host <syscall.h> and breaks libstdc++'s Linux futex headers.
    return ['/usr/bin/g++', '-std=c++20', '-O2', '-Wall', '-Wextra', '-Werror', '-fPIC', '-shared',
            '-I'+str(SPIKE_ROOT), '-I'+str(SPIKE_ROOT / 'riscv'), '-I'+str(SPIKE_ROOT / 'build'),
            str(source), '-o', str(plugin)]


def main(output, execute):
    out = output.absolute()
    require(out == out.resolve() and out.is_relative_to(RUNS), 'Fresh sole-verification output')
    out.mkdir(parents=True, exist_ok=False)
    pins, commands = {}, []
    result = dict(state='PREPARING', performance_measured=False, rtl_executed=False, target_elf_changed=False,
                  spike_binary_changed=False, zero_pmp_platform_equivalence=False)
    env = {k:v for k,v in os.environ.items() if k not in ('LD_PRELOAD', 'LD_LIBRARY_PATH', 'CPATH',
           'C_INCLUDE_PATH', 'CPLUS_INCLUDE_PATH', 'GCC_EXEC_PREFIX', 'COMPILER_PATH', 'LIBRARY_PATH')}
    env.update(PATH='/usr/bin:/bin', LC_ALL='C', PYTHONDONTWRITEBYTECODE='1')
    def pin(path, sha=None): bind(pins, path, sha)
    def run(argv, label, timeout=120):
        argv = list(map(str, argv)); pin(argv[0]); verify_pins(pins)
        commands.append(dict(label=label, argv=argv, timeout_seconds=timeout))
        result['state'] = label.upper()
        (out / 'status.json').write_text(json.dumps(result, indent=2)+'\n')
        (out / 'commands.json').write_text(json.dumps(commands, indent=2)+'\n')
        p = subprocess.run(argv, cwd=out, env=env, capture_output=True, timeout=timeout)
        (out / (label+'.log')).write_bytes(p.stdout+p.stderr)
        commands[-1]['returncode'] = p.returncode
        require(p.returncode == 0, label+' failed; see '+str(out / (label+'.log')))
        verify_pins(pins)
        return p.stdout.decode()
    try:
        pin(ACCEPTED / 'result.json', ACCEPTED_SHA)
        accepted = json.loads((ACCEPTED / 'result.json').read_text())
        require(accepted['state'] == 'REAL_QWEN3_DECODE_RVV_BUILD_REAUDITED_NOT_EXECUTED' and
                accepted['post_pins_match'] and accepted['elf_sha256'] == ELF_SHA, 'RVV ELF not independently built')
        pin(ACCEPTED / 'source-pins.json', accepted['source_pins_sha256'])
        for path,sha in json.loads((ACCEPTED / 'source-pins.json').read_text()).items(): pin(path, sha)
        elf = Path(accepted['elf']); pin(elf, ELF_SHA); pin(SPIKE, SPIKE_SHA); pin('/usr/bin/dtc')
        for path in (Path(__file__), HERE / 'test_decode_rvv_isa.py', HERE / 'check_decode_rvv.py',
                     HERE / 'test_decode_rvv_check.py', HERE / 'spike_soc_ports.cc', HERE / 'test_spike_soc_ports.py'):
            pin(path)
        for module in tuple(sys.modules.values()):
            path = getattr(module, '__file__', None)
            if path and Path(path).is_file() and Path(path).resolve().is_relative_to(ROOT): pin(path)
        pin(sys.executable)
        result.update(elf=str(elf), elf_sha256=ELF_SHA, spike=str(SPIKE), spike_sha256=SPIKE_SHA,
            instruction_budget=20000000, pmp_entries=1,
            memory_scope='Low 16 MiB data plus separate high 16 MiB stack region; no alias/translation proof')
        if execute:
            source = HERE / 'spike_soc_ports.cc'; plugin = out / 'spike_soc_ports.so'
            compile_cmd = plugin_command(source, plugin)
            text = run([*compile_cmd[:compile_cmd.index(str(source))], '-M', '-MT', 'object', str(source)], 'plugin-deps')
            for path in shlex.split(text.replace('\\\n', ' ').split(':',1)[1]): pin(path)
            run(compile_cmd, 'plugin-build'); pin(plugin)
            for name, path in (('spike', SPIKE), ('plugin', plugin)):
                text = run(['/usr/bin/ldd', path], name+'-libraries')
                for library in libraries(text): pin(library)
            (out / 'source-pins.json').write_text(json.dumps(pins, indent=2)+'\n')
            run(spike_command(plugin, elf), 'spike', 120)
            text = (out / 'spike.log').read_text()
            golden = [(BASE / f'part_{p}_expected.bin').read_bytes() for p in range(7)]
            packed = [(BASE / f'activation_{s}.bin').read_bytes() for s in range(4)]
            measured = check(text, golden, packed, isa_model=True)
            # These are exact ISA-model words, not the embedded tolerance oracle.
            for part, hexdata in enumerate(measured['outputs_hex']):
                target = out / f'isa_output_{part}.bin'; target.write_bytes(bytes.fromhex(hexdata))
            result.update(state='EXACT_ELF_RVV_SPIKE_REFERENCE_PASS', measured=measured,
                          independent_isa_output_words=896, csr_records=11)
        else: result['state'] = 'EXACT_ELF_RVV_SPIKE_PREFLIGHT_NOT_RUN'
        verify_pins(pins); (out / 'source-pins.json').write_text(json.dumps(pins, indent=2)+'\n')
        result.update(post_pins_match=True, source_pins_sha256=digest(out / 'source-pins.json'),
            limits=['Functional ISA reference only; Spike cycles excluded from performance',
                    'One permissive PMP entry accommodates the unchanged startup CSR write; not SoC PMP testing',
                    'No Linux/MMU or physical memory-service equivalence is claimed',
                    'RTL output/state must later match all ISA reference words and CSR records exactly'])
    except BaseException as exc:
        result.update(state='FAIL', error=repr(exc)); raise
    finally:
        (out / 'source-pins.json').write_text(json.dumps(pins, indent=2)+'\n')
        (out / 'commands.json').write_text(json.dumps(commands, indent=2)+'\n')
        result['artifacts'] = {str(p):digest(p) for p in out.iterdir()
                               if p.is_file() and p.name not in ('status.json','result.json')}
        (out / 'status.json').write_text(json.dumps(result, indent=2)+'\n')
        (out / 'result.json').write_text(json.dumps(result, indent=2)+'\n')


if __name__ == '__main__':
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--output', type=Path, required=True); p.add_argument('--execute-reviewed', action='store_true')
    a = p.parse_args(); main(a.output, a.execute_reviewed)
