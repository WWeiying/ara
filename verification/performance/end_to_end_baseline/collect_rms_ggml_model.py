#!/usr/bin/env python3
"""Scoped, host-only replay of the sealed ordered-RMS full-model experiment.

The executor's complete input/path validation is referenced by receipt hash.
This collector deliberately does not rehash the QEMU/native source tree.
"""
import argparse
from collections import Counter
import hashlib
import importlib
import io
import json
from pathlib import Path
import sys
import unittest


HERE = Path(__file__).resolve().parent
RUNS = Path('/home/wangwy/openproject/ara_dsa_signoff_integration/verification/out')
WORKER = RUNS / 'e2e_rms_ggml_model_qemu_20261106_01'
PREFLIGHT = RUNS / 'e2e_rms_ggml_model_preflight_20261106_01'
LIBRARY = RUNS / 'e2e_rms_ggml_library_20261106_03'
LATEST = RUNS / 'e2e_sdk_dispatch_model_pair_20261106_01'
PRIOR = RUNS / 'e2e_trace_context_model_pair_20261106_01'
MODEL = RUNS / 'e2e_output_model_20261106_01'
OUT = RUNS / 'e2e_rms_ggml_model_collect_20261106_01'
OWNED = ('collect_rms_ggml_model.py', 'test_collect_rms_ggml_model.py')
SUCCESS = 'RMS_GGML_MODEL_SCOPED_RAW_AUDIT_PASS'
RECEIPTS = {
    WORKER: '3a4e79242c74f24d1e994722ac9bf88b567b1ff24473eec96451e7655be8a72e',
    PREFLIGHT: '5c79a96a91ec0e94a652dab6dfac52cd8e4f8c2556bc15190e9d80449f99c731',
    LIBRARY: '5056fa1e9c42cfb4b5b71b21d933a7602de1cbf77a8ea62fdeee81aa8eb2e30f',
}
BASE_ELF = 'f0d8741421d95b08057973f58d370b9fc48c4325b08e909b299946e175dfcaad'
CANDIDATE_ELF = 'dbd7ea5f033940490de32c9de2b69f2cfb7d05527337eb0361564a5344f40f53'
BASE_LIBRARY = 'd335a23205c19f0f4e4e8e77b4160812a925b3e848cb967b4479b0a6f4d29c5f'
NEW_LIBRARY = '874f2bbfeee8b3acc88976b4166556061a7c43c728edfd2027de603821184087'
MODEL_OBJECT = 'a760df34b05ec4ec4a44ec4533ccbfba9d41995ca04d3d8dc61e2173ce0a83b1'
HISTOGRAMS = (
    {(128, 640): 28, (128, 320): 28, (2048, 40): 55, (2048, 1): 2},
    {(128, 16): 28, (128, 8): 28, (2048, 1): 57},
)
REPLAY_MODULES = ('audit', 'check_output_model', 'trace_context_model', 'rms_ggml_model',
                  'audit_sdk_guest_payload', 'build_trace_context_library', 'build_sdk_dispatch_library')


def require(ok, message):
    if not ok:
        raise ValueError(message)


def digest(path):
    h = hashlib.sha256()
    with Path(path).open('rb') as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b''):
            h.update(block)
    return h.hexdigest()


def read(path):
    return json.loads(Path(path).read_text())


def write(path, value):
    with Path(path).open('x') as stream:
        json.dump(value, stream, indent=2, sort_keys=True, allow_nan=False)
        stream.write('\n')


def same(actual, expected, message):
    require(json.dumps(actual, sort_keys=True, allow_nan=False) ==
            json.dumps(expected, sort_keys=True, allow_nan=False), message)


