#!/usr/bin/env python3
"""Run H/S/B only after raw strided and tail evidence has been rechecked."""
import argparse
from datetime import datetime, timezone
from pathlib import Path
import signal
import subprocess
import sys

sys.dont_write_bytecode = True
HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[2]
from run_strided_attention import s, Execution, checked_build as checked_strided_build
from run_tail_attention import checked_build as checked_tail_build, oracle_inputs
from check_strided_attention import check_log as check_strided
from check_tail_attention import check_log as check_tail
from check_threeway_attention import check_log
from run_after_verified_gate import wait_owner


def checked_build(build):
    report = s.read_json(build / 'build.json')
    kind = report.get('kind')
    wanted = dict(state='THREEWAY_ENTRY_BUILT_NOT_EXECUTED', execution='NOT_RUN',
                  post_pins_match=True, threeway_entry=True, trial_order=[0, 1, 2, 2, 1, 0],
                  trials=6, expected_commands=16, outputs_per_trial=768, heads=6,
                  head_dim=128, visible_tokens=128, kv_head=0, exact_scale_bits='3db504f3',
                  rvv_value_decode=True, rvv_baseline_decode=True, mapping_timed=True,
                  admission_timed=True, gather_timed=True, workspace_bytes=13120,
                  key_token_stride=144 if kind == 'q4_0' else 272, value_token_stride=272)
    s.require(kind in ('q4_0', 'q8_0') and all(type(report.get(k)) is type(v) and report[k] == v
              for k, v in wanted.items()), 'Wrong same-ELF three-way build')
    s.require(s.digest(build / 'source-pins.json') == report['source_pins_sha256'], 'Build receipt drift')
    pins = s.read_json(build / 'source-pins.json')
    s.merge_pins(pins, report['artifact_sha256'])
    s.require(pins.get(report['elf']) == report['elf_sha256'] == s.digest(Path(report['elf'])), 'ELF drift')
    s.merge_pins(pins, s.hashes([build / 'build.json', build / 'source-pins.json']))
    s.verify_pins(pins)
    return report, pins


def terminal_inputs(run, builder, owner_script):
    status, result = s.read_json(run / 'status.json'), s.read_json(run / 'result.json')
    s.require(status.get('state') == result.get('state') == 'PASS' and status.get('child_pid') is None and
              result.get('post_pins_match') is True and result.get('independent_protocol_checked') is True and
              type(result.get('simulator_exit_code')) is int and result['simulator_exit_code'] == 0,
              'Require checked terminal prerequisite PASS')
    loaded = builder(Path(status['build']))
    report, required = loaded[:2]
    s.require(status.get('elf') == report['elf'] and status.get('simv') == report['simv'] and
              result.get('elf_sha256') == report['elf_sha256'] and
              s.digest(run / 'source-pins.json') == result['source_pins_sha256'], 'Prerequisite identity mismatch')
    pins = s.read_json(run / 'source-pins.json')
    s.require(all(pins.get(path) == sha for path, sha in required.items()) and
              pins.get(str(owner_script)) == s.digest(owner_script), 'Prerequisite omitted implementation inputs')
    evidence = result['evidence_sha256']
    consumed = [run / 'source-pins.json', *(run / 'work' / name for name in
                 ('run.vcs.log', 'vector_trace.csv', 'uvm_result.json'))]
    s.require(all(evidence.get(str(path)) == s.digest(path) for path in consumed),
              'Prerequisite omitted or changed consumed evidence')
    s.merge_pins(pins, evidence)
    s.merge_pins(pins, s.hashes([run / 'status.json', run / 'result.json']))
    s.verify_pins(pins)
    log, trace, protocol = (run / 'work' / name for name in
                            ('run.vcs.log', 'vector_trace.csv', 'uvm_result.json'))
    s.check_result(protocol, report['elf_sha256'], report['accepted_image_pins'])
    uvm = s.read_json(protocol)
    s.require(uvm['log_sha256'] == s.digest(log) and uvm['vector_trace_sha256'] == s.digest(trace),
              'Prerequisite independent protocol input drift')
    return report, pins, result, log.read_text(), loaded[2:]


def prerequisites(strided, tail, report, pins):
    rtl = (ROOT / 'hardware/src/vlsu/vlsu.sv').read_text()
    kind = int(report['kind'] == 'q4_0')
    capture = ROOT / 'verification/out/akv-quantkv-host-capture-20261024-01' / (
        'capture-k-' + report['kind'] + '-v-q8_0') / 'decode/block'
    receipts = []
    for run, builder, script, is_tail in (
            (strided, checked_strided_build, HERE / 'run_strided_attention.py', False),
            (tail, checked_tail_build, HERE / 'run_tail_attention.py', True)):
        old, inherited, saved, text, extra = terminal_inputs(run, builder, script)
        s.require(old['kind'] == report['kind'] and old['accepted_image_pins'] == report['accepted_image_pins'],
                  'Prerequisite profile/image differs')
        if is_tail:
            oracle = oracle_inputs(inherited)
            raw = check_tail(text, kind, extra[0], rtl,
                             (capture / 'attn_k_input-0.bin').read_bytes(), oracle)
        else:
            s.require(Path(report['predecessor_strided_build']) == Path(s.read_json(run / 'status.json')['build']),
                      'Three-way build is not derived from this strided comparison')
            raw = check_strided(text, kind, (capture / 'kqv_out-0.bin').read_bytes(), rtl)
        s.require(all(saved.get(key) == value for key, value in raw.items()
                      if key not in ('state', 'independent_protocol_checked')), 'Saved prerequisite disagrees with raw evidence')
        s.merge_pins(pins, inherited)
        receipts.append(dict(run=str(run), state='RAW_RECHECKED', tail=is_tail,
                             result_sha256=s.digest(run / 'result.json')))
    s.verify_pins(pins)
    return receipts


