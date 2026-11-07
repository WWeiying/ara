"""Same-ELF SDK checks; only the expected dot count changes for balanced M4."""
import hashlib
import inspect
from pathlib import Path
import types

from audit import digest, require
import check_ffn_native as ffn
import check_supply_sdk as supply
import full_projection as full

PARENTS = {
    full: 'cd92998089d4fe0b2008d8543065bb379c88a80b5539c97ba96d6e0163c7fd26',
    ffn: 'b651b1285f652fba57538847dfbe07699cede675ae0eb2f8423411be2ef666a0',
    supply: '2ffde347047b6ebcb107592c970071106259933e38700d0db775d92a45a743e5',
}
REPLACEMENTS = {
    full: ('dot_active_cycles=4096 if wide else 8192',
           'dot_active_cycles=2048 if wide else 8192'),
    ffn: ('dot_active_cycles=(512 if wide else 1024)*blocks',
          'dot_active_cycles=(256 if wide else 1024)*blocks'),
}
SERVICE = ('weight_bytes', 'activation_bytes', 'payload_bytes', 'read_ranges', 'ar', 'r_beats',
           'useful_pairs', 'fp_uop_issue', 'accumulator_updates')


def specialize(parent):
    require(parent in REPLACEMENTS and digest(parent.__file__) == PARENTS[parent],
            'Sealed numerical checker identity differs')
    source = inspect.getsource(parent.check)
    old, new = REPLACEMENTS[parent]
    require(source.count(old) == 1 and new not in source, 'Unique structural count replacement required')
    generated = source.replace(old, new, 1)
    require(generated.count(new) == 1 and generated.replace(new, old, 1) == source,
            'Checker specialization changed numerical or other checks')
    namespace = dict(vars(parent))
    exec(compile(generated, str(Path(__file__).resolve()), 'exec'), namespace)
    return namespace['check'], dict(parent=str(Path(parent.__file__).resolve()),
        parent_sha256=PARENTS[parent], before=old, after=new,
        original_function_sha256=hashlib.sha256(source.encode()).hexdigest(),
        generated_function_sha256=hashlib.sha256(generated.encode()).hexdigest(),
        source_reversible=True, raw_log_rewritten=False, numerical_checks_changed=False)


def checker(kind, balanced):
    require(kind in ('prefill', 'ffn') and type(balanced) is int and balanced in (0, 1),
            'Explicit supported balanced SDK geometry required')
    require(all(digest(module.__file__) == sha for module, sha in PARENTS.items()),
            'Sealed SDK checker input differs')
    if kind == 'ffn':
        fn, report = specialize(ffn) if balanced else (ffn.check, None)
        return lambda text, expected: fn(text, 1, *expected), report
    if not balanced:
        return lambda text, expected: supply.check(text, 'prefill', 256, expected), None
    inner, report = specialize(full)
    # The unchanged supply checker still verifies role-specific read beats and
    # all phase/context counters. Only its private numerical-check callback is specialized.
    namespace = dict(vars(supply), prefill=types.SimpleNamespace(check=inner))
    outer = types.FunctionType(supply.check.__code__, namespace, supply.check.__name__,
                               supply.check.__defaults__, supply.check.__closure__)
    return lambda text, expected: outer(text, 'prefill', 256, expected), report


def check(text, kind, balanced, expected):
    require([line for line in text.splitlines() if 'Core Test' in line] ==
            ['Core Test *** SUCCESS *** (tohost = 0)'], 'Exact core completion required')
    fn, transform = checker(kind, balanced)
    value = fn(text, expected)
    commands = [supply.decode.fields(line, '[QBS_PERF]') for line in text.splitlines()
                if line.startswith('[QBS_PERF] ')]
    require(len(commands) == (128 if kind == 'prefill' else 12), 'SDK command inventory')
    for index, command in enumerate(commands):
        if kind == 'ffn':
            blocks = 24 if index >= 8 else 8
            profile = expected[2][index // 4]
            supply.decode.read_contract(command, 256, blocks, profile, 4)
        require(all(key in command for key in SERVICE), 'Missing service counters')
        require(command['dot_active_cycles'] <= command['busy_cycles'], 'Impossible dot occupancy')
    return dict(measured=value, structural_specialization=transform,
                service={key: sum(row[key] for row in commands) for key in SERVICE},
                balanced=balanced, kind=kind, whole_model=False, physical_bits=256,
                raw_log_rewritten=False, original_golden_and_csr_checks_retained=True)


def pair(base, candidate):
    require(base['balanced'] == 0 and candidate['balanced'] == 1 and
            base['kind'] == candidate['kind'] and base['physical_bits'] == candidate['physical_bits'] == 256,
            'Different physical platforms or SDK regions')
    a, b = base['measured'], candidate['measured']
    require(base['service'] == candidate['service'] and
            a['useful_pairs'] == b['useful_pairs'] and
            a['dot_issue_count'] == 2 * b['dot_issue_count'], 'Useful work, read work or dot count differs')
    require([(p['checksum'], p['fcsr'], p['vcsr']) for p in a['parts']] ==
            [(p['checksum'], p['fcsr'], p['vcsr']) for p in b['parts']], 'Paired output or CSR differs')
    if base['kind'] == 'prefill':
        ta, tb = a['trials'][0], b['trials'][0]
    else:
        require([(p['checksum'], p['fcsr']) for p in a['preparation']] ==
                [(p['checksum'], p['fcsr']) for p in b['preparation']], 'Activation payload or CSR differs')
        ta, tb = a['total'], b['total']
    keys = ('region', 'preparation', 'admission', 'execution')
    require(all(ta[key] > 0 and tb[key] > 0 for key in keys), 'Missing real SDK timing')
    return dict(baseline_cycles={key: ta[key] for key in keys},
                candidate_cycles={key: tb[key] for key in keys},
                ratios={key: ta[key] / tb[key] for key in keys},
                same_work=True, preparation_included=True, whole_model=False,
                limits=['Same-ELF signature/CSR checks plus fixed physical 256-bit service',
                        'SDK region only, not complete GGML or token/model performance'])
