#!/usr/bin/env python3
"""Paired VCS strided-cache inquiry, gated on actual native model integration."""
import argparse
from datetime import datetime, timezone
from pathlib import Path
import signal
import subprocess
import sys

sys.dont_write_bytecode = True
HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[2]
sys.path.insert(0, str(HERE.parent))
from run_common_attention import s, Execution
from check_strided_attention import check_log
from check_model_strided import check_log as check_model_log
from run_after_verified_gate import wait_owner

def checked_build(build):
    report = s.read_json(build / 'build.json')
    kind = report.get('kind')
    row = 72 if kind == 'q4_0' else 136
    required = dict(state='STRIDED_ENTRY_BUILT_NOT_EXECUTED', execution='NOT_RUN',
                    post_pins_match=True, common_entry=False, mapping_timed=True,
                    admission_timed=True, gather_timed=True, workspace_bytes=13120,
                    key_token_stride=2 * row, value_token_stride=272,
                    rvv_value_decode=True, rvv_baseline_decode=True,
                    heads=6, head_dim=128, visible_tokens=128, expected_commands=16,
                    trials=4, outputs_per_trial=768, kv_head=0, exact_scale_bits='3db504f3')
    s.require(kind in ('q4_0', 'q8_0') and all(type(report.get(k)) is type(v) and report.get(k) == v
              for k, v in required.items()),
              'Wrong strided full-cost build')
    s.require(report.get('ordinary_value_decode') == 'same RVV decoder as candidate', 'Unfair V decoder')
    s.require(s.digest(build / 'source-pins.json') == report['source_pins_sha256'], 'Build receipt drift')
    pins = s.read_json(build / 'source-pins.json')
    s.merge_pins(pins, report['artifact_sha256'])
    s.require(pins.get(report['elf']) == report['elf_sha256'] == s.digest(Path(report['elf'])), 'ELF drift')
    s.merge_pins(pins, s.hashes([build / 'build.json', build / 'source-pins.json']))
    s.verify_pins(pins)
    return report, pins


def checked_model(prior, pins):
    result = s.read_json(prior / 'result.json')
    status = s.read_json(prior / 'status.json')
    s.require(result.get('state') == status.get('state') == 'PASS' and status.get('child_pid') is None
              and result.get('current_inputs_match') is True, 'Model gate not checked terminal PASS')
    s.require(result.get('source_pins_sha256') == s.digest(prior / 'source-pins.json') and
              result.get('log_sha256') == s.digest(prior / 'qemu.log'), 'Model receipt identity drift')
    raw = check_model_log((prior / 'qemu.log').read_text())
    s.require(raw.get('native_command_attempts') == 448 and raw.get('key_panels') == 224
              and raw.get('key_bytes') == 128128, 'Wrong native model coverage')
    for key, value in raw.items():
        s.require(key == 'state' or result.get(key) == value, 'Raw model result disagrees: ' + key)
    model_pins = s.read_json(prior / 'source-pins.json')
    kernel = ROOT / 'software/akv/experimental/quantized_kv'
    critical = [kernel / name for name in ('runtime_strided.c', 'runtime_strided.h',
                'selection_strided.h', 'selection.h', 'native.h', 'runtime.h', 'online.h',
                'q8_0_value.h', 'ggml_decode.h', 'ggml_memory.h', 'ggml_entry_strided.h')]
    critical += [HERE / 'check_model_strided.py', HERE / 'check_model_live.py',
                 Path('/home/wangwy/llama/llama.cpp/ggml/src/ggml-cpu/arch/riscv/quant-kv.cpp')]
    for path in critical:
        s.require(model_pins.get(str(path)) == s.digest(path), 'Model/shared implementation differs: ' + str(path))
    # Model completion already checked its full 35k-file QEMU inventory. The
    # VCS inquiry consumes its sealed evidence and matching shared kernel, not
    # a fresh QEMU build or its unrelated source files.
    s.merge_pins(pins, {str(path): model_pins[str(path)] for path in critical})
    s.merge_pins(pins, s.hashes([prior / name for name in
                              ('result.json', 'status.json', 'source-pins.json', 'qemu.log')]))
    return raw


