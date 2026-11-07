#!/usr/bin/env python3
"""Build-only registered M4 successor of the committed QBS/AKV/RVV handoff."""

import argparse
import hashlib
import json
import os
from pathlib import Path
import re
import shlex
import shutil
import struct
import subprocess
import sys

import wide_soc_memory_smoke_handoff_build as parent

HERE = Path(__file__).resolve().parent
BASE = parent.OUTPUT
BASE_SHA = '8e2df9b622fb4df7ba3936f4a558b0c7dea1da138b7ef1a7be9459f09f2b9b60'
OUTPUT = parent.memory.VERIFY / 'verification/out/e2e_balanced_soc_handoff_build_20261106_01'
SOURCE_REL = 'apps/qbs_akv_handoff_smoke/main.c'
SOURCE_SHA = 'd532ca577d6f2f8ef93d2680f7fd98523c237c08638ab47b4b1f644a98df5198'
SCOPE = 'BALANCED_M4_HANDOFF_SCOPE m=4 n=3 k_blocks=1 qbs=4 checked_words=256 rvv=3 akv_full=3'
PASS = 'Balanced M4 QBS/AKV handoff smoke: PASS traps=0'
EXPECTED_CHECKS = dict(m=4, qbs_exec_commands=4, qbs_checked_calls=2, qbs_checked_values=256,
                       akv_v2_full_commands=3, akv_v1_row_loads=4, akv_checked_values=256,
                       akv_releases=3, rvv_calls=3, rvv_checked_values=96, expected_exceptions=0)
require, digest = parent.require, parent.digest


def transform(source):
    require(isinstance(source, str) and hashlib.sha256(source.encode()).hexdigest() == SOURCE_SHA,
            'Exact committed handoff source required')
    text, edits = source, []

    def edit(before, after, count=1):
        nonlocal text
        require(text.count(before) == count, 'Handoff exact anchor: ' + before[:70])
        text = text.replace(before, after)
        edits.append(dict(before=before, after=after, count=count))

    edit('''static const qbs_block_q8_k_t qbs_activation
    __attribute__((aligned(64))) = Q8_BLOCK(1);''',
         '''static const qbs_block_q8_k_t qbs_activation[4]
    __attribute__((aligned(64))) = {
        Q8_BLOCK(1), Q8_BLOCK(2), Q8_BLOCK(3), Q8_BLOCK(4)};''')
    edit('static uint32_t qbs_observed[32]', 'static uint32_t qbs_observed[128]')
    begin = source.index('static void issue_qbs_m1(int store_result) {')
    end = source.index('\nstatic void issue_akv_v2_full(void)', begin)
    old = source[begin:end]
    new = old.replace('issue_qbs_m1', 'issue_qbs_m4')
    for before, after in (('li t0, 32', 'li t0, 128'), ('e32, m1, ta, ma', 'e32, m4, ta, ma'),
                          ('0x00b5045b', '0x06b5045b'),
                          ('"t0", "v8", "memory"', '"t0", "v8", "v9", "v10", "v11", "memory"')):
        require(new.count(before) == 2, 'Both M4 instruction branches required')
        new = new.replace(before, after)
    poison_anchor = '"vsetvli zero, t0, e32, m4, ta, ma\\n"\n                 ".word'
    require(new.count(poison_anchor) == 2, 'Checked/discard M4 branch identity')
    # Only the checked branch poisons VRF; adjacent discard transfers retain
    # their original instruction sequence apart from M4 vtype/opcode.
    new = new.replace(poison_anchor,
                      '"vsetvli zero, t0, e32, m4, ta, ma\\n"\n'
                      '                 "vmv.v.i v8, -1\\n"\n                 ".word', 1)
    edit(old, new)
    begin = source.index('static int check_qbs(void) {')
    end = source.index('\nstatic int check_rvv(', begin)
    edit(source[begin:end], '''static int check_qbs(void) {
  static const uint32_t expected_results[4][3] = {
      {0x43800000u, 0x44000000u, 0x44400000u},
      {0x44000000u, 0x44800000u, 0x44c00000u},
      {0x44400000u, 0x44c00000u, 0x45100000u},
      {0x44800000u, 0x45000000u, 0x45400000u}};
  for (size_t index = 0; index < 128; ++index)
    qbs_observed[index] = 0xa5a5a5a5u;
  const uint64_t before = trap_count;
  issue_qbs_m4(1);
  if (check_no_trap("QBS M4", before)) return 1;

  int failures = 0;
  for (size_t row = 0; row < 4; ++row) {
    for (size_t col = 0; col < 32; ++col) {
      const uint32_t expected = col < 3 ? expected_results[row][col] : 0;
      const size_t index = 32 * row + col;
      if (qbs_observed[index] != expected) {
        printf("QBS M4 mismatch[row=%d col=%d]: got=%x expected=%x\\n",
               (int)row, (int)col, qbs_observed[index], expected);
        ++failures;
      }
    }
  }
  return failures;
}
''')
    edit('issue_qbs_m1(0);', 'issue_qbs_m4(0);', 2)
    edit('  initialize_descriptors();', '  initialize_descriptors();\n  printf("' + SCOPE + '\\n");')
    edit('QBS/AKV handoff smoke:', 'Balanced M4 QBS/AKV handoff smoke:', 3)
    restored = text
    for item in reversed(edits):
        require(restored.count(item['after']) == item['count'], 'Ambiguous handoff inverse')
        restored = restored.replace(item['after'], item['before'])
    require(restored == source, 'Original handoff source must restore byte-for-byte')
    return text, dict(source_sha256=SOURCE_SHA, generated_sha256=hashlib.sha256(text.encode()).hexdigest(),
                      edits=edits, source_reversible=True, m=4, n=3, k_blocks=1,
                      opcode='06b5045b', vtype='e32,m4,ta,ma', vl=128,
                      activation_rows=4, checked_qbs_words=256, checked_nonzero_words=24,
                      checked_zero_tail_words=232, checked_vrf_poison_calls=2,
                      original_akv_and_three_rvv_checks_unchanged=True,
                      discarded_transfer_branches_have_no_new_vlsu_request=True)


