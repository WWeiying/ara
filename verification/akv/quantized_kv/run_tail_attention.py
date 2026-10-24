#!/usr/bin/env python3
"""Correctness-only VCS closure for quantized Attention tails and panel reuse."""
import argparse
from datetime import datetime, timezone
from pathlib import Path
import signal
import subprocess
import sys

sys.dont_write_bytecode = True
HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[2]
from run_strided_attention import s, Execution, checked_model
from build_tail_attention import checked_gold
from check_tail_attention import check_log
from check_rvv_qbs import HostOracle


def checked_build(build):
    report = s.read_json(build / 'build.json')
    wanted = dict(state='TAIL_ENTRY_BUILT_NOT_EXECUTED', execution='NOT_RUN', post_pins_match=True,
                  prefixes=[5, 33], trials=6, expected_commands=12, native_calls=4,
                  outputs_per_trial=768, head_dim=128, heads=6, kv_head=0, performance=False,
                  rvv_value_decode=True, rvv_baseline_decode=True, workspace_bytes=13120)
    s.require(report.get('kind') in ('q8_0', 'q4_0') and all(type(report.get(k)) is type(v) and
              report[k] == v for k, v in wanted.items()), 'Wrong tail probe build')
    s.require(s.digest(build / 'source-pins.json') == report['source_pins_sha256'], 'Build pins receipt drift')
    pins = s.read_json(build / 'source-pins.json')
    s.merge_pins(pins, report['artifact_sha256'])
    s.require(pins.get(report['elf']) == report['elf_sha256'] == s.digest(Path(report['elf'])), 'ELF drift')
    s.merge_pins(pins, s.hashes([build / 'build.json', build / 'source-pins.json']))
    records, reference_pins = checked_gold(Path(report['gold_directory']), report['kind'])
    s.require({str(k): value for k, value in records.items()} == report['independent_gold'], 'Gold receipt differs')
    s.merge_pins(pins, reference_pins)
    s.verify_pins(pins)
    return report, pins, {k: Path(value['path']).read_bytes() for k, value in records.items()}


def oracle_inputs(pins):
    prior = ROOT / 'verification/out/akv-quantkv-rvv-qbs-20261024-01'
    result = s.read_json(prior / 'result.json')
    library = prior / 'host_score.so'
    s.require(result.get('state') == 'PASS' and result.get('post_pins_match') is True and
              s.digest(prior / 'source-pins.json') == result['source_pins_sha256'] and
              result['evidence_sha256'].get(str(library)) == s.digest(library), 'Independent QBS oracle drift')
    source = s.read_json(prior / 'source-pins.json')
    selected = {path: sha for path, sha in source.items() if Path(path).name in
                ('host_score.c', 'qbs_ref.c', 'qbs_ref.h', 'qbs_abi.h')}
    s.require(any(Path(path).name == 'qbs_ref.c' for path in selected), 'Oracle omits its arithmetic source')
    s.verify_pins(selected)
    s.merge_pins(pins, selected)
    s.merge_pins(pins, s.hashes([prior / 'result.json', prior / 'source-pins.json', library]))
    return HostOracle(library)