def run(args):
    s.require(1 <= args.timeout <= 10800 and args.strided_owner_pid >= 0 and args.tail_owner_pid >= 0,
              'Invalid bounds/owner PID')
    build, strided, tail = (p.resolve(strict=True) for p in (args.build, args.prerequisite, args.tail))
    out = args.output.resolve()
    s.require(not any(out.is_relative_to(p) or p.is_relative_to(out) for p in (build, strided, tail)),
              'Independent output directory required')
    out.mkdir(parents=True, exist_ok=False)
    work = out / 'work'
    work.mkdir()
    owner = Execution(out)
    owner.state.update(build=str(build), prerequisite=str(strided), tail=str(tail))
    owner.save()
    try:
        report, pins = checked_build(build)
        own = [Path(__file__), HERE / 'test_threeway_attention_run.py', *s.script_files(),
               Path(sys.executable).resolve()]
        for module in tuple(sys.modules.values()):
            name = getattr(module, '__file__', None)
            if name:
                path = Path(name).resolve()
                if path.is_relative_to(ROOT) and path.is_file():
                    own.append(path)
        s.merge_pins(pins, s.hashes(own))
        s.atomic_json(out / 'pre-wait-pins.json', pins)
        for gate, pid, script in ((strided, args.strided_owner_pid, HERE / 'run_strided_attention.py'),
                                  (tail, args.tail_owner_pid, HERE / 'run_tail_attention.py')):
            if pid:
                owner.state.update(state='WAITING_GATE', gate=str(gate), gate_owner_pid=pid)
                owner.save()
                wait_owner(gate, pid, script, 10800)
        s.verify_pins(pins)
        receipts = prerequisites(strided, tail, report, pins)
        s.atomic_json(out / 'prerequisite-audit.json', receipts)
        s.merge_pins(pins, s.hashes([out / 'pre-wait-pins.json', out / 'prerequisite-audit.json']))
        s.atomic_json(out / 'source-pins.json', pins)
        receipt = s.digest(out / 'source-pins.json')
        simv, elf = Path(report['simv']), Path(report['elf'])
        image = report['accepted_image_pins']
        owner.state.update(simv=str(simv), elf=str(elf), kind=report['kind'])

        def identity():
            s.require(s.digest(out / 'source-pins.json') == receipt, 'Worker manifest drift')
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
        owner.execute([simv, '-no_save', '-l', log, '+PRELOAD=' + str(elf), '+TESTCASE=quant_threeway_attention',
                       '+NO_FSDB', '+NO_INSTR_TRACE', '+QBS_PERF', '+VECTOR_TRACE=' + str(trace),
                       '+ARA_CONTRACT_TRACE_LIMIT=2000000', '+ARA_UVM_TRACE_LIMIT=2000000'],
                      work / 'console.log', args.timeout, 'RUNNING')
        capture = ROOT / 'verification/out/akv-quantkv-host-capture-20261024-01' / (
            'capture-k-' + report['kind'] + '-v-q8_0') / 'decode/block'
        parsed = check_log(log.read_text(), int(report['kind'] == 'q4_0'),
                           (capture / 'kqv_out-0.bin').read_bytes(),
                           (ROOT / 'hardware/src/vlsu/vlsu.sv').read_text())
        owner.execute([sys.executable, '-B', '-m', 'ara_verify.uvm_dut', '--require-events', '--require-backend',
                       '--require-axi', '--require-axi-write', '--vector-trace', trace, '--log', log,
                       '--simv', simv, '--elf', elf, '--output', work / 'uvm_result.json'], work / 'checker.log', 600, 'CHECKING')
        s.check_result(work / 'uvm_result.json', report['elf_sha256'], image)
        uvm = s.read_json(work / 'uvm_result.json')
        s.require(uvm['log_sha256'] == s.digest(log) and uvm['vector_trace_sha256'] == s.digest(trace), 'Protocol input drift')
        manifest('manifest-after')
        identity()
        parsed.update(state='PASS', simulator_exit_code=0, post_pins_match=True,
                      independent_protocol_checked=True, elf_sha256=report['elf_sha256'], source_pins_sha256=receipt,
                      evidence_sha256=s.hashes([log, trace, work / 'uvm_result.json', out / 'source-pins.json',
                          out / 'prerequisite-audit.json', out / 'manifest-before.log', out / 'manifest-after.log',
                          out / 'image-contract.log']))
        s.atomic_json(out / 'result.json', parsed)
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


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    for name in ('build', 'prerequisite', 'tail', 'output'):
        parser.add_argument('--' + name, type=Path, required=True)
    parser.add_argument('--timeout', type=int, default=10800)
    parser.add_argument('--strided-owner-pid', type=int, default=0)
    parser.add_argument('--tail-owner-pid', type=int, default=0)
    args = parser.parse_args()

    def interrupted(sig, _frame):
        raise InterruptedError(f'Signal {sig}')

    for sig in (signal.SIGTERM, signal.SIGINT):
        signal.signal(sig, interrupted)
    run(args)
