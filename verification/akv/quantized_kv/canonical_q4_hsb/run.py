#!/usr/bin/env python3
"""One fresh canonical Q4 same-ELF H/S/B experiment, never an old continuation."""
import argparse
from datetime import datetime, timezone
import hashlib
import importlib.util
from pathlib import Path
import signal
import subprocess
import sys

sys.dont_write_bytecode = True
HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[3]
PROGRAM = ROOT / 'verification/out/q4-untimed-verify-fixed-layout-20261025-01'
SOC_BUILD = ROOT / 'verification/out/canonical-shared-resources-build-20261025-02'
RECEIPT_SHA = '1275b929a431f877ee437bae878f6b85c3338ff2d2ef14d4a40925bada7bfbbc'
SOC_SHA = 'e554e706c54298aaf98ff6cfafc23e2c1fd23c6eba4da44c8b80be0da5103724'
ELF_SHA = '8203039cf8f16afabc6d76b0d28f148af551f95300df34a912ddd561b503ff1d'
TIMED_SHA = '88e43efe2b0cbd5f184b6f3fdd1693a063b3fb39fd1e03ff64d79bc3c63f1064'
TIMEOUT = 10800
GOLD = ROOT / ('verification/out/akv-quantkv-host-capture-20261024-01/'
               'capture-k-q4_0-v-q8_0/decode/block/kqv_out-0.bin')
RTL = ROOT / 'hardware/src/vlsu/vlsu.sv'
ARTIFACT_NAMES = (
    'README.md', 'attention_threeway_untimed.c', 'commands.json', 'compile.log', 'deps.log',
    'disassembly.log', 'fixed-timed-cfg.json', 'input-pins-after-link.json',
    'input-pins-after.json', 'input-pins-before.json', 'layout-review.json', 'link-review.json',
    'link.ld', 'link.log', 'link.map', 'main.o', 'object-relocation-review.json',
    'old-timed-cfg.json', 'original_fasthex.c', 'predecessor-assembly-review.json',
    'predecessor-commands.json', 'predecessor-new-timed-cfg.json',
    'predecessor-predecessor-identity.json', 'render.json', 'review-result.json',
    'threeway_attention.elf', 'timed-cfg.diff', 'timed-review.json')


def load(name, path, sha):
    if hashlib.sha256(path.read_bytes()).hexdigest() != sha:
        raise ValueError('Helper identity drift: ' + str(path))
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


canonical = load('canonical_q4_actual_image', ROOT /
    'verification/akv/canonical_promotion/canonical_runtime_v2/run.py',
    '99a4aedbe0a1f8869aeb6bbbb5079255d39bbd7bf89da1d6456d5a542605aa16')
s = canonical.original.s
Execution = canonical.original.Execution
sys.path.insert(0, str(HERE.parent))
checker = load('canonical_q4_strict_checker', HERE.parent / 'check_threeway_attention.py',
               'ac2fecc27be77220a442bfdfb2292c37a9fe585148d4fe79da9aae09ff34dd05')
renderer = load('canonical_q4_source_provenance', HERE.parent / 'untimed_verify/render.py',
                '4ff011fc5c1ab7589d95b0c5de44cd09d9ce1def022eeaa9e891d5c443e80f09')


def fields(report, wanted, context):
    s.require(all(type(report.get(k)) is type(v) and report[k] == v for k, v in wanted.items()),
              'Wrong ' + context + ' fields')


def review_flags(report):
    fields(report, dict(schema='q4_untimed_fixed_layout_consumer_evidence_v1',
        state='FIXED_LAYOUT_BUILD_REVIEW_PASS_NOT_EXECUTED', execution='NOT_RUN',
        elf_sha256=ELF_SHA, preserved_timedsource_hash=TIMED_SHA,
        all_nonmain_linked_function_bytes_equal=True, all_old_data_helper_addresses_restored=True,
        freshpairedexperiment_only=True, old_cycle_identity_claim=False, old_elf_continuation=False,
        old_image_validator_called=False, original_unpadded_address_failure_preserved=True,
        restored_nonmain_functions=36, restored_object_tensor_symbols=32,
        runtime_or_under_three_hours_acceptance=False, timedmachineidentity=False,
        timedsource_identical=True, timeout_changed=False, timeout_seconds=TIMEOUT,
        zero_new_globals=True, new_global_storage_objects={},
        new_canonical_image_admission='PARENT_OWNED_PENDING'), 'fixed program review')


