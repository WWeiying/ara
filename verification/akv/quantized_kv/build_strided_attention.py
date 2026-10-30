#!/usr/bin/env python3
"""Build-only fair-RVV strided-KV successor; never launch a simulator."""
import argparse
import importlib.util
from pathlib import Path
import re
import shlex
import subprocess
import sys

sys.dont_write_bytecode = True
HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[2]
sys.path.insert(0, str(HERE))
from run_common_attention import checked_build, s
from capture_host import validate_capture

CAPTURE = ROOT / 'verification/out/akv-quantkv-host-capture-20261024-01'
RUNTIME = ROOT / 'software/akv/experimental/quantized_kv/runtime_strided.c'
MAIN = HERE / 'attention_strided_main.c'
TEST = HERE / 'test_strided_attention_build.py'


def require_fair(report):
    s.require(report.get('rvv_value_decode') is True and
              report.get('rvv_baseline_decode') is True and
              report.get('ordinary_value_decode') == 'same RVV decoder as candidate' and
              report.get('scope') == 'Public-entry ABBA; both schedules use identical RVV V decoder',
              'Predecessor must be the matched-RVV-decoder build')


def interleave(metadata, raw, kind):
    """Exact two-head/capacity256 byte permutation, including masked rows."""
    s.require(kind in ('q8_0', 'q4_0'), 'Unsupported capture encoding')
    block = 18 if kind == 'q4_0' else 34
    row = block * 4
    s.require(metadata.get('type') == kind and metadata.get('shape') == [128, 256, 2, 1] and
              metadata.get('strides') == [block, row, 256 * row, 512 * row] and
              metadata.get('nbytes') == len(raw) == 512 * row, 'Unexpected full capture KV metadata')
    physical = bytearray(len(raw))
    for head in range(2):
        for token in range(256):
            source = (head * 256 + token) * row
            target = (token * 2 + head) * row
            physical[target:target + row] = raw[source:source + row]
    # Verify every logical row independently through the final physical strides.
    for head in range(2):
        for token in range(256):
            s.require(physical[token * (2 * row) + head * row:token * (2 * row) + head * row + row] ==
                      raw[head * 256 * row + token * row:head * 256 * row + token * row + row],
                      'Physical KV row differs from capture')
    return bytes(physical)


def command_templates(records, base):
    original = str(HERE / 'attention_rvv_baseline_main.c')
    compiles = [r['argv'] for r in records if '-c' in r['argv'] and original in r['argv']]
    links = [r['argv'] for r in records if '-nostdlib' in r['argv']]
    s.require(len(compiles) == len(links) == 1, 'Ambiguous predecessor commands')
    compile_command, link = list(compiles[0]), list(links[0])
    s.require(compile_command.count(original) == 1 and link.count(str(base / 'main.o')) == 1,
              'Wrong predecessor main')
    fp = [arg for arg in compile_command if arg.startswith('-ffp-contract=')]
    s.require(fp == ['-ffp-contract=fast'] and '-fno-fast-math' in compile_command and
              '-ffast-math' not in compile_command and '-Ofast' not in compile_command and
              '-ffunction-sections' in compile_command and '-fdata-sections' in compile_command and
              '-march=rv64gcv_zfh_zvfh' in compile_command and '-Werror' in compile_command and
              Path(compile_command[0]).name == 'riscv64-unknown-elf-gcc' and
              link.count('-Wl,--gc-sections') == 1 and link.count('-o') == 1 and
              sum(x.startswith('-Wl,-Map=') for x in link) == 1,
              'Compiler/FP/GC policy differs from accepted GNU build')
    return compile_command, link


def verify_disassembly(text):
    required = ('strided_value_decode', 'akv_quant_strided_execute', 'quantize_row_q8_0',
                'ggml_vec_dot_q4_0_q8_0', 'ggml_vec_dot_q8_0_q8_0',
                'quant_kv_ggml_mad_f32', 'quant_kv_ggml_scale_f32', 'qbs_native_execute_command')
    for name in required:
        s.require('<' + name + '>:' in text, 'Required implementation absent: ' + name)
    for name in ('qbs_ref_execute', 'archived_main', 'archived_attention_main',
                 'dequantize_row_q8_0', 'fair_value_decode', 'value_rvv_decode'):
        s.require(re.search(r'<'+re.escape(name)+r'(?:[.][^>]*)?>:', text) is None,
                  'Forbidden old/reference implementation retained: ' + name)
    decoder = text.split('<strided_value_decode>:', 1)[1].split('\n\n', 1)[0]
    for operation in ('vle8.v', 'vsext.vf4', 'vfcvt.f.x.v', 'vfmul.vf', 'vse32.v'):
        s.require(operation in decoder, 'RVV decoder instruction missing: ' + operation)
    main = text.split('<main>:', 1)[1].split('\n\n', 1)[0]
    s.require(re.search(r'vsetivli\s+zero,\s*1,\s*e32,\s*m1', main) is not None and
              re.search(r'vmv[.]v[.]i\s+v8,\s*0', main) is not None and
              re.search(r'vmv[.]x[.]s\s+zero,\s*v8', main) is not None,
              'Legal vtype/defined v8/drain not present in live main')


