"""Strict successor for the one sealed724 JSON-string native proposal artifact."""
import hashlib
import inspect
import json
from pathlib import Path
from types import FunctionType

import lzc_selector_native_seven_policy_runtime as prior

frozen, require = prior.frozen, prior.require
SCRIPT = Path(__file__).resolve()
TEST = SCRIPT.with_name('test_lzc_selector_native_seven_policy_runtime_v2.py')
TCL = prior.TCL
PLAN_OUTPUT = frozen.OUT / 'lzc-selector-native-seven-policy-plan-724-parent-20261006-01'
PLAN_SEAL = '325daa9245b1cef74cd8eb602d1e21f69c5abf4da78503af6fad69d44764ad46'
SIX_OUTPUT = frozen.OUT / 'branch-combo-six-policy-population-724-parent-20261006-01'
SIX_SEAL = '32d8deca7e562af7e5e0f8f28768d386772ecfc1c9f3908c193f9d2e5ce0d7cd'
SERIALIZED_SHA = '322c0d52f1bcca588be245a0a8629e2bbc5f94f3ef39593911a9295f7cc82a2d'
NATIVE_SHA = 'bb14a7acec4ba90afddfcb24b83e50e345fd2fc50adb5b2984cdcca28d857780'
PRIOR_SHA = '8ddb5cea4d09d4fc1ac6bd6a5ae4bd242e7c0ab9e755597e2bd6b9bcf097b3eb'

# Private function globals keep every frozen gate and verifier without monkeypatches.
for _name, _value in vars(prior).items():
    if isinstance(_value, FunctionType) and _value.__module__ == prior.__name__:
        globals()[_name] = FunctionType(_value.__code__, globals(), _name,
                                       _value.__defaults__, _value.__closure__)
    elif not _name.startswith('__') and _name not in ('SCRIPT', 'TEST', 'TCL'):
        globals().setdefault(_name, _value)


def digest_bytes(raw):
    return hashlib.sha256(raw).hexdigest()


def decode_json_native(raw, config, records, original, candidate60):
    # Exactly one decode: no format fallback, recursive decoding or escape repair.
    value = json.loads(raw)
    require(type(value) is str, 'Native proposal JSON must be exactly one string')
    native = value.encode('ascii')
    six_bytes, extra = seven.split_seven(native, config, records)
    require(six_bytes == original and extra == candidate60, 'Decoded original6/approved60 bytes differ')
    return native


def decoded_proposal(plan_output, plan, config):
    require(plan_output == PLAN_OUTPUT and plan_output.resolve() == plan_output
            and not plan_output.is_symlink(), 'Only exact sealed724 artifact directory accepted')
    artifact = plan_output / 'combined-seven-proposal.el'
    require(artifact.is_file() and not artifact.is_symlink()
            and frozen.sha(plan_output / 'application-plan.json') == PLAN_SEAL
            and plan['pins'].get(str(artifact)) == SERIALIZED_SHA
            and plan['six_config'] == str(SIX_OUTPUT / 'config.json')
            and plan['six_config_sha256'] == SIX_SEAL
            and config['output'] == str(SIX_OUTPUT)
            and config['population'] == plan['population'] == 724
            and frozen.sha(SIX_OUTPUT / 'config.json') == SIX_SEAL,
            'Known serialized proposal/plan/six binding differs')
    raw = artifact.read_bytes()
    require(digest_bytes(raw) == SERIALIZED_SHA, 'Serialized artifact bytes differ')
    proof_root = Path(plan['source_proof']).parent
    require(plan['source_proof_sha256'] == seven.PROOF_SEAL, 'Source proof seal differs')
    candidate = proof_root / 'candidate60.el'
    original = SIX_OUTPUT / 'combined.el'
    require(plan['pins'].get(str(candidate)) == frozen.sha(candidate)
            and config['pins'].get(str(original)) == frozen.sha(original), 'Exact component byte pins differ')
    native = decode_json_native(raw, config, plan['condition_native_records'],
                                original.read_bytes(), candidate.read_bytes())
    require(digest_bytes(native) == NATIVE_SHA, 'Known canonical native bytes differ')
    return native


