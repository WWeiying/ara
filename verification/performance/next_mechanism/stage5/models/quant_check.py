"""Exact source-bound Qwen2.5 Q4_0/Q8_0 KV content/native-entry audit."""
import hashlib
import importlib.util
import json
from pathlib import Path
import shlex

HERE = Path(__file__).resolve().parent
OUT = Path('/home/wangwy/openproject/ara_dsa_signoff_integration/verification/out')
BUILD = OUT/'stage5_libraries_build_20261110_01'
PREPARED = OUT/'stage5_libraries_prepare_20261110_02'
INPUTS = OUT/'stage5_libraries_prepare_20261110_01/inputs'
BUILD_SHA = 'f47864d88068b2aec18b7f63c9578d2bfeabd9e59f3fde5c5b0b386ece3b21fd'
PREFILL_SHA = '2d00cd0f6fb7218889fa88e3d8f9ce3c5285867441cf645d3bda237731495267'
BINDING_SHA = '5385247e7032bb09286a53e663efd39666751a3609b45b9bcb4bc58a11f2603b'
CPU = OUT/'stage5_qemu_prepare_variant_20261110_04/qemu-10.2.0/accel/tcg/cpu-exec.c'
CPU_SHA = '96c9c88df8d0a7b432993f250784e635c810ac1de5552529eae0eb6e1e6886a7'
SHAPE = dict(id='qwen25_q4kv', cache_k='q4_0', cache_v='q8_0', head_dim=128,
             prompt_tokens=40, layers=28, kv_heads=2, q_heads=12,
             logical_contexts=[40, 41, 42], vocabulary=151936,
             resident_decode=False, prefill_resident_commands=0,
             formats=['Q4_0', 'Q6_K'])
SHAPES = {SHAPE['id']: SHAPE,
          'qwen25_q8kv': dict(SHAPE, id='qwen25_q8kv', cache_k='q8_0')}


def require(ok, message):
    if not ok:
        raise ValueError(message)


def sha(path):
    h = hashlib.sha256()
    with path.open('rb') as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b''):
            h.update(block)
    return h.hexdigest()


def read(path):
    def unique(rows):
        result = {}
        for k, v in rows:
            require(k not in result, 'Duplicate JSON key')
            result[k] = v
        return result
    return json.loads(path.read_text(), object_pairs_hook=unique)


def load(path, digest, name):
    require(sha(path) == digest, 'Frozen checker source drift: ' + str(path))
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def compiled_sources():
    """Anchor formulas to the delivered library receipt, not mutable SDK copies."""
    evidence = {}

    def pin(path, digest):
        require(sha(path) == digest, 'Compiled source/manifest drift: ' + str(path))
        evidence[str(path)] = digest

    pin(BUILD/'build.json', BUILD_SHA)
    build = read(BUILD/'build.json')
    pin(PREPARED/'prepare.json', build['prepare_sha256'])
    pin(PREPARED/'source-pins.json', build['source_pins_sha256'])
    pins = read(PREPARED/'source-pins.json')
    for path in (BUILD/'compiler-dependencies.json', BUILD/'build/compile_commands.json'):
        pin(path, build['artifacts'][str(path)])
    deps = read(BUILD/'compiler-dependencies.json')
    commands = read(BUILD/'build/compile_commands.json')
    arch = INPUTS/'llama/ggml/src/ggml-cpu/arch/riscv'
    sdk = INPUTS/'sdk'
    sources = {k: v for k, v in pins.items()
               if k.startswith(str(sdk) + '/') and Path(k).suffix in ('.c', '.h')}
    require(bool(sources), 'Missing pinned SDK formula sources')
    for name in ('quant-kv.cpp', 'qbs.cpp'):
        path = str(arch/name)
        require(deps[path] == pins[path], 'Compiled source dependency differs')
        sources[path] = pins[path]
        rows = [r for r in commands if r['file'] == path]
        require(len(rows) == 1, 'Missing/duplicate compiled quant/QBS source')
        flags = shlex.split(rows[0]['command'])
        require(all('-D' + f in flags for f in
                    ('GGML_USE_RISCV_QUANT_KV', 'GGML_USE_RISCV_QUANT_PREFILL',
                     'GGML_USE_RISCV_REGISTER_PV')), 'Quant build feature drift')
    quant = sdk/'software/akv/experimental/quantized_kv'
    required = ('prefill/execute.h', 'prefill/prefix_schedule.h', 'prefill/prefix_panel.h',
                'prefill/native_prefix.h', 'native.h', 'online.h', 'runtime_strided.c',
                'register_pv/runtime.c', 'register_pv/online.h',
                'selection.h', 'selection_strided.h', 'runtime.h')
    require(all(str(quant/n) in sources for n in required), 'Missing SDK formula closure')
    for row in commands:
        if row['file'].startswith(str(quant) + '/'):
            require(row['file'] in sources, 'Unpinned compiled quant SDK source')
    for path, digest in sources.items():
        pin(Path(path), digest)
    pin(CPU, CPU_SHA)
    pin(HERE/'prefill_check.py', PREFILL_SHA)
    return evidence


