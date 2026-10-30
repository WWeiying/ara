#!/usr/bin/env python3
"""Bounded opposite-owner fault test on a baseline or shared-reader SoC."""
import argparse
from datetime import datetime, timezone
from pathlib import Path
import signal
import subprocess
import sys

sys.dont_write_bytecode = True
HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
from run_handoff import baseline, checked_soc, s, Execution, ROOT
import fault_checks as checks


def run(args):
    s.require(bool(args.baseline) != bool(args.soc_build), 'Select baseline or shared image')
    fixture = args.fixture.resolve(strict=True)
    build = s.read_json(fixture / 'build.json')
    s.require(build.get('state') == 'READER_FAULT_BUILT_NOT_EXECUTED' and
              build.get('post_pins_match') is True and build.get('trap_owner') == 'akv',
              'Wrong fault fixture')
    s.require(s.digest(fixture / 'source-pins.json') == build['source_pins_sha256'], 'Fixture receipt drift')
    pins = s.read_json(fixture / 'source-pins.json')
    s.merge_pins(pins, build['artifact_pins'])
    s.merge_pins(pins, s.hashes([fixture / 'build.json', fixture / 'source-pins.json']))
    if args.baseline:
        original, old_pins = baseline.checked_build(Path(build['predecessor']))
        s.merge_pins(pins, old_pins)
        simv = Path(original['simv'])
        image = original['accepted_image_pins']
        source = ROOT / 'hardware/src/vlsu/vlsu.sv'
    else:
        soc, snapshot, soc_pins, image = checked_soc(args.soc_build.resolve(strict=True))
        s.merge_pins(pins, soc_pins)
        simv = Path(soc['simv'])
        source = Path(snapshot['source_mapping'][str(ROOT / 'hardware/src/vlsu/vlsu.sv')])
    elf = Path(build['elf'])
    s.require(s.digest(elf) == build['elf_sha256'], 'ELF changed')
    exporter = ROOT / 'hardware/scripts/fsdb_trace/extract_cycles.py'
    own = [Path(__file__), HERE / 'fault_checks.py', HERE / 'fault_main.c', HERE / 'fault_probe.S',
           HERE / 'build_fault.py', HERE / 'test_fault_checks.py', exporter,
           *baseline.exporter_files(args.fsdbreport), *s.script_files(), Path(sys.executable).resolve()]
    for module in tuple(sys.modules.values()):
        filename = getattr(module, '__file__', None)
        if filename:
            path = Path(filename).resolve()
            if path.is_file() and path.is_relative_to(ROOT):
                own.append(path)
    s.merge_pins(pins, s.hashes(own))
    s.verify_pins(pins)
    out = args.output.resolve()
    s.require(not out.is_relative_to(fixture) and not out.is_relative_to(simv.parent),
              'Independent output required')
    out.mkdir(parents=True, exist_ok=False)
    work = out / 'work'
    work.mkdir()
    capture = checks.profile(not args.baseline)
    s.atomic_json(out / 'profile.json', capture)
    (out / 'probe.tcl').write_text(checks.script(not args.baseline))
    s.merge_pins(pins, s.hashes([out / 'profile.json', out / 'probe.tcl']))
    s.atomic_json(out / 'source-pins.json', pins)
    owner = Execution(out)
    owner.state.update(shared_image=not args.baseline, fixture=str(fixture),
                       elf=str(elf), simv=str(simv), source_pins_sha256=s.digest(out / 'source-pins.json'))
    owner.save()

    def identity():
        s.verify_pins(pins)
        s.require(s.hashes(s.image_files(simv)) == image, 'Image changed')

    try:
        identity()
        owner.execute([sys.executable, '-B', '-m', 'ara_verify.vcs_source_manifest', '--output',
            simv.parent / 'vcs_source_manifest.json', '--check'], out / 'manifest-before.log',
            300, 'MANIFEST_BEFORE')
        owner.execute(['bash', ROOT / 'hardware/scripts/llama_q4km_extract/check-sim-l2.sh',
                       simv.parent, elf], out / 'image-contract.log', 180, 'IMAGE_CONTRACT')
        log, trace = work / 'run.vcs.log', work / 'vector_trace.csv'
        owner.execute([simv, '-no_save', '-ucli', '-do', out / 'probe.tcl', '-l', log,
            '+PRELOAD=' + str(elf), '+TESTCASE=reader_reverse_fault', '+NO_FSDB', '+NO_INSTR_TRACE',
            '+QBS_PERF', '+AKV_PERF', '+VECTOR_TRACE=' + str(trace),
            '+ARA_CONTRACT_TRACE_LIMIT=2000000', '+ARA_UVM_TRACE_LIMIT=2000000'],
            work / 'console.log', 600, 'RUNNING')
        parsed = checks.check_log(log.read_text(), source.read_text())
        owner.execute([sys.executable, '-B', exporter, '--fsdb', work / 'reader.fsdb',
            '--profile', out / 'profile.json', '--begin', '0ns', '--end', '500000ns',
            '--output', out / 'cycles', '--fsdbreport', args.fsdbreport], out / 'extract.log', 180, 'EXTRACTING')
        metadata = s.read_json(out / 'cycles/metadata.json')
        s.require(not metadata.get('missing_signals') and
                  set(metadata['present_signals']) == {r['alias'] for r in capture['signals']}, 'Missing wave signal')
        waves = checks.check_cycles(out / 'cycles/cycles.csv', not args.baseline)
        owner.execute([sys.executable, '-B', '-m', 'ara_verify.uvm_dut', '--require-events', '--require-backend',
            '--require-axi', '--require-axi-write', '--vector-trace', trace, '--log', log, '--simv', simv,
            '--elf', elf, '--output', work / 'uvm_result.json'], work / 'checker.log', 600, 'CHECKING')
        s.check_result(work / 'uvm_result.json', build['elf_sha256'], image)
        protocol = s.read_json(work / 'uvm_result.json')
        s.require(protocol['log_sha256'] == s.digest(log) and
                  protocol['vector_trace_sha256'] == s.digest(trace), 'Protocol raw identity mismatch')
        owner.execute([sys.executable, '-B', '-m', 'ara_verify.vcs_source_manifest', '--output',
            simv.parent / 'vcs_source_manifest.json', '--check'], out / 'manifest-after.log', 300, 'MANIFEST_AFTER')
        identity()
        parsed.update(state='PASS', wave_evidence=waves, shared_image=not args.baseline,
            post_pins_match=True, independent_protocol_checked=True, elf_sha256=build['elf_sha256'],
            source_pins_sha256=s.digest(out / 'source-pins.json'), performance=False,
            evidence_sha256=s.hashes([log, trace, work / 'reader.fsdb', work / 'uvm_result.json',
                out / 'source-pins.json', out / 'profile.json', out / 'probe.tcl',
                out / 'cycles/cycles.csv', out / 'cycles/metadata.json', out / 'cycles/fsdbreport.raw.csv']))
        s.atomic_json(out / 'result.json', parsed)
        owner.state['state'] = 'PASS'
    except BaseException as exc:
        state = 'TIMEOUT' if isinstance(exc, subprocess.TimeoutExpired) else 'FAIL'
        owner.state.update(state=state, error=repr(exc))
        s.atomic_json(out / 'result.json', dict(state=state, error=repr(exc)))
        raise
    finally:
        owner.state.update(child_pid=None, finished=datetime.now(timezone.utc).isoformat())
        owner.save()


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--fixture', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--baseline', action='store_true')
    parser.add_argument('--soc-build', type=Path)
    parser.add_argument('--fsdbreport', type=Path, default=Path(
        '/home/wangwy/software/synopsys/install/verdi/V-2023.12-SP1/bin/fsdbreport'))
    args = parser.parse_args()
    def interrupted(sig, _frame):
        raise InterruptedError(f'Signal {sig}')
    signal.signal(signal.SIGTERM, interrupted)
    signal.signal(signal.SIGINT, interrupted)
    run(args)