def recipe(argv, output):
    source = BASE / 'archive-input' / SOURCE_REL
    target = output / 'source' / 'main.c'
    old_include = '-I' + str(BASE / 'archive-input/apps/common')
    return [str(target) if a == str(source) else
            '-I' + str(output / 'source/common') if a == old_include else
            str(output / 'handoff-main.o') if a == str(BASE / 'handoff-main.o') else
            str(output / 'balanced_soc_handoff.elf') if a == str(BASE / 'qbs_akv_handoff_smoke.elf') else
            a.replace('-Map=' + str(BASE / 'link.map'), '-Map=' + str(output / 'link.map')) for a in argv]


def elf_objects(raw):
    require(raw[:6] == b'\x7fELF\x02\x01', 'ELF64 little-endian required')
    h = struct.unpack_from('<16sHHIQQQIHHHHHH', raw)
    require(h[2] == 243 and h[11] == 64 and h[6] + 64 * h[12] <= len(raw), 'RISC-V section table')
    sections = [struct.unpack_from('<IIQQQQIIQQ', raw, h[6] + 64 * i) for i in range(h[12])]
    objects = {}
    for section in sections:
        if section[1] != 2:
            continue
        require(section[9] == 24 and section[6] < len(sections), 'Symbol table geometry')
        names = sections[section[6]]
        strings = raw[names[4]:names[4] + names[5]]
        for at in range(section[4], section[4] + section[5], 24):
            name, info, _, index, address, size = struct.unpack_from('<IBBHQQ', raw, at)
            if info & 15 != 1 or not (0 < index < len(sections)):
                continue
            label = strings[name:].split(b'\0', 1)[0].decode()
            sec = sections[index]
            data = None if sec[1] == 8 else raw[sec[4] + address - sec[3]:sec[4] + address - sec[3] + size]
            require(label not in objects and (data is None or len(data) == size), 'Object symbol identity')
            objects[label] = dict(address=address, size=size, data=data)
    return objects