def workspace_sizes():
    """RV64 LP64 layouts translated from the source-hashed SDK structures."""
    def aligned(size, alignment):
        return (size + alignment - 1) // alignment * alignment

    # online.h: score[8][32], value[256], maximum[8], sum[8].
    online = aligned(4 * (8 * 32 + 256 + 8 + 8), 64)
    # native.h: Q8 queries[8][8*34], aligned descriptor[64], online.
    native = aligned(aligned(8 * 8 * 34, 64) + 64 + online, 64)
    panel_bytes = 32 * 8 * 34
    # native_prefix.h: five pointers + unsigned; visible pointer, unsigned,
    # then aligned Q8 query storage for four rows.
    context = aligned(5 * 8 + 4, 8)
    prefix_native = aligned(aligned(context + 8 + 4, 64) + 4 * 8 * 34, 64)
    # prefix_panel.h: native, five unsigneds, size_t, aligned panel.
    prefix_panel = aligned(aligned(aligned(prefix_native + 5 * 4, 8) + 8, 64)
                           + panel_bytes, 64)
    # execute.h adds output[8][256]; runtime_strided.c adds four unsigneds.
    return dict(prefill=aligned(native + prefix_panel + 8 * 256 * 4, 64),
                decode=aligned(native + panel_bytes + 4 * 4, 64))


def expected_records(spec, step):
    shape = SHAPES.get(spec.get('id'))
    require(shape is not None and all(spec.get(k) == v for k, v in shape.items()),
            'Unsupported quant model shape')
    require(step in (0, 1, 2), 'Unknown quant phase')
    heads, kv, dim = spec['q_heads'], spec['kv_heads'], spec['head_dim']
    gqa = heads // kv
    # selection{,_strided}.h uses packed Q4_0/Q8_0 block bytes, not F16 bytes.
    row_bytes = dim // 32 * (18 if spec['cache_k'] == 'q4_0' else 34)
    workspace = workspace_sizes()
    if step == 0:
        commands = groups = decodes = 0
        # execute.h flattens query/GQA rows in groups of MAX_HEADS=8.
        # prefix_schedule.h groups equal visible lengths into M4/M2/M1 per tile.
        for first in range(0, spec['prompt_tokens'] * gqa, 8):
            visible = [(first + r) // gqa + 1
                       for r in range(min(8, spec['prompt_tokens'] * gqa - first))]
            groups += kv
            decodes += kv * max(visible)
            for token in range(0, max(visible), 32):
                lengths = [min(32, max(0, v - token)) for v in visible]
                row = 0
                while row < len(lengths):
                    if not lengths[row]:
                        row += 1
                        continue
                    end = row + 1
                    while end < len(lengths) and lengths[end] == lengths[row]:
                        end += 1
                    while row < end:
                        row += 4 if end - row >= 4 else 2 if end - row >= 2 else 1
                        commands += kv
        return [('GGML_RISCV_QUANT_PREFILL', dict(status=0, mapping=0, memory=1,
            runtime_called=1, selection=0, commands=commands, groups=groups,
            value_decodes=decodes, queries_quantized=spec['prompt_tokens'] * heads,
            key_bytes=decodes * row_bytes, workspace=workspace['prefill']))]
    tokens = spec['prompt_tokens'] + step
    tiles = (tokens + 31) // 32
    commands_per_tile = gqa // 4 + (gqa % 4) // 2 + gqa % 2
    return [
        ('GGML_RISCV_QUANT_KV', dict(status=0, mapping=0, memory=1, runtime_called=1,
            command_attempts=kv * tiles * commands_per_tile, groups=kv,
            value_decodes=kv * tokens, executor_status=0)),
        ('GGML_RISCV_QUANT_KV_LAYOUT', dict(selection=0, key_panels=kv * tiles,
            key_bytes=kv * tokens * row_bytes, workspace=workspace['decode'],
            k_token_stride=kv * row_bytes, k_head_stride=row_bytes)),
        ('GGML_RISCV_QUANT_KV_PV', dict(grouped=0, completed_groups=kv)),
        ('GGML_RISCV_QUANT_KV_REGISTER_PV', dict(enabled=1, status=0, completed_groups=kv))]


def fields(line):
    parts = line.split()
    require(bool(parts), 'Empty quant record')
    result = {}
    for word in parts[1:]:
        require(word.count('=') == 1, 'Malformed quant/phase field')
        k, v = word.split('=')
        require(k not in result, 'Duplicate quant/phase field')
        result[k] = v
    return parts[0], result