def run(args):
    s.require(1 <= args.timeout <= 7200, 'Bound must be 1..7200 seconds')
    build, prior, out = args.build.resolve(strict=True), args.prerequisite.resolve(strict=True), args.output.resolve()
    s.require(not out.is_relative_to(build) and not out.is_relative_to(prior), 'Independent output required')
    out.mkdir(parents=True, exist_ok=False)
    work = out / 'work'
    work.mkdir()
    owner = Execution(out)
    owner.state.update(build=str(build), prerequisite=str(prior))
    owner.save()
    try:
        report, pins, gold = checked_build(build)
        checked_model(prior, pins)
        oracle = oracle_inputs(pins)
        own = [Path(__file__), HERE / 'test_tail_attention_run.py', HERE / 'test_tail_attention_check.py',
               HERE / 'test_tail_attention_build.py', *s.script_files(), Path(sys.executable).resolve()]
        for module in tuple(sys.modules.values()):
            name = getattr(module, '__file__', None)
            if name:
                path = Path(name).resolve()
                if path.is_relative_to(ROOT) and path.is_file():
                    own.append(path)
        s.merge_pins(pins, s.hashes(own))
        s.verify_pins(pins)
        s.atomic_json(out / 'source-pins.json', pins)
        receipt = s.digest(out / 'source-pins.json')
        simv, elf = Path(report['simv']), Path(report['elf'])
        image = report['accepted_image_pins']
        owner.state.update(simv=str(simv), elf=str(elf), kind=report['kind'])

        def identity():
            s.require(s.digest(out / 'source-pins.json') == receipt, 'Worker receipt drift')
            s.verify_pins(pins)
            s.require(s.hashes(s.image_files(simv)) == image, 'Image inventory drift')

        def manifest(stage):
            owner.execute([sys.executable, '-B', '-m', 'ara_verify.vcs_source_manifest', '--output',
                           simv.parent / 'vcs_source_manifest.json', '--check'], out / (stage + '.log'), 300, stage.upper())

        identity()
        manifest('manifest-before')
        owner.execute(['bash', ROOT / 'hardware/scripts/llama_q4km_extract/check-sim-l2.sh', simv.parent, elf],
                      out / 'image-contract.log', 180, 'IMAGE_CONTRACT')
        identity()
        log, trace = work / 'run.vcs.log', work / 'vector_trace.csv'
        owner.execute([simv, '-no_save', '-l', log, '+PRELOAD=' + str(elf), '+TESTCASE=quant_tail_attention',
                       '+NO_FSDB', '+NO_INSTR_TRACE', '+QBS_PERF', '+VECTOR_TRACE=' + str(trace),
                       '+ARA_CONTRACT_TRACE_LIMIT=2000000', '+ARA_UVM_TRACE_LIMIT=2000000'],
                      work / 'console.log', args.timeout, 'RUNNING')
        key = ROOT / 'verification/out/akv-quantkv-host-capture-20261024-01' / (
            'capture-k-' + report['kind'] + '-v-q8_0') / 'decode/block/attn_k_input-0.bin'
        s.require(str(key) in pins, 'Independent weight bytes are not pinned')
        result = check_log(log.read_text(), int(report['kind'] == 'q4_0'), gold,
                           (ROOT / 'hardware/src/vlsu/vlsu.sv').read_text(), key.read_bytes(), oracle)
        owner.execute([sys.executable, '-B', '-m', 'ara_verify.uvm_dut', '--require-events', '--require-backend',
                       '--require-axi', '--require-axi-write', '--vector-trace', trace, '--log', log, '--simv', simv,
                       '--elf', elf, '--output', work / 'uvm_result.json'], work / 'checker.log', 600, 'CHECKING')
        s.check_result(work / 'uvm_result.json', report['elf_sha256'], image)
        uvm = s.read_json(work / 'uvm_result.json')
        s.require(uvm['log_sha256'] == s.digest(log) and uvm['vector_trace_sha256'] == s.digest(trace), 'Protocol input drift')
        manifest('manifest-after')
        identity()
        result.update(state='PASS', simulator_exit_code=0, post_pins_match=True, independent_protocol_checked=True,
                      elf_sha256=report['elf_sha256'], source_pins_sha256=receipt,
                      evidence_sha256=s.hashes([log, trace, work / 'uvm_result.json', out / 'source-pins.json',
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
    parser.add_argument('--timeout', type=int, default=3600)
    args = parser.parse_args()

    def interrupted(sig, _frame):
        raise InterruptedError(f'Signal {sig}')

    for sig in (signal.SIGTERM, signal.SIGINT):
        signal.signal(sig, interrupted)
    run(args)


if __name__ == '__main__':
    main()