def payload_proof(original, candidate):
    old, new = elf_objects(original), elf_objects(candidate)
    expected = b''.join(struct.pack('<f', 1.0) + bytes([row]) * 256 + struct.pack('<16h', *([16 * row] * 16))
                        for row in (1, 2, 3, 4))
    require(new['qbs_activation']['size'] == 1168 and new['qbs_activation']['data'] == expected and
            new['qbs_observed']['size'] == 512, 'Actual ELF M4 activation/output geometry')
    names = ('qbs_weights', 'akv_query', 'akv_key', 'akv_value')
    require(all(old[n]['data'] == new[n]['data'] and old[n]['size'] == new[n]['size'] for n in names),
            'Inherited weight or AKV payload changed')
    return dict(activation_bytes=1168, activation_values=[1, 2, 3, 4], output_bytes=512,
                unchanged_payloads={n: hashlib.sha256(new[n]['data']).hexdigest() for n in names})


def check_log(text):
    """Check UART evidence only; a runtime consumer still needs SoC/protocol/EOC gates."""
    require(not re.search(r'(?i)\bFAIL\b|\bSKIP\b|mismatch|\btrapped\b|Fatal:|Error[-:]|'
                          r'UVM_(?:ERROR|FATAL)|mcause_val|timeout', text), 'Handoff failure/skip/exception')
    lines = text.replace('\r', '').splitlines()
    require(lines.count(SCOPE) == 1 and [l for l in lines if 'handoff smoke:' in l] == [PASS] and
            lines.index(SCOPE) < lines.index(PASS), 'Unique M4 scope/terminal required')
    return dict(EXPECTED_CHECKS)


def instruction_contract(disassembly):
    instructions = re.findall(r'^\s*[0-9a-f]+:\s+([0-9a-f]{8})\s', disassembly, re.M)
    require(instructions.count('06b5045b') >= 2 and '00b5045b' not in instructions,
            'Actual ELF lacks M4 branches or retained M1 opcode')
    require(len(re.findall(r'vsetvli\s+zero,t0,e32,m4,ta,ma', disassembly)) >= 2 and
            len(re.findall(r'addi\s+t0,zero,128', disassembly)) >= 2,
            'Actual ELF M4/VL128 setup missing')
    for opcode in ('0005155b', '0005455b', '00b5605b', '0005345b', '0000505b'):
        require(opcode in instructions, 'Inherited custom instruction missing: ' + opcode)
    require('pmpaddr0' in disassembly and not re.search(r'\b(?:satp|pmpcfg\w*)\b', disassembly),
            'Unchanged startup PMP/satp contract')
    return dict(static_opcode_sites=instructions.count('06b5045b'), opcode='06b5045b', vl=128,
                vtype='e32,m4,ta,ma', inherited_custom_instructions_present=True)


