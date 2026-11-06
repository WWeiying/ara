#!/usr/bin/env python3
"""Committed handoff adjunct: reuse frozen common objects, build only, no SDK/EDA."""
import argparse
import hashlib
import json
import os
from pathlib import Path
import re
import shlex
import shutil
import subprocess
import sys

import wide_soc_memory_smoke_build as memory

HERE = Path(__file__).resolve().parent
BASE = memory.OUTPUT
BASE_SHA = 'e7b8183b27ea68dd6adfd393ad5ac8972a67be1fdf5b67a2c9df11ba59f252ce'
OUTPUT = memory.VERIFY/'verification/out/e2e_wide_soc_handoff_smoke_build_20261106_01'
COMMIT = '372797bbb3482cf0c982736edbd71c6b4dbe77e4'
INPUTS = {
    'apps/qbs_akv_handoff_smoke/main.c': ('cfb748c4b6c7979ac9cba1fd10b6dcf75aea5204', 'd532ca577d6f2f8ef93d2680f7fd98523c237c08638ab47b4b1f644a98df5198'),
    'apps/common/qbs_abi.h': ('017d713266c3a860ccb931a8792bf20fec5bf0ab', '691fcc9c0a674193c5f4879e43e9fb72404e822a39dd6037444ae75a2387dada'),
    'apps/common/akv_abi.h': ('deffaa8d5e13267b3f7b758e0641ee603ba78fc9', '59ae7775780d7a4cf41fa2ae4d445133dda27a11b467cfe25a0db86d353c7e1f'),
}
OWNED = ('wide_soc_memory_smoke_handoff_build.py', 'wide_soc_memory_smoke_handoff_test.py')
PASS = 'QBS/AKV handoff smoke: PASS traps=0'
require, digest, write = memory.require, memory.digest, memory.write


def check_log(text):
    require(not re.search(r'(?i)\bFAIL\b|\bSKIP\b|mismatch|\btrapped\b|Fatal:|Error[-:]|UVM_(?:ERROR|FATAL)|mcause_val|timeout', text),
            'Handoff failure/skip/exception/tool diagnostic')
    records = [s for s in text.replace('\r', '').splitlines() if s.startswith('QBS/AKV handoff smoke:')]
    require(records == [PASS], 'Missing/duplicate/nonzero-trap handoff terminal')
    return dict(marker=PASS, expected_exceptions=0, qbs_checked_values=64, akv_checked_values=256,
                rvv_checked_values=96, capability_checks=2)


def loader_contract(source):
    require('if(ph[i].p_type == PT_LOAD && ph[i].p_memsz)' in source and
            'if (ph[i].p_filesz)' in source and
            'sections.push_back(std::make_pair(ph[i].p_paddr, ph[i].p_memsz));' in source and
            'write(ph[i].p_paddr, ph[i].p_filesz, (uint8_t*)buf + ph[i].p_offset);' in source and
            source.count('sections.push_back') == 1, 'DPI loader enumeration contract changed')
    return 'PT_LOAD && p_memsz && p_filesz: enumerate p_paddr,p_memsz; copy p_filesz bytes'