def run(args):
    s.require(1 <= args.timeout <= 10800 and args.gate_owner_pid >= 0, 'Bad timeout/owner')
    build, prior, out = args.build.resolve(strict=True), args.prerequisite.resolve(strict=True), args.output.resolve()
    s.require(not out.is_relative_to(build) and not out.is_relative_to(prior), 'Independent output required')
    out.mkdir(parents=True, exist_ok=False)
    work = out / 'work'
    work.mkdir()
    owner = Execution(out)
    owner.state.update(build=str(build), prerequisite=str(prior))
    owner.save()
    try:
        report, pins = checked_build(build)
        own = [Path(__file__), HERE / 'check_strided_attention.py', HERE / 'test_strided_attention_check.py',
               HERE / 'test_strided_attention_run.py', HERE / 'run_common_attention.py',
               HERE / 'check_model_strided.py', HERE / 'check_model_live.py',
               ROOT / 'verification/akv/run_after_verified_gate.py',
               ROOT / 'verification/akv/paired_heads/contexts/run_context.py',
               ROOT / 'hardware/scripts/llama_q4km_extract/check-sim-l2.sh',
               *s.script_files(), Path(sys.executable).resolve()]
        for module in tuple(sys.modules.values()):
            name = getattr(module, '__file__', None)
            if name:
                path = Path(name).resolve()
                if path.is_relative_to(ROOT) and path.is_file():
                    own.append(path)
        s.merge_pins(pins, s.hashes(own))
        s.atomic_json(out / 'pre-wait-pins.json', pins)
        if args.gate_owner_pid:
            owner.state.update(state='WAITING_MODEL', gate_owner_pid=args.gate_owner_pid)
            owner.save()
            wait_owner(prior, args.gate_owner_pid, HERE / 'run_model_strided.py', 7200)
        s.verify_pins(pins)
        model = checked_model(prior, pins)
        s.atomic_json(out / 'model-prerequisite.json', dict(state='RAW_MODEL_RECHECKED',
            prerequisite=str(prior), native_commands=model['native_command_attempts'],
            full_qemu_source_replay=False, shared_kernel_checked=True,
            result_sha256=s.digest(prior / 'result.json')))
        s.merge_pins(pins, s.hashes([out / 'pre-wait-pins.json', out / 'model-prerequisite.json']))
        s.atomic_json(out / 'source-pins.json', pins)
        receipt = s.digest(out / 'source-pins.json')
        simv, elf = Path(report['simv']), Path(report['elf'])
        image = report['accepted_image_pins']
        owner.state.update(elf=str(elf), simv=str(simv), kind=report['kind'])

        def identity():
            s.require(s.digest(out / 'source-pins.json') == receipt, 'Worker receipt drift')
            s.verify_pins(pins)
            s.require(s.hashes(s.image_files(simv)) == image, 'Image inventory drift')

        def manifest(stage):
            owner.execute([sys.executable, '-B', '-m', 'ara_verify.vcs_source_manifest', '--output',
                           simv.parent / 'vcs_source_manifest.json', '--check'],
                          out / (stage + '.log'), 300, stage.upper())

        identity()
        manifest('manifest-before')
        owner.execute(['bash', ROOT / 'hardware/scripts/llama_q4km_extract/check-sim-l2.sh', simv.parent, elf],
                      out / 'image-contract.log', 180, 'IMAGE_CONTRACT')
        identity()
        log, trace = work / 'run.vcs.log', work / 'vector_trace.csv'
        owner.execute([simv, '-no_save', '-l', log, '+PRELOAD=' + str(elf),
                       '+TESTCASE=quant_strided_attention', '+NO_FSDB', '+NO_INSTR_TRACE', '+QBS_PERF',
                       '+VECTOR_TRACE=' + str(trace), '+ARA_CONTRACT_TRACE_LIMIT=2000000',
                       '+ARA_UVM_TRACE_LIMIT=2000000'], work / 'console.log', args.timeout, 'RUNNING')
        data = ROOT / 'verification/out/akv-quantkv-host-capture-20261024-01' / (
            'capture-k-' + report['kind'] + '-v-q8_0') / 'decode/block'
        result = check_log(log.read_text(), int(report['kind'] == 'q4_0'),
                           (data / 'kqv_out-0.bin').read_bytes(), (ROOT / 'hardware/src/vlsu/vlsu.sv').read_text())
        owner.execute([sys.executable, '-B', '-m', 'ara_verify.uvm_dut', '--require-events', '--require-backend',
                       '--require-axi', '--require-axi-write', '--vector-trace', trace, '--log', log,
                       '--simv', simv, '--elf', elf, '--output', work / 'uvm_result.json'],
                      work / 'checker.log', 600, 'CHECKING')
        s.check_result(work / 'uvm_result.json', report['elf_sha256'], image)
        uvm = s.read_json(work / 'uvm_result.json')
        s.require(uvm['log_sha256'] == s.digest(log) and uvm['vector_trace_sha256'] == s.digest(trace),
                  'Protocol inputs differ')
        manifest('manifest-after')
        identity()
        result.update(state='PASS', simulator_exit_code=0, post_pins_match=True,
                      independent_protocol_checked=True, elf_sha256=report['elf_sha256'],
                      source_pins_sha256=receipt, same_rvv_value_decoder=True,
                      evidence_sha256=s.hashes([log, trace, work / 'uvm_result.json',
                          out / 'source-pins.json', out / 'model-prerequisite.json',
                          out / 'manifest-before.log', out / 'manifest-after.log', out / 'image-contract.log']))
        s.atomic_json(out / 'result.json', result)
        owner.state['state'] = 'PASS'
    except BaseException as exc:
        state = 'TIMEOUT' if isinstance(exc, subprocess.TimeoutExpired) else \
                'INTERRUPTED' if isinstance(exc, InterruptedError) else 'FAIL'
        owner.state.update(state=state, error=repr(exc))
        s.atomic_json(out / 'result.json', dict(state=state, error=repr(exc)))
        raise
    finally:
        owner.state.update(child_pid=None, finished=datetime.now(timezone.utc).isoformat())
        owner.save()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    for name in ('build', 'prerequisite', 'output'):
        parser.add_argument('--' + name, type=Path, required=True)
    parser.add_argument('--timeout', type=int, default=10800)
    parser.add_argument('--gate-owner-pid', type=int, default=0)
    args = parser.parse_args()

    def interrupted(sig, _frame):
        raise InterruptedError(f'Signal {sig}')

    for sig in (signal.SIGTERM, signal.SIGINT):
        signal.signal(sig, interrupted)
    run(args)


if __name__ == '__main__':
    main()