def successor_dependencies():
    return (Path(prior.__file__).resolve(), SCRIPT, TEST,
            SCRIPT.with_name('run_lzc_selector_native_seven_policy_v2.py'),
            SCRIPT.with_name('test_run_lzc_selector_native_seven_policy_v2.py'))


def serialization_binding(plan_output, output, native):
    require(plan_output == PLAN_OUTPUT and digest_bytes(native) == NATIVE_SHA,
            'Serialized/native binding differs')
    artifact = plan_output / 'combined-seven-proposal.el'
    require(frozen.sha(artifact) == SERIALIZED_SHA
            and (output / 'combined-seven.el').read_bytes() == native, 'Normalized runtime file differs')
    return dict(schema='known724-json-string-native-normalization-v1',
                source_artifact=str(artifact), source_sha256=SERIALIZED_SHA,
                source_plan_sha256=PLAN_SEAL, source_six_config_sha256=SIX_SEAL,
                native_artifact=str(output / 'combined-seven.el'), native_sha256=NATIVE_SHA,
                json_decode_passes=1, format_fallback=False, original_six_bytes_exact=True,
                approved60_bytes_exact=True, frozen_source_changed=False,
                successor_entry=str(SCRIPT), successor_entry_sha256=frozen.sha(SCRIPT))


def verify_serialization_binding(runtime, output):
    native = (output / 'combined-seven.el').read_bytes()
    require(runtime.get('serialized_native_binding') == serialization_binding(PLAN_OUTPUT, output, native)
            and runtime['six_output'] == str(SIX_OUTPUT) and runtime['six_config_sha256'] == SIX_SEAL
            and runtime['seven_output'] == str(PLAN_OUTPUT) and runtime['seven_plan_sha256'] == PLAN_SEAL
            and runtime['pins'].get(str(PLAN_OUTPUT / 'combined-seven-proposal.el')) == SERIALIZED_SHA
            and runtime['pins'].get(str(output / 'combined-seven.el')) == NATIVE_SHA,
            'Serialized/native pins or provenance differ')


def adapted(function, replacements):
    require(frozen.sha(Path(prior.__file__).resolve()) == PRIOR_SHA, 'Frozen runtime adapter source differs')
    source = inspect.getsource(function)
    for old, new in replacements:
        require(source.count(old) == 1, 'Exact frozen serialization adapter boundary differs')
        source = source.replace(old, new, 1)
    # Source is the SHA-bound frozen helper, never artifact-provided code.
    exec(compile(source, str(SCRIPT), 'exec'), globals())
    return globals()[function.__name__]


prepare = adapted(prior.prepare, (
    ("require(accept_contract, 'Explicit parent acceptance of padding X/0 limits required')",
     "require(six_output == SIX_OUTPUT and six_seal == SIX_SEAL and plan_output == PLAN_OUTPUT and plan_seal == PLAN_SEAL, 'Only known sealed724 inputs accepted')\n    require(accept_contract, 'Explicit parent acceptance of padding X/0 limits required')"),
    ("combined = (plan_output / 'combined-seven-proposal.el').read_bytes()",
     'combined = decoded_proposal(plan_output, plan, config)'),
    ("plan_output / 'application-plan.json', six_output / 'config.json', six.prior.TCL):",
     "plan_output / 'application-plan.json', six_output / 'config.json', six.prior.TCL, *successor_dependencies()):"),
    ("frozen.write(output / 'runtime-plan.json', runtime)",
     "runtime['serialized_native_binding'] = serialization_binding(plan_output, output, combined)\n    frozen.write(output / 'runtime-plan.json', runtime)"),
))
read_config = adapted(prior.read_config, (
    ("(Path(runtime['seven_output']) / 'combined-seven-proposal.el').read_bytes()",
     "decoded_proposal(Path(runtime['seven_output']), plan, config)"),
    ("*(output / name for name in HELPERS))",
     "*(output / name for name in HELPERS), *successor_dependencies())"),
    ('derived = copy.deepcopy(config)',
     'verify_serialization_binding(runtime, output)\n    derived = copy.deepcopy(config)'),
))


if __name__ == '__main__':
    main()
