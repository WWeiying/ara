#!/usr/bin/env python3
"""Reuse the accepted norm experiment; rebuild only the new output/caller objects."""
import argparse
import json
import os
from pathlib import Path
import shlex
import subprocess
import sys

from audit import digest, require, verify_pins
from prepare_wide_soc import HERE, ROOT, RUNS
from run_supply_sdk import bind
from build_rms_norm_native import link_archives, TOOLCHAIN
from build_decode_rvv import custom_instructions
from run_wide_soc_smoke import elf_admission
from rms_norm_output_source import candidate, caller

PARENT = RUNS / 'e2e_rms_norm_completed_build_20261106_01'
PARENT_SHA = '2180232000caee59c88dec098a1868656160b4d38f2ac0785e0c5f77c8111f7d'
ACCEPTED = ROOT / 'verification/performance/evidence/rms_norm_scoped_20261106_01/result.json'
ACCEPTED_SHA = 'ea968161e15276aa7c6eaa27913d4512aafdfc681499a7d8ed522af1a0ae2ba4'


def replace_object(link, old, new):
    require(link.count(str(old)) == 1, 'Missing/duplicate original object')
    return [str(new) if value == str(old) else value for value in link]


def parent_acceptance(accepted):
    require(accepted['state'] == 'REAL_QWEN3_FUSED_RMS_NORM_SCOPED_ACCEPTANCE_INDEPENDENTLY_REPLAYED' and
            accepted['outputs_checked'] == 40960 and accepted['boundary_cases'] == 53 and
            accepted['order_sensitive_sum_cases'] == 10 and accepted['timing_includes_csr_completion'],
            'Parent performance/numerical acceptance differs')