class ScopedPins:
    """Only explicit selections perform I/O; inventories are not verification loops."""
    def __init__(self, inventory, identities):
        self.inventory = inventory
        self.inherited_identities = identities
        self.values, self.identities, self.roles = {}, {}, {}

    def pin(self, path, expected=None, role='collector', bound=True):
        lexical = str(Path(path).absolute())
        target = str(Path(path).resolve(strict=True))
        if bound:
            require(target in self.inventory, 'Selected input absent from bound inventory: ' + target)
            require(expected is None or expected == self.inventory[target], 'Conflicting selected pin: ' + target)
            expected = self.inventory[target]
            require(lexical in self.inherited_identities, 'Selected path absent from executor identity map: ' + lexical)
            require(self.inherited_identities[lexical] == target, 'Selected path identity drift: ' + lexical)
        actual = digest(target)
        require(expected is None or actual == expected, 'Selected hash mismatch: ' + target)
        require(target not in self.values or self.values[target] == actual, 'Selected input drift: ' + target)
        self.values[target] = actual
        self.identities[lexical] = target
        self.roles.setdefault(target, [])
        if role not in self.roles[target]:
            self.roles[target].append(role)
        return actual

    def verify(self):
        for lexical, target in self.identities.items():
            require(str(Path(lexical).resolve(strict=True)) == target, 'Final selected path drift: ' + lexical)
        for path, expected in self.values.items():
            require(digest(path) == expected, 'Final selected input drift: ' + path)


def admit(worker, prepared, library):
    checks = ((worker, dict(state='RMS_GGML_PREBUILT_MODEL_PAIR_FUNCTIONAL_PASS', child_pid=None,
                           compiled_translation_units=0, rtl_changed=False, performance_measured=False,
                           model_library_promoted=False, post_pins_match=True, post_path_identities_match=True,
                           reused_prebuilt_guest_payload=True, preflight=str(PREFLIGHT),
                           preflight_result_sha256=RECEIPTS[PREFLIGHT])),
              (prepared, dict(state='RMS_GGML_MODEL_PAIR_PREPARED_NOT_EXECUTED', child_pid=None,
                              performance_measured=False, rtl_changed=False, production_library_promoted=False,
                              compiled_translation_units=1, common_model_object_reused=True, default_enabled=False,
                              baseline_link_reproduced_exactly=True, guest_cpio_parsed_and_bound=True,
                              library_build=str(LIBRARY))),
              (library, dict(state='RMS_GGML_LIBRARY_BUILT_ARCHIVE_VERIFIED', target_executed=False,
                             performance_measured=False, rtl_changed=False, production_library_promoted=False,
                             default_enabled=False, member='ops.cpp.o', unchanged_other_members=31, members=32,
                             original_object_reproduced_exactly=True, public_exports_unchanged=True,
                             inventory_and_order_unchanged=True, original_library_unchanged=True,
                             post_pins_match=True, helpers_identical_to_measured_sources=True,
                             baseline_already_uses_ordered_rvv=True)))
    for record, expected in checks:
        for key, value in expected.items():
            require(key in record and type(record[key]) is type(value) and record[key] == value,
                    'Receipt admission: ' + key)
    for record in (worker, prepared, library):
        require(record['baseline_library_sha256'] == BASE_LIBRARY and
                record['candidate_library_sha256'] == NEW_LIBRARY, 'Library receipt binding')
    for record in (worker, prepared):
        require(record['baseline_elf_sha256'] == BASE_ELF and record['candidate_elf_sha256'] == CANDIDATE_ELF and
                record['common_model_object_sha256'] == MODEL_OBJECT, 'ELF/model object receipt binding')