def loader_admission(section_text, program_text):
    allocated = []
    for line in section_text.splitlines():
        match = re.match(r'^\s*\[\s*(\d+)\]\s+(.*)$', line)
        if not match or int(match[1]) == 0:
            continue
        fields = match[2].split()
        require(len(fields) in (9, 10), 'Unexpected readelf section record')
        if len(fields) == 10 and 'A' in fields[6] and int(fields[4], 16):
            address, size = int(fields[2], 16), int(fields[4], 16)
            require(address % 32 == 0, 'Allocated section not 32-byte aligned: '+fields[0])
            allocated.append(dict(name=fields[0], type=fields[1], address=address, bytes=size,
                                  rounded_end=(address+size+31)//32*32))
    loads = []
    pattern = (r'^\s*LOAD\s+(0x[0-9a-f]+)\s+(0x[0-9a-f]+)\s+(0x[0-9a-f]+)\s+'
               r'(0x[0-9a-f]+)\s+(0x[0-9a-f]+)\s+([RWE ]+)\s+(0x[0-9a-f]+)\s*$')
    for line in program_text.splitlines():
        if line.lstrip().startswith('LOAD '):
            match = re.fullmatch(pattern, line)
            require(match is not None, 'Unexpected readelf LOAD record')
            _, va, pa, filesz, memsz = (int(match[i], 16) for i in range(1, 6))
            if memsz and filesz:
                require(va == pa and pa % 32 == 0 and filesz <= memsz, 'DPI segment alignment/identity')
                loads.append(dict(address=pa, file_bytes=filesz, memory_bytes=memsz,
                                  rounded_end=(pa+memsz+31)//32*32))
    require(allocated and loads, 'Empty loader admission inventory')
    for rows in (allocated, loads):
        ordered = sorted(rows, key=lambda d:d['address'])
        for first, second in zip(ordered, ordered[1:]):
            require(first['rounded_end'] <= second['address'], 'Rounded preload ranges overlap')
    for row in loads:
        require(0x80000000 <= row['address'] < row['rounded_end'] <= 0x80100000, 'Preload exceeds 1 MiB L2')
    for section in allocated:
        require(any(p['address'] <= section['address'] and
                    section['address']+section['bytes'] <= p['address']+p['memory_bytes'] for p in loads),
                'Allocated section outside DPI-enumerated segments')
    return dict(allocated_sections=allocated, dpi_enumerated_segments=loads,
                all_allocated_section_addresses_32_aligned=True, rounded_sections_nonoverlapping=True,
                rounded_dpi_segments_nonoverlapping=True, accepted_for_128_and_256_preload=True)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--build', action='store_true')
    args = parser.parse_args(); require(args.build, 'Explicit committed adjunct build required')
    owned = {str(HERE/n) for n in OWNED}
    observations = []
    for d in sorted((memory.VERIFY/'verification/out').iterdir()):
        path = d/'source-pins.json'
        if path.is_file():
            old = json.loads(path.read_text())
            require(not owned.intersection(old), 'Adjunct helper already sealed: '+str(path))
            observations.append(dict(path=str(path), sha256=digest(path),
                                     inherited_documentation=[k for k in old if k.lower().endswith('.md')]))
    OUTPUT.mkdir(exist_ok=False)
    pins, identities, commands = {}, {}, []
    env = {k:v for k,v in os.environ.items() if k not in
           ('LD_PRELOAD', 'CPATH', 'C_INCLUDE_PATH', 'CPLUS_INCLUDE_PATH', 'GCC_EXEC_PREFIX', 'COMPILER_PATH', 'LIBRARY_PATH')}
    env.update(PATH='/usr/bin:/bin', LC_ALL='C')
    result = dict(state='WIDE_SOC_HANDOFF_BUILD_FAIL', target_executed=False, simulation_executed=False,
                  rtl_changed=False, sdk_used=False, local_akv_assembly_used=False, sealed_sources_modified=False)

    def pin(path, expected=None):
        lexical = Path(path).absolute(); actual = lexical.resolve(strict=True); sha = digest(actual)
        require(expected is None or sha == expected, 'Input SHA mismatch: '+str(path))
        require(str(actual) not in pins or pins[str(actual)] == sha, 'Input drift: '+str(path))
        pins[str(actual)] = sha; identities[str(lexical)] = str(actual)
        return sha

    def verify():
        require(all(str(Path(p).resolve(strict=True)) == q for p,q in identities.items()), 'Path drift')
        require(all(digest(p) == h for p,h in pins.items()), 'Consumed input/tool/object drift')

    def run(argv, label, cwd=None):
        argv = list(map(str, argv)); pin(argv[0]); verify()
        commands.append(dict(label=label, argv=argv, cwd=str(cwd or OUTPUT)))
        write(OUTPUT/'commands.json', commands)
        child = subprocess.run(argv, cwd=cwd or OUTPUT, env=env, capture_output=True, timeout=120)
        (OUTPUT/(label+'.log')).write_bytes(child.stdout+child.stderr)
        commands[-1]['returncode'] = child.returncode; write(OUTPUT/'commands.json', commands)
        require(child.returncode == 0, label+' failed; preserved')
        verify(); return child.stdout

    try:
        write(OUTPUT/'worker-pin-inventory.json', observations)
        pin(BASE/'result.json', BASE_SHA)
        base = json.loads((BASE/'result.json').read_text())
        require(base['state'] == 'WIDE_SOC_MEMORY_SMOKE_ELF_BUILT_NOT_EXECUTED', 'Wrong common-object receipt')
        pin(BASE/'source-pins.json', base['source_pins_sha256'])
        inherited = json.loads((BASE/'source-pins.json').read_text())
        for path in (HERE/'wide_soc_memory_smoke_build.py', *[HERE/n for n in OWNED]):
            pin(path, inherited.get(str(path)))
        git = Path(shutil.which('git')).resolve(strict=True)
        require(run([git, 'rev-parse', COMMIT+'^{commit}'], 'commit', memory.MAIN).decode().strip() == COMMIT,
                'Commit identity')
        archive = OUTPUT/'archive-input'
        manifest = {}
        for i, (name, (blob, sha)) in enumerate(INPUTS.items()):
            content = run([git, 'show', COMMIT+':'+name], 'extract-'+str(i), memory.MAIN)
            require(hashlib.sha1(b'blob '+str(len(content)).encode()+b'\0'+content).hexdigest() == blob and
                    hashlib.sha256(content).hexdigest() == sha, 'Committed blob identity')
            dest = archive/name; dest.parent.mkdir(parents=True, exist_ok=True)
            with dest.open('xb') as stream:
                stream.write(content)
            pin(dest, sha); manifest[name] = dict(blob=blob, sha256=sha, actual_input=str(dest))
        write(OUTPUT/'archive-input.json', dict(commit=COMMIT, inputs=manifest))
        source = archive/'apps/qbs_akv_handoff_smoke/main.c'
        require(not re.search(r'\b(?:pmpaddr\w*|pmpcfg\w*|satp)\b', source.read_text()), 'App changed PMP/satp policy')
        cc = Path(base['toolchain']['driver'])
        for name in ('driver', 'cc1', 'as', 'collect2', 'ld'):
            path = Path(base['toolchain'][name]); pin(path, inherited[str(path.resolve())])
        objects = [BASE/f'{i}.o' for i in (2, 3, 4, 5)]
        for obj in objects:
            pin(obj, inherited[str(obj)])
        common = BASE/'source-snapshot/common'
        for name in ('printf.h', 'crt0.S', 'encoding.h'):
            pin(common/name, inherited[str(common/name)])
        linker = common/'link.ld'; pin(linker, inherited[str(linker)])
        libgcc = Path(base['runtime_archive']); pin(libgcc, base['runtime_archive_sha256'])
        flags = [f for f in base['compile_flags'] if not f.startswith('-I')]+[
            '-I'+str(archive/'apps/common'), '-I'+str(common), '-DVLEN=1024', '-DNR_LANES=4', '-std=gnu11']
        dep = run([cc, *flags, '-M', '-MT', 'main', source], 'dependencies').decode()
        for path in shlex.split(dep.replace('\\\n', ' ').split(':', 1)[1]):
            pin(path)
        app_object = OUTPUT/'handoff-main.o'
        run([cc, *flags, '-Wall', '-Wextra', '-c', source, '-o', app_object], 'compile-main'); pin(app_object)
        elf = OUTPUT/'qbs_akv_handoff_smoke.elf'
        run([cc, *flags, '-static', '-nostdlib', '-nostartfiles', app_object, *objects, libgcc,
             '-Wl,--gc-sections,--no-relax,-Map='+str(OUTPUT/'link.map'), '-T', linker, '-o', elf], 'link')
        pin(elf)
        readelf = cc.with_name('riscv64-unknown-elf-readelf')
        objdump = cc.with_name('riscv64-unknown-elf-objdump')
        pin(readelf); pin(objdump)
        loader = memory.MAIN/'hardware/tb/dpi/elfloader.cc'; pin(loader)
        contract = loader_contract(loader.read_text())
        admissions = {}
        for label, image in (('memory', Path(base['elf'])), ('handoff', elf)):
            pin(image, base['elf_sha256'] if label == 'memory' else None)
            sections = run([readelf, '-W', '-S', image], label+'-sections').decode()
            programs = run([readelf, '-W', '-l', image], label+'-program-headers').decode()
            admissions[label] = loader_admission(sections, programs)
            admissions[label].update(elf=str(image), sha256=digest(image))
        write(OUTPUT/'loader-admission.json', dict(loader=str(loader.resolve()), loader_sha256=digest(loader),
                                                  enumeration=contract, images=admissions))
        dis = run([objdump, '-d', '-M', 'no-aliases', elf], 'disassembly').decode()
        for opcode in ('0005155b', '0005455b', '00b5045b', '00b5605b', '0005345b', '0000505b'):
            require(opcode in dis, 'Missing committed instruction '+opcode)
        require('pmpaddr0' in dis and not re.search(r'\b(?:satp|pmpcfg\w*)\b', dis), 'Startup CSR contract differs')
        require('QBS/AKV handoff smoke: %s traps=%ld' in source.read_text(), 'Terminal changed')
        run([sys.executable, '-B', HERE/'wide_soc_memory_smoke_handoff_test.py'], 'host-tests')
        verify()
        result.update(state='WIDE_SOC_HANDOFF_COMMITTED_ELF_BUILT_NOT_EXECUTED', elf=str(elf), elf_sha256=digest(elf),
                      commit=COMMIT, committed_inputs=manifest, toolchain=base['toolchain'], compile_flags=flags,
                      reused_common_objects={str(p):digest(p) for p in objects}, reused_common_receipt_sha256=BASE_SHA,
                      reused_linker=str(linker), reused_linker_sha256=digest(linker),
                      required_terminal=PASS, skip_is_not_acceptance=True, expected_exceptions=0,
                      checks=dict(qbs_exec_commands=4, qbs_checked_calls=2, qbs_checked_values=64,
                                  akv_v2_full_commands=3, akv_v1_row_loads=4, akv_checked_values=256,
                                  akv_releases=3, rvv_calls=3, rvv_checked_values=96, capability_checks=2),
                      pmp_satp=dict(app_touches_pmp=False, app_touches_satp=False,
                                    startup_writes=['pmpaddr0'], startup_writes_pmpcfg=False,
                                    startup_writes_satp=False, permission_or_translation_test=False),
                      loader_admission=admissions, loader_source_sha256=digest(loader), post_pins_match=True,
                      limitations=['AKV-v2 FULL plus v1 row-copy/load interface, not a separate v1 FILL test',
                                   'ELF only; no SoC runtime/physical-256/PMP/performance claim'])
    except Exception as exc:
        result.update(error=repr(exc), post_pins_match=False)
    finally:
        write(OUTPUT/'source-pins.json', pins); write(OUTPUT/'path-identities.json', identities)
        write(OUTPUT/'commands.json', commands)
        result['source_pins_sha256'] = digest(OUTPUT/'source-pins.json')
        result['artifacts'] = {str(p):digest(p) for p in sorted(OUTPUT.rglob('*')) if p.is_file() and p.name != 'result.json'}
        write(OUTPUT/'result.json', result)
    print(json.dumps(result, indent=2))
    return int(result['state'] != 'WIDE_SOC_HANDOFF_COMMITTED_ELF_BUILT_NOT_EXECUTED')


if __name__ == '__main__':
    sys.dont_write_bytecode = True
    sys.exit(main())