def capture_payloads(kind, pins):
    receipt = s.read_json(CAPTURE / 'result.json')
    s.require(receipt['state'] == 'REAL_HOST_QUANTIZED_KV_CAPTURED' and
              s.digest(CAPTURE / 'source-pins.json') == receipt['source_pins_sha256'], 'Capture provenance drift')
    directory = CAPTURE / ('capture-k-' + kind + '-v-q8_0')
    checked = validate_capture(directory, kind)
    s.require(checked == receipt['captures'][kind] and checked['visible_tokens'] == 128,
              'Accepted capture bytes/metadata changed')
    s.merge_pins(pins, checked['file_sha256'])
    s.merge_pins(pins, s.hashes([CAPTURE / 'result.json', CAPTURE / 'source-pins.json']))
    data = directory / 'decode/block'
    qmeta, golden = (s.read_json(data / (name + '.json')) for name in ('attn_q_input-0', 'kqv_out-0'))
    s.require(qmeta['shape'] == [128, 1, 12, 1] and qmeta['strides'] == [4, 512, 512, 6144] and
              qmeta['type'] == 'f32' and golden['shape'] == [1536, 1, 1, 1] and golden['type'] == 'f32',
              'Original Query/golden group coordinates differ')
    s.require((data / 'attn_mask_input-0.bin').read_bytes() == bytes(256) + b'\x00\xfc' * 128,
              'Capture is not the original visible128 prefix')
    payloads, sources = {}, {}
    for label, encoding in (('key', kind), ('value', 'q8_0')):
        name = 'attn_' + label[0] + '_input-0'
        path = data / (name + '.bin')
        metadata = s.read_json(data / (name + '.json'))
        payloads[label] = interleave(metadata, path.read_bytes(), encoding)
        sources[label] = dict(path=str(path), sha256=pins[str(path)], metadata_path=str(data / (name + '.json')))
    return payloads, sources