def quant_records(lines, spec):
    expected = [expected_records(spec, s) for s in range(3)]
    sequence = [(m, s) for m in (0, 1) for s in range(3)]
    phase = None
    active = False
    rows = []
    seen = 0
    index = 0
    for raw in lines:
        line = raw.rstrip('\r\n')
        if line.startswith('STAGE5_STEP_BEGIN '):
            _, f = fields(line)
            require(phase is None and seen < 6, 'Overlapping/extra quant phase')
            phase = sequence[seen]
            m, s = phase
            require(f == dict(case=spec['id'], requested=str(m), step=str(s),
                input_rows=str(40 if s == 0 else 1), logical_context=str(40 + s)),
                'Wrong quant phase identity/shape')
            index = 0
            active = False
        elif line.startswith('BIND_COUNTER '):
            _, f = fields(line)
            require(phase is not None and
                    (f.get('case'), f.get('requested'), f.get('step')) ==
                    (spec['id'], str(phase[0]), str(phase[1])), 'Wrong quant snapshot identity')
            if f.get('when') == 'before':
                require(not active and index == 0, 'Duplicate/reversed quant snapshot')
                active = True
            else:
                require(f.get('when') == 'after' and active and
                        index == len(expected[phase[1]]) * spec['layers'],
                        'Incomplete quant layer records')
                active = False
        elif line.startswith('STAGE5_STEP_END '):
            _, f = fields(line)
            require(phase is not None and not active and
                    (f.get('case'), f.get('requested'), f.get('step')) ==
                    (spec['id'], str(phase[0]), str(phase[1])) and
                    index == len(expected[phase[1]]) * spec['layers'], 'Incomplete quant phase')
            rec = expected[phase[1]][0][1]
            rows.append(dict(requested=phase[0], step=phase[1], layers=spec['layers'],
                commands=spec['layers'] * rec.get('commands', rec.get('command_attempts'))))
            seen += 1
            phase = None
        elif 'GGML_RISCV_QUANT_' in line:
            require(phase is not None and active, 'Quant record outside call snapshot')
            records = expected[phase[1]]
            require(index < len(records) * spec['layers'], 'Extra quant layer record')
            tag, f = fields(line)
            name, values = records[index % len(records)]
            require(line.startswith(name + ' ') and tag == name and
                    f == {k: str(v) for k, v in values.items()},
                    'Quant status/order/shape differs: ' + line)
            index += 1
    require(phase is None and seen == 6, 'Missing quant phases')
    return rows


def reconcile(result, entries, quant):
    require([(p['requested'], p['step']) for p in result['phases']] ==
            [(m, s) for m in (0, 1) for s in range(3)], 'Incomplete binding phases')
    for phase in result['phases']:
        key = phase['requested'], phase['step']
        require(entries[key]['qbs'] > 0, 'Missing QBS native phase entry')
        require(entries[key]['pv_prepare'] == phase['architectural'].get('pv', 0),
                'PV preparation entry count differs')
    require(all(entries[(0, s)] == entries[(1, s)] for s in range(3)),
            'Native entry distribution differs between arms')
    format_commands = sum(r['native_qbexec'] for r in result['qbs'].values())
    totals = []
    for mode in (0, 1):
        extra = sum(r['commands'] for r in quant if r['requested'] == mode)
        actual = sum(entries[(mode, s)]['qbs'] for s in range(3))
        require(actual == format_commands + extra, 'QBS native-entry exact quant accounting differs')
        totals.append(dict(requested=mode, format_commands=format_commands,
                           quant_commands=extra, native_entries=actual))
    return totals


def check(directory):
    out = Path(directory)
    dependencies = compiled_sources()
    spec = read(out/'spec.json')
    expected_records(spec, 0)
    base = load(HERE/'prefill_check.py', PREFILL_SHA, 'frozen_quant_native_entries')
    content = load(out/'inputs/binding_check.py', BINDING_SHA, 'frozen_quant_binding')
    pcs, symbols = read(out/'pcs.json'), read(out/'symbols.json')
    with (out/'guest.log').open() as stream:
        result = content.check_lines(stream, spec, pcs)
    with (out/'guest.log').open() as stream:
        quant = quant_records(stream, spec)
    with (out/'guest.log').open() as stream:
        entries = base.native_entries(stream, symbols)
    with (out/'guest.log').open() as stream:
        exits = [line.strip() for line in stream if line.startswith('GUEST_TEST_EXIT=')]
    require(exits == ['GUEST_TEST_EXIT=0'], 'Missing/failed/duplicate Linux child exit')
    totals = reconcile(result, entries, quant)
    dependencies[str(out/'inputs/binding_check.py')] = BINDING_SHA
    dependencies[str(HERE/'quant_check.py')] = sha(HERE/'quant_check.py')
    result.update(quant_phase_commands=quant, native_command_accounting=totals,
        native_entry_tb_hits=[dict(requested=k[0], step=k[1], **v) for k, v in entries.items()],
        explicitly_not_executed_tb_hits=[dict(requested=k[0], step=k[1], **v)
                                       for k, v in base.native_entries.stopped.items()],
        source_dependencies=dependencies, qemu_tb_semantics_source_sha256=CPU_SHA,
        linux_child_exit_checked=True, scoped_native_entry_hits_checked=True,
        quant_source_bound_exact_commands_checked=True,
        instruction_retirement_claim=False, rtl_or_model_speed_claim=False)
    return result
