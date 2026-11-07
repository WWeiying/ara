#!/usr/bin/env python3
"""Compile two caller partitions only; reuse 15 frozen objects per ELF."""
import argparse
import json
import os
from pathlib import Path
import re
import shlex
import struct
import subprocess
import sys

from audit import digest, require, verify_pins
from prepare_wide_soc import RUNS, HERE, ROOT, VERIFY
from run_supply_sdk import bind
from run_wide_soc_smoke import elf_admission
import build_decode_matched as parent
from decode_partition_driver import transform, contract, SOURCE_SHA

BASE = RUNS/'e2e_decode_matched_build_20261106_01'
BASE_SHA = '420ef73ec51acafa3104b5a964d7548e96dea584a45b21aab1010f613880761f'
BASE_ELF_SHA = '78ac4ba24c0269b877ca7e79c605775fee6e283c0347c896154006e9236d7ec3'
OWNED = ('decode_partition_driver.py', 'decode_partition_build.py', 'decode_partition_check.py',
         'decode_partition_run.py', 'decode_partition_test.py')


def elf_symbols(raw):
    """Read ELF64 symbol locations; assembly payload labels can have size zero."""
    require(raw[:6] == b'\x7fELF\x02\x01', 'ELF64 little-endian required')
    h = struct.unpack_from('<16sHHIQQQIHHHHHH', raw)
    require(h[11] == 64 and h[6]+64*h[12] <= len(raw), 'Invalid section table')
    sections = [struct.unpack_from('<IIQQQQIIQQ', raw, h[6]+i*64) for i in range(h[12])]
    result = {}
    for s in sections:
        if s[1] != 2: continue
        require(s[9] == 24 and s[6] < len(sections), 'Invalid symbol table')
        st = sections[s[6]]; strings = raw[st[4]:st[4]+st[5]]
        for at in range(s[4], s[4]+s[5], 24):
            name, info, other, section, value, size = struct.unpack_from('<IBBHQQ', raw, at)
            if not (name and 0 < section < len(sections)): continue
            text = strings[name:].split(b'\0', 1)[0].decode()
            sh = sections[section]; offset = sh[4]+value-sh[3]
            if info >> 4:
                require(text not in result, 'Duplicate global symbol')
                result[text] = (offset, size, info & 15)
    return result