def node_histograms(norm):
    require(norm['operators'] == 452 and norm['sum_rows'] == 59622 and len(norm['steps']) == 4,
            'Norm graph totals')
    result = []
    total_rows = 0
    for index, step in enumerate(norm['steps']):
        kind, phase = divmod(index, 2)
        require((step['kind'], step['step']) == (kind, phase), 'Norm step sequence')
        nodes = step['operators']
        require(len(nodes) == 113, 'Norm nodes per step')
        hist = Counter()
        fused = Counter()
        for node in nodes:
            require(set(node) == {'fused', 'width', 'sum_rows', 'output_rows'} and
                    all(type(value) is int for value in node.values()), 'Norm node fields/types')
            require(node['fused'] == 1 and node['sum_rows'] == node['output_rows'], 'Nonfused or lost output node')
            hist[node['width'], node['sum_rows']] += 1
            fused[node['fused']] += 1
        require(hist == HISTOGRAMS[phase], 'Per-node Norm histogram differs from accepted graph')
        rows = sum(width_rows[1] * count for width_rows, count in hist.items())
        require(rows == (29082 if phase == 0 else 729), 'Per-step Norm row total')
        total_rows += rows
        result.append(dict(kind=kind, step=phase, phase='prefill' if phase == 0 else 'decode',
                           nodes=113, sum_rows=rows, output_rows=rows, fused_distribution=dict(fused),
                           histogram=[dict(width=w, sum_rows=r, output_rows=r, fused=1, nodes=n)
                                      for (w, r), n in sorted(hist.items())]))
    require(total_rows == 59622, 'Independent Norm row conservation')
    return dict(operators=452, sum_rows=total_rows, output_rows=total_rows,
                fused_distribution={1: 452}, steps=result)


def replay_raw(text, control, schema, measured, accepted_native):
    from trace_context_model import check as native_check
    from rms_ggml_model import norm_work
    require('RMS_GGML_MODEL_FAIL' not in text, 'RMS driver failure')
    replay = dict(native=native_check(text, control, schema), norm=norm_work(text))
    same(replay, measured, 'Raw native/Norm replay differs from original worker')
    same(replay['native'], accepted_native, 'Native work differs from accepted baseline')
    native = replay['native']
    require(native['logits_compared'] == 607744 and native['comparisons'] == 4 and
            native['identical_full_logits'] is True and native['identical_native_work'] is True and
            native['identical_tokens_and_csr'] is True and native['performance_measured'] is False,
            'Numerical/native replay verdict')
    return replay, node_histograms(replay['norm'])


def archive_replay(before, after, replacement, original):
    from build_trace_context_library import archive_members
    from build_sdk_dispatch_library import compare_member_archives
    old, new = archive_members(before), archive_members(after)
    require(len(old) == len(new) == 32, 'Expected 32 archive members')
    require([data for name, data in old if name == 'ops.cpp.o'] == [original], 'Original ops reproduction')
    evidence = compare_member_archives(old, new, 'ops.cpp.o', replacement)
    require(sum(row['changed'] for row in evidence) == 1 and
            sum(not row['changed'] for row in evidence) == 31, 'Only ops member may change')
    return evidence


def one(records, label):
    rows = [record for record in records if record['label'] == label]
    require(len(rows) == 1 and rows[0]['returncode'] == 0, 'Missing/failed command: ' + label)
    return rows[0]


def link_pair(commands, baseline_library, candidate_library):
    base, candidate = one(commands, 'reproduce-baseline'), one(commands, 'link-candidate')
    argv = base['argv']
    require(argv.count(str(baseline_library)) == 1 and '-static' in argv and argv.count('-o') == 1 and
            argv[argv.index('-o') + 1] == str(PREFLIGHT / 'baseline-reproduced') and
            argv.count(str(PRIOR / 'model.o')) == 1, 'Accepted baseline link structure')
    expected = [str(candidate_library) if arg == str(baseline_library) else
                str(PREFLIGHT / 'candidate') if i == argv.index('-o') + 1 else arg
                for i, arg in enumerate(argv)]
    require(candidate['argv'] == expected and base['cwd'] == candidate['cwd'] == str(PREFLIGHT) and
            base['environment'] == candidate['environment'], 'Candidate link changes more than archive/output')
    return dict(common_model_object=str(PRIOR / 'model.o'), only_archive_and_output_differ=True)


def ownership():
    observations = []
    for root in (WORKER, RUNS / 'e2e_qwen3_f16_phase_vcs_20261106_01'):
        path = root / 'source-pins.json'
        data = path.read_bytes()
        inventory = json.loads(data)
        require(not any(str(HERE / name) in inventory for name in OWNED), 'Owned helper already consumed')
        observations.append(dict(path=str(path), sha256=hashlib.sha256(data).hexdigest(),
                                 inventory_entries=len(inventory), owned_conflicts=[]))
    return observations