def main(output):
    out = output.absolute()
    require(out == out.resolve() and out.is_relative_to(RUNS), 'Fresh sole-verification output')
    out.mkdir(parents=True, exist_ok=False)
    pins, commands = {}, []
    result = dict(state='PREPARING', rtl_changed=False, production_library_changed=False,
                  performance_measured=False, whole_model=False)
    env = {k:v for k,v in os.environ.items() if k not in ('LD_PRELOAD', 'CPATH', 'C_INCLUDE_PATH',
           'CPLUS_INCLUDE_PATH', 'GCC_EXEC_PREFIX', 'COMPILER_PATH', 'LIBRARY_PATH')}
    env.update(PATH='/usr/bin:/bin', LC_ALL='C')
    def pin(path, sha=None): bind(pins, path, sha)
    def run(argv, label):
        argv = list(map(str, argv)); pin(argv[0]); verify_pins(pins)
        commands.append(dict(label=label, argv=argv))
        result['state'] = label.upper()
        (out / 'status.json').write_text(json.dumps(result, indent=2)+'\n')
        (out / 'commands.json').write_text(json.dumps(commands, indent=2)+'\n')
        p = subprocess.run(argv, cwd=out, env=env, capture_output=True, timeout=180)
        (out / (label+'.log')).write_bytes(p.stdout+p.stderr)
        require(p.returncode == 0, label+' failed')
        verify_pins(pins)
        return p.stdout.decode()
    try:
        pin(ACCEPTED, ACCEPTED_SHA)
        accepted = json.loads(ACCEPTED.read_text())
        parent_acceptance(accepted)
        pin(Path(accepted['run']) / 'result.json', accepted['result_sha256'])
        old = json.loads((PARENT / 'build.json').read_text())
        pin(PARENT / 'build.json'); pin(PARENT / 'source-pins.json', PARENT_SHA)
        require(old['source_pins_sha256'] == PARENT_SHA and old['elf_sha256'] == accepted['elf_sha256'] and
                old['timing_includes_csr_completion'] and old['state'] ==
                'REAL_QWEN3_FUSED_RMS_NORM_ABBA_BUILT_NOT_EXECUTED', 'Parent exact build mismatch')
        for collection in (json.loads((PARENT / 'source-pins.json').read_text()), old['artifacts']):
            for path, sha in collection.items(): pin(path, sha)
        arithmetic = Path(old['parent_build'])
        recipes = {r['label']:r['argv'] for r in json.loads((arithmetic / 'commands.json').read_text())}
        parent_commands = {r['label']:r['argv'] for r in json.loads((PARENT / 'commands.json').read_text())}
        matches = [Path(path) for path in pins if path.endswith('/llama/ggml/src/ggml-cpu/ops.cpp')]
        require(len(matches) == 1, 'Missing/ambiguous accepted GGML ops source')
        source_path = matches[0]
        source = source_path.read_text()
        generated = {'candidate':candidate(source), 'strict-candidate':candidate(source, 'strict_candidate'),
                     'main':caller((PARENT / 'completed.cpp').read_text())}
        units = {}
        for name, text in generated.items():
            path = out / (name+'.cpp'); path.write_text(text); pin(path); units[name] = path
        units['output-checks'] = HERE / 'rms_output_checks.cpp'
        for path in (ROOT / 'software/rvv/experimental/ordered_rms_norm/rms_output.h',
                     HERE / 'rms_norm_output_source.py', HERE / 'test_rms_norm_output.py',
                     HERE / 'rms_output_checks.cpp', Path(__file__), Path(sys.executable)): pin(path)
        for module in tuple(sys.modules.values()):
            path = getattr(module, '__file__', None)
            if path and Path(path).is_file() and Path(path).resolve().is_relative_to(ROOT): pin(path)
        objects = {}
        for name, source in units.items():
            cmd = list(parent_commands['compile-main'] if name in ('main','output-checks') else
                       recipes['compile-'+name])
            cmd[cmd.index('-c')+1] = str(source)
            obj = out / (name+'.o'); cmd[cmd.index('-o')+1] = str(obj)
            if name == 'output-checks':
                cmd += ['-frounding-math', '-fno-tree-vectorize', '-ffp-contract=off']
            dep = [v for i,v in enumerate(cmd) if i not in (cmd.index('-c'),cmd.index('-o'),cmd.index('-o')+1)]
            text = run([*dep, '-M', '-MT', 'object'], 'deps-'+name)
            for value in shlex.split(text.replace('\\\n',' ').split(':',1)[1]):
                path = Path(value).resolve(strict=True)
                require(str(path) in pins or path.is_relative_to(TOOLCHAIN) and
                        path.suffix in ('.h','.tcc','.inl','.inc',''), 'Unknown dependency: '+str(path))
                pin(path, pins.get(str(path)))
            run(cmd, 'compile-'+name); pin(obj); objects[name] = obj
        link = list(parent_commands['link'])
        for name in ('main','candidate','strict-candidate'):
            link = replace_object(link, (PARENT if name == 'main' else arithmetic) / (name+'.o'), objects[name])
        link.insert(link.index('-Wl,--gc-sections'), str(objects['output-checks']))
        elf = out / 'rms_output.elf'; link[link.index('-o')+1] = str(elf)
        link = ['-Wl,-Map='+str(out / 'link.map') if v.startswith('-Wl,-Map=') else v for v in link]
        run(link, 'link'); pin(elf)
        linked = link_archives((out / 'link.map').read_text(), old['runtime_archives'])
        objdump = Path(link[0]).with_name('riscv64-unknown-elf-objdump')
        dis = run([objdump, '-d', elf], 'disassembly')
        candidate_dis = run([objdump, '-d', objects['candidate']], 'candidate-disassembly')
        require(all(op in candidate_dis for op in ('vfwredosum.vs','vfmul.vf','vfmul.vv','vse32.v')) and
                '<rms_output_checks>:' in dis and '<strict_candidate_rms_sum>:' in dis,
                'New output or original strict checks missing')
        require(not custom_instructions(elf.read_bytes()), 'Custom opcode in ordinary RVV experiment')
        loads = {str(w):elf_admission(elf.read_bytes(), w//8) for w in (128,256)}
        verify_pins(pins); (out / 'source-pins.json').write_text(json.dumps(pins, indent=2)+'\n')
        result.update(state='REAL_FUSED_RMS_VECTOR_OUTPUT_BUILT_NOT_EXECUTED', elf=str(elf),
            elf_sha256=digest(elf), source_pins_sha256=digest(out / 'source-pins.json'),
            parent_build=str(PARENT), parent_elf_sha256=old['elf_sha256'], data=old['data'],
            rows=[1,4], width=2048, trials=8, outputs_checked=40960, boundary_cases=53, sum_cases=10,
            output_boundary_cases=155, order=[0,1,1,0], timing_includes_csr_completion=True,
            recompiled_objects=4, reused_objects=len([p for p in link if p.endswith('.o')])-4,
            linked_archives=linked, preload_segments=loads, baseline_arithmetic_unchanged=True,
            candidate='Ordered FP64 sum plus guarded two-rounding RVV fused output')
    except BaseException as exc:
        result.update(state='FAIL', error=repr(exc)); raise
    finally:
        (out / 'commands.json').write_text(json.dumps(commands, indent=2)+'\n')
        result['artifacts'] = {str(p):digest(p) for p in out.iterdir()
                               if p.is_file() and p.name not in ('status.json','build.json')}
        (out / 'status.json').write_text(json.dumps(result, indent=2)+'\n')
        (out / 'build.json').write_text(json.dumps(result, indent=2)+'\n')


if __name__ == '__main__':
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--output', type=Path, required=True)
    main(p.parse_args().output)