def payload_lengths():
    result = {'decode_profiles': 28, 'decode_flags': 28}
    for s in range(4):
        k = 6144 if s == 2 else 2048
        result['decode_input_'+str(s)] = k*4
        result['decode_quantized_'+str(s)] = (k//256)*292
    for p, (k, profile) in enumerate(zip(parent.K, parent.PROFILES)):
        length = 128*(k//256)*(144 if profile == 1 else 210)
        for prefix in ('decode_weights_', 'native_decode_weights_'): result[prefix+str(p)] = length
        for prefix in ('decode_expected_', 'rvv_decode_expected_'): result[prefix+str(p)] = 512
    return result


def verify_payloads(original, candidate):
    a, b = elf_symbols(original), elf_symbols(candidate)
    for name, size in payload_lengths().items():
        require(name in a and name in b, 'Missing immutable payload '+name)
        x, y = a[name][0], b[name][0]
        require(original[x:x+size] == candidate[y:y+size] and len(candidate[y:y+size]) == size,
                'ELF payload differs: '+name)
    return payload_lengths()


def link_recipe(template, driver, elf, linkmap):
    original = str(BASE/'driver.o')
    require(template.count(original) == 1 and len(parent.objects(template)) == 16 and
            template.count('-o') == 1 and sum(x.startswith('-Wl,-Map=') for x in template) == 1,
            'Unexpected parent link inventory')
    result = [str(driver) if x == original else x for x in template]
    result[result.index('-o')+1] = str(elf)
    return ['-Wl,-Map='+str(linkmap) if x.startswith('-Wl,-Map=') else x for x in result]


def build(output):
    out = output.absolute()
    require(out == out.resolve() and out.is_relative_to(RUNS), 'Fresh sole-verification build required')
    out.mkdir(parents=True, exist_ok=False)
    pins, commands = {}, []
    result = dict(state='PREPARING', target_executed=False, rtl_executed=False,
                  performance_measured=False, production_library_changed=False, whole_model=False)
    env = {k: v for k, v in os.environ.items() if k not in
           ('LD_PRELOAD', 'LD_LIBRARY_PATH', 'CPATH', 'C_INCLUDE_PATH', 'CPLUS_INCLUDE_PATH',
            'GCC_EXEC_PREFIX', 'COMPILER_PATH', 'LIBRARY_PATH')}
    env.update(PATH='/usr/bin:/bin', LC_ALL='C', PYTHONDONTWRITEBYTECODE='1')

    def pin(path, sha=None): bind(pins, path, sha)

    def run(argv, label):
        argv = list(map(str, argv)); pin(argv[0]); verify_pins(pins)
        commands.append(dict(label=label, argv=argv, timeout_seconds=300))
        (out/'commands.json').write_text(json.dumps(commands, indent=2)+'\n')
        (out/'status.json').write_text(json.dumps(dict(result, state=label), indent=2)+'\n')
        try:
            child = subprocess.run(argv, cwd=out, env=env, capture_output=True, timeout=300)
        except subprocess.TimeoutExpired as exc:
            (out/(label+'.log')).write_bytes((exc.stdout or b'')+(exc.stderr or b'')); raise
        (out/(label+'.log')).write_bytes(child.stdout+child.stderr)
        commands[-1]['returncode'] = child.returncode
        require(child.returncode == 0, label+' failed; preserve this attempt')
        verify_pins(pins)
        return child.stdout.decode()

    try:
        pin(BASE/'build.json', BASE_SHA); old = json.loads((BASE/'build.json').read_text())
        require(old['state'] == 'REAL_DECODE_MATCHED_ABBA_BUILT_NOT_EXECUTED' and old['post_pins_match'] and
                old['elf_sha256'] == BASE_ELF_SHA and old['n'] == 64 and old['full_k'] and
                old['native_commands'] == 28 and old['outputs'] == 1792, 'Wrong matched parent')
        pin(BASE/'source-pins.json', old['source_pins_sha256'])
        inventory = json.loads((BASE/'source-pins.json').read_text())
        pin(BASE/'commands.json', old['artifacts'][str(BASE/'commands.json')])
        pin(old['elf'], BASE_ELF_SHA); original_elf = Path(old['elf']).read_bytes()
        pin(HERE/'decode_matched.cpp', SOURCE_SHA)
        source = (HERE/'decode_matched.cpp').read_text()
        recipes = json.loads((BASE/'commands.json').read_text())
        template = parent.labelled(recipes, 'compile-0')
        link = parent.labelled(recipes, 'link')
        pin(template[0], inventory[str(Path(template[0]).resolve())])
        retained = [p for p in parent.objects(link) if p != str(BASE/'driver.o')]
        require(len(retained) == 15, 'Exactly 15 frozen objects must remain')
        for p in retained: pin(p, inventory[p])
        pin(link[link.index('-T')+1], inventory[link[link.index('-T')+1]])
        for p, sha in old['linked_archives'].items(): pin(p, sha)
        # Inherit only consumed files, not unrelated model/QEMU inventories.
        for name in OWNED: pin(HERE/name)
        for module in tuple(sys.modules.values()):
            p = getattr(module, '__file__', None)
            if p and Path(p).is_file() and any(Path(p).resolve().is_relative_to(r) for r in (ROOT, VERIFY)):
                pin(p, inventory.get(str(Path(p).resolve())))
        pin(sys.executable)
        pin(parent.ISA/'result.json', parent.ISA_SHA)
        isa = json.loads((parent.ISA/'result.json').read_text())
        require(isa['state'] == 'EXACT_ELF_RVV_SPIKE_REFERENCE_PASS' and isa['post_pins_match'] and
                isa['independent_isa_output_words'] == 896 and isa['csr_records'] == 11,
                'Original independent ISA reference required')
        pin(parent.ISA/'source-pins.json', isa['source_pins_sha256'])
        oracle_dir = out/'oracle'; oracle_dir.mkdir()
        for name, record in old['oracle_copies'].items():
            source_file = Path(record['source']); pin(source_file, record['source_sha256'])
            copy = BASE/'oracle'/name; pin(copy, record['sha256'])
            raw = source_file.read_bytes()
            payload = parent.oracle_payload(name, raw)
            require(payload == copy.read_bytes(), 'Original oracle prefix changed')
            if name.startswith('rvv_'):
                part = int(name[4]); require(raw.hex() == isa['measured']['outputs_hex'][part], 'ISA bits differ')
            target = oracle_dir/name; target.write_bytes(payload); pin(target, record['sha256'])
        flags = parent.checked_flags((oracle_dir/'flags.bin').read_bytes())
        for name in ('cc1plus', 'as', 'collect2', 'ld'):
            path = Path(run([template[0], '-print-prog-name='+name], 'tool-'+name).strip()).resolve(strict=True)
            require(str(path) in inventory and path.is_relative_to(parent.TOOLCHAIN), 'Unaccepted compiler subprogram')
            pin(path, inventory[str(path)])
        groups = []
        for group in (0, 1):
            folder = out/f'group{group}'; folder.mkdir()
            text, proof = transform(source, group)
            src = folder/'decode_partition_main.cpp'; src.write_text(text); pin(src, proof['generated_sha256'])
            (folder/'transform.json').write_text(json.dumps(proof, indent=2)+'\n'); pin(folder/'transform.json')
            obj = folder/'driver.o'; recipe = parent.compile_recipe(template, src, obj)
            dep = [x for i, x in enumerate(recipe) if i not in
                   (recipe.index('-c'), recipe.index('-o'), recipe.index('-o')+1)]
            dependencies = run([*dep, '-M', '-MT', 'object'], f'group{group}-deps')
            for p in shlex.split(dependencies.replace('\\\n', ' ').split(':', 1)[1]):
                path = Path(p).resolve(strict=True)
                require(path == src or str(path) in inventory, 'Unpinned compiler dependency: '+str(path))
                pin(path, pins[str(path)] if path == src else inventory[str(path)])
            run(recipe, f'group{group}-compile'); pin(obj)
            elf = folder/'decode_partition.elf'
            actual_link = link_recipe(link, obj, elf, folder/'link.map')
            run(actual_link, f'group{group}-link'); pin(elf)
            libraries = {str(Path(p).resolve()) for p in re.findall(r'^LOAD (.+[.]a)$', (folder/'link.map').read_text(), re.M)}
            require(libraries == set(old['linked_archives']), 'Runtime library inventory changed')
            dis = run([Path(template[0]).with_name('riscv64-unknown-elf-objdump'), '-d', elf], f'group{group}-disassembly')
            parent.check_disassembly(dis)
            signature = parent.custom_signature(elf.read_bytes(), dis)
            pin(BASE/'disassembly.log', old['artifacts'][str(BASE/'disassembly.log')])
            require(signature == parent.custom_signature(original_elf, (BASE/'disassembly.log').read_text()),
                    'SDK custom instructions changed')
            payloads = verify_payloads(original_elf, elf.read_bytes())
            groups.append(dict(**contract(group), elf=str(elf), elf_sha256=digest(elf),
                               driver_object=str(obj), driver_object_sha256=digest(obj),
                               driver_sha256=proof['generated_sha256'], immutable_payloads=payloads,
                               preload_segments={str(w): elf_admission(elf.read_bytes(), w//8) for w in (128, 256)}))
        history = []
        for name in ('e2e_decode_rvv_rtl128_20261106_01', 'e2e_decode_rvv_rtl256_20261106_01',
                     'e2e_decode_matched_rtl128_20261106_01', 'e2e_decode_matched_rtl256_20261106_01'):
            path = RUNS/name/'result.json'; pin(path)
            r = json.loads(path.read_text()); require(r['state'] == 'FAIL', 'Historical failure changed')
            history.append(dict(path=str(path), sha256=digest(path), error=r['error'], relabeled=False))
        verify_pins(pins)
        result.update(state='DECODE_PARTITIONS_BUILT_NOT_EXECUTED', groups=groups, order=[0, 1, 1, 0],
                      parent_build_sha256=BASE_SHA, parent_elf_sha256=BASE_ELF_SHA,
                      isa_reference_result_sha256=parent.ISA_SHA, native_flags=flags,
                      reused_objects={p: pins[p] for p in retained}, compiled_translation_units=2,
                      arithmetic_objects_recompiled=False, old_results=history, post_pins_match=True,
                      limits=['Build only; each partition still requires actual RTL bits/CSR and independent protocol PASS',
                              'Original N128 Spike reference selects N64 prefixes; mixed custom-opcode ELF not executed in plain Spike',
                              'Partition ROI ledger is not a continuous seven-part measurement or whole-model speedup',
                              'Only two caller objects compiled; original arithmetic/data/workspace layouts retained'])
    except BaseException as exc:
        result.update(state='FAIL', error=repr(exc)); raise
    finally:
        (out/'source-pins.json').write_text(json.dumps(pins, indent=2)+'\n')
        (out/'commands.json').write_text(json.dumps(commands, indent=2)+'\n')
        result['source_pins_sha256'] = digest(out/'source-pins.json')
        result['artifacts'] = {str(p): digest(p) for p in out.rglob('*') if p.is_file() and p.name not in ('build.json', 'status.json')}
        (out/'build.json').write_text(json.dumps(result, indent=2)+'\n')
        (out/'status.json').write_text(json.dumps(result, indent=2)+'\n')


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', type=Path, required=True)
    build(parser.parse_args().output)