def build(output=OUTPUT):
    require(output.absolute() == OUTPUT and output.resolve() == output.absolute(), 'Assigned fresh build output only')
    out = output.absolute()
    out.mkdir(parents=True, exist_ok=False)
    pins, paths, commands = {}, {}, []
    result = dict(state='FAIL', target_executed=False, rtl_executed=False, simulations_launched=0,
                  performance_measured=False, production_rtl_changed=False, sdk_used=False)

    def pin(path, expected=None):
        lexical = Path(path).absolute()
        real = lexical.resolve(strict=True)
        actual = digest(real)
        require(expected is None or actual == expected, 'Input identity: ' + str(path))
        require(str(lexical) not in paths or paths[str(lexical)] == str(real), 'Path retargeted')
        require(str(real) not in pins or pins[str(real)] == actual, 'Input changed')
        paths[str(lexical)], pins[str(real)] = str(real), actual
        return actual

    def verify():
        require(all(str(Path(p).resolve(strict=True)) == r for p, r in paths.items()), 'Path identity drift')
        require(all(digest(p) == s for p, s in pins.items()), 'Input/tool/object drift')

    def save(name, value):
        with (out / name).open('x') as stream:
            json.dump(value, stream, indent=2, sort_keys=True)
            stream.write('\n')

    env = {k: v for k, v in os.environ.items() if k not in (
        'LD_PRELOAD', 'LD_LIBRARY_PATH', 'CPATH', 'C_INCLUDE_PATH', 'CPLUS_INCLUDE_PATH',
        'GCC_EXEC_PREFIX', 'COMPILER_PATH', 'LIBRARY_PATH')}
    env.update(PATH='/usr/bin:/bin', LC_ALL='C', PYTHONDONTWRITEBYTECODE='1')

    def run(argv, label):
        argv = list(map(str, argv))
        pin(argv[0])
        verify()
        row = dict(label=label, argv=argv, cwd=str(out), timeout_seconds=120)
        commands.append(row)
        child = subprocess.run(argv, cwd=out, env=env, capture_output=True, timeout=120)
        (out / (label + '.log')).write_bytes(child.stdout + child.stderr)
        row['returncode'] = child.returncode
        require(child.returncode == 0, label + ' failed; evidence retained')
        verify()
        return child.stdout.decode()

    try:
        pin(BASE / 'result.json', BASE_SHA)
        old = json.loads((BASE / 'result.json').read_text())
        require(old['state'] == 'WIDE_SOC_HANDOFF_COMMITTED_ELF_BUILT_NOT_EXECUTED' and old['post_pins_match'],
                'Exact accepted committed handoff build required')
        pin(BASE / 'source-pins.json', old['source_pins_sha256'])
        inherited = json.loads((BASE / 'source-pins.json').read_text())
        pin(BASE / 'commands.json', old['artifacts'][str(BASE / 'commands.json')])
        pin(old['elf'], old['elf_sha256'])
        source = BASE / 'archive-input' / SOURCE_REL
        pin(source, SOURCE_SHA)
        text, proof = transform(source.read_text())
        folder = out / 'source'
        (folder / 'common').mkdir(parents=True)
        generated = folder / 'main.c'
        generated.write_text(text)
        pin(generated, proof['generated_sha256'])
        for relative, (_, expected) in parent.INPUTS.items():
            if relative == SOURCE_REL:
                continue
            src = BASE / 'archive-input' / relative
            pin(src, expected)
            dst = folder / 'common' / Path(relative).name
            shutil.copyfile(src, dst)
            pin(dst, expected)
        for key in ('driver', 'cc1', 'as', 'collect2', 'ld'):
            tool = Path(old['toolchain'][key])
            pin(tool, inherited[str(tool.resolve())])
        for path, expected in old['reused_common_objects'].items():
            pin(path, expected)
        require(len(old['reused_common_objects']) == 4, 'Four original common objects required')
        pin(old['reused_linker'], old['reused_linker_sha256'])
        loader = parent.memory.MAIN / 'hardware/tb/dpi/elfloader.cc'
        pin(loader, old['loader_source_sha256'])
        parent.loader_contract(loader.read_text())
        records = json.loads((BASE / 'commands.json').read_text())
        recipes = {}
        for label in ('dependencies', 'compile-main', 'link'):
            selected = [r for r in records if r['label'] == label]
            require(len(selected) == 1 and selected[0]['returncode'] == 0, 'Original recipe inventory')
            recipes[label] = recipe(selected[0]['argv'], out)
        for token in recipes['link']:
            if token.endswith('.a'):
                pin(token, inherited[str(Path(token).resolve())])
        for module in tuple(sys.modules.values()):
            path = getattr(module, '__file__', None)
            if path and Path(path).is_file() and Path(path).resolve().parent == HERE:
                pin(path, inherited.get(str(Path(path).resolve())))
        pin(HERE / 'test_balanced_soc_handoff.py')
        pin(sys.executable)
        save('transform.json', proof)
        dep = run(recipes['dependencies'], 'dependencies')
        for name in shlex.split(dep.replace('\\\n', ' ').split(':', 1)[1]):
            path = Path(name).resolve(strict=True)
            if str(path) in pins:
                pin(path, pins[str(path)])
            else:
                require(str(path) in inherited, 'Unaccepted compiler header: ' + str(path))
                pin(path, inherited[str(path)])
        run(recipes['compile-main'], 'compile-main')
        require(not re.search(r'warning:|error:', (out / 'compile-main.log').read_text(), re.I),
                'Review new compiler diagnostic')
        pin(out / 'handoff-main.o')
        run(recipes['link'], 'link')
        elf = out / 'balanced_soc_handoff.elf'
        pin(elf)
        cc = Path(old['toolchain']['driver'])
        readelf, objdump = cc.with_name('riscv64-unknown-elf-readelf'), cc.with_name('riscv64-unknown-elf-objdump')
        for path in (readelf, objdump):
            pin(path, inherited[str(path.resolve())])
        sections = run([readelf, '-W', '-S', elf], 'sections')
        programs = run([readelf, '-W', '-l', elf], 'program-headers')
        admission = parent.loader_admission(sections, programs)
        actual_payload = payload_proof(Path(old['elf']).read_bytes(), elf.read_bytes())
        disassembly = run([objdump, '-d', '-M', 'no-aliases', elf], 'disassembly')
        actual_instructions = instruction_contract(disassembly)
        run([sys.executable, '-B', '-m', 'unittest', 'test_balanced_soc_handoff', '-v'], 'host-tests')
        verify()
        result.update(state='BALANCED_SOC_M4_HANDOFF_ELF_BUILT_NOT_EXECUTED',
            elf=str(elf), elf_sha256=digest(elf), compiled_translation_units=1,
            original_build_sha256=BASE_SHA, committed_source_sha256=SOURCE_SHA,
            generated_source_sha256=proof['generated_sha256'], source_transform_reversible=True,
            common_objects_recompiled=False, reused_common_objects=old['reused_common_objects'],
            reused_linker=old['reused_linker'], reused_linker_sha256=old['reused_linker_sha256'],
            toolchain=old['toolchain'], expected_runtime_checks=dict(EXPECTED_CHECKS),
            required_scope=SCOPE, required_terminal=PASS, skip_is_not_acceptance=True,
            loader_admission=admission, actual_elf_payload=actual_payload,
            actual_elf_instructions=actual_instructions,
            pmp_satp=dict(app_touches_pmp=False, app_touches_satp=False,
                          startup_writes=['pmpaddr0'], permission_or_translation_test=False),
            post_pins_match=True, limits=[
                'Build and static opcode/payload proof only; no actual QBS/AKV/RVV handoff execution accepted',
                'All four QBS commands use M4; checked calls poison VRF/output and verify all four rows and zero tails',
                'Original three RVV checks, AKV payloads and adjacent discard ownership transfers retained',
                'No SDK, local AKV assembly, RTL, synthesis, FPGA or performance changes'])
    except BaseException as exc:
        result.update(state='FAIL', error=repr(exc))
        raise
    finally:
        try:
            verify()
        except Exception as exc:
            result.update(state='FAIL', post_pins_match=False, pin_error=repr(exc))
        save('commands.json', commands)
        save('source-pins.json', pins)
        save('path-identities.json', paths)
        result['source_pins_sha256'] = digest(out / 'source-pins.json')
        result['artifacts'] = {str(p): digest(p) for p in out.rglob('*') if p.is_file() and p.name != 'result.json'}
        save('result.json', result)
    require(result['state'] == 'BALANCED_SOC_M4_HANDOFF_ELF_BUILT_NOT_EXECUTED', 'Build failed')
    print(json.dumps(dict(state=result['state'], elf=result['elf'], elf_sha256=result['elf_sha256'],
                          result_sha256=digest(out / 'result.json'))))
    return result


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--build', action='store_true')
    args = parser.parse_args()
    require(args.build, 'Explicit isolated ELF build required')
    build()