def checked_program():
    receipt = PROGRAM / 'consumer-evidence.json'
    s.require(s.digest(receipt) == RECEIPT_SHA, 'Fixed consumer receipt SHA differs')
    report = s.read_json(receipt)
    review_flags(report)
    artifacts = report['artifact_map']
    s.require(set(artifacts) == {str(PROGRAM / n) for n in ARTIFACT_NAMES}, 'Incomplete artifact map')
    pins = {}
    s.merge_pins(pins, artifacts)
    s.verify_pins(pins)
    # Both published maps and the intermediate after-link map are mandatory.
    maps = [PROGRAM / n for n in ('input-pins-before.json', 'input-pins-after-link.json',
                                  'input-pins-after.json')]
    fields(report, dict(source_input_map=str(maps[0]), source_input_map_after=str(maps[2]),
        source_input_map_sha256=s.digest(maps[0]), source_input_map_after_sha256=s.digest(maps[2])),
        'input map references')
    before = s.read_json(maps[0])
    s.require(before and all(s.read_json(p) == before and s.digest(p) == s.digest(maps[0]) for p in maps),
              'Input before/after maps differ')
    s.merge_pins(pins, before)
    review = s.read_json(PROGRAM / 'review-result.json')
    link = s.read_json(PROGRAM / 'link-review.json')
    objects = report['original_16_object_identity_map']
    s.require(len(objects) == 16 and all(Path(p).suffix == '.o' and Path(p).name != 'main.o'
              and before.get(p) == sha for p, sha in objects.items()) and
              objects == review['unchanged_link_objects'] == link['unchanged_link_objects'],
              'Need all sixteen original nonmain objects')
    s.merge_pins(pins, objects)
    fields(review, dict(schema='q4_untimed_fixed_layout_review_v1',
        state='FIXED_LAYOUT_BUILD_REVIEW_PASS_NOT_EXECUTED', execution='NOT_RUN',
        scope='NEW_SAME_ELF_HSB_EXPERIMENT_NOT_OLD_ELF_CONTINUATION', elf_sha256=ELF_SHA,
        fixed_layout_pass=True, post_input_pins_match=True, nonmain_function_bytes_and_addresses_pass=True,
        nonmain_function_count=36, object_tensor_address_size_count=32,
        main_machine_code_differs_from_old=True, main_recompiled=False, binary_patches=False,
        old_image_validation_called=False, old_timed_machine_identity_claimed=False,
        timed_source_identical=True, timeout_increased=False, timeout_seconds=TIMEOUT,
        runtime_acceptance=False, under_three_hours_claim=False, performance_claim=False,
        new_global_arrays=False, compile_action='REUSE_REVIEWED_MAIN_OBJECT_RELINK_ONLY'), 'build review')
    fields(review['experiment_contract'], dict(kind='q4_0', trial_order=[0, 1, 2, 2, 1, 0],
        trials=6, outputs_per_trial=768, expected_commands=16, heads=6, head_dim=128,
        visible_tokens=128, kv_head=0, key_token_stride=144, value_token_stride=272,
        mapping_timed=True, admission_timed=True, gather_timed=True, workspace_bytes=13120,
        rvv_value_decode=True, rvv_baseline_decode=True), 'experiment contract')
    fields(review, dict(input_pins_sha256=s.digest(maps[0]),
                        input_pins_after_sha256=s.digest(maps[2])), 'review input map hashes')
    s.require(all(artifacts.get(str(PROGRAM / n)) == sha for n, sha in review['artifacts'].items())
              and set(review['artifacts']) == set(ARTIFACT_NAMES) - {'review-result.json'},
              'Review artifact map differs')
    fields(link, dict(state='FIXED_LAYOUT_LINK_PASS_NOT_EXECUTED', execution='NOT_RUN',
        comparison_scope='NEW_SAME_ELF_HSB_NOT_OLD_TIMED_MACHINE_IDENTITY',
        elf_sha256=ELF_SHA, main_recompiled=False, main_binary_patched=False,
        post_pins_match=True, timeout_change=False,
        linker_inverse_except_scoped_text_slot_and_assertions=True), 'link review')
    for key, name in (('frozen_review_receipt', 'review-result.json'),
                      ('layout_evidence', 'layout-review.json'),
                      ('timed_machine_difference_evidence', 'timed-review.json')):
        fields(report, {key: str(PROGRAM / name), key + '_sha256': s.digest(PROGRAM / name)}, 'evidence reference')
    old_review = Path(report['original_unpadded_review'])
    s.require(before.get(str(old_review)) == report['original_unpadded_review_sha256'] == s.digest(old_review),
              'Original unpadded review not preserved')
    layout = s.read_json(PROGRAM / 'layout-review.json')
    funcs, data = layout['nonmain_functions'], layout['objects_and_tensor_symbols']
    s.require(len(funcs) == 36 and len(data) == 32, 'Wrong layout evidence extent')
    for row in [*funcs.values(), *data.values()]:
        s.require(row['address_equal'] is True and row['size_equal'] is True and
                  row['new_address'] == row['old_address'], 'Layout address/size mismatch')
        if 'bytes_equal' in row:
            s.require(row['bytes_equal'] is True, 'Nonmain function bytes differ')
        if 'payload_equal' in row:
            s.require(row['payload_equal'] is True and row['new_payload_sha256'] == row['old_payload_sha256'],
                      'Data payload differs')
    s.require(layout['main']['bytes_equal'] is False and
              all(row['bytes_equal'] is True and row['new_sha256'] == row['old_sha256']
                  for row in layout['nonmain_text_ranges']), 'Main/nonmain scope differs')
    timed = s.read_json(PROGRAM / 'timed-review.json')
    fields(timed, dict(state='TIMED_MAIN_DIFFERENCE_RETAINED_EXPLICITLY',
        accepted_scope='NEW_SAME_ELF_HSB_PAIRING_PER_PARENT_DECISION',
        old_timed_machine_identity_claimed=False, old_static_sites=713, new_static_sites=717,
        unknown_edges=[], timed_source_identical=True, main_object_recompiled_or_patched=False,
        cycle_performance_claim=False), 'timed machine review')
    s.require(review['timed_cfg'] == timed, 'Timed evidence differs')
    original = (PROGRAM / 'original_fasthex.c').read_bytes()
    generated = (PROGRAM / 'attention_threeway_untimed.c').read_bytes()
    s.require(before.get(str(renderer.ORIGINAL)) == renderer.ORIGINAL_SHA256 and
              renderer.ORIGINAL.read_bytes() == original, 'Original source provenance drift')
    provenance = renderer.provenance(original, generated)
    s.require(renderer.render(original) == generated and renderer.inverse(generated) == original and
              provenance == s.read_json(PROGRAM / 'render.json') == review['source_provenance'] and
              provenance['timed_region_sha256'] == TIMED_SHA, 'Source provenance differs')
    elf = PROGRAM / 'threeway_attention.elf'
    fields(report, dict(elf=str(elf), generated_main=str(PROGRAM / 'attention_threeway_untimed.c'),
                       generated_main_sha256=provenance['generated_sha256']), 'program paths')
    s.require(pins.get(str(elf)) == ELF_SHA == s.digest(elf), 'Fixed ELF differs')
    s.require(s.digest(GOLD) == data['attention_golden']['new_payload_sha256'],
              'Actual Q4 capture gold differs from linked model gold')
    s.merge_pins(pins, {str(receipt): RECEIPT_SHA,
                        str(GOLD): data['attention_golden']['new_payload_sha256']})
    s.verify_pins(pins)
    return report, pins


