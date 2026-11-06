#!/usr/bin/env python3
"""Accept a compiled RVV ELF after a narrowly scoped GCC clone-name audit.

Original build-03 remains FAIL. No arithmetic, compile diagnostics, runtime
checks or source/image identity requirements are relaxed by this audit.
"""
import argparse
import json
from pathlib import Path
import re

from audit import digest, require, verify_pins
from prepare_wide_soc import HERE, RUNS
from build_decode_rvv import BASE, COMMON, NAMES, custom_instructions
from run_wide_soc_smoke import elf_admission
from decode_rvv_data import unpack_q4_r32

BUILD = RUNS / 'e2e_decode_rvv_build_20261106_03'
BUILD_SHA = '7538276fca4b276242029902a57f5c8228dec1e31c02059b7fb4a77454de6b1d'
PINS_SHA = 'f11842d026f8cfe04f4e61a9fe3cb81a4cc779ae28ab2f875e325254d486a0a8'
ELF_SHA = 'fa87eeffd8605ae96e10f10c0c53e34db93068af9ebfe72b00535335bba6789b'


def symbols(text):
    labels = list(re.finditer(r'(?m)^([0-9a-f]+) <([^>]+)>:$', text))
    names = [row[2] for row in labels]
    require(len(names) == len(set(names)), 'Duplicate disassembly symbols')
    bodies = {row[2]: text[row.end():labels[i+1].start() if i+1 < len(labels) else len(text)]
              for i,row in enumerate(labels)}
    required = ('ggml_gemv_q4_K_32x1_q8_K', 'ggml_vec_dot_q6_K_q8_K', 'quantize_row_q8_K')
    clone = 'ggml_vec_dot_q6_K_q8_K_vl1024.isra.0'
    require(all(name in bodies for name in (*required, clone)) and
            not any(name in bodies for name in ('qbs_native_execute_command', 'qbs_ref_execute')),
            'Required genuine kernels absent or custom/reference executor present')
    require([name for name in names if name.startswith('ggml_vec_dot_q6_K_q8_K_vl1024')] == [clone],
            'Unexpected/multiple VLEN1024 clone names')
    wrapper = bodies['ggml_vec_dot_q6_K_q8_K']
    require(re.search(r'\bcsrr\s+\w+,vlenb\b', wrapper) and re.search(r'\bli\s+\w+,1024\b', wrapper) and
            re.search(r'\b(?:jr|j|jal|jalr)\b[^\n]*<'+re.escape(clone)+r'>', wrapper) and
            all(op in bodies[clone] for op in ('\tvsetvli', '\tvle8.v', '\tvwmul.vv')),
            'VLEN dispatcher does not target a real vector clone')
    return dict(required=list(required), gcc_clone=clone, dispatcher_reference_checked=True)


def main(output):
    out = output.absolute()
    require(out == out.resolve() and out.is_relative_to(RUNS), 'Fresh sole-verification audit')
    out.mkdir(parents=True, exist_ok=False)
    result = dict(state='PREPARING', runtime_accepted=False, performance_measured=False, synthesis_run=False)
    pins = {}
    try:
        require(digest(BUILD / 'build.json') == BUILD_SHA and digest(BUILD / 'source-pins.json') == PINS_SHA,
                'Unreviewed failed producer identity')
        report = json.loads((BUILD / 'build.json').read_text())
        require(report['state'] == 'FAIL' and report['error'] ==
                "ValueError('Production RVV path missing or custom/reference executor leaked')", 'Wrong failure scope')
        pins = json.loads((BUILD / 'source-pins.json').read_text()); verify_pins(pins); verify_pins(report['artifacts'])
        for path, sha in report['artifacts'].items(): pins[path] = sha
        pins[str(BUILD / 'build.json')] = BUILD_SHA
        commands = json.loads((BUILD / 'commands.json').read_text())
        require(commands[-1]['label'] == 'disassembly' and
                len([r for r in commands if r['label'].startswith('compile-')]) == 6,
                'Missing compilation/link/disassembly stages')
        link = next(r['argv'] for r in commands if r['label'] == 'link')
        actual_objects = [word for word in link if word.endswith('.o')]
        expected = [str(BUILD / f'compiled-{i}.o') for i in range(6)] + [str(BASE / '1.o')] + [str(COMMON / f'{i}.o') for i in range(3,9)]
        require(len(actual_objects) == len(set(actual_objects)) and set(actual_objects) == set(expected),
                'Unexpected object/runtime executor in baseline link')
        libraries = {}
        for name in ('libstdc++.a', 'libm.a', 'libc.a', 'libgcc.a', 'libnosys.a'):
            path = Path((BUILD / ('locate-'+name+'.log')).read_text().strip()).resolve(strict=True)
            require(pins.get(str(path)) == digest(path), 'Runtime archive unpinned'); libraries[str(path)] = digest(path)
        linked = {str(Path(p).resolve(strict=True)) for p in re.findall(r'^LOAD (.+[.]a)$',
                  (BUILD / 'link.map').read_text(), re.M)}
        require(linked == set(libraries), 'Actual runtime archive selection differs')
        symbol_check = symbols((BUILD / 'disassembly.log').read_text())
        elf = BUILD / 'decode_rvv.elf'; require(digest(elf) == ELF_SHA, 'Compiled RVV ELF identity')
        require(not custom_instructions(elf.read_bytes()), 'Custom instruction in RVV code section')
        loads = {str(w): elf_admission(elf.read_bytes(), w//8) for w in (128,256)}
        base = json.loads((BASE / 'build.json').read_text()); capture = Path(base['capture'])
        for part, name in enumerate(NAMES):
            packed = (BUILD / f'weight_{part}.bin').read_bytes()
            raw = unpack_q4_r32(packed, 128, base['k'][part]) if base['profiles'][part] == 1 else packed
            require(raw == (capture / (name+'.bin')).read_bytes(), 'Actual model bytes changed')
        for path in (Path(__file__), HERE / 'test_decode_rvv_build_audit.py'): pins[str(path)] = digest(path)
        verify_pins(pins); (out / 'source-pins.json').write_text(json.dumps(pins, indent=2)+'\n')
        result.update(state='REAL_QWEN3_DECODE_RVV_BUILD_REAUDITED_NOT_EXECUTED', producer=str(BUILD),
            producer_state='FAIL', producer_relabelled=False, producer_result_sha256=BUILD_SHA,
            source_pins_sha256=digest(out / 'source-pins.json'), checked_inputs=len(pins),
            checked_producer_artifacts=len(report['artifacts']), post_pins_match=True,
            elf=str(elf), elf_sha256=ELF_SHA, symbols=symbol_check, no_custom_opcodes=True,
            preload_segments=loads, linked_archives=libraries, m=1, n=128, outputs=896, k=base['k'],
            limitation='Build only. Independent RVV numeric oracle, cross-width repeatability, protocol and timings pending',
            adaptation='Only GCC static-kernel .isra.0 suffix; original compile FAIL report unchanged')
    except BaseException as exc:
        result.update(state='FAIL', error=repr(exc)); raise
    finally: (out / 'result.json').write_text(json.dumps(result, indent=2)+'\n')


if __name__ == '__main__':
    p = argparse.ArgumentParser(description=__doc__); p.add_argument('--output', type=Path, required=True)
    main(p.parse_args().output)