def build(base, out):
    base, out = base.resolve(strict=True), out.resolve()
    s.require(not out.is_relative_to(base) and not base.is_relative_to(out), 'Use an independent fresh output')
    report, pins = checked_build(base)
    require_fair(report)
    compiler_template, old_link = command_templates(s.read_json(base / 'commands.json'), base)
    simv = Path(report['simv'])
    image = report['accepted_image_pins']
    s.require(s.hashes(s.image_files(simv)) == image, 'Accepted simulator identity differs')
    conf = dict(line.split('=', 1) for line in (simv.parent / 'simulator.conf').read_text().splitlines() if '=' in line)
    s.require(conf.get('sim_l2_bytes') == '16777216' and conf.get('qbs_enabled') == '1', 'Require accepted 16MiB QBS image')
    helper = ROOT / 'verification/akv/refill_overlap_probe/build.py'
    image_check = ROOT / 'hardware/scripts/llama_q4km_extract/check-sim-l2.sh'
    compiler = Path(compiler_template[0])
    objdump = compiler.with_name('riscv64-unknown-elf-objdump')
    own = [Path(__file__), MAIN, TEST, RUNTIME, helper, image_check,
           HERE / 'run_common_attention.py', HERE / 'capture_host.py', HERE / 'layout.py',
           base / 'commands.json', compiler, compiler.resolve(), objdump, objdump.resolve(),
           Path(sys.executable).resolve(), Path('/usr/bin/readelf')]
    s.merge_pins(pins, s.hashes(own))
    # Refuse to bless newly observed bytes over any predecessor pin.
    original_objects = [Path(x) for x in old_link if x.endswith(('.o', '.a'))]
    for path in original_objects:
        s.require(pins.get(str(path)) == s.digest(path), 'Original object absent from pins or changed: ' + str(path))
    payloads, source_files = capture_payloads(report['kind'], pins)
    s.verify_pins(pins)
    out.mkdir(parents=True, exist_ok=False)
    commands = []

    def execute(argv, label):
        argv = list(map(str, argv))
        commands.append(dict(argv=argv, cwd=str(out)))
        s.atomic_json(out / 'commands.json', commands)
        with (out / (label + '.log')).open('x') as log:
            subprocess.run(argv, cwd=out, stdout=log, stderr=subprocess.STDOUT, check=True, timeout=180)
        return (out / (label + '.log')).read_text()

    try:
        data_paths = {}
        for label, payload in payloads.items():
            path = out / ('attention_strided_' + label + '.bin')
            path.write_bytes(payload)
            s.require(path.read_bytes() == payload, 'Generated physical KV write differs')
            data_paths[label] = path
        assembly = out / 'strided-data.S'
        assembly.write_text('.section .rodata,"a",@progbits\n' + ''.join(
            f'.balign 64\n.global attention_strided_{label}\nattention_strided_{label}:\n.incbin "{path}"\n'
            for label, path in data_paths.items()))
        s.merge_pins(pins, s.hashes([assembly, *data_paths.values()]))
        original = str(HERE / 'attention_rvv_baseline_main.c')
        new_objects = []
        for source, name in ((MAIN, 'main'), (RUNTIME, 'runtime-strided'), (assembly, 'strided-data')):
            command = list(compiler_template)
            command[command.index(original)] = str(source)
            target = out / (name + '.o')
            command[command.index('-o') + 1] = str(target)
            excluded = {command.index('-c'), command.index('-o'), command.index('-o') + 1}
            deps = execute([x for i, x in enumerate(command) if i not in excluded] + ['-M', '-MT', 'object'], 'deps-' + name)
            dependencies = [Path(x).resolve(strict=True) for x in shlex.split(deps.replace('\\\n', ' ').split(':', 1)[1])]
            s.merge_pins(pins, s.hashes(dependencies))
            s.verify_pins(pins)
            execute(command, 'compile-' + name)
            new_objects.append(target)
        elf = out / 'strided_attention.elf'
        link = [str(new_objects[0]) if x == str(base / 'main.o') else
                '-Wl,-Map=' + str(out / 'link.map') if x.startswith('-Wl,-Map=') else x for x in old_link]
        link[link.index('-o') + 1] = str(elf)
        link[link.index('-Wl,--gc-sections'):link.index('-Wl,--gc-sections')] = list(map(str, new_objects[1:]))
        execute(link, 'link')
        disassembly = execute([objdump, '-d', elf], 'disassembly')
        verify_disassembly(disassembly)
        spec = importlib.util.spec_from_file_location('strided_attention_elf', helper)
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        sections = module.alloc_sections(elf)
        s.require(sections and min(x['address'] for x in sections) >= 0x80000000 and
                  max(x['address'] + x['bytes'] for x in sections) < 0x81000000 - 65536, 'ELF exceeds reserved 16MiB bounds')
        execute(['bash', image_check, simv.parent, elf], 'image-contract')
        s.require(s.hashes(s.image_files(simv)) == image, 'Simulator inventory drift during build')
        s.verify_pins(pins)
        s.atomic_json(out / 'source-pins.json', pins)
        updated = dict(report)
        updated.update(state='STRIDED_ENTRY_BUILT_NOT_EXECUTED', execution='NOT_RUN',
                       elf=str(elf), elf_sha256=s.digest(elf), sections=sections,
                       predecessor_common_build=str(base), common_entry=False, strided_entry=True,
                       mapping_timed=True, admission_timed=True, gather_timed=True,
                       rvv_value_decode=True, rvv_baseline_decode=True,
                       ordinary_value_decode='same RVV decoder as candidate',
                       key_token_stride=144 if report['kind'] == 'q4_0' else 272,
                       value_token_stride=272, workspace_bytes=13120, kv_capacity=256,
                       physical_kv_heads=2, selected_kv_heads=1, expected_commands=16,
                       expected_panels_per_candidate=4,
                       expected_copied_bytes_per_candidate=9216 if report['kind'] == 'q4_0' else 17408,
                       physical_data={label: dict(path=str(path), sha256=s.digest(path),
                                                  bytes=path.stat().st_size, source=source_files[label])
                                      for label, path in data_paths.items()},
                       entry_initialization='Legal e32/m1 VL1 and defined v8 before each pre-window drain',
                       scope='Original six-query-head KV-head-0 group only; both schedules read identical token-major KV and use the same RVV V decoder; not whole-model execution',
                       source_pins_sha256=s.digest(out / 'source-pins.json'), post_pins_match=True,
                       artifact_sha256=s.hashes(p for p in out.iterdir() if p.is_file()))
        s.atomic_json(out / 'build.json', updated)
        print('STRIDED_ENTRY_BUILT_NOT_EXECUTED', report['kind'], 'commands=16 sim_launched=0')
    except BaseException as exc:
        s.atomic_json(out / 'build.json', dict(state='FAIL', execution='NOT_RUN', error=repr(exc)))
        raise


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--base', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    build(args.base, args.output)


if __name__ == '__main__':
    main()