def own_pins():
    paths = [HERE / n for n in ('run.py', 'test_run.py', 'README.md')]
    paths += [GOLD, RTL, Path(sys.executable).resolve(), ROOT /
              'hardware/scripts/llama_q4km_extract/check-sim-l2.sh', *s.script_files()]
    paths += [Path('/usr/bin') / n for n in ('bash', 'readelf', 'awk', 'sed', 'grep', 'tail', 'head')]
    for module in tuple(sys.modules.values()):
        name = getattr(module, '__file__', None)
        if name and Path(name).resolve().is_relative_to(ROOT) and Path(name).is_file():
            paths.append(Path(name).resolve())
    return s.hashes(paths)


def prepare_inputs(build):
    report, pins = checked_program()
    soc, canonical_pins, image = canonical.checked_soc(build, SOC_SHA)
    s.merge_pins(pins, canonical_pins)
    s.merge_pins(pins, image)
    s.merge_pins(pins, own_pins())
    s.verify_pins(pins)
    return report, soc, pins, image


def simulation_command(simv, elf, work):
    return [simv, '-no_save', '-l', work / 'run.vcs.log', '+PRELOAD=' + str(elf),
        '+TESTCASE=quant_threeway_attention', '+NO_FSDB', '+NO_INSTR_TRACE', '+QBS_PERF',
        '+VECTOR_TRACE=' + str(work / 'vector_trace.csv'),
        '+ARA_CONTRACT_TRACE_LIMIT=2000000', '+ARA_UVM_TRACE_LIMIT=2000000']


