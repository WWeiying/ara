#!/usr/bin/env python3
"""Build accepted-vector versus signed-max ABBA; never launch simulations."""
import argparse
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[2]
sys.path.insert(0, str(ROOT/'verification/qbs'))
from run_half_scale_soc import atomic_json, digest, hashes


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    out = args.output.resolve()
    if not out.is_relative_to(ROOT/'verification/out'):
        raise ValueError('Use fresh verification/out directory')
    base = ROOT/'verification/qbs/combined_zvfh_m4/projection/build-03'
    candidate = ROOT/'verification/out/q8k-signed-max-compile-20261026-01'
    native = ROOT/'verification/out/q8k-signed-max-native-20261026-01'
    receipt = json.loads((native/'result.json').read_text())
    if receipt['state'] != 'PASS' or receipt['checks'] != 4000 or \
            receipt['log_sha256'] != digest(native/'qemu.log') or \
            receipt['manifest_sha256'] != digest(native/'manifest.json'):
        raise ValueError('Missing full quantizer numerical acceptance')
    cpins = json.loads((candidate/'inputs.json').read_text())
    if hashes(map(Path, cpins)) != cpins:
        raise ValueError('Candidate source drift')
    previous = json.loads((base/'build.json').read_text())
    if digest(base/'manifest.json') != previous['manifest_sha256']:
        raise ValueError('Prior build manifest drift')
    oldpins = json.loads((base/'manifest.json').read_text())
    commands = json.loads((base/'commands.json').read_text())
    header = candidate/'ggml/src/ggml-cpu/arch/riscv'
    llama = Path('/home/wangwy/llama/llama.cpp/ggml')
    sources = {HERE/'projection.patch', HERE/'projection_candidate.cpp', Path(__file__),
               native/'result.json', native/'qemu.log', native/'manifest.json',
               base/'build.json', base/'manifest.json', base/'commands.json',
               base.parent/'projection.cpp'}
    sources.update(llama.rglob('*.h'))
    sources.update((ROOT/'software/qbs/include').rglob('*.h'))
    sources.update((ROOT/'apps/common').glob('*.h'))
    sources.update((ROOT/'apps/include').rglob('*.h'))
    for command in commands:
        if '-c' in command:
            sources.add(Path(command[command.index('-c')+1]))
        sources.add(Path(command[0]).resolve())
    sources.update(base/name for name in ('contract.json', 'contract.h', 'data.S', 'link.ld',
                                         'activation_f32.bin', 'activation_q8k_m4.bin',
                                         'weight_r4.bin', 'oracle_f32.bin'))
    # Reuse the independently checked data and unchanged SDK, not historical
    # external repack pins: that TU was intentionally integrated afterwards.
    for path in sources:
        if str(path) in oldpins and digest(path) != oldpins[str(path)]:
            raise ValueError('Accepted harness/data/SDK changed: '+str(path))
    pins = dict(cpins)
    pins.update(hashes(sources))
    out.mkdir(parents=True, exist_ok=False)
    for name in ('projection.cpp',):
        shutil.copyfile(base.parent/name, out/name)
    subprocess.run(['git', 'apply', str(HERE/'projection.patch')], cwd=out,
                   env=dict(os.environ, GIT_CEILING_DIRECTORIES=str(out.parent)), check=True)
    for name in ('contract.h', 'data.S', 'link.ld'):
        shutil.copyfile(base/name, out/name)
    contract = json.loads((base/'contract.json').read_text())
    contract.update(order=['accepted_vector', 'signed_max', 'signed_max', 'accepted_vector'],
                    current_numerical_receipt=str(native/'result.json'),
                    baseline='Accepted vector quantizer with scalar signed maximum',
                    candidate='Same quantizer with integer RVV signed maximum',
                    both_vector_paths_required=True)
    atomic_json(out/'contract.json', contract)
    executed = []
    candidate_command = None
    candidate_object = out/'signed-max.o'
    for index, original in enumerate(commands):
        if '-c' not in original and '-nostdlib' not in original:
            continue
        command = [part.replace(str(base), str(out)) for part in original]
        if '-c' in command:
            pos = command.index('-c')+1
            if command[pos] == str(base.parent/'projection.cpp'):
                command[pos] = str(out/'projection.cpp')
            elif command[pos] == str(out/'generic.cpp'):
                command[pos] = str(base/'generic.cpp')
                candidate_command = list(command)
                candidate_command[pos] = str(HERE/'projection_candidate.cpp')
                candidate_command[candidate_command.index('-o')+1] = str(candidate_object)
                candidate_command = ['-ffp-contract=off' if x == '-ffp-contract=fast' else x
                                     for x in candidate_command]
                candidate_command += ['-I'+str(header)]
        else:
            if candidate_command is None:
                raise ValueError('No preparation compile template')
            executed.append(candidate_command)
            with (out/'candidate-compile.log').open('x') as stream:
                subprocess.run(candidate_command, cwd=out, stdout=stream, stderr=subprocess.STDOUT,
                               check=True, timeout=180)
            command.insert(command.index('-lm'), str(candidate_object))
        executed.append(command)
        atomic_json(out/'commands.json', executed)
        with (out/f'command-{index}.log').open('x') as stream:
            subprocess.run(command, cwd=out, stdout=stream, stderr=subprocess.STDOUT,
                           check=True, timeout=180)
    elf = out/'qbs_current_projection_soc'
    objdump = Path(commands[0][0]).with_name('riscv64-unknown-elf-objdump')
    disassembly = subprocess.check_output([objdump, '-d', elf], text=True)
    if not all(op in disassembly for op in ('candidate_prepare', 'vfirst.m', 'vredmaxu.vs',
                                           'qbs_native_execute_command')):
        raise ValueError('Missing candidate or native execution')
    (out/'disassembly.log').write_text(disassembly)
    if hashes(map(Path, pins)) != pins:
        raise ValueError('Build input drift')
    pins.update(hashes(p for p in out.iterdir() if p.is_file()))
    atomic_json(out/'manifest.json', pins)
    atomic_json(out/'build.json', dict(state='READY', execution='NOT_RUN',
        manifest_sha256=digest(out/'manifest.json'), elf_sha256=digest(elf),
        scope='Same-ELF accepted vector versus signed-max vector projection; not full model',
        performance_validation=False, production_modified=False))
    print(json.dumps(dict(state='READY', execution='NOT_RUN', output=str(out))))


if __name__ == '__main__':
    main()