def collect(output):
    output = Path(output).absolute()
    require(output == OUT and output.resolve() == OUT, 'Assigned fresh sole-verification output only')
    observed = ownership()
    output.mkdir(exist_ok=False)
    result = dict(state='RMS_GGML_MODEL_SCOPED_RAW_AUDIT_FAIL', target_executed=False,
                  performance_measured=False, production_library_promoted=False,
                  qemu_source_tree_rehashed=False, full_worker_pins_rehashed=False)
    try:
        # Authenticate the terminal receipt before selecting anything from its inventory.
        require(digest(WORKER / 'result.json') == RECEIPTS[WORKER], 'Accepted worker receipt changed')
        worker = read(WORKER / 'result.json')
        require(digest(WORKER / 'source-pins.json') == worker['source_pins_sha256'], 'Worker inventory binding')
        inventory = read(WORKER / 'source-pins.json')
        artifacts = worker['artifacts']
        require(set(artifacts) == {str(WORKER / name) for name in
                                  ('source-pins.json', 'path-identities.json', 'commands.json', 'qemu.log', 'qemu.stderr')},
                'Unexpected worker artifact inventory')
        require(digest(WORKER / 'path-identities.json') == artifacts[str(WORKER / 'path-identities.json')],
                'Executor path identity inventory binding')
        pins = ScopedPins(inventory, read(WORKER / 'path-identities.json'))
        pins.pin(WORKER / 'result.json', RECEIPTS[WORKER], 'terminal_full_input_acceptance', bound=False)
        for path, expected in artifacts.items():
            pins.pin(path, expected, 'worker_artifact', bound=False)
        require(worker['log_sha256'] == artifacts[str(WORKER / 'qemu.log')], 'Worker raw log binding')
        prepared, library = read(PREFLIGHT / 'result.json'), read(LIBRARY / 'result.json')
        for root, record in ((PREFLIGHT, prepared), (LIBRARY, library)):
            pins.pin(root / 'result.json', RECEIPTS[root], 'accepted_receipt')
            pins.pin(root / 'source-pins.json', record['source_pins_sha256'], 'inventory_blob_not_recursive_rehash')
            pins.pin(root / 'path-identities.json', role='path_inventory_blob')
            pins.pin(root / 'commands.json', role='build_commands')
        admit(worker, prepared, library)
        for name in OWNED:
            pins.pin(HERE / name, role='collector_source', bound=False)
            with (output / name).open('xb') as stream:
                stream.write((HERE / name).read_bytes())
        pins.pin(Path(sys.executable), role='host_python', bound=False)
        for name in REPLAY_MODULES:
            pins.pin(HERE / (name + '.py'), role='sealed_replay_helper')
        # Only authenticated modules are imported for the host replay.
        for name in REPLAY_MODULES:
            module = importlib.import_module(name)
            require(Path(module.__file__).resolve() == (HERE / (name + '.py')).resolve(), 'Replay module root')
        for name in ('execute_rms_ggml_model.py', 'run_rms_ggml_model.py', 'build_rms_ggml_library.py',
                     'trace_context_model_driver.cpp'):
            pins.pin(HERE / name, role='producer_source')
        for path, expected in library['header_pins'].items():
            pins.pin(path, expected, 'actual_wrapper_and_leaf_headers')
        tests = importlib.import_module('test_collect_rms_ggml_model')
        require(Path(tests.__file__).resolve() == (HERE / OWNED[1]).resolve(), 'Unit test module root')
        stream = io.StringIO()
        test_result = unittest.TextTestRunner(stream=stream, verbosity=2).run(
            unittest.defaultTestLoader.loadTestsFromModule(tests))
        with (output / 'unit-tests.log').open('x') as log:
            log.write(stream.getvalue())
        require(test_result.wasSuccessful() and test_result.testsRun >= 10, 'Collector admission/replay unit tests')
        pins.pin(LATEST / 'result.json', role='accepted_native_baseline')
        pins.pin(MODEL / 'qemu.log', role='native_control_raw')
        pins.pin(PRIOR / 'projection-schema.json', role='exact_197_tensor_schema')
        replay, histograms = replay_raw((WORKER / 'qemu.log').read_text(), (MODEL / 'qemu.log').read_text(),
                                       read(PRIOR / 'projection-schema.json'), worker['measured'],
                                       read(LATEST / 'result.json')['measured'])
        write(output / 'raw-replay.json', replay)
        write(output / 'node-histograms.json', histograms)
        baseline_library, candidate_library = Path(library['baseline_library']), Path(library['candidate_library'])
        pins.pin(baseline_library, BASE_LIBRARY, 'actual_archive')
        pins.pin(candidate_library, NEW_LIBRARY, 'actual_archive')
        candidate_object = Path(library['candidate_object'])
        original_object = LIBRARY / 'objects/original-ops.cpp.o'
        pins.pin(candidate_object, library['candidate_object_sha256'], 'replacement_ops_object')
        pins.pin(original_object, library['original_object_sha256'], 'reproduced_original_ops_object')
        members = archive_replay(baseline_library.read_bytes(), candidate_library.read_bytes(),
                                 candidate_object.read_bytes(), original_object.read_bytes())
        pins.pin(LIBRARY / 'archive-members.json', role='original_archive_comparison')
        same(members, read(LIBRARY / 'archive-members.json'), 'Archive replay differs from library worker')
        links = link_pair(read(PREFLIGHT / 'commands.json'), baseline_library, candidate_library)
        for arg in one(read(PREFLIGHT / 'commands.json'), 'link-candidate')['argv']:
            if arg.endswith('.a'):
                pins.pin(arg, role='actual_link_archive')
        pins.pin(PRIOR / 'model.o', MODEL_OBJECT, 'common_model_object')
        pins.pin(PREFLIGHT / 'baseline-reproduced', BASE_ELF, 'baseline_reproduced_elf')
        for name in ('inputs/rms_model_driver.cpp', 'objects/driver.o', 'initramfs.list', 'guest-payload.json'):
            pins.pin(PREFLIGHT / name, role='actual_driver_and_payload_metadata')
        init_lines = [line.split() for line in (PREFLIGHT / 'initramfs.list').read_text().splitlines()
                      if line.startswith('file /init ')]
        require(len(init_lines) == 1 and len(init_lines[0]) == 6 and init_lines[0][3:] == ['755', '0', '0'],
                'Canonical init listing')
        files = dict(init=Path(init_lines[0][2]), base=LATEST / 'candidate',
                     candidate=PREFLIGHT / 'candidate', test=PREFLIGHT / 'test')
        for name, path in files.items():
            expected = {'base': BASE_ELF, 'candidate': CANDIDATE_ELF,
                        'test': prepared['driver_elf_sha256']}.get(name)
            pins.pin(path, expected, 'actual_guest_elf_' + name)
        pins.pin(PREFLIGHT / 'initramfs.cpio', role='actually_consumed_cpio')
        from audit_sdk_guest_payload import validate_payload
        payload = validate_payload((PREFLIGHT / 'initramfs.cpio').read_bytes(),
                                   {name: path.read_bytes() for name, path in files.items()})
        same(payload, read(PREFLIGHT / 'guest-payload.json'), 'Actual newc replay differs from preflight')
        commands = read(WORKER / 'commands.json')
        require(len(commands) == 1, 'Exactly one executed QEMU command required')
        command = one(commands, 'qemu')
        pins.pin(LATEST / 'commands.json', role='accepted_native_qemu_recipe')
        expected = list(one(read(LATEST / 'commands.json'), 'qemu')['argv'])
        require(expected.count('-initrd') == 1 and expected[expected.index('-initrd') + 1] == str(LATEST / 'initramfs.cpio'),
                'Accepted QEMU initrd identity')
        expected[expected.index('-initrd') + 1] = str(PREFLIGHT / 'initramfs.cpio')
        require(command['argv'] == expected and command['cwd'] == str(WORKER) and
                command['environment'] == dict(PATH='/usr/bin:/bin', LC_ALL='C', HOME=str(WORKER),
                                               PYTHONDONTWRITEBYTECODE='1'), 'Executed QEMU recipe changed')
        for path in (expected[0], expected[expected.index('-bios') + 1], expected[expected.index('-kernel') + 1]):
            pins.pin(path, role='consumed_qemu_binary_firmware_kernel_not_source_tree')
        require((WORKER / 'qemu.stderr').stat().st_size == 0, 'QEMU stderr is not empty')
        write(output / 'payload-replay.json', payload)
        write(output / 'archive-replay.json', dict(members=members, link=links, changed_members=['ops.cpp.o'],
                                                  unchanged_members=31))
        write(output / 'ownership.json', observed)
        scope = dict(worker_inventory_entries=len(inventory), selected_inputs=len(pins.values),
                     full_worker_pins_rehashed=False, qemu_source_tree_rehashed=False,
                     complete_native_source_closure_rehashed=False,
                     upstream_complete_input_and_path_acceptance_referenced_by_sha256=RECEIPTS[WORKER],
                     unselected_inputs='No source-tree/model-disk/whole-toolchain rescan; inherited executor acceptance only',
                     selected_input_roles=pins.roles)
        write(output / 'audit-scope.json', scope)
        pins.verify()
        write(output / 'source-pins.json', pins.values)
        write(output / 'path-identities.json', pins.identities)
        artifact_names = (*OWNED, 'unit-tests.log', 'raw-replay.json', 'node-histograms.json',
                          'payload-replay.json', 'archive-replay.json', 'ownership.json', 'audit-scope.json',
                          'source-pins.json', 'path-identities.json')
        result.update(state=SUCCESS, worker=str(WORKER), worker_result_sha256=RECEIPTS[WORKER],
                      preflight_result_sha256=RECEIPTS[PREFLIGHT], library_result_sha256=RECEIPTS[LIBRARY],
                      upstream_complete_input_acceptance_referenced=True, selected_input_post_match=True,
                      selected_inputs=len(pins.values), worker_inventory_entries=len(inventory),
                      source_pins_sha256=digest(output / 'source-pins.json'), tests_passed=test_result.testsRun,
                      measured=replay['native'], norm=histograms, actual_newc_elf_count=4,
                      baseline_elf_sha256=BASE_ELF, candidate_elf_sha256=CANDIDATE_ELF,
                      only_changed_archive_member='ops.cpp.o', unchanged_archive_members=31,
                      artifacts={str(output / name): digest(output / name) for name in artifact_names},
                      limitations=['Functional integration for this Qwen3 model/prompt and two quantized-KV configurations only',
                                   '607744 full-logit bitwise comparisons are independently replayed driver verdicts, not exported logit arrays',
                                   'No hardware/model speedup; production baseline already auto-vectorizes ordered RMS',
                                   'Runtime selection remains opt-in; no production library promotion',
                                   'Targeted hash/path revalidation, not a second full QEMU/native source-closure audit'])
        write(output / 'result.json', result)
        write(output / 'compact-evidence.json', dict(state=SUCCESS, run=str(output),
              result_sha256=digest(output / 'result.json'), source_pins_sha256=result['source_pins_sha256'],
              worker_result_sha256=RECEIPTS[WORKER], logits_compared=607744, norm_operators=452,
              norm_rows=59622, all_norm_nodes_fused=True, actual_newc_elf_count=4,
              only_changed_archive_member='ops.cpp.o', full_worker_pins_rehashed=False,
              qemu_source_tree_rehashed=False, target_executed=False, performance_measured=False,
              production_library_promoted=False))
        return result
    except Exception as exc:
        result['error'] = str(exc)
        if not (output / 'result.json').exists():
            write(output / 'result.json', result)
        raise


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', type=Path, default=OUT)
    args = parser.parse_args()
    report = collect(args.output)
    print(json.dumps(dict(state=report['state'], output=str(args.output),
                          result_sha256=digest(args.output / 'result.json'))))


if __name__ == '__main__':
    main()