def protocol(work, elf_sha, image):
    path = work / 'uvm_result.json'
    s.check_result(path, elf_sha, image)
    result = s.read_json(path)
    s.require(result['log_sha256'] == s.digest(work / 'run.vcs.log') and
              result['vector_trace_sha256'] == s.digest(work / 'vector_trace.csv'), 'Protocol raw input drift')


def run(args):
    s.require(type(args.timeout) is int and args.timeout == TIMEOUT, 'Simulator bound fixed at 10800 seconds')
    build = args.soc_build.resolve(strict=True)
    output = args.output.absolute()
    s.require(output == output.resolve() and not output.exists() and not any(
        output.is_relative_to(p) or p.is_relative_to(output) for p in (build, PROGRAM, HERE, GOLD.parent)),
        'Use a fresh independent output without aliases')
    s.require(not any(output.is_relative_to(ROOT / p) for p in ('hardware', 'software', 'verification/akv')),
              'Output must not overlap source directories')
    output.mkdir(parents=True)
    work = output / 'work'
    work.mkdir()
    owner = Execution(output)
    owner.env['PATH'] = '/usr/bin:/bin'
    owner.env['READELF'] = '/usr/bin/readelf'
    for key in ('BASH_ENV', 'ENV', 'PYTHONHOME', 'PYTHONSTARTUP', 'PYTHONINSPECT'):
        owner.env.pop(key, None)
    owner.state.update(soc_build=str(build), simulations_launched=0, timeout_seconds=TIMEOUT)
    owner.save()
    result = dict(new_paired_experiment=True, old_elf_continuation=False, old_cycle_identity=False,
                  timed_machine_identity=False, whole_model=False, hardware_only=False,
                  deployment_approved=False, under_three_hours_acceptance=False, execution='NOT_RUN')
    try:
        report, soc, pins, image = prepare_inputs(build)
        elf, simv = Path(report['elf']), Path(soc['simv'])
        owner.state.update(elf=str(elf), simv=str(simv))
        s.atomic_json(output / 'source-pins.json', pins)
        receipt = s.digest(output / 'source-pins.json')
        result.update(elf_sha256=report['elf_sha256'], consumer_receipt_sha256=RECEIPT_SHA,
                      soc_build_sha256=SOC_SHA, source_pins_sha256=receipt, image_pins=image)

        def identity():
            s.require(s.digest(output / 'source-pins.json') == receipt, 'Worker receipt drift')
            s.verify_pins(pins)
            s.require(s.hashes(s.image_files(simv)) == image, 'Canonical image drift')

        def manifest(stage):
            owner.execute([sys.executable, '-B', '-m', 'ara_verify.vcs_source_manifest', '--output',
                simv.parent / 'vcs_source_manifest.json', '--check'], output / (stage + '.log'),
                300, stage.upper().replace('-', '_'))

        identity()
        if args.preflight_only:
            result.update(state='CANONICAL_Q4_HSB_PREFLIGHT_NOT_RUN', simulations_launched=0,
                          post_pins_match=True, independent_protocol_checked=False)
        else:
            manifest('manifest-before')
            owner.execute(['bash', ROOT / 'hardware/scripts/llama_q4km_extract/check-sim-l2.sh',
                simv.parent, elf], output / 'image-contract.log', 180, 'IMAGE_CONTRACT')
            identity()
            owner.state['simulations_launched'] = 1
            result['execution'] = 'SIMULATION_ATTEMPTED'
            owner.execute(simulation_command(simv, elf, work), work / 'console.log', TIMEOUT, 'RUNNING')
            parsed = checker.check_log((work / 'run.vcs.log').read_text(), 1, GOLD.read_bytes(), RTL.read_text())
            result['raw_replay'] = parsed
            owner.execute([sys.executable, '-B', '-m', 'ara_verify.uvm_dut', '--require-events',
                '--require-backend', '--require-axi', '--require-axi-write', '--vector-trace',
                work / 'vector_trace.csv', '--log', work / 'run.vcs.log', '--simv', simv, '--elf', elf,
                '--output', work / 'uvm_result.json'], work / 'checker.log', 600, 'CHECKING')
            protocol(work, report['elf_sha256'], image)
            manifest('manifest-after')
            identity()
            result.update(state='PASS', acceptance='CANONICAL_Q4_HSB_NEW_PAIR_PASS',
                execution='SIMULATED_ONCE', simulations_launched=1, simulator_exit_code=0,
                independent_protocol_checked=True, post_pins_match=True,
                paired_cycles_measured=True, old_timed_machine_identity_claimed=False)
        identity()
        result['evidence_sha256'] = s.hashes(p for p in output.rglob('*') if p.is_file() and
                                            p.name not in ('result.json', 'status.json'))
        s.atomic_json(output / 'result.json', result)
        owner.state['state'] = result['state']
        return result
    except BaseException as exc:
        state = 'TIMEOUT' if isinstance(exc, subprocess.TimeoutExpired) else 'INTERRUPTED' if isinstance(exc, InterruptedError) else 'FAIL'
        owner.state.update(state=state, error=repr(exc))
        result.pop('acceptance', None)
        result['post_pins_match'] = False
        result.update(state=state, error=repr(exc), simulations_launched=owner.state['simulations_launched'])
        result['partial_evidence_sha256'] = s.hashes(p for p in output.rglob('*') if p.is_file() and
                                                    p.name not in ('result.json', 'status.json'))
        s.atomic_json(output / 'result.json', result)
        raise
    finally:
        owner.state.update(child_pid=None, finished=datetime.now(timezone.utc).isoformat())
        owner.save()


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__, allow_abbrev=False)
    parser.add_argument('--soc-build', type=Path, default=SOC_BUILD)
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--timeout', type=int, choices=(TIMEOUT,), default=TIMEOUT)
    parser.add_argument('--preflight-only', action='store_true')
    args = parser.parse_args()

    def interrupted(sig, _frame):
        raise InterruptedError(f'Signal {sig}')

    for sig in (signal.SIGTERM, signal.SIGINT):
        signal.signal(sig, interrupted)
    run(args)
